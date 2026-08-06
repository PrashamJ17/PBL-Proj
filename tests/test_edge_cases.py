"""Edge cases and boundary conditions.

Degenerate inputs must return empty-but-well-formed results rather than raising or,
worse, silently returning something wrong. A simulator that crashes on n=1 will crash
in the middle of a hierarchical fit where each tenant is small -- which is precisely
the regime this whole project targets.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from keel.experiments.kill_test import budget_curve, run, train_churn_model
from keel.sim import SimConfig, simulate
from keel.sim.counterfactual import LADDER, potential_outcomes
from keel.sim.hazard import expit

BASE = SimConfig(n_customers=400, n_months=12, seed=7)


# --- degenerate populations -------------------------------------------------


def test_zero_customers():
    r = simulate(replace(BASE, n_customers=0))
    assert len(r.panel) == 0
    assert len(r.customers) == 0
    assert list(r.panel.columns), "empty panel must still carry its schema"


def test_zero_months():
    r = simulate(replace(BASE, n_months=0))
    assert len(r.panel) == 0
    assert list(r.panel.columns)


def test_single_customer():
    r = simulate(replace(BASE, n_customers=1, n_months=6))
    assert len(r.customers) == 1
    assert len(r.panel) >= 1


def test_single_month():
    r = simulate(replace(BASE, n_months=1))
    assert set(r.panel["month"]) == {0}


def test_potential_outcomes_on_empty_snapshot():
    """Asking for a decision point beyond the simulation must not raise."""
    r = simulate(replace(BASE, n_months=6))
    po = potential_outcomes(r, decision_month=99, horizon=6)
    assert po.empty
    assert "tau_true" in po.columns


def test_potential_outcomes_single_customer():
    r = simulate(replace(BASE, n_customers=1, n_months=12))
    po = potential_outcomes(r, decision_month=2, horizon=6)
    assert len(po) <= 1


# --- boundary parameter values ----------------------------------------------


@pytest.mark.parametrize("corr", [0.0, 0.5, 0.95, -0.5])
def test_correlation_boundaries(corr):
    """attention/engagement correlation across its usable range, including zero
    (independent latents) and negative (inverted)."""
    r = simulate(replace(BASE, attention_engagement_corr=corr))
    assert len(r.panel) > 0
    assert np.isfinite(r.latents.attention).all()
    assert ((r.latents.attention >= 0) & (r.latents.attention <= 1)).all()


def test_extreme_correlation_is_clipped():
    """rho=1.0 must not produce NaN via sqrt(1-rho^2)."""
    r = simulate(replace(BASE, attention_engagement_corr=1.0))
    assert np.isfinite(r.latents.attention).all()


@pytest.mark.parametrize("salience", [0.0, 1.8, 6.0])
@pytest.mark.parametrize("saveability", [0.0, -2.0, -8.0])
def test_extreme_intervention_scales(salience, saveability):
    """tau must stay a valid probability difference under any scale."""
    cfg = replace(
        BASE,
        intervention=replace(
            BASE.intervention, salience_scale=salience, saveability_scale=saveability
        ),
    )
    po = potential_outcomes(simulate(cfg), decision_month=3, horizon=6)
    if po.empty:
        pytest.skip("no eligible customers")
    assert (po["tau_true"] >= -1.0).all() and (po["tau_true"] <= 1.0).all()
    assert np.isfinite(po["tau_true"]).all()


def test_zero_salience_makes_offer_purely_beneficial():
    """With no salience penalty there can be no sleeping dogs -- tau <= 0 always.

    A direct check that the two forces are wired up with the right signs."""
    cfg = replace(BASE, intervention=replace(BASE.intervention, salience_scale=0.0))
    po = potential_outcomes(simulate(cfg), decision_month=3, horizon=6)
    assert (po["tau_true"] <= 1e-9).all()
    assert "sleeping_dog" not in set(po["quadrant"])


def test_zero_saveability_makes_offer_purely_harmful():
    """The mirror image: no protective effect means tau >= 0 always."""
    cfg = replace(BASE, intervention=replace(BASE.intervention, saveability_scale=0.0))
    po = potential_outcomes(simulate(cfg), decision_month=3, horizon=6)
    assert (po["tau_true"] >= -1e-9).all()
    assert "persuadable" not in set(po["quadrant"])


def test_extreme_hazard_intercepts():
    """Nobody churns voluntarily / everybody does. Both must be handled."""
    never = simulate(replace(BASE, hazard=replace(BASE.hazard, intercept=-20.0)))
    assert never.panel["churn_voluntary"].sum() == 0

    always = simulate(replace(BASE, hazard=replace(BASE.hazard, intercept=20.0)))
    assert always.customers["censored"].sum() == 0


def test_involuntary_churn_survives_zero_voluntary_hazard():
    """With the voluntary hazard switched off, customers must STILL churn from
    failed payments.

    This is D-001 made testable: the two processes are genuinely independent. A
    model that treats churn as one outcome would be blind to everything this test
    exercises -- which is 20-40% of real churn.
    """
    cfg = replace(BASE, hazard=replace(BASE.hazard, intercept=-20.0))
    r = simulate(cfg)
    assert r.panel["churn_voluntary"].sum() == 0
    assert r.panel["churn_involuntary"].sum() > 0
    assert not r.customers["censored"].all()
    assert set(r.customers["churn_kind"].unique()) <= {"none", "involuntary"}


def test_no_churn_at_all_when_both_processes_disabled():
    cfg = replace(
        BASE,
        hazard=replace(BASE.hazard, intercept=-20.0),
        payments=replace(BASE.payments, monthly_failure_rate=0.0),
    )
    r = simulate(cfg)
    assert r.customers["censored"].all()


def test_zero_payment_failures():
    cfg = replace(BASE, payments=replace(BASE.payments, monthly_failure_rate=0.0))
    r = simulate(cfg)
    assert r.panel["churn_involuntary"].sum() == 0


def test_full_payment_failure_with_no_recovery():
    cfg = replace(
        BASE,
        payments=replace(BASE.payments, monthly_failure_rate=1.0, passive_recovery_rate=0.0),
    )
    r = simulate(cfg)
    assert (r.customers["churn_kind"] == "involuntary").all()


# --- numerical invariants ---------------------------------------------------


def test_expit_is_stable_at_extremes():
    x = np.array([-1e4, -700.0, -50.0, 0.0, 50.0, 700.0, 1e4])
    y = expit(x)
    assert np.isfinite(y).all()
    assert ((y >= 0.0) & (y <= 1.0)).all()
    assert y[0] == pytest.approx(0.0, abs=1e-12)
    assert y[-1] == pytest.approx(1.0, abs=1e-12)


def test_probabilities_are_in_range():
    po = potential_outcomes(simulate(BASE), decision_month=3, horizon=6)
    for col in ("p_churn_control", "p_churn_treated"):
        assert ((po[col] >= 0) & (po[col] <= 1)).all()


def test_tau_equals_treated_minus_control():
    po = potential_outcomes(simulate(BASE), decision_month=3, horizon=6)
    expected = po["p_churn_treated"] - po["p_churn_control"]
    assert np.allclose(po["tau_true"], expected)


def test_clv_is_positive_and_finite():
    po = potential_outcomes(simulate(BASE), decision_month=3, horizon=6)
    assert (po["clv"] > 0).all()
    assert np.isfinite(po["clv"]).all()


def test_common_random_numbers_pair_the_arms():
    """Under CRN, a customer whose treated hazard is uniformly lower can never
    churn in the treated arm while surviving in the control arm.

    This is the property that makes the paired outcomes valid; if it broke, the
    realised uplift estimates would be pure noise."""
    cfg = replace(BASE, intervention=replace(BASE.intervention, salience_scale=0.0))
    po = potential_outcomes(simulate(cfg), decision_month=3, horizon=6)
    # salience=0 => treated hazard <= control hazard for everyone => no one is harmed
    assert ((po["y1"] == 1) & (po["y0"] == 0)).sum() == 0


def test_horizon_one_is_valid():
    po = potential_outcomes(simulate(BASE), decision_month=3, horizon=1)
    assert len(po) > 0
    assert np.isfinite(po["tau_true"]).all()


@pytest.mark.parametrize("offer", LADDER, ids=[o.name for o in LADDER])
def test_every_ladder_rung_produces_valid_outcomes(offer):
    po = potential_outcomes(simulate(BASE), decision_month=3, horizon=6, offer=offer)
    assert np.isfinite(po["tau_true"]).all()
    assert (po["offer_cost"] >= 0).all()


def test_cheaper_rungs_cost_less():
    """The ladder must actually be ordered by cost, or the policy layer's
    cheapest-effective-intervention logic is meaningless."""
    sim = simulate(BASE)
    costs = {
        o.name: potential_outcomes(sim, 3, 6, offer=o)["offer_cost"].mean() for o in LADDER
    }
    assert costs["feature_nudge"] < costs["discount_20_3mo"]
    assert costs["discount_20_3mo"] < costs["discount_40_6mo"]


# --- kill test robustness ---------------------------------------------------


def test_churn_model_handles_single_class_training_data():
    """If nobody churned before the decision month, training must degrade
    gracefully rather than raise."""
    cfg = replace(BASE, hazard=replace(BASE.hazard, intercept=-20.0))
    scores, auc = train_churn_model(simulate(cfg), decision_month=3)
    assert np.isfinite(scores).all()


def test_kill_test_runs_on_small_population():
    """n=300 is the regime this project actually targets."""
    sim = simulate(replace(BASE, n_customers=300, n_months=18))
    results, po, _ = run(sim, decision_month=6, horizon=6, budget_fraction=0.2)
    assert len(results) == 6
    assert all(np.isfinite(r.expected_value) for r in results)


def test_do_nothing_is_exactly_zero():
    """The baseline must be zero by construction, not approximately."""
    sim = simulate(replace(BASE, n_customers=300, n_months=18))
    results, _, _ = run(sim, decision_month=6, horizon=6)
    do_nothing = next(r for r in results if r.name == "do_nothing")
    assert do_nothing.expected_value == 0.0
    assert do_nothing.n_treated == 0


def test_zero_budget_yields_zero_value():
    sim = simulate(replace(BASE, n_customers=300, n_months=18))
    curve = budget_curve(sim, decision_month=6, horizon=6)
    first = curve.iloc[0]
    assert first["budget_fraction"] == 0.0
    assert first["churn_score"] == 0.0 and first["oracle_uplift"] == 0.0


def test_full_budget_equals_treat_all_for_every_ranking():
    """At 100% budget every ranking treats everyone, so they must all agree."""
    sim = simulate(replace(BASE, n_customers=300, n_months=18))
    curve = budget_curve(sim, decision_month=6, horizon=6)
    last = curve.iloc[-1]
    assert last["churn_score"] == pytest.approx(last["oracle_uplift"], rel=1e-9)
    assert last["churn_score"] == pytest.approx(last["random"], rel=1e-9)


def test_oracle_abstention_never_loses_money():
    """Treating only positive-expected-value customers cannot lose money in
    expectation. If this ever fails, the value calculation is wrong."""
    sim = simulate(replace(BASE, n_customers=800, n_months=18))
    results, _, _ = run(sim, decision_month=6, horizon=6)
    oracle = next(r for r in results if r.name == "oracle_uplift_abstain")
    assert oracle.expected_value >= 0.0


def test_oracle_abstention_harms_nobody():
    sim = simulate(replace(BASE, n_customers=800, n_months=18))
    _, po, _ = run(sim, decision_month=6, horizon=6)
    treated = po[po["value_of_treating"] > 0]
    assert (treated["tau_true"] <= 0).all(), "abstention policy selected a sleeping dog"
