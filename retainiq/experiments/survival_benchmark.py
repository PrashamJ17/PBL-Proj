"""Phase 3 benchmark: discrete-time hazard against Cox, RSF and DeepSurv.

Two experiments, answering two different questions.

**Static** (`run_static`) -- one covariate vector per subject, predict the whole
survival curve. This is the head-to-head the phase gate names, and it is run on real
public data (Telco, GBSG2) as well as SubSim. Every model sees identical inputs.

**Landmark** (`run_landmark`) -- at month L, using only what was observable at L,
predict the next w months for customers still active. This is what a monthly
retention decision actually is, and it is where covariates that move matter. Only
SubSim can support it, because no public survival dataset carries a behavioural panel
with the outcome attached.

--------------------------------------------------------------------------------
PRE-REGISTERED PREDICTION -- written before the first run (D-021)
--------------------------------------------------------------------------------
The rule from D-021 is that the expected outcome and the meaning of each possible
result go in the code *before* the experiment runs, because the temptation to
reinterpret is strongest exactly when the result disappoints.

**Static, on GBSG2.** Expect to LOSE or tie on concordance. GBSG2 is continuous-time
medical data with 686 subjects; discretising to months throws away resolution the
baselines keep, and this is the dataset family RSF and DeepSurv were developed on. A
loss here is a result about discretisation, not a refutation.

**Static, on Telco.** Expect a TIE on concordance -- Telco's signal is dominated by
contract type and tenure, which every model can represent, and with 7k rows there is
enough data for all of them. Expect a WIN on calibration (IBS, D-calibration,
calibration slope), because the discrete model estimates absolute per-period
probabilities directly while Cox and DeepSurv profile the baseline out and bolt a
Breslow estimate on afterwards.

**Static, on SubSim.** Same expectation as Telco, with a smaller calibration margin,
because baseline covariates in SubSim are weakly informative about a trajectory that
has not happened yet.

**Landmark, on SubSim.** This is the one that should be decisive. Expect a
SUBSTANTIAL win, on both discrimination and calibration, over any fixed-covariate
model -- including over the same discrete model restricted to baseline covariates.
The mechanism is not sophistication, it is *representation*: engagement collapse is
the dominant churn signal (D-002) and a baseline-covariate model cannot see it happen.

**What each outcome would mean.**

* Win on calibration, tie on concordance -> the phase gate is met as stated, and the
  right headline is "calibrated, competitive on rank", not "beats Cox".
* Loss on calibration anywhere -> the gate FAILS. Calibration is the one thing this
  model is supposed to be for, since CLV is a functional of absolute survival. A
  discrete-time model that is not better calibrated than Cox has no reason to exist
  here and Phase 3 needs rethinking, not tuning.
* Win on concordance too -> pleasant, and to be reported with suspicion until the
  split and the leakage exclusions have been re-checked. `TotalCharges` is exactly
  the kind of column that produces a surprise win on Telco.
* No win at the landmark task -> the time-varying argument in D-043 is wrong, which
  would be the most informative failure available here.
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from retainiq.benchmarks.survival_data import (
    SUBSIM_FEATURES,
    load_gbsg2,
    load_telco,
    split_by_unit,
    subsim_person_period,
    subsim_survival,
)
from retainiq.models.survival.baselines import available_baselines, missing_baselines
from retainiq.models.survival.discrete import (
    PERIOD,
    UNIT,
    CompetingRisksHazard,
    DiscreteTimeHazard,
    SurvivalData,
)
from retainiq.models.survival.metrics import (
    calibration_at_horizon,
    concordance_index,
    d_calibration,
    estimable_horizon,
    integrated_brier_score,
)


@dataclass
class Score:
    """One model on one dataset. Rank metric first, calibration metrics after --
    but the calibration ones are the headline (D-045)."""

    dataset: str
    model: str
    c_index: float
    ibs: float
    """Integrated Brier score. LOWER is better. A proper scoring rule, so it
    penalises miscalibration that concordance is blind to."""
    cal_mae: float
    """Mean absolute gap between predicted and Kaplan-Meier survival, in bins of
    predicted risk, at the reference horizon. LOWER is better."""
    cal_slope: float
    """Regression of observed on predicted across those bins. 1.0 is perfect;
    below 1.0 means the model's spread of predictions is too wide."""
    d_cal_p: float
    """D-calibration p-value. Small means the survival function is demonstrably
    wrong. Large is failure to reject, not proof -- read it next to `cal_mae`."""
    n_train: int
    n_test: int


