"""Survival baselines: Kaplan-Meier, Cox, Random Survival Forest, DeepSurv.

These are the comparators the Phase 3 gate names, and they are real ones. The Phase 0
rule applies unchanged (D-012): the claim under test is not "existing survival models
are bad", it is that a discrete-time hazard is the right *shape* of model for
retention decisioning. A strawman comparator would settle nothing.

Every baseline is optional. `lifelines`, `scikit-survival` and `torch` are Phase 3
extras, so each class reports `available()` and the benchmark skips what is missing
rather than failing. `KaplanMeierBaseline` needs nothing and is always present --
which matters, because it is the floor every other model has to clear.

A note on what each one can and cannot see
------------------------------------------
Cox, RSF and DeepSurv all take **one covariate vector per subject**. Where the real
covariates move over time (SubSim: engagement, support pain, payment failures) they
get the value at the start of the window and nothing after. That is not a handicap we
imposed; it is what those model families are. Reported explicitly wherever it applies,
because the resulting gap is a claim about representation, not about tuning.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from keel.models.survival.discrete import SurvivalData
from keel.models.survival.metrics import _step_lookup, kaplan_meier


class SurvivalBaseline(ABC):
    """Common interface: fit on a `SurvivalData`, predict S(t) on a grid of times."""

    name: str = "baseline"
    #: True when the model uses only the marginal distribution, so a rank metric is
    #: undefined for it (every subject gets the same curve).
    is_marginal: bool = False

    @staticmethod
    def available() -> bool:
        return True

    @abstractmethod
    def fit(self, data: SurvivalData) -> SurvivalBaseline: ...

    @abstractmethod
    def survival_at(self, X: pd.DataFrame, times: np.ndarray) -> np.ndarray:
        """S(t | x) at each of `times`. Shape `(len(X), len(times))`."""

    def risk_score(self, X: pd.DataFrame, horizon: float) -> np.ndarray:
        """Higher means earlier failure. Default: probability of failing by `horizon`."""
        return 1.0 - self.survival_at(X, np.array([horizon]))[:, 0]


# --- the floor ---------------------------------------------------------------


class KaplanMeierBaseline(SurvivalBaseline):
    """The marginal survival curve, given to everybody. Uses no covariates at all.

    Included because it is the honest floor, and it is a surprisingly hard one on a
    proper scoring rule: a model that ranks well but is badly calibrated can lose to
    it on the integrated Brier score while winning on concordance by a mile. That
    contrast is the point of reporting both.
    """

    name = "kaplan_meier"
    is_marginal = True

    def fit(self, data: SurvivalData) -> KaplanMeierBaseline:
        self.times_, self.surv_ = kaplan_meier(data.duration, data.event > 0)
        return self

    def survival_at(self, X: pd.DataFrame, times: np.ndarray) -> np.ndarray:
        curve = _step_lookup(self.times_, self.surv_, np.asarray(times, dtype=float))
        return np.tile(curve, (len(X), 1))


# --- Cox -------------------------------------------------------------------


class CoxBaseline(SurvivalBaseline):
    """Cox proportional hazards (lifelines), with the Breslow baseline for S(t)."""

    name = "cox_ph"

    def __init__(self, penalizer: float = 0.1):
        self.penalizer = penalizer

    @staticmethod
    def available() -> bool:
        try:
            import lifelines  # noqa: F401
        except ImportError:
            return False
        return True

    def fit(self, data: SurvivalData) -> CoxBaseline:
        from lifelines import CoxPHFitter
        from lifelines.exceptions import ConvergenceError

        # Constant columns are singular by construction and appear naturally in small
        # slices -- at n=250 a landmark subset can contain no departed champion at
        # all. Dropping them is what a practitioner would do and keeps the comparison
        # about the method rather than about a crash.
        self.kept_ = [c for c in data.X.columns if data.X[c].std() > 1e-12]
        frame = data.X[self.kept_].copy()
        frame["__duration"] = data.duration.astype(float)
        frame["__event"] = (data.event > 0).astype(int)

        # A ridge penalty, not zero: Telco's one-hot contract and service columns are
        # close to collinear and the unpenalised fit does not converge. Escalated
        # rather than fixed, because a penalty large enough for the hardest slice
        # would over-shrink every other one -- and the escalation is recorded, since
        # "Cox needed 100x the regularisation at n=250" is itself a small-sample
        # result rather than a detail.
        for penalizer in (self.penalizer, self.penalizer * 10, self.penalizer * 100):
            try:
                self.model_ = CoxPHFitter(penalizer=penalizer)
                self.model_.fit(frame, duration_col="__duration", event_col="__event")
                self.penalizer_used_ = penalizer
                return self
            except (ConvergenceError, np.linalg.LinAlgError):
                continue
        raise ConvergenceError(
            f"Cox did not converge on {len(frame)} rows with "
            f"{(data.event > 0).sum()} events, up to penalizer "
            f"{self.penalizer * 100}."
        )

    def survival_at(self, X: pd.DataFrame, times: np.ndarray) -> np.ndarray:
        sf = self.model_.predict_survival_function(
            X[self.kept_], times=np.asarray(times, dtype=float)
        )
        return sf.to_numpy().T

    def risk_score(self, X: pd.DataFrame, horizon: float) -> np.ndarray:
        # The partial-likelihood score is the natural ranking for Cox and does not
        # depend on the Breslow baseline, so use it rather than a survival difference.
        return self.model_.predict_partial_hazard(X[self.kept_]).to_numpy()


# --- Random Survival Forest ---------------------------------------------------


class RSFBaseline(SurvivalBaseline):
    """Random Survival Forest (scikit-survival), log-rank splitting."""

    name = "rsf"

    def __init__(self, n_estimators: int = 300, min_samples_leaf: int = 15, seed: int = 0):
        self.n_estimators = n_estimators
        self.min_samples_leaf = min_samples_leaf
        self.seed = seed

    @staticmethod
    def available() -> bool:
        try:
            import sksurv.ensemble  # noqa: F401
        except ImportError:
            return False
        return True

    @staticmethod
    def _structured(duration: np.ndarray, event: np.ndarray) -> np.ndarray:
        out = np.empty(len(duration), dtype=[("event", "?"), ("time", "<f8")])
        out["event"] = event > 0
        out["time"] = duration.astype(float)
        return out

    def fit(self, data: SurvivalData) -> RSFBaseline:
        from sksurv.ensemble import RandomSurvivalForest

        self.model_ = RandomSurvivalForest(
            n_estimators=self.n_estimators,
            min_samples_leaf=self.min_samples_leaf,
            n_jobs=-1,
            random_state=self.seed,
        )
        self.model_.fit(data.X.to_numpy(dtype=float),
                        self._structured(data.duration, data.event))
        return self

    def survival_at(self, X: pd.DataFrame, times: np.ndarray) -> np.ndarray:
        fns = self.model_.predict_survival_function(X.to_numpy(dtype=float))
        # RSF's step functions are only defined on the training event times; asking
        # beyond the last one returns the final value, which is the correct
        # right-continuous extension rather than an extrapolation.
        grid = np.clip(np.asarray(times, dtype=float),
                       None, float(self.model_.unique_times_[-1]))
        return np.vstack([fn(grid) for fn in fns])

    def risk_score(self, X: pd.DataFrame, horizon: float) -> np.ndarray:
        return self.model_.predict(X.to_numpy(dtype=float))


# --- DeepSurv ------------------------------------------------------------------


class DeepSurvBaseline(SurvivalBaseline):
    """DeepSurv (Katzman et al., 2018): an MLP trained on the Cox partial likelihood.

    Written directly against torch rather than pulled from `pycox`, for the same
    reason `keel/benchmarks/models.py` hand-rolls its uplift learners: the method is
    forty lines, the dependency stays narrow, and a referee can read it.

    The architecture and training protocol follow the paper -- two hidden layers,
    batch norm, dropout, SELU-family activation, Adam with weight decay, early
    stopping on a held-out partial likelihood. Ties in the risk set use Breslow's
    approximation, which is also what the baseline hazard below assumes, so the two
    halves are consistent.

    Reported honestly: the paper tunes architecture per dataset by random search. We
    do not, because a per-dataset search on our side and fixed settings for the
    discrete model would bias the comparison in *our* favour. One fixed configuration
    is used everywhere, for every model, including ours.
    """

    name = "deepsurv"

    def __init__(
        self,
        hidden: tuple[int, ...] = (32, 32),
        dropout: float = 0.1,
        lr: float = 0.01,
        weight_decay: float = 1e-4,
        epochs: int = 300,
        patience: int = 25,
        seed: int = 0,
    ):
        self.hidden = hidden
        self.dropout = dropout
        self.lr = lr
        self.weight_decay = weight_decay
        self.epochs = epochs
        self.patience = patience
        self.seed = seed

    @staticmethod
    def available() -> bool:
        try:
            import torch  # noqa: F401
        except ImportError:
            return False
        return True

    # -- the partial likelihood ------------------------------------------------

    @staticmethod
    def _cox_loss(risk, time, event):
        """Negative Breslow partial log-likelihood.

        Sorting by *descending* time makes the risk set {j : T_j >= T_i} a prefix, so
        the denominator is a cumulative log-sum-exp. Tied times are mapped to the last
        member of their tie group, which is what gives every tied subject the same
        (full) risk set -- Breslow's approximation. Getting this wrong shrinks the
        risk set for all but one of each tie and quietly inflates the likelihood.
        """
        import torch

        order = torch.argsort(time, descending=True)
        risk, time, event = risk[order], time[order], event[order]
        log_denom = torch.logcumsumexp(risk, dim=0)

        # Last index of each tied time in this descending order.
        n = time.shape[0]
        idx = torch.arange(n, device=time.device)
        same_as_next = torch.zeros(n, dtype=torch.bool, device=time.device)
        same_as_next[:-1] = time[:-1] == time[1:]
        last = idx.clone()
        for k in range(n - 2, -1, -1):
            if same_as_next[k]:
                last[k] = last[k + 1]

        contrib = risk - log_denom[last]
        observed = event > 0
        if observed.sum() == 0:
            return risk.sum() * 0.0
        return -contrib[observed].mean()

    def _build(self, n_features: int):
        import torch
        from torch import nn

        torch.manual_seed(self.seed)
        layers: list = []
        prev = n_features
        for h in self.hidden:
            layers += [nn.Linear(prev, h), nn.BatchNorm1d(h), nn.SELU(), nn.Dropout(self.dropout)]
            prev = h
        layers.append(nn.Linear(prev, 1, bias=False))
        return nn.Sequential(*layers)

    def fit(self, data: SurvivalData) -> DeepSurvBaseline:
        import torch

        X = data.X.to_numpy(dtype=float)
        self.mean_, self.std_ = X.mean(0), X.std(0)
        self.std_[self.std_ < 1e-9] = 1.0
        Z = (X - self.mean_) / self.std_

        rng = np.random.default_rng(self.seed)
        perm = rng.permutation(len(Z))
        n_val = max(1, int(0.2 * len(Z)))
        val_idx, tr_idx = perm[:n_val], perm[n_val:]

        tens = lambda a: torch.as_tensor(a, dtype=torch.float32)  # noqa: E731
        Xtr, Xva = tens(Z[tr_idx]), tens(Z[val_idx])
        ttr, tva = tens(data.duration[tr_idx]), tens(data.duration[val_idx])
        etr, eva = tens((data.event > 0)[tr_idx]), tens((data.event > 0)[val_idx])

        self.net_ = self._build(Z.shape[1])
        opt = torch.optim.Adam(self.net_.parameters(), lr=self.lr,
                               weight_decay=self.weight_decay)

        best, best_state, waited = float("inf"), None, 0
        for _ in range(self.epochs):
            self.net_.train()
            opt.zero_grad()
            loss = self._cox_loss(self.net_(Xtr).squeeze(-1), ttr, etr)
            loss.backward()
            opt.step()

            self.net_.eval()
            with torch.no_grad():
                v = float(self._cox_loss(self.net_(Xva).squeeze(-1), tva, eva))
            if v < best - 1e-5:
                best, waited = v, 0
                best_state = {k: p.detach().clone() for k, p in self.net_.state_dict().items()}
            else:
                waited += 1
                if waited >= self.patience:
                    break
        if best_state is not None:
            self.net_.load_state_dict(best_state)

        self._breslow(data, Z)
        return self

    def _breslow(self, data: SurvivalData, Z: np.ndarray) -> None:
        """Breslow's estimator of the baseline cumulative hazard.

        H0(t) = sum over event times s <= t of d_s / sum_{j at risk at s} exp(risk_j).
        Needed because the partial likelihood deliberately does not estimate it --
        which is precisely the second objection to Cox-family models in D-043: the
        absolute survival level is bolted on after the fact and nothing in the fit
        optimised it.
        """
        risk = np.exp(self._risk(Z))
        dur, ev = data.duration.astype(float), (data.event > 0)
        times = np.unique(dur[ev])
        increments = []
        for t in times:
            at_risk = risk[dur >= t].sum()
            increments.append((dur == t).sum() * ev[dur == t].mean() / max(at_risk, 1e-12))
        self.base_times_ = times
        self.base_cumhaz_ = np.cumsum(increments)

    def _risk(self, Z: np.ndarray) -> np.ndarray:
        import torch

        self.net_.eval()
        with torch.no_grad():
            return self.net_(torch.as_tensor(Z, dtype=torch.float32)).squeeze(-1).numpy()

    def survival_at(self, X: pd.DataFrame, times: np.ndarray) -> np.ndarray:
        Z = (X.to_numpy(dtype=float) - self.mean_) / self.std_
        risk = np.exp(self._risk(Z))
        h0 = _step_lookup(self.base_times_, self.base_cumhaz_,
                          np.asarray(times, dtype=float))
        # _step_lookup returns 1.0 before the first event time; for a cumulative
        # hazard the value there is 0.
        h0 = np.where(np.asarray(times, dtype=float) < self.base_times_[0], 0.0, h0)
        return np.exp(-np.outer(risk, h0))

    def risk_score(self, X: pd.DataFrame, horizon: float) -> np.ndarray:
        Z = (X.to_numpy(dtype=float) - self.mean_) / self.std_
        return self._risk(Z)


ALL_BASELINES: list[type[SurvivalBaseline]] = [
    KaplanMeierBaseline,
    CoxBaseline,
    RSFBaseline,
    DeepSurvBaseline,
]


def available_baselines() -> list[SurvivalBaseline]:
    """Instances of every baseline whose dependency is installed."""
    return [cls() for cls in ALL_BASELINES if cls.available()]


def missing_baselines() -> list[str]:
    return [cls.name for cls in ALL_BASELINES if not cls.available()]
