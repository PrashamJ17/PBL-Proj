"""Tests for holdout assignment and incrementality measurement (D-065).

Two things are being defended. The estimator must recover an effect we already know,
because everything Phase 6 is for depends on that. And the ledger must refuse to let a
holdout be edited after the fact, because that is how retention measurement fails in
practice — not through bad statistics but through a holdout that quietly erodes until the
two groups differ by more than the treatment did.
"""

from __future__ import annotations

import numpy as np
import pytest

from retainiq.policy.holdout import (
    HoldoutLedger,
    assign_holdout,
    measure_incrementality,
    minimum_detectable_effect,
    required_holdout_size,
)

# --- assignment is deterministic, stable and unbiased ------------------------


def test_assignment_is_deterministic_across_calls_and_order():
    ids = [f"c{i}" for i in range(500)]
    a = assign_holdout(ids, 0.2, salt="s")
    b = assign_holdout(ids, 0.2, salt="s")
    assert np.array_equal(a, b)
    # Order independence: a customer's arm cannot depend on their row position.
    shuffled = list(reversed(ids))
    c = assign_holdout(shuffled, 0.2, salt="s")
    assert dict(zip(ids, a, strict=True)) == dict(zip(shuffled, c, strict=True))


def test_membership_is_stable_when_the_customer_base_grows():
    """The property that makes a longitudinal comparison mean anything: onboarding new
    customers must not move existing ones between arms."""
    old = [f"c{i}" for i in range(300)]
    new = old + [f"c{i}" for i in range(300, 600)]
    a = dict(zip(old, assign_holdout(old, 0.15, salt="s"), strict=True))
    b = dict(zip(new, assign_holdout(new, 0.15, salt="s"), strict=True))
    assert all(a[k] == b[k] for k in old)


def test_holdout_fraction_is_approximately_honoured():
    ids = [f"c{i}" for i in range(20_000)]
    assert abs(assign_holdout(ids, 0.10, salt="s").mean() - 0.10) < 0.01


def test_changing_the_salt_reshuffles_everyone():
    ids = [f"c{i}" for i in range(1000)]
    a = assign_holdout(ids, 0.3, salt="v1")
    b = assign_holdout(ids, 0.3, salt="v2")
    assert not np.array_equal(a, b)


def test_duplicate_ids_are_refused():
    with pytest.raises(ValueError, match="duplicate"):
        assign_holdout(["a", "b", "a"], 0.2)


def test_degenerate_fractions_are_refused():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="fraction"):
            assign_holdout(["a", "b"], bad)


# --- the ledger will not let a holdout erode ---------------------------------


def test_ledger_refuses_to_reassign_a_customer():
    led = HoldoutLedger()
    ids = ["a", "b", "c"]
    led.record("exp1", ids, np.array([True, False, False]))
    with pytest.raises(ValueError, match="refusing to reassign"):
        led.record("exp1", ids, np.array([False, False, False]))


def test_ledger_accepts_new_customers_in_an_existing_experiment():
    led = HoldoutLedger()
    led.record("exp1", ["a", "b"], np.array([True, False]))
    led.record("exp1", ["a", "b", "c"], np.array([True, False, True]))
    assert len(led.arm_of("exp1")) == 3


def test_experiments_are_independent():
    led = HoldoutLedger()
    led.record("exp1", ["a"], np.array([True]))
    led.record("exp2", ["a"], np.array([False]))       # allowed: different experiment
    assert led.arm_of("exp1")["a"] == "holdout"
    assert led.arm_of("exp2")["a"] == "treated"


def test_ledger_summary_counts_both_arms():
    led = HoldoutLedger()
    led.record("e", [f"c{i}" for i in range(10)], np.array([True] * 3 + [False] * 7))
    s = led.summary()
    assert int(s.loc[0, "holdout"]) == 3 and int(s.loc[0, "treated"]) == 7


def test_mismatched_lengths_are_refused():
    led = HoldoutLedger()
    with pytest.raises(ValueError, match="same length"):
        led.record("e", ["a", "b"], np.array([True]))


# --- the estimator ------------------------------------------------------------