def horizon_grid(
    duration: np.ndarray, event: np.ndarray, n_points: int = 20
) -> np.ndarray:
    """Evaluation grid, from the 10th percentile of durations to the last estimable
    time.

    Two separate caps, and both are needed. The 90th percentile keeps the integrand
    away from the thin end of the risk set. `estimable_horizon` is the hard one: under
    administrative censoring `G(t)` hits exactly zero at the end of follow-up, and
    evaluating there is not noisy but undefined.
    """
    lo, hi = np.percentile(duration, [10, 90])
    hi = min(hi, estimable_horizon(duration, event))
    return np.unique(np.linspace(max(lo, 1.0), max(hi, max(lo, 1.0) + 1.0), n_points))


def _survival_at_own_time(
    model, X: pd.DataFrame, duration: np.ndarray, offset: float = 0.0
) -> np.ndarray:
    """S(T_i | x_i) at each subject's own observed time, for D-calibration.

    `offset = -1e-9` gives the left limit S(T_i-), which the discreteness correction
    in `d_calibration` needs. Every model is queried the same way, so no model gets a
    correction the others do not.
    """
    times = np.unique(duration.astype(float)) + offset
    curves = model.survival_at(X, times)
    col = np.searchsorted(np.unique(duration.astype(float)), duration.astype(float))
    return curves[np.arange(len(X)), np.clip(col, 0, len(times) - 1)]


def score_model(name: str, model, train: SurvivalData, test: SurvivalData) -> Score:
    """Fit on `train`, score on `test`. One code path for our model and every baseline."""
    model.fit(train) if not isinstance(model, DiscreteTimeHazard) else model.fit_data(train)

    # The grid is a property of the *evaluation* set, because that is whose censoring
    # distribution supplies the IPCW weights. It is identical for every model on a
    # given split, so this is a statement about where the metric is defined rather
    # than a choice any model benefits from.
    grid = horizon_grid(test.duration, test.event > 0)
    ref = float(np.median(train.duration))

    surv = model.survival_at(test.X, grid)
    risk = model.risk_score(test.X, ref)
    event = (test.event > 0).astype(int)

    marginal = getattr(model, "is_marginal", False)
    c = float("nan") if marginal else concordance_index(test.duration, event, risk)

    cal = calibration_at_horizon(
        test.duration, event, model.survival_at(test.X, np.array([ref]))[:, 0], ref
    )
    _, p, _ = d_calibration(
        test.duration,
        event,
        _survival_at_own_time(model, test.X, test.duration),
        survival_before_observed=_survival_at_own_time(
            model, test.X, test.duration, offset=-1e-9
        ),
    )

    return Score(
        dataset=test.name.split("[")[0],
        model=name,
        c_index=c,
        ibs=integrated_brier_score(test.duration, event, surv, grid),
        cal_mae=float(cal["mean_abs_error"]),
        cal_slope=float(cal["slope"]),
        d_cal_p=p,
        n_train=len(train),
        n_test=len(test),
    )


def our_models(data: SurvivalData, seed: int = 0) -> dict[str, object]:
    """The Phase 3 entries. Competing risks where the data has more than one cause.

    Note what is *not* here: no per-dataset tuning. One configuration everywhere, for
    the same reason the DeepSurv baseline is not tuned per dataset -- tuning one side
    only is how a benchmark turns into an advertisement.
    """
    pool = min(24, int(np.percentile(data.duration, 75)))
    if len(data.causes) > 1:
        return {
            "discrete_logistic": CompetingRisksHazard(
                data.cause_names, learner="logistic", pool_after=pool, seed=seed
            ),
            "discrete_gbm": CompetingRisksHazard(
                data.cause_names, learner="gbm", seed=seed
            ),
        }
    return {
        "discrete_logistic": DiscreteTimeHazard("logistic", pool_after=pool, seed=seed),
        "discrete_gbm": DiscreteTimeHazard("gbm", seed=seed),
    }


