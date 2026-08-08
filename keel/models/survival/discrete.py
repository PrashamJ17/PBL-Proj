"""Discrete-time survival: the person-period hazard model.

The whole method in one sentence: expand each customer into one row per period they
were **at risk**, label the row 1 if they failed in that period, and fit a binary
classifier. The fitted probability is the hazard `h(t | x)`, and survival is the
product of its complements:

    S(t | x) = prod_{s <= t} (1 - h(s | x))

Why this and not Cox
--------------------
Cox is the default in the survival literature and it is the wrong default *here*,
for four reasons that are specific to what this project needs (D-043):

1. **Time-varying covariates are the whole point.** Engagement, support pain and
   payment failures move every month, and they are what carries the churn signal.
   Cox handles this only via a start-stop dataset, which is exactly the construction
   in which availability leakage is easiest to introduce and hardest to see. Here
   each person-period row *is* one point-in-time feature build, so the Phase 1
   guarantee (`FeatureStore._visible`) extends to the survival model unchanged.

2. **We need absolute probabilities, not a ranking.** CLV is a functional of S(t).
   Cox's partial likelihood profiles the baseline hazard out as a nuisance, so
   absolute survival arrives only via a Breslow add-on that nothing in the fit
   optimised.

3. **Proportional hazards is false in subscriptions and testable.** Contract type
   does not multiply a common baseline; a month-to-month customer and an annual one
   have differently *shaped* hazards. Here the baseline is a free function of period
   and covariate-by-period interactions cost nothing.

4. **Billing is discrete.** Churn happens at a renewal boundary. Continuous-time
   machinery spends its complexity budget on ties that are not ties at all -- they
   are genuinely simultaneous events in a monthly cycle.

The cost, stated plainly: the person-period frame is `sum_i d_i` rows rather than
`n`, so it is bigger by the mean duration. At Keel's scale (thousands of customers,
tens of months) that is nothing. At tens of millions of customers it would matter.

Competing risks
---------------
Voluntary and involuntary churn are separate processes and are never summed
(invariant 5). The competing-risks form respects that: a **separate** cause-specific
hazard is fitted per cause, and they combine only at the survival-function level,
where `1 - sum_k h_k` is the probability of surviving all causes. No label is ever
merged (D-044).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

UNIT = "unit"
PERIOD = "period"
EVENT = "event"


# --- data container ----------------------------------------------------------


@dataclass
class SurvivalData:
    """Right-censored durations with fixed covariates.

    `duration` counts **completed periods at risk** and must be >= 1: a customer who
    never completed a period contributes no row to the person-period frame and
    carries no information about the hazard. Loaders drop them explicitly rather
    than silently coercing to 1.

    `event` is 0 for censored, otherwise the integer **cause** code. A plain
    single-risk dataset uses 1.
    """

    name: str
    X: pd.DataFrame
    duration: np.ndarray
    event: np.ndarray
    cause_names: dict[int, str] = field(default_factory=lambda: {1: "event"})

    def __post_init__(self) -> None:
        self.duration = np.asarray(self.duration).astype(int)
        self.event = np.asarray(self.event).astype(int)
        if len(self.X) != len(self.duration) or len(self.duration) != len(self.event):
            raise ValueError("X, duration and event must be the same length")
        if len(self.duration) == 0:
            raise ValueError(
                f"{self.name}: dataset is empty. A survival model cannot be fitted to "
                "zero subjects; check the loader's filters."
            )
        if (self.duration < 1).any():
            raise ValueError(
                "duration must be >= 1 period; a subject with zero periods at risk "
                "contributes no person-period rows. Drop them in the loader, "
                "explicitly, so the exclusion is visible."
            )
        # Covariates reach scikit-learn unchanged, whose NaN message names a solver
        # rather than the column at fault. Real billing exports carry NaNs, so say
        # which column and let the caller decide how to fill it -- imputing silently
        # here would hide a data problem inside a model.
        nan_cols = [c for c in self.X.columns if self.X[c].isna().any()]
        if nan_cols:
            raise ValueError(
                f"{self.name}: missing values in covariate(s) {nan_cols}. Impute or "
                "drop them in the loader, where the choice is visible, rather than "
                "letting the model decide."
            )
        # `event` is a cause code, so values above 1 are legitimate -- but only if
        # they were declared. An undeclared code silently becomes a cause nobody
        # models, and its subjects are treated as censored without anyone saying so.
        undeclared = sorted(set(np.unique(self.event)) - {0} - set(self.cause_names))
        if undeclared:
            raise ValueError(
                f"{self.name}: event codes {undeclared} are not declared in "
                f"cause_names={self.cause_names}. Either declare them or map them to "
                "an existing cause; leaving them undeclared silently censors those "
                "subjects."
            )

    def __len__(self) -> int:
        return len(self.duration)

    @property
    def features(self) -> list[str]:
        return list(self.X.columns)

    @property
    def causes(self) -> list[int]:
        return sorted(c for c in np.unique(self.event) if c > 0)

    def summary(self) -> str:
        rate = float((self.event > 0).mean())
        parts = [
            f"{self.name}: n={len(self):,}  events={int((self.event > 0).sum()):,} "
            f"({rate:.1%})  censored={(self.event == 0).mean():.1%}",
            f"  duration: median {np.median(self.duration):.0f}, "
            f"max {self.duration.max()}  covariates: {len(self.features)}",
        ]
        if len(self.causes) > 1:
            split = ", ".join(
                f"{self.cause_names.get(c, c)} {(self.event == c).mean():.1%}"
                for c in self.causes
            )
            parts.append(f"  causes: {split}")
        return "\n".join(parts)

    def subset(self, idx: np.ndarray) -> SurvivalData:
        return SurvivalData(
            name=f"{self.name}[n={len(idx)}]",
            X=self.X.iloc[idx].reset_index(drop=True),
            duration=self.duration[idx],
            event=self.event[idx],
            cause_names=dict(self.cause_names),
        )

    def person_period(self, cause: int | None = None) -> pd.DataFrame:
        """Expand to one row per (subject, period at risk).

        Periods are 1-indexed. The event flag is 1 only on the **final** row of a
        subject who failed, which is what makes the binomial likelihood of this frame
        equal to the discrete-time survival likelihood.

        With `cause` given, the flag marks that cause only; failures from a competing
        cause become 0 in the final period, i.e. the subject is treated as censored
        *by* the competing event. That is the cause-specific hazard, and it is the
        quantity that composes correctly into overall survival.
        """
        rep = np.repeat(np.arange(len(self)), self.duration)
        period = np.concatenate([np.arange(1, d + 1) for d in self.duration])

        failed = self.event > 0 if cause is None else self.event == cause
        last = period == self.duration[rep]
        flag = (last & failed[rep]).astype(int)

        out = self.X.iloc[rep].reset_index(drop=True)
        out.insert(0, UNIT, rep)
        out.insert(1, PERIOD, period)
        out[EVENT] = flag
        return out


# --- the baseline hazard in time --------------------------------------------


def restricted_cubic_spline(x: np.ndarray, knots: np.ndarray) -> np.ndarray:
    """Harrell's restricted (natural) cubic spline basis, linear beyond the outer knots.

    `K` knots give `K - 1` columns: `x` itself plus `K - 2` cubic terms. Restricting
    the tails to be linear is what stops the fitted baseline hazard from doing
    something violent in the sparse final periods, where a handful of subjects remain
    at risk.
    """
    k = np.asarray(knots, dtype=float)
    if len(k) < 3:
        raise ValueError("a restricted cubic spline needs at least 3 knots")
    denom = (k[-1] - k[-2]) if (k[-1] - k[-2]) > 1e-12 else 1e-12
    scale = (k[-1] - k[0]) ** 2

    cols = [x]
    for j in range(len(k) - 2):
        cube = np.clip(x - k[j], 0, None) ** 3
        cube -= np.clip(x - k[-2], 0, None) ** 3 * (k[-1] - k[j]) / denom
        cube += np.clip(x - k[-1], 0, None) ** 3 * (k[-2] - k[j]) / denom
        cols.append(cube / scale)
    return np.column_stack(cols)


def period_basis(
    period: np.ndarray,
    kind: str = "dummies",
    pool_after: int = 24,
    knots: np.ndarray | None = None,
) -> pd.DataFrame:
    """Encode the period index as the baseline-hazard term.

    ``dummies`` -- one indicator per period up to `pool_after`, then a pooled tail
    with a log-time slope. Fully non-parametric where the data is and stable where it
    is not. This is the textbook choice (Singer & Willett) and the default.

    ``spline`` -- a restricted cubic spline on log(period). Smoother, uses far fewer
    parameters, and is the better option when periods are many and events are few.

    ``raw`` -- period and log(period), for tree learners, which partition the axis
    themselves and gain nothing from an explicit basis.
    """
    p = np.asarray(period, dtype=float)
    logp = np.log(p)

    if kind == "raw":
        return pd.DataFrame({"period": p, "log_period": logp})

    if kind == "spline":
        if knots is None:
            knots = np.quantile(np.unique(logp), [0.05, 0.35, 0.65, 0.95])
        basis = restricted_cubic_spline(logp, np.asarray(knots))
        return pd.DataFrame(basis, columns=[f"t_spline_{i}" for i in range(basis.shape[1])])

    if kind != "dummies":
        raise ValueError(f"unknown period basis {kind!r}")

    frame = pd.DataFrame(
        {f"t_{k}": (p == k).astype(float) for k in range(1, pool_after + 1)}
    )
    # The pooled tail is the reference category; the log slope lets it keep moving
    # rather than pinning every late period to one shared hazard.
    tail = (p > pool_after).astype(float)
    frame["t_tail"] = tail
    frame["t_tail_log"] = tail * (logp - np.log(max(pool_after, 1)))
    return frame


# --- the model ---------------------------------------------------------------


class DiscreteTimeHazard:
    """Cause-specific discrete-time hazard, fitted on a person-period frame.

    Parameters
    ----------
    learner:
        ``logistic`` -- regularised logistic regression on the period basis. This is
        the classical discrete-time model and it is the *calibrated* one: a
        well-specified logistic fit returns probabilities, not scores.
        ``gbm`` -- histogram gradient boosting, which buys interactions and
        non-linearity at the cost of needing the isotonic step below.
    baseline:
        Period encoding; see `period_basis`. Defaults to ``dummies`` for logistic and
        ``raw`` for gbm.
    calibrate:
        Fit an isotonic map from raw hazard to observed frequency on a held-out slice
        of **subjects**. Off for logistic (which is already calibrated and would only
        lose data to the split), on for gbm.
    allow_extrapolation:
        Permit predictions past the last period seen during fitting. Off by default,
        matching the same discipline `clv()` applies (invariant 12): beyond the
        observed support the period basis is asserting a functional form rather than
        estimating one, and that should be a visible choice.
    """

    def __init__(
        self,
        learner: str = "logistic",
        baseline: str | None = None,
        pool_after: int = 24,
        calibrate: bool | None = None,
        calibration_fraction: float = 0.25,
        seed: int = 0,
        allow_extrapolation: bool = False,
    ):
        if learner not in ("logistic", "gbm"):
            raise ValueError(f"unknown learner {learner!r}; use 'logistic' or 'gbm'")
        self.learner = learner
        self.baseline = baseline or ("raw" if learner == "gbm" else "dummies")
        self.pool_after = pool_after
        self.calibrate = (learner == "gbm") if calibrate is None else calibrate
        self.calibration_fraction = calibration_fraction
        self.seed = seed
        self.allow_extrapolation = allow_extrapolation
        self.observed_support: int | None = None
        """Largest period seen during fitting. Predictions beyond it extrapolate."""

        self.features: list[str] = []
        self.cause: int = 1
        self.model = None
        self.iso: IsotonicRegression | None = None
        self.name = f"discrete_{learner}"

    # -- fitting ---------------------------------------------------------------

    def _design(self, frame: pd.DataFrame) -> pd.DataFrame:
        basis = period_basis(
            frame[PERIOD].to_numpy(), self.baseline, self.pool_after
        )
        basis.index = frame.index
        return pd.concat([frame[self.features].astype(float), basis], axis=1)

    def _new_model(self):
        if self.learner == "logistic":
            # Scaled + L2. The dummy baseline is high-dimensional and the late
            # periods are thin, so unpenalised MLE would separate on them.
            return make_pipeline(
                StandardScaler(),
                LogisticRegression(max_iter=2000, C=1.0, random_state=self.seed),
            )
        return HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.06, max_depth=3,
            min_samples_leaf=40, random_state=self.seed,
        )

    def _check_support(self, horizon: int) -> None:
        """Refuse to project past the periods the model actually saw.

        The same discipline `clv()` applies (invariant 12, D-046). Beyond the
        observed support the period basis is extrapolating: the dummy basis has no
        coefficient for those periods and the spline basis is running on its linear
        tail. Neither is estimated from data, and the resulting survival curve is not
        merely uncertain -- it is a functional-form assumption presented as an
        estimate. Silence here would let a 24-month CLV be built from 8 months of
        history without anyone noticing.
        """
        if self.observed_support is None or self.allow_extrapolation:
            return
        if horizon > self.observed_support:
            raise ValueError(
                f"horizon {horizon} exceeds the observed support of "
                f"{self.observed_support} periods. Beyond it the period basis is "
                "extrapolating rather than estimating. Shorten the horizon, or pass "
                "allow_extrapolation=True so the assumption is a visible line of code."
            )

    def fit(self, pp: pd.DataFrame, features: list[str]) -> DiscreteTimeHazard:
        """Fit on an already-expanded person-period frame."""
        self.features = list(features)
        y = pp[EVENT].to_numpy().astype(int)
        self.observed_support = int(pp[PERIOD].max()) if len(pp) else None

        # Without this, scikit-learn raises "this solver needs samples of at least 2
        # classes", which names the solver rather than the problem. Zero events is a
        # real situation -- a young business that has not lost anyone yet -- and the
        # honest answer is that the hazard is unidentified, not that the optimiser
        # is unhappy.
        if len(y) == 0:
            raise ValueError("no person-period rows to fit; the dataset expanded to nothing")
        if len(np.unique(y)) < 2:
            only = "no events" if y.max() == 0 else "no censored periods"
            raise ValueError(
                f"cannot fit a hazard: the person-period frame contains {only} "
                f"({int(y.sum())} events in {len(y)} rows). The hazard is "
                "unidentified from this data. Use Kaplan-Meier for a marginal "
                "estimate, or wait for events to accrue."
            )

        if not self.calibrate:
            self.model = self._new_model().fit(self._design(pp), y)
            self.iso = None
            return self

        # **The split is by subject, never by row.** Person-period rows from one
        # customer are the same customer at consecutive months: they share
        # covariates and an outcome. A row-wise split puts month 5 in train and
        # month 6 in calibration, which is leakage of exactly the kind Phase 1
        # exists to prevent -- and it makes the calibration map look better than it
        # is, so nothing downstream would flag it.
        units = pp[UNIT].to_numpy()
        uniq = np.unique(units)
        rng = np.random.default_rng(self.seed)
        held = set(rng.choice(uniq, size=max(1, int(len(uniq) * self.calibration_fraction)),
                              replace=False).tolist())
        hold_mask = np.isin(units, list(held))

        self.model = self._new_model().fit(self._design(pp[~hold_mask]), y[~hold_mask])
        raw = self._raw_hazard(pp[hold_mask])
        self.iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        self.iso.fit(raw, y[hold_mask])
        return self

    def fit_data(self, data: SurvivalData, cause: int = 1) -> DiscreteTimeHazard:
        """Convenience: expand `data` for one cause and fit."""
        self.cause = cause
        return self.fit(data.person_period(cause=cause), data.features)

    # -- prediction ------------------------------------------------------------

    def _raw_hazard(self, frame: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("fit() first")
        return self.model.predict_proba(self._design(frame))[:, 1]

    def hazard(self, frame: pd.DataFrame) -> np.ndarray:
        """P(fail in this period | at risk at the start of it) for each row."""
        raw = self._raw_hazard(frame)
        return raw if self.iso is None else np.clip(self.iso.predict(raw), 0.0, 1.0)

    def hazard_grid(self, X: pd.DataFrame, horizon: int) -> np.ndarray:
        """Hazard for every subject at every period 1..horizon. Shape `(n, horizon)`.

        Holds covariates fixed at their current values across the window. That is the
        right assumption for a *static* covariate set and an approximation for a
        time-varying one -- `survival_from_panel` is the version that uses a real
        covariate path.
        """
        if horizon < 1:
            raise ValueError(f"horizon must be >= 1 period, got {horizon}")
        self._check_support(horizon)

        n = len(X)
        rep = np.repeat(np.arange(n), horizon)
        grid = X.iloc[rep].reset_index(drop=True)
        grid.insert(0, UNIT, rep)
        grid.insert(1, PERIOD, np.tile(np.arange(1, horizon + 1), n))
        return self.hazard(grid).reshape(n, horizon)

    def survival(self, X: pd.DataFrame, horizon: int) -> np.ndarray:
        """S(t) for t = 1..horizon. Shape `(n, horizon)`."""
        return np.cumprod(1.0 - self.hazard_grid(X, horizon), axis=1)

    def survival_from_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        """Survival along an explicit covariate path.

        `panel` carries `unit`, `period` and the covariates, one row per period. Use
        this when the covariates genuinely move -- it is the case `hazard_grid`
        approximates and the case Cox cannot express without a start-stop frame.
        """
        out = panel[[UNIT, PERIOD]].copy()
        out["hazard"] = self.hazard(panel)
        out = out.sort_values([UNIT, PERIOD], kind="stable")
        out["survival"] = out.groupby(UNIT)["hazard"].transform(
            lambda h: np.cumprod(1.0 - h.to_numpy())
        )
        return out.reset_index(drop=True)

    # -- convenience for the evaluation harness -------------------------------

    def survival_at(
        self, X: pd.DataFrame, times: np.ndarray, horizon: int | None = None
    ) -> np.ndarray:
        """S(t) at arbitrary (possibly non-integer) `times`. Shape `(n, len(times))`.

        Signature matches `SurvivalBaseline.survival_at` so the evaluation harness
        can score this model and the comparators through one code path.
        """
        times = np.asarray(times, dtype=float)
        horizon = horizon or max(1, int(np.ceil(times.max())))
        curve = self.survival(X, horizon)
        idx = np.clip(np.floor(times).astype(int) - 1, -1, horizon - 1)
        cols = [
            np.ones(len(X)) if i < 0 else curve[:, i]
            for i in idx
        ]
        return np.column_stack(cols)

    def risk_score(self, X: pd.DataFrame, horizon: float) -> np.ndarray:
        """A single number per subject for rank metrics: P(fail within `horizon`)."""
        return 1.0 - self.survival(X, max(1, int(np.ceil(horizon))))[:, -1]


class CompetingRisksHazard:
    """One cause-specific hazard per cause, combined only at the survival level.

    Overall survival is `prod_t (1 - sum_k h_k(t))` and the cumulative incidence of
    cause k is `sum_{s<=t} h_k(s) * S(s-1)`. Nothing is summed at the *label* level,
    which is the error invariant 5 forbids: each cause keeps its own model, its own
    coefficients and its own interpretation, and the CIFs are reported separately
    (D-044).
    """

    def __init__(self, causes: dict[int, str], **kwargs):
        self.causes = causes
        self.models = {c: DiscreteTimeHazard(**kwargs) for c in causes}
        self.name = "competing_risks"

    def fit(self, data: SurvivalData) -> CompetingRisksHazard:
        for cause, model in self.models.items():
            model.fit_data(data, cause=cause)
        return self

    def cause_hazards(self, X: pd.DataFrame, horizon: int) -> dict[int, np.ndarray]:
        return {c: m.hazard_grid(X, horizon) for c, m in self.models.items()}

    def survival(self, X: pd.DataFrame, horizon: int) -> np.ndarray:
        total = sum(self.cause_hazards(X, horizon).values())
        # Cause-specific hazards are fitted independently, so their sum can exceed 1
        # for a customer that every model considers doomed. Clipping keeps the
        # survival function valid; the clip rate is worth watching, not hiding.
        return np.cumprod(1.0 - np.clip(total, 0.0, 1.0), axis=1)

    def survival_at(
        self, X: pd.DataFrame, times: np.ndarray, horizon: int | None = None
    ) -> np.ndarray:
        """Overall survival at `times`, matching the `SurvivalBaseline` interface."""
        times = np.asarray(times, dtype=float)
        horizon = horizon or max(1, int(np.ceil(times.max())))
        curve = self.survival(X, horizon)
        idx = np.clip(np.floor(times).astype(int) - 1, -1, horizon - 1)
        return np.column_stack([
            np.ones(len(X)) if i < 0 else curve[:, i] for i in idx
        ])

    def risk_score(self, X: pd.DataFrame, horizon: float) -> np.ndarray:
        return 1.0 - self.survival(X, max(1, int(np.ceil(horizon))))[:, -1]

    def cumulative_incidence(self, X: pd.DataFrame, horizon: int) -> dict[int, np.ndarray]:
        """CIF_k(t): probability of having failed from cause k by t, *in the presence
        of the other causes*. This is the quantity a business actually wants -- a
        customer lost to an expired card is not available to be lost voluntarily."""
        hazards = self.cause_hazards(X, horizon)
        total = np.clip(sum(hazards.values()), 0.0, 1.0)
        surv = np.cumprod(1.0 - total, axis=1)
        prev = np.column_stack([np.ones(len(X)), surv[:, :-1]])
        return {c: np.cumsum(h * prev, axis=1) for c, h in hazards.items()}