def test_recovers_a_known_effect_it_was_given():
    """Constructed so the answer is known exactly: treated retain at 0.90, holdout at
    0.80, so the lift is 0.10."""
    rng = np.random.default_rng(0)
    n = 40_000
    held = rng.random(n) < 0.2
    retained = np.where(held, rng.random(n) < 0.80, rng.random(n) < 0.90)
    est = measure_incrementality(retained, held, np.full(n, 100.0))
    assert est.lift == pytest.approx(0.10, abs=0.01)
    assert est.lift_ci[0] < 0.10 < est.lift_ci[1]
    assert est.significant


def test_no_effect_is_not_reported_as_an_effect():
    rng = np.random.default_rng(1)
    n = 20_000
    held = rng.random(n) < 0.2
    retained = rng.random(n) < 0.85          # identical in both arms
    est = measure_incrementality(retained, held, np.full(n, 100.0))
    assert not est.significant
    assert est.lift_ci[0] < 0 < est.lift_ci[1]
    assert "NOT DISTINGUISHABLE" in est.verdict


def test_a_harmful_campaign_is_reported_as_harmful():
    rng = np.random.default_rng(2)
    n = 40_000
    held = rng.random(n) < 0.2
    retained = np.where(held, rng.random(n) < 0.90, rng.random(n) < 0.80)
    est = measure_incrementality(retained, held, np.full(n, 100.0))
    assert est.lift < 0
    assert "NEGATIVE" in est.verdict


def test_cost_is_subtracted_from_incremental_value():
    rng = np.random.default_rng(3)
    n = 10_000
    held = rng.random(n) < 0.2
    retained = np.where(held, rng.random(n) < 0.80, rng.random(n) < 0.90)
    free = measure_incrementality(retained, held, np.full(n, 100.0), cost_per_treated=0.0)
    paid = measure_incrementality(retained, held, np.full(n, 100.0), cost_per_treated=5.0)
    assert paid.incremental_value == pytest.approx(
        free.incremental_value - 5.0 * free.n_treated)


def test_a_missing_arm_is_refused_rather_than_guessed():
    """Without a holdout there is no counterfactual. Returning a save rate here is
    exactly the error the module exists to prevent."""
    n = 100
    for held in (np.zeros(n, bool), np.ones(n, bool)):
        with pytest.raises(ValueError, match="both arms"):
            measure_incrementality(np.ones(n, bool), held, np.full(n, 10.0))


def test_tiny_arms_are_flagged_rather_than_reported():
    rng = np.random.default_rng(4)
    n = 40
    held = np.array([True] * 5 + [False] * 35)
    retained = rng.random(n) < 0.8
    assert "TOO SMALL" in measure_incrementality(retained, held, np.full(n, 10.0)).verdict


def test_negative_value_is_refused():
    n = 100
    held = np.array([True] * 20 + [False] * 80)
    with pytest.raises(ValueError, match="cannot be negative"):
        measure_incrementality(np.ones(n, bool), held, np.full(n, -1.0))


def test_everyone_retained_gives_zero_lift_not_a_crash():
    """Degenerate but real: a short horizon in which nobody churned in either arm."""
    n = 200
    held = np.array([True] * 40 + [False] * 160)
    est = measure_incrementality(np.ones(n, bool), held, np.full(n, 10.0))
    assert est.lift == 0.0
    assert not est.significant


# --- power -------------------------------------------------------------------


def test_mde_shrinks_with_size_and_matches_hand_arithmetic():
    mdes = [minimum_detectable_effect(n) for n in (250, 1000, 4000, 10_000)]
    assert mdes == sorted(mdes, reverse=True)
    # n=250, 10% holdout, p=0.8: (1.96+0.8416)*sqrt(0.16*(1/225+1/25)) = 0.2363
    assert minimum_detectable_effect(250) == pytest.approx(0.2363, abs=1e-3)


def test_required_size_inverts_the_mde():
    n = required_holdout_size(0.05)
    assert minimum_detectable_effect(n) == pytest.approx(0.05, rel=0.02)


def test_the_delivered_effect_is_undetectable_at_every_realistic_size():
    """The finding this module exists to produce. The simulator's calibrated offer moves
    retention by about 0.011, and the MDE exceeds that even at 10,000 customers."""
    delivered = 0.0108
    for n in (250, 500, 1000, 2000, 4000, 10_000):
        assert minimum_detectable_effect(n) > delivered
    assert required_holdout_size(delivered) > 100_000


def test_a_zero_or_negative_effect_is_refused():
    for bad in (0.0, -0.01):
        with pytest.raises(ValueError, match="effect must be positive"):
            required_holdout_size(bad)
