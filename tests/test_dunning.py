"""Tests for the dunning simulator and retry policies.

The load-bearing tests here are the ones that pin the *mechanism*: that decline codes
behave differently from each other, that payday timing matters for the codes it should
matter for and not for the others, and that a policy optimising recovery rate can lose
to one optimising value. If those stop holding, the Phase 2 conclusion is not a
conclusion.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from retainiq.experiments.dunning import Economics, evaluate, run
from retainiq.policy.dunning import (
    AGGRESSIVE,
    ALL_POLICIES,
    CODE_AWARE,
    NO_RETRY,
    PROCESSOR_DEFAULT,
    QUIET_CODE_AWARE,
    apply_policy,
    next_payday,
)
from retainiq.sim.dunning import (
    DECLINE_CODES,
    PASSIVE_RECOVERY_BAND,
    DunningConfig,
    calibrate_recovery_scale,
    generate_failures,
    measure_recovery,
    retry_success_prob,
    timing_multiplier,
)

CFG = DunningConfig()


@pytest.fixture(scope="module")
def failures():
    return generate_failures(20_000, CFG, np.random.default_rng(0))


# --- the generative process -------------------------------------------------


def test_decline_code_shares_sum_to_one():
    assert sum(c.share for c in DECLINE_CODES) == pytest.approx(1.0, abs=1e-9)


def test_failure_mix_matches_declared_shares(failures):
    observed = failures["code"].value_counts(normalize=True)
    for code in DECLINE_CODES:
        assert observed[code.name] == pytest.approx(code.share, abs=0.02)


def test_failures_span_the_month(failures):
    """Day-of-month must vary, or retry *timing* cannot be studied at all."""
    days = pd.DatetimeIndex(failures["failed_at"]).day
    assert days.min() <= 2 and days.max() >= 28


def test_success_probabilities_are_valid(failures):
    p = retry_success_prob(
        failures["code_idx"].to_numpy(),
        np.ones(len(failures), dtype=int),
        failures["failed_at"],
        CFG,
    )
    assert ((p >= 0) & (p <= 1)).all()
    assert np.isfinite(p).all()


# --- the mechanism ----------------------------------------------------------


def test_payday_timing_only_affects_payday_sensitive_codes():
    """Salary cycles should move `insufficient_funds` and nothing else.

    If timing affected every code equally it would be a global fudge factor rather
    than a mechanism, and code-aware scheduling would have no reason to work."""
    # Both must be weekday business hours, so that payday proximity is the ONLY
    # thing differing. 2024-03-01 is a Friday (payday); 2024-03-11 is a Monday
    # (not). An earlier version used 2024-03-10, a Sunday, and the business-hours
    # factor -- not payday -- explained the difference.
    on_payday = pd.DatetimeIndex([pd.Timestamp("2024-03-01 10:00")] * 2)
    off_payday = pd.DatetimeIndex([pd.Timestamp("2024-03-11 10:00")] * 2)

    sensitive = np.array([True, True])
    insensitive = np.array([False, False])

    assert (
        timing_multiplier(on_payday, sensitive, CFG)[0]
        > timing_multiplier(off_payday, sensitive, CFG)[0]
    )
    assert timing_multiplier(on_payday, insensitive, CFG)[0] == pytest.approx(
        timing_multiplier(off_payday, insensitive, CFG)[0]
    )


def test_expired_cards_are_not_recoverable_by_retry(failures):
    """Retrying the same expired card cannot work. A model that recovers them is
    not modelling the thing it claims to."""
    out = apply_policy(failures, AGGRESSIVE, CFG, np.random.default_rng(1))
    expired = out[out["code"] == "expired_card"]
    assert expired["recovered"].mean() < 0.20


def test_account_updater_rescues_expired_cards(failures):
    """...and a card updater is precisely what does fix them."""
    with_updater = replace(CFG, account_updater=True)
    a = apply_policy(failures, CODE_AWARE, CFG, np.random.default_rng(1))
    b = apply_policy(failures, CODE_AWARE, with_updater, np.random.default_rng(1))

    a_exp = a[a["code"] == "expired_card"]["recovered"].mean()
    b_exp = b[b["code"] == "expired_card"]["recovered"].mean()
    assert b_exp > a_exp + 0.20


def test_success_decays_with_attempt_number():
    codes = np.zeros(5, dtype=int)
    ts = pd.DatetimeIndex([pd.Timestamp("2024-03-01 10:00")] * 5)
    p = retry_success_prob(codes, np.arange(1, 6), ts, CFG)
    assert (np.diff(p) < 0).all(), "a card that keeps failing is telling you something"


def test_insufficient_funds_is_the_biggest_recoverable_group(failures):
    """The premise of payday-aligned retries: this is where the money is."""
    out = apply_policy(failures, CODE_AWARE, CFG, np.random.default_rng(1))
    by_code = out.groupby("code")["recovered"].mean()
    assert by_code["insufficient_funds"] > 0.6
    assert by_code["insufficient_funds"] > by_code["do_not_honor"]


# --- policies ---------------------------------------------------------------


def test_no_retry_recovers_nothing(failures):
    out = apply_policy(failures, NO_RETRY, CFG, np.random.default_rng(1))
    assert out["recovered"].sum() == 0
    assert out["attempts"].sum() == 0
    assert out["emails"].sum() == 0


def test_every_policy_respects_max_attempts(failures):
    for policy in ALL_POLICIES:
        out = apply_policy(failures, policy, CFG, np.random.default_rng(1))
        assert out["attempts"].max() <= CFG.max_attempts


def test_recovered_failures_have_a_recovery_time(failures):
    out = apply_policy(failures, CODE_AWARE, CFG, np.random.default_rng(1))
    assert out.loc[out["recovered"], "days_to_recovery"].notna().all()
    assert out.loc[~out["recovered"], "days_to_recovery"].isna().all()


def test_code_aware_beats_default_with_fewer_attempts(failures):
    """The Phase 2 headline: better-targeted retries, not more of them."""
    default = apply_policy(failures, PROCESSOR_DEFAULT, CFG, np.random.default_rng(1))
    aware = apply_policy(failures, CODE_AWARE, CFG, np.random.default_rng(1))

    assert aware["recovered"].mean() > default["recovered"].mean()
    assert aware["attempts"].mean() < default["attempts"].mean()


def test_quiet_variant_keeps_recovery_with_less_contact(failures):
    """The timing does the work, not the nagging. If this fails, the emails were
    carrying the recovery and the fatigue argument weakens."""
    loud = apply_policy(failures, CODE_AWARE, CFG, np.random.default_rng(1))
    quiet = apply_policy(failures, QUIET_CODE_AWARE, CFG, np.random.default_rng(1))

    assert quiet["emails"].mean() < loud["emails"].mean() * 0.8
    assert quiet["recovered"].mean() == pytest.approx(loud["recovered"].mean(), abs=0.01)


def test_next_payday_is_in_the_future_and_on_a_payday():
    ts = pd.DatetimeIndex([pd.Timestamp("2024-03-05 12:00"), pd.Timestamp("2024-03-20 12:00")])
    nxt = next_payday(ts, CFG)
    assert (nxt > ts).all()
    assert set(nxt.day).issubset(set(CFG.payday_days))


# --- calibration ------------------------------------------------------------


def test_passive_policy_lands_in_the_published_band():
    """Processor-native retries should reproduce the published median band."""
    rate = measure_recovery(PROCESSOR_DEFAULT, CFG, n=20_000)
    lo, hi = PASSIVE_RECOVERY_BAND
    assert lo <= rate <= hi, f"passive recovery {rate:.3f} outside {PASSIVE_RECOVERY_BAND}"


def test_passive_policy_matches_subsim():
    """The detailed and aggregate models must not disagree.

    SubSim's `passive_recovery_rate` is what the Phase 0 calibration gates were tuned
    against; this module is calibrated to reproduce it."""
    from retainiq.sim.config import SimConfig

    target = SimConfig().payments.passive_recovery_rate
    assert measure_recovery(PROCESSOR_DEFAULT, CFG, n=20_000) == pytest.approx(target, abs=0.04)


def test_calibration_solver_converges():
    scale = calibrate_recovery_scale(target=0.35, n=8_000)
    got = measure_recovery(PROCESSOR_DEFAULT, replace(CFG, recovery_scale=scale), n=8_000)
    assert got == pytest.approx(0.35, abs=0.03)


def test_dedicated_dunning_approaches_the_published_upper_band():
    """Calibrated on the passive band only; the top-quartile figure should then be
    reproduced without further tuning. This is the out-of-sample check on the
    generative model."""
    cfg = replace(CFG, account_updater=True)
    rate = measure_recovery(CODE_AWARE, cfg, n=20_000)
    assert rate > 0.50, f"dedicated dunning only reached {rate:.3f}"


# --- economics --------------------------------------------------------------


def test_aggressive_dunning_is_dominated(failures):
    """The Phase 2 finding: trying harder buys nothing.

    `aggressive` uses ~2.5x the attempts and ~3.9x the emails of `code_aware` and
    does NOT recover more. It loses on value and does not even win on the vendor's
    own headline metric.

    An earlier version of the simulator had aggressive winning on recovery, but
    that came from retries compounding on expired cards -- which cannot happen
    (D-033). Fixing it removed aggressive's only advantage."""
    econ = Economics()
    aggressive = evaluate(failures, AGGRESSIVE, CFG, econ, np.random.default_rng(1))
    aware = evaluate(failures, CODE_AWARE, CFG, econ, np.random.default_rng(1))

    assert aggressive.attempts_per_failure > 2 * aware.attempts_per_failure
    assert aggressive.recovery_rate <= aware.recovery_rate + 0.005
    assert aggressive.net_value < aware.net_value


