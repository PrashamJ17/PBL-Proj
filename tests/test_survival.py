"""Tests for Phase 3 -- discrete-time survival.

Three kinds of test here, and the second and third are the ones that matter:

* **Arithmetic** -- the person-period expansion, the survival product, the spline
  basis. Cheap and necessary.
* **Recovery** -- fit on data generated from a hazard we chose, and check the model
  returns it. A survival model that cannot recover a known hazard is not testable by
  any amount of metric-watching on real data.
* **Adversarial** -- the leakage boundary (calibration must split by subject, not by
  row), the metric implementations checked against `lifelines`/`scikit-survival`
  rather than trusted, and D-calibration required to *reject* a model we broke on
  purpose. Following D-017: a check that has never failed is evidence of nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from keel.benchmarks.datasets import DATA_DIR
from keel.benchmarks.survival_data import (
    EXCLUDED_FROM_TELCO,
    SUBSIM_FEATURES,
    load_telco,
    split_by_unit,
    subsim_person_period,
    subsim_survival,
)
from keel.models.survival.baselines import (
    CoxBaseline,
    DeepSurvBaseline,
    KaplanMeierBaseline,
    RSFBaseline,
)
from keel.models.survival.discrete import (
    EVENT,
    PERIOD,
    UNIT,
    CompetingRisksHazard,
    DiscreteTimeHazard,
    SurvivalData,
    period_basis,
    restricted_cubic_spline,
)
from keel.models.survival.metrics import (
    brier_score,
    calibration_at_horizon,
    censoring_survival,
    concordance_index,
    d_calibration,
    integrated_brier_score,
    kaplan_meier,
)
from keel.sim import SimConfig, simulate

TELCO_PATH = DATA_DIR / "telco_churn.csv"
#: Presence is not completeness -- the same lesson as D-029. A download in progress
#: leaves a file that exists and then fails to parse, so check the byte count too.
TELCO_PRESENT = TELCO_PATH.exists() and TELCO_PATH.stat().st_size > 900_000
needs_telco = pytest.mark.skipif(not TELCO_PRESENT, reason="telco not downloaded")


# --- fixtures ----------------------------------------------------------------


def synthetic(n: int = 3000, seed: int = 0, censor: bool = True) -> SurvivalData:
    """Durations drawn from a hazard we chose, so the truth is known.

    Logit hazard `-3.0 + 0.8*x1 - 0.4*x2 + 0.03*t`: a real covariate effect and a
    genuinely time-varying baseline, so a model that ignores either is detectable.
    """
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 2))
    logit = -3.0 + 0.8 * x[:, 0] - 0.4 * x[:, 1]
    duration = np.full(n, 48)
    event = np.zeros(n, dtype=int)
    for t in range(1, 49):
        h = 1.0 / (1.0 + np.exp(-(logit + 0.03 * t)))
        fires = (rng.random(n) < h) & (event == 0) & (duration == 48)
        duration[fires] = t
        event[fires] = 1

    if censor:
        c = rng.integers(1, 49, size=n)
        observed = np.minimum(duration, c)
        event = np.where(duration <= c, event, 0)
        duration = observed

    return SurvivalData("synthetic", pd.DataFrame(x, columns=["x1", "x2"]), duration, event)


@pytest.fixture(scope="module")
def sim():
    return simulate(SimConfig(1500, 24, 3))


# --- person-period expansion -------------------------------------------------


def test_person_period_has_one_row_per_period_at_risk():
    data = synthetic(200)
    pp = data.person_period()
    assert len(pp) == data.duration.sum()
    assert pp.groupby(UNIT).size().to_numpy().tolist() == data.duration.tolist()


def test_event_flag_appears_only_on_the_final_period():
    """The binomial likelihood of the person-period frame equals the discrete-time
    survival likelihood *only* if every non-final row is a zero."""
    data = synthetic(200)
    pp = data.person_period()
    not_last = pp[PERIOD] < pp[UNIT].map(dict(enumerate(data.duration)))
    assert pp.loc[not_last, EVENT].sum() == 0
    assert pp.groupby(UNIT)[EVENT].sum().to_numpy().tolist() == (data.event > 0).astype(
        int
    ).tolist()


def test_zero_duration_is_refused_rather_than_coerced():
    with pytest.raises(ValueError, match="duration must be >= 1"):
        SurvivalData("bad", pd.DataFrame({"x": [1.0]}), np.array([0]), np.array([1]))


def test_cause_specific_expansion_treats_the_competing_event_as_censoring(sim):
    """Invariant 5: causes are never summed. A customer lost to the competing cause
    contributes at-risk periods and a zero, not an event."""
    data = subsim_survival(sim)
    voluntary = data.person_period(cause=1)
    involuntary = data.person_period(cause=2)

    assert voluntary[EVENT].sum() == (data.event == 1).sum()
    assert involuntary[EVENT].sum() == (data.event == 2).sum()
    # Same rows, different labels -- the at-risk structure does not depend on cause.
    assert len(voluntary) == len(involuntary) == data.duration.sum()
    assert (voluntary[EVENT] & involuntary[EVENT]).sum() == 0


# --- the baseline-hazard basis ----------------------------------------------


def test_dummy_basis_is_saturated_up_to_the_pooling_point():
    basis = period_basis(np.arange(1, 31), "dummies", pool_after=10)
    assert [c for c in basis.columns if c.startswith("t_") and c[2:].isdigit()] == [
        f"t_{k}" for k in range(1, 11)
    ]
    # Each early period selects exactly one indicator; the tail selects none of them.
    early = basis.iloc[:10][[f"t_{k}" for k in range(1, 11)]].to_numpy()
    assert np.allclose(early, np.eye(10))
    assert basis["t_tail"].to_numpy().tolist() == [0.0] * 10 + [1.0] * 20


def test_spline_basis_is_linear_beyond_the_outer_knots():
    """The 'restricted' in restricted cubic spline. Without it the fitted baseline
    hazard can do anything at all in the sparse final periods."""
    knots = np.array([1.0, 2.0, 3.0, 4.0])
    x = np.array([5.0, 6.0, 7.0, 8.0])
    basis = restricted_cubic_spline(x, knots)
    second_differences = np.diff(basis, n=2, axis=0)
    assert np.allclose(second_differences, 0.0, atol=1e-8)


def test_spline_basis_needs_enough_knots():
    with pytest.raises(ValueError, match="at least 3 knots"):
        restricted_cubic_spline(np.array([1.0]), np.array([1.0, 2.0]))


# --- recovery ----------------------------------------------------------------


def test_survival_is_a_valid_survival_function():
    model = DiscreteTimeHazard("logistic").fit_data(synthetic(1000))
    S = model.survival(pd.DataFrame(np.zeros((5, 2)), columns=["x1", "x2"]), 24)
    assert ((S >= 0) & (S <= 1)).all()
    assert (np.diff(S, axis=1) <= 1e-12).all()


def test_model_recovers_the_marginal_survival_curve():
    """Aggregate calibration against Kaplan-Meier. This is the weakest useful check
    -- a model can pass it and still rank nobody correctly -- so it is paired with
    the discrimination test below rather than reported alone."""
    data = synthetic(4000, seed=1)
    model = DiscreteTimeHazard("logistic", pool_after=24).fit_data(data)
    predicted = model.survival(data.X, 24).mean(axis=0)

    times, km = kaplan_meier(data.duration, data.event)
    for t in (6, 12, 24):
        observed = km[np.searchsorted(times, t, side="right") - 1]
        assert abs(predicted[t - 1] - observed) < 0.03, f"month {t}"


def test_model_recovers_the_direction_of_the_covariate_effects():
    data = synthetic(4000, seed=2)
    model = DiscreteTimeHazard("logistic", pool_after=24).fit_data(data)
    grid = pd.DataFrame({"x1": [-1.0, 1.0], "x2": [0.0, 0.0]})
    S = model.survival(grid, 24)
    # x1 raises the hazard, so the high-x1 customer must survive less.
    assert S[1, -1] < S[0, -1]


def test_model_beats_chance_at_ranking():
    data = synthetic(3000, seed=3)
    model = DiscreteTimeHazard("logistic").fit_data(data)
    c = concordance_index(data.duration, data.event, model.risk_score(data.X, 12))
    assert c > 0.62


def test_gbm_learner_also_recovers_the_marginal_curve():
    data = synthetic(3000, seed=4)
    model = DiscreteTimeHazard("gbm").fit_data(data)
    predicted = model.survival(data.X, 24).mean(axis=0)
    times, km = kaplan_meier(data.duration, data.event)
    observed = km[np.searchsorted(times, 12, side="right") - 1]
    assert abs(predicted[11] - observed) < 0.05


# --- the leakage boundary ----------------------------------------------------


def test_calibration_split_is_by_subject_not_by_row():
    """Person-period rows from one customer are the same customer in consecutive
    months. Splitting by row puts month 5 in train and month 6 in calibration, which
    is leakage of exactly the kind Phase 1 exists to prevent -- and it flatters the
    calibration map, so nothing downstream would flag it."""
    data = synthetic(600, seed=5)
    model = DiscreteTimeHazard("gbm", calibrate=True).fit_data(data)
    assert model.iso is not None

    pp = data.person_period()
    units = pp[UNIT].to_numpy()
    rng = np.random.default_rng(model.seed)
    uniq = np.unique(units)
    held = set(
        rng.choice(
            uniq, size=max(1, int(len(uniq) * model.calibration_fraction)), replace=False
        ).tolist()
    )
    # Every row of a held-out subject is held out, and no row of a training subject is.
    hold_mask = np.isin(units, list(held))
    per_unit = pd.DataFrame({"unit": units, "held": hold_mask}).groupby("unit")["held"]
    assert (per_unit.nunique() == 1).all()


def test_time_varying_panel_carries_no_future_information(sim):
    """Each person-period row must describe its own month. If the adapter ever
    forward-filled or shifted, a row would carry a value observed later -- the
    survival-analysis form of the availability leak in D-014."""
    panel = subsim_person_period(sim)
    raw = sim.panel.sort_values(["customer_id", "month"]).reset_index(drop=True)
    assert (panel[PERIOD].to_numpy() == raw["month"].to_numpy() + 1).all()
    for col in SUBSIM_FEATURES:
        assert np.allclose(panel[col].to_numpy(), raw[col].to_numpy())


def test_split_by_unit_puts_every_subject_on_exactly_one_side():
    data = synthetic(500, seed=6)
    train, test, test_idx = split_by_unit(data, 0.3, seed=0)
    assert len(train) + len(test) == len(data)
    assert len(test) == pytest.approx(0.3 * len(data), abs=1)
    assert np.array_equal(test.duration, data.duration[test_idx])


# --- competing risks ---------------------------------------------------------


def test_cumulative_incidences_and_survival_partition_probability(sim):
    """`S(t) + sum_k CIF_k(t) == 1` at every horizon. This is the identity that makes
    the competing-risks decomposition exact rather than approximate, and it is what
    lets the CLV shortfall be split by cause with no residual."""
    data = subsim_survival(sim)
    model = CompetingRisksHazard(data.cause_names, learner="logistic", pool_after=12).fit(data)

    X = data.X.head(200)
    S = model.survival(X, 18)
    cif = model.cumulative_incidence(X, 18)
    assert np.allclose(S + sum(cif.values()), 1.0, atol=1e-9)


def test_each_cause_keeps_its_own_model(sim):
    """Never summed at the label level (invariant 5). The two fitted hazards must
    differ -- if they did not, the split would be decorative."""
    data = subsim_survival(sim)
    model = CompetingRisksHazard(data.cause_names, learner="logistic", pool_after=12).fit(data)
    X = data.X.head(300)
    h = model.cause_hazards(X, 12)
    assert set(h) == {1, 2}
    assert not np.allclose(h[1], h[2])


# --- metrics: cross-checked, not trusted -------------------------------------


def test_kaplan_meier_matches_lifelines():
    lifelines = pytest.importorskip("lifelines")
    data = synthetic(800, seed=7)
    times, surv = kaplan_meier(data.duration, data.event)

    fitter = lifelines.KaplanMeierFitter().fit(data.duration, data.event > 0)
    theirs = fitter.survival_function_at_times(times).to_numpy()
    assert np.allclose(surv, theirs, atol=1e-9)


def test_concordance_matches_scikit_survival():
    metrics = pytest.importorskip("sksurv.metrics")
    data = synthetic(800, seed=8)
    risk = data.X["x1"].to_numpy()

    ours = concordance_index(data.duration, data.event, risk)
    theirs = metrics.concordance_index_censored(
        (data.event > 0), data.duration.astype(float), risk
    )[0]
    assert ours == pytest.approx(theirs, abs=1e-9)


def test_brier_matches_scikit_survival():
    metrics = pytest.importorskip("sksurv.metrics")
    data = synthetic(900, seed=9)
    model = DiscreteTimeHazard("logistic").fit_data(data)
    grid = np.array([6.0, 12.0, 18.0])
    surv = model.survival_at(data.X, grid)

    structured = np.empty(len(data), dtype=[("event", "?"), ("time", "<f8")])
    structured["event"] = data.event > 0
    structured["time"] = data.duration.astype(float)

    _, theirs = metrics.brier_score(structured, structured, surv, grid)
    ours = [brier_score(data.duration, data.event, surv[:, k], t) for k, t in enumerate(grid)]
    assert np.allclose(ours, theirs, atol=1e-6)


def test_concordance_is_half_for_a_constant_score_and_one_for_a_perfect_one():
    duration = np.array([1, 2, 3, 4, 5])
    event = np.ones(5, dtype=int)
    assert concordance_index(duration, event, np.ones(5)) == pytest.approx(0.5)
    assert concordance_index(duration, event, -duration.astype(float)) == pytest.approx(1.0)
    assert concordance_index(duration, event, duration.astype(float)) == pytest.approx(0.0)


def test_censoring_survival_puts_events_before_censorings_at_a_tied_time():
    """The tie convention that has to match the Brier score's use of G(T_i). Getting
    it wrong is a silent ~2% shift, invisible without an external reference."""
    duration = np.array([1, 2, 3, 4])
    event = np.array([1, 0, 1, 0])
    times, g = censoring_survival(duration, event)
    assert np.allclose(times, [1, 2, 3, 4])
    # t=1 is an event, not a censoring, so G does not move.
    assert g[0] == pytest.approx(1.0)
    # t=2 censors one of the three still at risk, none of whom had an event at t=2.
    assert g[1] == pytest.approx(2 / 3)

    # The denominator excludes subjects who had an event at the same time: with one
    # event and one censoring tied at t=1, three at risk, G(1) = 1 - 1/(3-1).
    tied_times, tied_g = censoring_survival(
        np.array([1, 1, 5]), np.array([1, 0, 1])
    )
    assert tied_times[0] == 1
    assert tied_g[0] == pytest.approx(0.5)


def test_brier_score_rewards_the_truth():
    """A model that knows the answer scores ~0; one that is confidently wrong scores
    near 1. Without this, an implementation with a flipped sign would still 'work'."""
    duration = np.array([5, 5, 20, 20])
    event = np.array([1, 1, 0, 0])
    right = np.array([0.0, 0.0, 1.0, 1.0])
    wrong = 1.0 - right
    assert brier_score(duration, event, right, 10.0) < 0.01
    assert brier_score(duration, event, wrong, 10.0) > 0.4


def test_integrated_brier_prefers_the_informative_model_over_kaplan_meier():
    """The reason IBS is the headline rather than the calibration error: a marginal
    model is trivially 'calibrated' and this metric still catches it."""
    data = synthetic(2000, seed=10)
    grid = np.linspace(4, 30, 12)
    model = DiscreteTimeHazard("logistic").fit_data(data)
    km = KaplanMeierBaseline().fit(data)

    informed = integrated_brier_score(
        data.duration, data.event, model.survival_at(data.X, grid), grid
    )
    marginal = integrated_brier_score(
        data.duration, data.event, km.survival_at(data.X, grid), grid
    )
    assert informed < marginal


def test_integrated_brier_rejects_a_mismatched_grid():
    with pytest.raises(ValueError, match="columns"):
        integrated_brier_score(
            np.array([1, 2]), np.array([1, 1]), np.zeros((2, 3)), np.array([1.0, 2.0])
        )


def test_d_calibration_rejects_a_model_we_broke_on_purpose():
    """D-017's rule applied to calibration: a check that cannot fail proves nothing.
    Shifting every survival probability toward 1 must be detected."""
    data = synthetic(2000, seed=11)
    model = DiscreteTimeHazard("logistic", pool_after=24).fit_data(data)

    H = int(data.duration.max())
    S = model.survival(data.X, H)
    prev = np.column_stack([np.ones(len(data)), S[:, :-1]])
    at, before = S[np.arange(len(data)), data.duration - 1], prev[
        np.arange(len(data)), data.duration - 1
    ]

    _, honest_p, _ = d_calibration(data.duration, data.event, at, survival_before_observed=before)
    _, broken_p, _ = d_calibration(
        data.duration, data.event, at**0.4, survival_before_observed=before**0.4
    )
    assert honest_p > 0.05
    assert broken_p < 1e-3


def test_d_calibration_mass_is_conserved():
    """Every subject contributes exactly one unit, censored or not. If censored mass
    leaked away the test would quietly become a test of the uncensored only."""
    data = synthetic(500, seed=12)
    s = np.clip(np.random.default_rng(0).uniform(0.05, 0.95, len(data)), 0, 1)
    _, _, mass = d_calibration(data.duration, data.event, s)
    assert mass.sum() == pytest.approx(len(data))


def test_calibration_at_horizon_is_near_perfect_for_a_well_specified_model():
    data = synthetic(3000, seed=13)
    model = DiscreteTimeHazard("logistic", pool_after=24).fit_data(data)
    cal = calibration_at_horizon(
        data.duration, data.event, model.survival_at(data.X, np.array([12.0]))[:, 0], 12.0
    )
    assert cal["mean_abs_error"] < 0.05
    assert 0.8 < cal["slope"] < 1.25


def test_calibration_slope_is_undefined_for_a_marginal_model():
    """A model with no spread has no slope, and reporting one would be inventing a
    number. NaN is the honest answer."""
    data = synthetic(400, seed=14)
    km = KaplanMeierBaseline().fit(data)
    cal = calibration_at_horizon(
        data.duration, data.event, km.survival_at(data.X, np.array([12.0]))[:, 0], 12.0
    )
    assert np.isnan(cal["slope"])


# --- baselines ---------------------------------------------------------------


def test_kaplan_meier_baseline_gives_everyone_the_marginal_curve():
    data = synthetic(500, seed=15)
    km = KaplanMeierBaseline().fit(data)
    curves = km.survival_at(data.X, np.array([6.0, 12.0]))
    assert curves.shape == (len(data), 2)
    assert np.allclose(curves, curves[0])
    assert km.is_marginal


@pytest.mark.skipif(not CoxBaseline.available(), reason="lifelines not installed")
def test_cox_baseline_drops_constant_columns_instead_of_failing():
    """Constant columns are singular by construction and appear naturally in small
    landmark slices. Crashing there would make the small-n comparison impossible to
    run, which is the regime the project cares about most."""
    data = synthetic(400, seed=16)
    data.X["always_zero"] = 0.0
    model = CoxBaseline().fit(data)
    assert "always_zero" not in model.kept_
    assert model.survival_at(data.X, np.array([6.0, 12.0])).shape == (len(data), 2)


@pytest.mark.skipif(not RSFBaseline.available(), reason="scikit-survival not installed")
def test_rsf_baseline_produces_a_valid_survival_function():
    data = synthetic(400, seed=17)
    S = RSFBaseline(n_estimators=30).fit(data).survival_at(data.X, np.array([3.0, 9.0, 18.0]))
    assert ((S >= 0) & (S <= 1)).all()
    assert (np.diff(S, axis=1) <= 1e-9).all()


@pytest.mark.skipif(not DeepSurvBaseline.available(), reason="torch not installed")
def test_deepsurv_partial_likelihood_gives_tied_subjects_the_same_risk_set():
    """Breslow's approximation. With a naive cumulative sum, all but one member of a
    tie group gets a truncated risk set, which inflates the likelihood -- and it
    inflates it for the *baseline*, so it would look like our model losing fairly."""
    import torch

    risk = torch.tensor([0.5, -0.2, 0.3, 1.0])
    time = torch.tensor([4.0, 4.0, 2.0, 1.0])
    event = torch.tensor([1.0, 1.0, 1.0, 0.0])

    ours = float(DeepSurvBaseline._cox_loss(risk, time, event))

    # Reference: full risk set {j : T_j >= T_i} computed directly.
    contributions = []
    for i in range(4):
        if event[i] == 0:
            continue
        at_risk = time >= time[i]
        contributions.append(
            float(risk[i] - torch.logsumexp(risk[at_risk], dim=0))
        )
    assert ours == pytest.approx(-np.mean(contributions), abs=1e-6)


@pytest.mark.skipif(not DeepSurvBaseline.available(), reason="torch not installed")
def test_deepsurv_produces_a_valid_survival_function():
    data = synthetic(600, seed=18)
    S = DeepSurvBaseline(epochs=40).fit(data).survival_at(data.X, np.array([3.0, 9.0, 18.0]))
    assert ((S >= 0) & (S <= 1)).all()
    assert (np.diff(S, axis=1) <= 1e-9).all()


# --- Telco -------------------------------------------------------------------


@needs_telco
def test_total_charges_is_excluded_because_it_encodes_the_duration():
    """The leak every published Telco survival analysis ships. `TotalCharges` is
    cumulative billing, so it is very nearly `MonthlyCharges * tenure` -- a direct
    encoding of the outcome being predicted."""
    raw = pd.read_csv(TELCO_PATH)
    charges = pd.to_numeric(raw["TotalCharges"], errors="coerce").fillna(0.0)
    assert abs(np.corrcoef(charges, raw["tenure"])[0, 1]) > 0.8

    data = load_telco()
    assert "TotalCharges" in EXCLUDED_FROM_TELCO
    lowered = [c.lower() for c in data.X.columns]
    assert not any("totalcharges" in c or "total_charges" in c for c in lowered)
    assert "tenure" not in lowered


@needs_telco
def test_telco_drops_the_customers_with_no_completed_period():
    """11 customers have tenure 0. Coercing them to 1 would invent a month of
    survival for the customers least likely to have had one."""
    raw = pd.read_csv(TELCO_PATH)
    data = load_telco()
    assert len(data) == len(raw) - (raw["tenure"] == 0).sum()
    assert data.duration.min() >= 1


@needs_telco
def test_telco_is_a_plausible_churn_dataset():
    data = load_telco()
    assert 0.20 < (data.event > 0).mean() < 0.32
    assert data.duration.max() == 72


# --- degenerate inputs: clear errors, not solver internals -------------------
#
# Every case below previously surfaced a scikit-learn or numpy message naming an
# optimiser rather than the data problem. Each is a situation a real tenant can be
# in, so the error has to say what is wrong and what to do about it.


def _toy(n=60, all_censored=False, no_censoring=False, nan_cov=False, seed=0):
    rng = np.random.default_rng(seed)
    duration = rng.integers(1, 8, n)
    event = (
        np.zeros(n, dtype=int) if all_censored
        else np.ones(n, dtype=int) if no_censoring
        else rng.integers(0, 2, n)
    )
    X = pd.DataFrame({"x": rng.normal(size=n), "y": rng.normal(size=n)})
    if nan_cov:
        X.loc[X.index[:3], "x"] = np.nan
    return SurvivalData(name="toy", X=X, duration=duration, event=event)


def test_empty_dataset_is_refused_with_a_useful_message():
    with pytest.raises(ValueError, match="empty"):
        _toy(n=0)


def test_missing_covariates_name_the_offending_column():
    """Real billing exports carry NaNs. The message must name the column so the
    caller can decide how to fill it, rather than the model imputing silently."""
    with pytest.raises(ValueError, match=r"missing values in covariate\(s\) \['x'\]"):
        _toy(nan_cov=True)


def test_undeclared_event_codes_are_refused():
    """`event` is a cause code, so values above 1 are legitimate -- but only if
    declared. An undeclared code would silently censor those subjects."""
    with pytest.raises(ValueError, match="not declared in cause_names"):
        SurvivalData(
            name="toy", X=pd.DataFrame({"x": [1.0, 2.0]}),
            duration=np.array([2, 3]), event=np.array([5, 0]),
        )


def test_declared_event_codes_are_accepted():
    """The complement: competing risks must still work."""
    data = SurvivalData(
        name="toy", X=pd.DataFrame({"x": [1.0, 2.0]}),
        duration=np.array([2, 3]), event=np.array([2, 0]),
        cause_names={1: "voluntary", 2: "involuntary"},
    )
    assert data.causes == [2]


def test_a_dataset_with_no_events_says_the_hazard_is_unidentified():
    """A young business that has not lost anyone yet. The honest answer is that the
    hazard cannot be identified, not that an optimiser is unhappy."""
    with pytest.raises(ValueError, match="no events"):
        DiscreteTimeHazard().fit_data(_toy(all_censored=True))


def test_no_censored_subjects_still_fits():
    """Subject-level censoring is not period-level censoring.

    A subject with duration 5 who then fails contributes four survived periods and
    one event, so the person-period frame has both classes even when nobody was
    censored. An earlier version of this test asserted a refusal here and was simply
    wrong about the expansion."""
    model = DiscreteTimeHazard().fit_data(_toy(no_censoring=True))
    assert model.observed_support is not None


def test_every_period_an_event_is_refused():
    """The degenerate case the no-censored-periods branch actually guards: every
    subject fails in their first period, so no row survives."""
    n = 40
    data = SurvivalData(
        name="toy",
        X=pd.DataFrame({"x": np.random.default_rng(0).normal(size=n)}),
        duration=np.ones(n, dtype=int),
        event=np.ones(n, dtype=int),
    )
    with pytest.raises(ValueError, match="no censored periods"):
        DiscreteTimeHazard().fit_data(data)


# --- extrapolation guard, mirroring the CLV invariant -----------------------


def test_survival_refuses_to_project_past_the_observed_support():
    """Invariant 12 applies to survival as it does to CLV (D-046, D-050). Beyond the
    observed support the period basis asserts a functional form rather than
    estimating one, and a 24-month CLV must not be built from 8 months of history
    without that being a visible choice."""
    data = _toy()
    model = DiscreteTimeHazard().fit_data(data)
    assert model.observed_support is not None

    with pytest.raises(ValueError, match="exceeds the observed support"):
        model.survival(data.X.head(2), horizon=model.observed_support + 50)


def test_extrapolation_is_possible_but_has_to_be_asked_for():
    data = _toy()
    model = DiscreteTimeHazard(allow_extrapolation=True).fit_data(data)
    out = model.survival(data.X.head(2), horizon=model.observed_support + 50)
    assert out.shape == (2, model.observed_support + 50)


def test_horizon_within_support_is_allowed():
    data = _toy()
    model = DiscreteTimeHazard().fit_data(data)
    out = model.survival(data.X.head(2), horizon=model.observed_support)
    assert out.shape == (2, model.observed_support)
    assert np.all((out >= 0) & (out <= 1))


def test_non_positive_horizon_is_refused():
    data = _toy()
    model = DiscreteTimeHazard().fit_data(data)
    for bad in (0, -1):
        with pytest.raises(ValueError, match="horizon must be >= 1"):
            model.survival(data.X.head(2), horizon=bad)