def run_static(data: SurvivalData, seed: int = 0, test_fraction: float = 0.3) -> pd.DataFrame:
    """Head-to-head on fixed covariates. This is the phase gate."""
    train, test, _ = split_by_unit(data, test_fraction, seed)
    train.name = test.name = data.name

    scores = [score_model(n, m, train, test) for n, m in our_models(data, seed).items()]
    for baseline in available_baselines():
        scores.append(score_model(baseline.name, baseline, train, test))
    return pd.DataFrame([asdict(s) for s in scores])


# --- landmark / dynamic prediction ------------------------------------------


@dataclass
class Landmark:
    """Everything observable at month L about the customers still paying at month L."""

    units: np.ndarray
    X_now: pd.DataFrame
    """Covariates *at* the landmark -- nothing after it."""
    duration: np.ndarray
    """Months survived past the landmark, capped at the window (1-indexed)."""
    event: np.ndarray


def _landmark_slice(
    panel: pd.DataFrame, data: SurvivalData, landmark: int, window: int, cause: int = 1
) -> Landmark:
    """Customers who survived month `landmark`, with their outcome over the next
    `window` months.

    Covariates come from the landmark month and nothing after it. Using the realised
    future path would make a time-varying model look far better than it can be in
    production, where next month's engagement is exactly what you do not have. That
    error is the survival-analysis form of availability leakage (D-014), and it is
    the reason this experiment is landmarked rather than run on oracle paths.

    The prediction target is the **cause-specific** hazard for `cause`. A customer
    lost to the competing cause inside the window is *censored* there, not counted as
    an event -- which is the correct competing-risks treatment and the only one
    compatible with invariant 5. Scoring a voluntary-churn model against an all-cause
    outcome would charge it for involuntary churn it never modelled, and did: the
    first run of this experiment had exactly that mismatch and the model lost to
    Kaplan-Meier on the Brier score because of it.
    """
    at_risk = panel[panel[PERIOD] == landmark]
    units = at_risk[UNIT].to_numpy()
    # Survived the landmark month itself, so the covariates observed during it are
    # strictly prior to every period being predicted.
    alive = data.duration[units] > landmark
    units, at_risk = units[alive], at_risk[alive]

    remaining = data.duration[units] - landmark
    duration = np.clip(remaining, 1, window)
    event = ((data.event[units] == cause) & (remaining <= window)).astype(int)
    return Landmark(
        units=units,
        X_now=at_risk[SUBSIM_FEATURES].reset_index(drop=True),
        duration=duration,
        event=event,
    )


