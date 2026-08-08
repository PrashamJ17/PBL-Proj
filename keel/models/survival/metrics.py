"""Survival evaluation metrics -- discrimination *and* calibration.

Written against numpy/scipy only, deliberately. `lifelines` and `scikit-survival`
both provide most of these, but they are optional extras (Phase 3) while the tests
that use these metrics run in CI on the base install. A metric that cannot be
computed in CI is a metric that silently stops being checked.

They are still cross-checked against those libraries where available --
`test_concordance_matches_scikit_survival` and `test_brier_matches_scikit_survival`
assert agreement rather than merely trusting this file.

Why calibration is treated as a first-class metric here
-------------------------------------------------------
The survival literature reports concordance (a rank statistic) almost to the
exclusion of everything else, and Cox's partial likelihood does not even estimate
the baseline hazard -- it is profiled out as a nuisance.

That is fine if you only need an ordering. This project needs **money**: CLV is
`sum_t margin * S(t) / (1+d)^t`, which is a functional of the *absolute* survival
probabilities. A model can rank customers perfectly and still value them at twice
what they are worth. So every comparison in Phase 3 reports a rank metric and a
calibration metric side by side, and the calibration one is the headline.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

# --- non-parametric baselines -----------------------------------------------


def kaplan_meier(duration: np.ndarray, event: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Kaplan-Meier survival estimate.

    Returns `(times, survival)` where `times` are the distinct observed times in
    ascending order and `survival[i]` is S(times[i]), the probability of surviving
    *past* `times[i]`.
    """
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event, dtype=float)

    times = np.unique(duration)
    n_at_risk = np.array([(duration >= t).sum() for t in times], dtype=float)
    n_events = np.array([((duration == t) & (event > 0)).sum() for t in times], dtype=float)

    with np.errstate(divide="ignore", invalid="ignore"):
        factors = np.where(n_at_risk > 0, 1.0 - n_events / n_at_risk, 1.0)
    return times, np.cumprod(factors)


def _step_lookup(times: np.ndarray, values: np.ndarray, query: np.ndarray) -> np.ndarray:
    """Right-continuous step function: value at the largest `times` <= `query`.

    Before the first observed time the step function is 1.0 (nothing has happened
    yet), which is what both the KM survival and the censoring distribution should
    return there.
    """
    query = np.asarray(query, dtype=float)
    idx = np.searchsorted(times, query, side="right") - 1
    out = np.ones_like(query, dtype=float)
    valid = idx >= 0
    out[valid] = values[idx[valid]]
    return out