def test_quieter_contact_is_worth_money(failures):
    """Same schedule, fewer emails, same recovery -- and more money.

    This isolates the fatigue cost: the two policies retry identically and differ
    only in how often they email."""
    econ = Economics()
    loud = evaluate(failures, CODE_AWARE, CFG, econ, np.random.default_rng(1))
    quiet = evaluate(failures, QUIET_CODE_AWARE, CFG, econ, np.random.default_rng(1))

    assert quiet.emails_per_failure < loud.emails_per_failure * 0.8
    assert quiet.recovery_rate == pytest.approx(loud.recovery_rate, abs=0.01)
    assert quiet.net_value > loud.net_value


def test_the_quiet_advantage_is_entirely_fatigue(failures):
    """With no fatigue cost, emailing less buys almost nothing.

    Pins the conclusion to the mechanism rather than to an accident of the
    policies: if quiet still won by a wide margin at zero fatigue, something other
    than contact cost would be driving it."""
    cfg = replace(CFG, contact_fatigue_per_email=0.0)
    econ = Economics()
    loud = evaluate(failures, CODE_AWARE, cfg, econ, np.random.default_rng(1))
    quiet = evaluate(failures, QUIET_CODE_AWARE, cfg, econ, np.random.default_rng(1))

    gap = abs(quiet.net_value - loud.net_value)
    assert gap < 0.005 * loud.net_value, "without fatigue the two should be near-identical"