def run_landmark(
    result,
    landmarks: tuple[int, ...] = (3, 6, 9, 12),
    window: int = 6,
    seed: int = 0,
    test_fraction: float = 0.3,
) -> pd.DataFrame:
    """Dynamic prediction on SubSim: does seeing covariates move actually pay?

    Three entries, chosen so the comparison isolates *representation* rather than
    learner strength:

    * ``discrete_timevarying`` -- ONE model fitted on the full person-period frame
      with the covariates as they moved. It serves every landmark without refitting,
      which is the practical advantage: pooling across tenures rather than splitting
      the data by landmark.
    * ``discrete_baseline_only`` -- the same model class, same learner, restricted to
      month-0 covariates. The controlled comparison.
    * ``cox_landmark`` -- Cox refitted at each landmark on the customers at risk
      there, with their covariates at that moment. The strong, standard comparator:
      it *does* see the moving covariates, at the cost of a smaller training set per
      landmark.

    A win for the first over the third is a claim about pooling; a win over the
    second is the claim about time variation. They are reported separately because
    they are different claims.
    """
    from retainiq.models.survival.baselines import CoxBaseline, KaplanMeierBaseline

    data = subsim_survival(result)
    panel = subsim_person_period(result, cause=1)

    rng = np.random.default_rng(seed)
    order = rng.permutation(len(data))
    n_test = int(round(test_fraction * len(data)))
    train_units = np.sort(order[n_test:])
    is_train = np.isin(panel[UNIT].to_numpy(), train_units)

    pooled = DiscreteTimeHazard("logistic", pool_after=12, seed=seed).fit(
        panel[is_train], SUBSIM_FEATURES
    )
    baseline_only = DiscreteTimeHazard("logistic", pool_after=12, seed=seed).fit_data(
        data.subset(train_units), cause=1
    )

    def conditional(model, X: pd.DataFrame, landmark: int) -> np.ndarray:
        """S(landmark + k | survived to landmark), k = 1..window.

        The model's own time axis is absolute tenure, so the window is read off the
        full curve and renormalised by survival to the landmark. Nothing beyond the
        landmark enters the covariates.
        """
        full = model.survival(X, landmark + window)
        return full[:, landmark:] / np.maximum(full[:, landmark - 1], 1e-12)[:, None]

    rows = []
    for landmark in landmarks:
        tr = _landmark_slice(panel[is_train], data, landmark, window)
        te = _landmark_slice(panel[~is_train], data, landmark, window)
        if len(te.X_now) < 50 or te.event.sum() < 5 or tr.event.sum() < 5:
            continue

        # Everyone still alive at the end of the window is censored there, so
        # G(window) = 0 and the last grid point is not estimable -- the same trap
        # `estimable_horizon` exists for, arriving through a different door.
        grid = np.arange(1.0, estimable_horizon(te.duration, te.event) + 0.5)
        if len(grid) < 2:
            continue

        fit_frame = SurvivalData(name="lm", X=tr.X_now, duration=tr.duration, event=tr.event)
        cox = CoxBaseline().fit(fit_frame)
        km = KaplanMeierBaseline().fit(fit_frame)

        entries = {
            "discrete_timevarying": conditional(pooled, te.X_now, landmark)[
                :, : len(grid)
            ],
            "discrete_baseline_only": conditional(
                baseline_only, data.X.iloc[te.units].reset_index(drop=True), landmark
            )[:, : len(grid)],
            "cox_landmark": cox.survival_at(te.X_now, grid),
            "kaplan_meier": km.survival_at(te.X_now, grid),
        }

        for name, surv in entries.items():
            risk = 1.0 - surv[:, -1]
            c = (
                float("nan")
                if name == "kaplan_meier"
                else concordance_index(te.duration, te.event, risk)
            )
            rows.append({
                "landmark": landmark,
                "model": name,
                "n_at_risk": len(te.X_now),
                "events": int(te.event.sum()),
                "c_index": c,
                "ibs": integrated_brier_score(te.duration, te.event, surv, grid),
            })
    return pd.DataFrame(rows)


def run_static_seeds(data: SurvivalData, seeds: int = 10) -> pd.DataFrame:
    """`run_static` repeated over resplits, summarised as mean and win rate.

    The evaluation set changes with the seed here, unlike the small-n sweep in
    `retainiq/benchmarks/small_n.py` where it is held fixed -- these datasets are single
    fixed samples, so a resplit is the only source of variation available. That makes
    this a statement about split sensitivity, not about sampling from the population,
    and it is weaker than the D-023 design for exactly that reason.

    `beats_*_on_ibs` is the share of seeds on which `discrete_logistic` has the lower
    integrated Brier score than that baseline, paired on the same split.
    """
    frames = []
    for seed in range(seeds):
        frame = run_static(data, seed=seed)
        frame["seed"] = seed
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)

    summary = df.groupby("model")[["c_index", "ibs", "cal_mae", "cal_slope"]].mean()
    ibs = df.pivot(index="seed", columns="model", values="ibs")
    ours = ibs["discrete_logistic"]
    summary["ibs_sd"] = df.groupby("model")["ibs"].std()
    summary["ours_beats_it_on_ibs"] = [
        float((ours < ibs[m]).mean()) if m != "discrete_logistic" else float("nan")
        for m in summary.index
    ]
    summary.insert(0, "dataset", data.name)
    summary.insert(1, "seeds", seeds)
    return summary.reset_index()


