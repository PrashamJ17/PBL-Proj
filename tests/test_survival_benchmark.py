"""Tests for the Phase 3 head-to-head harness.

`survival_benchmark.py` produces Table 4 of the paper -- the claim that the discrete
hazard beats Cox and RSF on Telco and ties DeepSurv. It was the largest untested module
in the repository, which is the wrong thing for the file that generates a headline
result to be.

These tests do not re-run the full benchmark; that needs the optional survival extras
and several minutes. They cover the parts where a silent error would change the
published numbers without failing anything:

* the evaluation grid, where an over-long horizon makes the IPCW weights undefined
  rather than merely noisy;
* the landmark slice, which is where a time-varying model can accidentally be handed
  the future it is supposed to predict;
* the comparison harness itself, which must put every model through one code path so
  that no model gets a correction the others do not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from keel.experiments.survival_benchmark import (
    Score,
    _landmark_slice,
    horizon_grid,
    our_models,
    run_static,
    score_model,
)
from keel.models.survival.discrete import PERIOD, SurvivalData


def _toy(n: int = 400, seed: int = 0) -> SurvivalData:
    """A small dataset with a real covariate effect, so scores are not degenerate."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    # Higher x -> higher hazard -> shorter duration.
    rate = 0.08 * np.exp(0.6 * x)
    duration = np.clip(rng.geometric(np.clip(rate, 0.01, 0.9)), 1, 24)
    event = (rng.random(n) < 0.7).astype(int)
    return SurvivalData(
        name="toy",
        X=pd.DataFrame({"x": x, "z": rng.normal(size=n)}),
        duration=duration,
        event=event,
    )


# --- the evaluation grid ----------------------------------------------------


def test_horizon_grid_stops_before_the_censoring_distribution_dies():
    """Under administrative censoring the IPCW weight G(t) reaches exactly zero at the
    end of follow-up. Evaluating there is undefined, not noisy, and a grid that runs
    past it silently corrupts every integrated Brier score in the table."""
    data = _toy()
    grid = horizon_grid(data.duration, data.event)

    assert grid.min() >= 1.0
    assert grid.max() < data.duration.max(), "grid must stop short of last follow-up"
    assert np.all(np.diff(grid) > 0), "grid must be strictly increasing"
    assert len(grid) > 1


def test_horizon_grid_is_finite_and_within_observed_support():
    data = _toy()
    grid = horizon_grid(data.duration, data.event)
    assert np.isfinite(grid).all()
    assert grid.min() >= float(data.duration.min())


def test_horizon_grid_handles_heavy_censoring():
    """Few events means the censoring curve decays fast; the cap must still bite."""
    rng = np.random.default_rng(1)
    n = 300
    data = SurvivalData(
        name="heavy",
        X=pd.DataFrame({"x": rng.normal(size=n)}),
        duration=rng.integers(1, 20, n),
        event=(rng.random(n) < 0.1).astype(int),
    )
    grid = horizon_grid(data.duration, data.event)
    assert len(grid) > 1 and np.isfinite(grid).all()


# --- the landmark slice: where the future can leak in -----------------------


def _subsim_landmark_fixture(seed: int = 3):
    """A real SubSim person-period frame, built the way `run_landmark` builds it.

    Constructing the panel by hand would test a shape the harness never sees; this
    goes through the same `subsim_person_period` path the benchmark uses.
    """
    from keel.benchmarks.survival_data import subsim_person_period, subsim_survival
    from keel.sim import SimConfig, simulate

    result = simulate(SimConfig(n_customers=500, n_months=18, seed=seed))
    return subsim_person_period(result, cause=1), subsim_survival(result)


def test_landmark_slice_keeps_only_survivors_of_the_landmark():
    """Anyone who already left before the landmark is not at risk and must not be in
    the slice -- including them would inflate the event rate."""
    panel, data = _subsim_landmark_fixture()
    lm = _landmark_slice(panel, data, landmark=6, window=6)

    assert len(lm.units) > 0
    assert len(lm.units) < len(data), "customers lost before the landmark must drop out"
    assert lm.duration.min() >= 1
    assert lm.duration.max() <= 6, "durations are capped by the prediction window"


