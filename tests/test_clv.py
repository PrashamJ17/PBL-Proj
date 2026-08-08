"""Tests for Phase 3 -- customer lifetime value.

CLV is arithmetic on top of a survival curve, so most of these are identities. Two
are not, and they are the reason this file exists:

* `test_clv_refuses_to_extrapolate_past_the_observed_support` pins D-046. Extending a
  survival curve past the data is the standard way CLV is computed and it is a
  fabrication -- the model has no evidence there. The guard has to be a hard error,
  not a warning, because a warning in a notebook is a warning nobody reads.
* `test_cause_shortfalls_sum_to_the_total_shortfall` pins the exactness of the
  competing-risks decomposition. If it ever drifts, the voluntary/involuntary split
  in a client report stops adding up to the money actually missing.
"""

from __future__ import annotations

import numpy as np
import pytest

from keel.benchmarks.survival_data import subsim_survival
from keel.models.clv import (
    ExtrapolationError,
    clv,
    expected_remaining_months,
    monthly_discount,
    treatment_value,
    value_at_risk,
    value_shortfall_by_cause,
)
from keel.models.survival.discrete import CompetingRisksHazard
from keel.sim import SimConfig, simulate


@pytest.fixture(scope="module")
def sim():
    return simulate(SimConfig(1200, 24, 5))


# --- discounting -------------------------------------------------------------


def test_monthly_discount_compounds_to_the_annual_rate():
    monthly = monthly_discount(0.12)
    assert (1 + monthly) ** 12 == pytest.approx(1.12)
    # And it is NOT annual/12, which is the shortcut that quietly overstates value.
    assert monthly < 0.12 / 12


def test_zero_discount_is_the_identity():
    assert monthly_discount(0.0) == pytest.approx(0.0)


def test_impossible_discount_rate_is_refused():
    with pytest.raises(ValueError, match="must be > -100%"):
        monthly_discount(-1.5)


# --- the CLV sum -------------------------------------------------------------


def test_certain_survival_gives_the_discounted_annuity():
    survival = np.ones((1, 12))
    expected = sum(100.0 / (1 + monthly_discount(0.12)) ** t for t in range(1, 13))
    assert clv(survival, 100.0, 0.12)[0] == pytest.approx(expected)


def test_undiscounted_certain_survival_is_just_margin_times_horizon():
    assert clv(np.ones((1, 24)), 50.0, 0.0)[0] == pytest.approx(50.0 * 24)


def test_clv_is_monotone_in_survival():
    good = np.full((1, 12), 0.9)
    bad = np.full((1, 12), 0.4)
    assert clv(good, 100.0)[0] > clv(bad, 100.0)[0]


def test_clv_scales_with_margin():
    survival = np.full((2, 12), 0.8)
    values = clv(survival, np.array([10.0, 100.0]))
    assert values[1] == pytest.approx(10.0 * values[0])


def test_expected_remaining_months_is_the_sum_of_the_survival_curve():
    survival = np.array([[1.0, 0.5, 0.25]])
    assert expected_remaining_months(survival)[0] == pytest.approx(1.75)


def test_value_at_risk_is_value_times_the_chance_of_losing_it():
    assert value_at_risk(np.array([1000.0]), np.array([0.2]))[0] == pytest.approx(200.0)


# --- the horizon guard (D-046) ----------------------------------------------


def test_clv_refuses_to_extrapolate_past_the_observed_support():
    """The standard `ARPU / churn_rate` formula is an infinite sum that assumes a
    constant hazard forever. Retention hazards decline with tenure (D-004), so that
    is biased, not merely uncertain -- and the survival model has no evidence at all
    beyond its training window."""
    survival = np.full((3, 36), 0.9)
    with pytest.raises(ExtrapolationError, match="observed support"):
        clv(survival, 100.0, observed_support=24)


def test_extrapolation_is_possible_but_has_to_be_asked_for():
    survival = np.full((3, 36), 0.9)
    values = clv(survival, 100.0, observed_support=24, allow_extrapolation=True)
    assert (values > 0).all()


def test_horizon_within_support_is_allowed():
    assert clv(np.full((2, 12), 0.9), 100.0, observed_support=24).shape == (2,)


# --- the competing-risks decomposition ---------------------------------------


def test_cause_shortfalls_sum_to_the_total_shortfall(sim):
    """`sum_k shortfall_k == V0 - V`, exactly and with no residual.

    This is what makes "72% of the leak is voluntary" a measurement rather than an
    apportionment. If the identity broke, the split shown to a client would no longer
    add up to the money actually missing."""
    data = subsim_survival(sim)
    model = CompetingRisksHazard(data.cause_names, learner="logistic", pool_after=12).fit(data)

    horizon = 18
    survival = model.survival(data.X, horizon)
    cif = model.cumulative_incidence(data.X, horizon)
    margin = data.X["mrr"].to_numpy() * 0.75

    perfect = clv(np.ones_like(survival), margin, 0.12)
    actual = clv(survival, margin, 0.12)
    shortfalls = value_shortfall_by_cause(cif, margin, 0.12)

    total = sum(shortfalls.values())
    assert np.allclose(total, perfect - actual, rtol=1e-9, atol=1e-6)


def test_both_causes_carry_real_money(sim):
    """Invariant 5 in monetary form. If one cause came out at zero the split would be
    decorative, and the Phase 2 dunning work would have nothing to attach to."""
    data = subsim_survival(sim)
    model = CompetingRisksHazard(data.cause_names, learner="logistic", pool_after=12).fit(data)
    cif = model.cumulative_incidence(data.X, 18)
    shortfalls = value_shortfall_by_cause(cif, data.X["mrr"].to_numpy() * 0.75)

    total = sum(v.sum() for v in shortfalls.values())
    for cause, value in shortfalls.items():
        assert 0.05 < value.sum() / total < 0.95, f"cause {cause} share is degenerate"


# --- the bridge to Phase 4 ---------------------------------------------------


def test_treatment_value_follows_the_projects_sign_convention():
    """`tau = P(churn | treated) - P(churn | control)`, so NEGATIVE tau helps
    (invariant 4). A sign error here would invert every future targeting decision."""
    helpful = treatment_value(np.array([1000.0]), np.array([-0.05]), 5.0)
    harmful = treatment_value(np.array([1000.0]), np.array([+0.05]), 5.0)
    assert helpful[0] == pytest.approx(45.0)
    assert harmful[0] == pytest.approx(-55.0)


def test_identical_treatment_effects_are_worth_different_amounts():
    """The whole reason Phase 3 exists. A churn model cannot tell these two apart;
    only value can."""
    values = treatment_value(np.array([12.0, 1200.0]), np.array([-0.1, -0.1]), 5.0)
    assert values[0] < 0 < values[1]


def test_cost_can_exceed_the_benefit():
    assert treatment_value(np.array([100.0]), np.array([-0.01]), 50.0)[0] < 0