def run_landmark_small_n(
    sizes: tuple[int, ...] = (250, 500, 1000, 2000, 4000),
    seeds: int = 12,
    months: int = 24,
) -> pd.DataFrame:
    """The landmark comparison as a function of business size.

    Reported as a **win rate over seeds**, not a mean, for the reason established in
    D-023: a business gets one draw, not an average, and a method with a good mean
    and a wide spread is a gamble. Each seed is a fresh simulated business, and both
    models are scored on the same one.

    The hypothesis this tests: a single pooled discrete-time fit should beat a Cox
    refit *per landmark* when data is scarce, because the refit splits an already
    small sample by tenure, while pooling shares one covariate effect across every
    landmark and lets the period basis carry the tenure dependence. At large n the
    advantage should vanish -- Cox has enough events per landmark to estimate the
    same thing. A result that did *not* narrow with n would mean something other
    than pooling was driving it.
    """
    from retainiq.sim import SimConfig, simulate

    rows = []
    for n in sizes:
        per_seed = []
        for seed in range(seeds):
            frame = run_landmark(simulate(SimConfig(n, months, seed)), seed=seed)
            if frame.empty:
                continue
            agg = frame.groupby("model")[["c_index", "ibs"]].mean().reset_index()
            agg["seed"] = seed
            per_seed.append(agg)
        if not per_seed:
            continue

        df = pd.concat(per_seed, ignore_index=True)
        c = df.pivot(index="seed", columns="model", values="c_index")
        i = df.pivot(index="seed", columns="model", values="ibs")
        rows.append({
            "n_customers": n,
            "seeds": len(c),
            "c_discrete_tv": c["discrete_timevarying"].mean(),
            "c_cox_landmark": c["cox_landmark"].mean(),
            "c_discrete_baseline": c["discrete_baseline_only"].mean(),
            "beats_cox_on_c": (c["discrete_timevarying"] > c["cox_landmark"]).mean(),
            "beats_baseline_on_c": (
                c["discrete_timevarying"] > c["discrete_baseline_only"]
            ).mean(),
            "beats_cox_on_ibs": (i["discrete_timevarying"] < i["cox_landmark"]).mean(),
            "beats_km_on_ibs": (i["discrete_timevarying"] < i["kaplan_meier"]).mean(),
        })
    return pd.DataFrame(rows)


# --- reporting ---------------------------------------------------------------


def _print(frame: pd.DataFrame, title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    print(frame.to_string(index=False, float_format=lambda v: f"{v:.4f}"))


def main(seeds: int = 10, small_n: bool = True) -> None:
    from retainiq.sim import SimConfig, simulate

    missing = missing_baselines()
    if missing:
        print(f"NOTE: baselines unavailable in this environment: {', '.join(missing)}")
        print('      install with: make install-survival\n')

    sim = simulate(SimConfig(4000, 24, 7))
    datasets = []
    for loader, label in ((load_telco, "telco"), (load_gbsg2, "gbsg2")):
        try:
            datasets.append(loader())
        except Exception as exc:  # noqa: BLE001 - dataset availability, not a bug
            print(f"skipping {label}: {exc}")
    datasets.append(subsim_survival(sim))

    frames = []
    for data in datasets:
        print(data.summary())
        frames.append(run_static_seeds(data, seeds=seeds))

    _print(
        pd.concat(frames, ignore_index=True),
        f"STATIC -- fixed covariates, mean over {seeds} resplits "
        "(ibs: lower better; cal_slope: 1.0 is perfect)",
    )
    _print(run_landmark(sim), "LANDMARK -- SubSim, covariates as they moved (n=4000)")
    if small_n:
        _print(
            run_landmark_small_n(),
            "LANDMARK by business size -- win rate over seeds, not the mean (D-023)",
        )


if __name__ == "__main__":
    main()