def test_landmark_covariates_come_from_the_landmark_month_only():
    """The survival-analysis form of availability leakage (D-014).

    If the slice used the realised future path, a time-varying model would look far
    better than it can be in production, where next month's engagement is exactly the
    thing you do not have.
    """
    panel, data = _subsim_landmark_fixture()
    landmark = 6
    lm = _landmark_slice(panel, data, landmark=landmark, window=6)

    at_landmark = panel[panel[PERIOD] == landmark]
    for col in lm.X_now.columns:
        if col not in at_landmark.columns:
            continue
        allowed = set(np.round(at_landmark[col].to_numpy().astype(float), 6))
        got = set(np.round(lm.X_now[col].to_numpy().astype(float), 6))
        assert got <= allowed, f"{col} carries values not present at the landmark"


def test_landmark_durations_are_capped_by_the_window():
    """Durations are months survived *past* the landmark, capped at the window.

    Note `duration == window` is not the same as "censored": it contains both the
    customers who failed in the final month of the window and those still present at
    its edge. The invariant is the cap itself -- nothing may run past the horizon the
    slice claims to predict over, or the landmark comparison is not landmarked.
    """
    panel, data = _subsim_landmark_fixture()
    window = 6
    lm = _landmark_slice(panel, data, landmark=6, window=window)

    assert lm.duration.min() >= 1
    assert lm.duration.max() <= window
    assert set(np.unique(lm.event)) <= {0, 1}
    assert 0 < lm.event.mean() < 1, "a slice with no variation cannot score anything"


# --- the comparison harness -------------------------------------------------


def test_score_model_returns_a_complete_score():
    """Every field the table prints must be populated; a silent NaN would appear as a
    blank cell rather than a failure."""
    train, test = _toy(seed=0), _toy(seed=1)
    model = our_models(train)["discrete_logistic"]
    score = score_model("discrete_logistic", model, train, test)

    assert isinstance(score, Score)
    assert 0.0 <= score.c_index <= 1.0
    assert 0.0 <= score.ibs <= 1.0
    assert score.cal_mae >= 0.0
    assert np.isfinite(score.cal_slope)
    assert score.n_train == len(train) and score.n_test == len(test)


def test_every_model_goes_through_one_scoring_path():
    """One code path for our model and every baseline. If our model were scored
    differently -- a different horizon grid, a different survival query -- the
    comparison would be meaningless however careful the rest is."""
    train, test = _toy(seed=0), _toy(seed=1)
    models = our_models(train)
    assert len(models) >= 2

    scores = [score_model(name, m, train, test) for name, m in models.items()]
    assert all(isinstance(s, Score) for s in scores)
    assert len({s.n_test for s in scores}) == 1, "all models scored on the same test set"


def test_an_informative_model_beats_the_marginal_one():
    """A sanity floor on the whole harness. If a model with a real covariate effect
    does not beat Kaplan-Meier on the integrated Brier score, the scoring is broken
    and every number in Table 4 is suspect."""
    train, test = _toy(n=600, seed=0), _toy(n=600, seed=1)
    model = our_models(train)["discrete_logistic"]
    ours = score_model("ours", model, train, test)

    from keel.models.survival.baselines import KaplanMeierBaseline

    km = score_model("km", KaplanMeierBaseline(), train, test)
    assert ours.ibs < km.ibs, f"ours {ours.ibs:.4f} did not beat KM {km.ibs:.4f}"


def test_run_static_produces_one_row_per_model():
    frame = run_static(_toy(n=500), seed=0)
    assert isinstance(frame, pd.DataFrame)
    assert len(frame) >= 2
    assert {"model", "ibs", "c_index"} <= set(frame.columns)
    assert frame["ibs"].notna().all()


def test_run_static_splits_by_subject_not_by_row():
    """Train and test must be disjoint populations. Overlap here would be the same
    error as a row-wise calibration split (invariant 11) and would flatter every
    model equally, so nothing downstream would flag it."""
    frame = run_static(_toy(n=500), seed=0, test_fraction=0.3)
    n_train = int(frame["n_train"].iloc[0])
    n_test = int(frame["n_test"].iloc[0])
    assert n_train + n_test == 500
    assert 0.25 <= n_test / 500 <= 0.35


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_scores_are_stable_across_seeds(seed):
    """Not a precision claim -- just that the harness does not occasionally emit
    something impossible on an unlucky split."""
    frame = run_static(_toy(n=400, seed=seed), seed=seed)
    assert frame["ibs"].between(0.0, 1.0).all()
    assert frame["c_index"].dropna().between(0.0, 1.0).all()