def test_no_retry_has_zero_value(failures):
    econ = Economics()
    r = evaluate(failures, NO_RETRY, CFG, econ, np.random.default_rng(1))
    assert r.net_value == 0.0
    assert r.clv_retained == 0.0


def test_every_policy_beats_doing_nothing(failures):
    """Dunning is worth doing. If any policy lost to no_retry the economics would
    be wrong somewhere."""
    results = run(n_failures=8_000, seed=0)
    baseline = next(r for r in results if r.name == "no_retry")
    for r in results:
        assert r.net_value >= baseline.net_value


# --- edge cases -------------------------------------------------------------


def test_zero_failures():
    empty = generate_failures(0, CFG, np.random.default_rng(0))
    out = apply_policy(empty, CODE_AWARE, CFG, np.random.default_rng(1))
    assert len(out) == 0


def test_single_failure():
    one = generate_failures(1, CFG, np.random.default_rng(0))
    out = apply_policy(one, CODE_AWARE, CFG, np.random.default_rng(1))
    assert len(out) == 1


def test_policy_application_is_deterministic(failures):
    a = apply_policy(failures, CODE_AWARE, CFG, np.random.default_rng(7))
    b = apply_policy(failures, CODE_AWARE, CFG, np.random.default_rng(7))
    assert a["recovered"].equals(b["recovered"])


def test_empty_schedule_is_handled(failures):
    from retainiq.policy.dunning import RetryPolicy

    never = RetryPolicy("never", schedule=())
    out = apply_policy(failures, never, CFG, np.random.default_rng(1))
    assert out["recovered"].sum() == 0