def censoring_survival(duration: np.ndarray, event: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Estimate of the *censoring* distribution G(t) = P(C > t).

    This is the reweighting term that makes the Brier score unbiased under
    independent censoring: an observation censored early stands in for the subjects
    we can no longer see, so it is upweighted by 1/G.

    **Not simply Kaplan-Meier with the indicator flipped.** At a time where events
    and censorings are tied, the convention is that events happen first, so the
    denominator is `at_risk - events` rather than `at_risk`. On monthly data almost
    every time is tied, and the difference is not academic: using the naive flip
    moved the integrated Brier score by ~2% here and put us out of agreement with
    `scikit-survival`, which `test_brier_matches_scikit_survival` caught.
    """
    duration = np.asarray(duration, dtype=float)
    censored = ~(np.asarray(event, dtype=float) > 0)

    times = np.unique(duration)
    at_risk = np.array([(duration >= t).sum() for t in times], dtype=float)
    events = np.array([((duration == t) & ~censored).sum() for t in times], dtype=float)
    censorings = np.array([((duration == t) & censored).sum() for t in times], dtype=float)

    denom = at_risk - events
    with np.errstate(divide="ignore", invalid="ignore"):
        factors = np.where(denom > 0, 1.0 - censorings / np.maximum(denom, 1e-12), 1.0)
    return times, np.cumprod(factors)


def estimable_horizon(
    duration: np.ndarray, event: np.ndarray, min_censoring_survival: float = 0.05
) -> float:
    """Largest time at which the IPCW Brier score is actually estimable.

    Every inverse-probability weight is `1 / G(t)`, so the score stops being defined
    where `G(t)` reaches zero -- and under administrative censoring it reaches
    **exactly** zero at the end of the study, because nobody can be censored later
    than the last day of follow-up. A 24-month simulation has `G(24) = 0` by
    construction.

    This is not a corner case that can be papered over with a clip: evaluating there
    produced integrated Brier scores of ~2.6e7 on SubSim, six orders of magnitude
    out, and the ranking of the models was scrambled rather than merely inflated. It
    was invisible on Telco and GBSG2, where follow-up is staggered and `G` stays
    positive throughout, which is exactly why it survived the first round of runs.

    The 5% floor is a convention, not a derivation. Weights above 20x are dominated
    by a handful of subjects whatever the threshold, so the grid stops there.
    """
    times, g = censoring_survival(duration, event)
    usable = times[g > min_censoring_survival]
    return float(usable[-1]) if len(usable) else float(times[0])


# --- discrimination ----------------------------------------------------------


def concordance_index(
    duration: np.ndarray, event: np.ndarray, risk: np.ndarray
) -> float:
    """Harrell's C for right-censored data. Higher `risk` should mean earlier failure.

    A pair (i, j) is **comparable** when i experienced an event and either
    `T_j > T_i`, or `T_j == T_i` and j was censored -- j is then known to have
    survived at least as long. Tied event times are *not* comparable, because
    neither ordering is established. That is scikit-survival's convention, and
    `test_concordance_matches_scikit_survival` pins the agreement.

    Ties in `risk` count as half-concordant, so an all-constant score returns
    exactly 0.5 rather than 0.
    """
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event, dtype=float) > 0
    risk = np.asarray(risk, dtype=float)

    concordant = tied_risk = comparable = 0.0
    for i in np.flatnonzero(event):
        later = (duration > duration[i]) | ((duration == duration[i]) & ~event)
        later[i] = False
        if not later.any():
            continue
        comparable += later.sum()
        concordant += (risk[i] > risk[later]).sum()
        tied_risk += (risk[i] == risk[later]).sum()

    if comparable == 0:
        return float("nan")
    return float((concordant + 0.5 * tied_risk) / comparable)


# --- calibration -------------------------------------------------------------


def brier_score(
    duration: np.ndarray,
    event: np.ndarray,
    survival_at_t: np.ndarray,
    t: float,
    censor_times: np.ndarray | None = None,
    censor_surv: np.ndarray | None = None,
) -> float:
    """Inverse-probability-of-censoring-weighted Brier score at one horizon (Graf 1999).

    `survival_at_t[i]` is the model's predicted P(T_i > t | x_i).

    Three cases per subject:

    * failed by `t` (observed): the truth is 0, weighted by 1/G(T_i);
    * still alive at `t`: the truth is 1, weighted by 1/G(t);
    * censored before `t`: contributes nothing -- we genuinely do not know.

    Lower is better. Unlike concordance this is a **proper scoring rule**, so it
    punishes a model whose probabilities are systematically off even when its
    ordering is perfect.
    """
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(event, dtype=float) > 0
    s = np.clip(np.asarray(survival_at_t, dtype=float), 0.0, 1.0)

    if censor_times is None or censor_surv is None:
        censor_times, censor_surv = censoring_survival(duration, event)

    # G evaluated *at* the event time, not at its left limit. That is safe precisely
    # because `censoring_survival` puts events before censorings at a tied time, so
    # G has not yet been decremented by anything happening at T_i. With the naive
    # flipped-indicator estimator it would not be, and the left limit would be
    # required instead -- the two choices have to be made together.
    g_at_event = _step_lookup(censor_times, censor_surv, duration)
    g_at_t = float(_step_lookup(censor_times, censor_surv, np.array([t]))[0])

    failed = event & (duration <= t)
    alive = duration > t

    # Undefined rather than large. Returning a number here -- by clipping the weight
    # or by dropping the subjects -- would silently bias the score toward whichever
    # model happens to be optimistic about the customers we can no longer weight.
    # See `estimable_horizon`, which is how callers stay out of this region.
    if (alive.any() and g_at_t <= 0.0) or (failed.any() and (g_at_event[failed] <= 0).any()):
        return float("nan")

    term = np.zeros(len(duration), dtype=float)
    term[failed] = (s[failed] ** 2) / g_at_event[failed]
    if alive.any():
        term[alive] = ((1.0 - s[alive]) ** 2) / g_at_t
    return float(term.mean())


def integrated_brier_score(
    duration: np.ndarray,
    event: np.ndarray,
    survival: np.ndarray,
    horizons: np.ndarray,
) -> float:
    """Brier score integrated over `horizons` by the trapezoid rule, then normalised.

    `survival` is `(n_subjects, len(horizons))`. The grid should stop well short of
    the last observed time: as the risk set empties the IPCW weights blow up and the
    integrand becomes mostly noise. Callers here use the 90th percentile of observed
    durations.
    """
    horizons = np.asarray(horizons, dtype=float)
    if survival.shape[1] != len(horizons):
        raise ValueError(
            f"survival has {survival.shape[1]} columns but {len(horizons)} horizons given"
        )
    ct, cs = censoring_survival(duration, event)
    scores = np.array([
        brier_score(duration, event, survival[:, k], t, ct, cs)
        for k, t in enumerate(horizons)
    ])
    span = horizons[-1] - horizons[0]
    if span <= 0:
        return float(scores.mean())
    return float(np.trapezoid(scores, horizons) / span)


def d_calibration(
    duration: np.ndarray,
    event: np.ndarray,
    survival_at_observed: np.ndarray,
    n_bins: int = 10,
    survival_before_observed: np.ndarray | None = None,
) -> tuple[float, float, np.ndarray]:
    """D-calibration (Haider et al., JMLR 2020). Returns `(chi2, p_value, bin_mass)`.

    The idea, which is elegant: if a model's survival function is right, then
    `S(T_i | x_i)` evaluated at each subject's own event time is **Uniform(0, 1)**.
    So bin those values and test for uniformity.

    Censored subjects are not thrown away -- a subject censored at C with predicted
    `S(C) = s` is known only to fall somewhere in `[0, s]`, so it contributes one
    unit of probability mass spread over that range. Discarding them would bias the
    test toward whichever model is optimistic about the censored.

    The discreteness correction, and why it is not a fudge
    -----------------------------------------------------
    `S(T) ~ Uniform(0, 1)` holds for a **continuous** distribution. Survival on a
    monthly grid jumps, so `S(T_i)` lands at the bottom of the interval the event
    fell in and the top bin is systematically starved. Measured on a well-specified
    synthetic fit: chi2 = 61.7 using `S(t)`, against 2.3 using the interval midpoint
    `(S(t) + S(t-)) / 2` -- the rejection was an artifact of the grid, not a defect
    of the model.

    Pass `survival_before_observed` (the left limit `S(t-)`) to use the midpoint.
    This is the standard randomised-PIT correction for discrete distributions, and
    the harness applies it to **every** model through one code path -- the left limit
    is just `survival_at(X, t - 1e-9)`, which is well defined for a step function
    whether it came from Cox, an RSF or a discrete hazard. Applying it to our model
    alone would be exactly the kind of asymmetry this project is meant to avoid.

    **A large p-value is not proof of calibration** -- it is failure to reject, and
    it comes cheap at small n. It is reported next to the effect size, never alone.
    """
    event = np.asarray(event, dtype=float) > 0
    s = np.clip(np.asarray(survival_at_observed, dtype=float), 0.0, 1.0)
    if survival_before_observed is not None:
        before = np.clip(np.asarray(survival_before_observed, dtype=float), 0.0, 1.0)
        s = 0.5 * (s + np.maximum(before, s))
    n = len(s)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    mass = np.zeros(n_bins, dtype=float)

    for i in range(n):
        if event[i]:
            b = min(int(s[i] * n_bins), n_bins - 1)
            mass[b] += 1.0
            continue
        # Censored: uniform over [0, s_i]. Bins wholly below s_i get a full
        # bin-width of mass; the bin containing s_i gets the partial overlap.
        if s[i] <= 1e-12:
            mass[0] += 1.0
            continue
        overlap = np.clip(np.minimum(edges[1:], s[i]) - edges[:-1], 0.0, None)
        mass += overlap / s[i]

    expected = n / n_bins
    chi2 = float(((mass - expected) ** 2 / expected).sum())
    p = float(stats.chi2.sf(chi2, df=n_bins - 1))
    return chi2, p, mass


def calibration_at_horizon(
    duration: np.ndarray,
    event: np.ndarray,
    survival_at_t: np.ndarray,
    t: float,
    n_bins: int = 10,
) -> dict[str, float | np.ndarray]:
    """Predicted vs observed survival at one horizon, in bins of predicted risk.

    Within each bin the *observed* survival is the Kaplan-Meier estimate at `t`
    computed on that bin alone -- not the raw proportion still present, which would
    count censored subjects as failures and make every model look pessimistic.

    Returns the per-bin arrays plus two summaries: `mean_abs_error` (the
    size-weighted mean gap, in probability) and `slope` (the regression of observed
    on predicted; 1.0 is perfect, below 1.0 means predictions are too spread out).
    """
    s = np.clip(np.asarray(survival_at_t, dtype=float), 0.0, 1.0)
    order = np.argsort(s, kind="stable")
    groups = np.array_split(order, n_bins)

    pred, obs, sizes = [], [], []
    for g in groups:
        if len(g) == 0:
            continue
        times, surv = kaplan_meier(duration[g], event[g])
        obs.append(float(_step_lookup(times, surv, np.array([t]))[0]))
        pred.append(float(s[g].mean()))
        sizes.append(len(g))

    pred_a, obs_a, w = np.array(pred), np.array(obs), np.array(sizes, dtype=float)
    mae = float(np.average(np.abs(pred_a - obs_a), weights=w))

    # Weighted least squares of observed on predicted. Degenerate when every bin
    # has the same prediction, which is exactly what a KM-only model does.
    var = np.average((pred_a - np.average(pred_a, weights=w)) ** 2, weights=w)
    if var < 1e-12:
        slope = float("nan")
    else:
        cov = np.average(
            (pred_a - np.average(pred_a, weights=w)) * (obs_a - np.average(obs_a, weights=w)),
            weights=w,
        )
        slope = float(cov / var)

    return {
        "predicted": pred_a,
        "observed": obs_a,
        "bin_sizes": w,
        "mean_abs_error": mae,
        "slope": slope,
    }
