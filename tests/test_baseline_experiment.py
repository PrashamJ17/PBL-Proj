"""Tests for the comparison of abstention with Lemmens & Gupta's rule (D-075).

The comparison is only worth having if it is fair, so most of what is pinned here is
fairness: both rules get the same pilot, neither sees the customers it is scored on, and
the configuration reported as "theirs" is the one fixed before any result was seen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from retainiq.benchmarks.small_n import exact_interval
from retainiq.experiments.abstention import draw_pilot, run_once
from retainiq.experiments.baseline import (
    ALPHA,
    BUDGET,
    CONFIGS,
    DRAWS,
    OURS,
    PRIMARY,
    RANKING,
    SENSITIVITY,
    SIZES,
    by_policy,
    can_act,
    compare,
    lg_decision,
    report,
    run_draw,
    sweep,
    validation_size,
)

SEED, N = 1003, 800


@pytest.fixture(scope="module")
def pilot():
    return draw_pilot(N, SEED)


@pytest.fixture(scope="module")
def draw():
    return pd.DataFrame(run_draw(N, SEED))


def table_row(text: str, policy: str) -> str:
    """The policy's line in the first results table (not its line in the key above it)."""
    return next(ln for ln in text.splitlines()
                if ln.strip().startswith(policy) and "[" in ln)


def results(values: dict[str, list[float]]) -> pd.DataFrame:
    """A hand-made frame: one value per draw for each policy."""
    return pd.DataFrame([
        {"n_customers": 500, "seed": s, "policy": p, "value": v, "n_treated": int(v != 0),
         "n_eligible": 100}
        for p, vals in values.items() for s, v in enumerate(vals)
    ])


# --- what was fixed in advance ------------------------------------------------


def test_the_primary_configuration_is_the_one_pre_registered():
    """Their estimator, equal halves, and the calibration model scoring the test set."""
    assert (PRIMARY.estimator, PRIMARY.calibration_share, PRIMARY.refit) == (
        "profit_loss", 0.5, False)
    assert CONFIGS[0] is PRIMARY


def test_the_design_is_the_one_pre_registered():
    assert SIZES == (250, 500, 1000, 2000, 4000)
    assert DRAWS == 100
    assert BUDGET == 0.30
    assert ALPHA == 0.30


def test_their_best_case_uses_more_data_for_fitting_and_refits():
    best = next(c for c in CONFIGS if c.name == "lg_best_case")
    assert best.calibration_share > PRIMARY.calibration_share and best.refit


def test_the_sensitivity_run_is_kept_apart_from_the_pre_registered_ones():
    assert not {c.name for c in SENSITIVITY} & {c.name for c in CONFIGS}


def test_every_pre_registered_configuration_keeps_the_floor_of_ten_per_arm():
    """The floor was fixed in advance. Only a run labelled as added afterwards drops it."""
    assert {c.min_arm for c in CONFIGS} == {10}
    assert [c.name for c in SENSITIVITY if c.min_arm != 10] == ["lg_no_floor"]


# --- where their rule has no choice to make -----------------------------------------


def test_the_validation_sample_is_what_the_calibration_share_leaves():
    assert validation_size(150, PRIMARY) == 75
    best = next(c for c in CONFIGS if c.name == "lg_best_case")
    assert validation_size(150, best) == 50


def test_a_pilot_too_small_for_ten_per_arm_under_the_cap_leaves_no_size_to_choose():
    """Thirty-seven validation customers, a 30% cap: eleven at most. Ten treated and ten
    controls do not fit in eleven, so the rule cannot act whatever the data show."""
    assert not can_act(75, PRIMARY)
    assert can_act(150, PRIMARY)


def test_the_best_case_holds_back_fewer_customers_and_so_needs_a_larger_pilot():
    best = next(c for c in CONFIGS if c.name == "lg_best_case")
    assert not can_act(150, best) and can_act(300, best)


def test_without_the_floor_their_rule_can_always_act():
    no_floor = next(c for c in SENSITIVITY if c.name == "lg_no_floor")
    assert can_act(75, no_floor) and can_act(20, no_floor)


def test_when_their_rule_cannot_act_it_treats_nobody(pilot):
    """`can_act` is a statement about `lg_decision`; this ties the two together."""
    from dataclasses import replace

    few = np.arange(60)
    small = replace(pilot, train=pilot.train.iloc[few].reset_index(drop=True),
                    treated=pilot.treated[few], churned=pilot.churned[few])
    assert not can_act(len(small.train), PRIMARY)
    mask, fraction = lg_decision(small, PRIMARY, SEED)
    assert not mask.any() and fraction == 0.0


def test_the_report_says_where_a_rule_could_not_act():
    frame = results({OURS: [0, 3], "lg_primary": [0, 0]})
    frame["can_act"] = frame["policy"] == OURS
    text = report(frame)
    assert "could not act *" in table_row(text, "lg_primary")
    assert "by construction, not by" in text
    assert "could not act" not in table_row(text, OURS)


def test_a_rule_that_chose_to_treat_nobody_is_not_marked_as_unable():
    frame = results({OURS: [0, 3], "lg_primary": [0, 0]})
    frame["can_act"] = True
    assert "could not act" not in table_row(report(frame), "lg_primary")


# --- the same pilot for both ---------------------------------------------------


def test_a_pilot_is_the_same_every_time_it_is_drawn(pilot):
    again = draw_pilot(N, SEED)
    pd.testing.assert_frame_equal(pilot.train, again.train)
    pd.testing.assert_frame_equal(pilot.test, again.test)
    assert np.array_equal(pilot.treated, again.treated)
    assert np.array_equal(pilot.churned, again.churned)


def test_the_pilot_shows_only_the_outcome_of_the_arm_each_customer_was_in(pilot):
    expected = np.where(pilot.treated == 1, pilot.train["y1"], pilot.train["y0"])
    assert np.array_equal(pilot.churned, expected)


def test_this_projects_policies_are_exactly_those_of_the_abstention_experiment(draw):
    """The comparison reuses the abstention experiment's own numbers for abstention, so
    a difference from that experiment cannot creep in here."""
    ours = run_once(N, SEED)
    for name in (OURS, RANKING):
        row = draw[draw["policy"] == name].iloc[0]
        assert row["value"] == pytest.approx(ours[name].realised_value)
        assert row["n_treated"] == ours[name].n_treated


def test_every_configuration_is_scored_on_every_draw(draw):
    expected = {OURS, RANKING, *(c.name for c in (*CONFIGS, *SENSITIVITY))}
    assert set(draw["policy"]) == expected
    assert draw["n_eligible"].nunique() == 1


# --- their method sees what a business would see, and nothing else ---------------


@pytest.mark.parametrize("config", CONFIGS, ids=lambda c: c.name)
def test_their_decision_does_not_depend_on_the_test_customers_outcomes(pilot, config):
    """The decision is made before anyone knows how the test customers turn out.
    Scrambling those outcomes must leave it unchanged."""
    from dataclasses import replace

    mask, fraction = lg_decision(pilot, config, SEED)
    scrambled = pilot.test.copy()
    for col in ("y0", "y1", "tau_true", "p_churn_control", "p_churn_treated",
                "value_of_treating"):
        scrambled[col] = np.random.default_rng(1).permutation(scrambled[col].to_numpy())
    again, fraction_again = lg_decision(replace(pilot, test=scrambled), config, SEED)
    assert np.array_equal(mask, again) and fraction == fraction_again


@pytest.mark.parametrize("config", CONFIGS, ids=lambda c: c.name)
def test_their_decision_does_not_depend_on_the_arm_the_pilot_did_not_observe(pilot, config):
    """A pilot customer who was treated has an outcome under treatment and no other.
    Their rule must not be able to read the one that was never observed."""
    from dataclasses import replace

    mask, _ = lg_decision(pilot, config, SEED)
    train = pilot.train.copy()
    unseen = np.where(pilot.treated == 1, "y0", "y1")
    for col in ("y0", "y1"):
        hide = unseen == col
        train.loc[train.index[hide], col] = 1 - train.loc[train.index[hide], col]
    again, _ = lg_decision(replace(pilot, train=train), config, SEED)
    assert np.array_equal(mask, again)


@pytest.mark.parametrize("config", CONFIGS, ids=lambda c: c.name)
def test_their_campaign_never_exceeds_the_budget(pilot, config):
    mask, fraction = lg_decision(pilot, config, SEED)
    assert fraction <= BUDGET
    assert mask.sum() <= int(round(BUDGET * len(pilot.test)))


def test_a_calibration_sample_with_one_outcome_treats_nobody(pilot):
    """Nobody churned in the part the model would be fitted on: there is nothing to
    learn from, and the decision is to leave everyone alone."""
    from dataclasses import replace

    quiet = replace(pilot, churned=np.zeros_like(pilot.churned))
    mask, fraction = lg_decision(quiet, PRIMARY, SEED)
    assert not mask.any() and fraction == 0.0


def test_their_decision_is_reproducible(pilot):
    a, fa = lg_decision(pilot, PRIMARY, SEED)
    b, fb = lg_decision(pilot, PRIMARY, SEED)
    assert np.array_equal(a, b) and fa == fb


# --- counting ---------------------------------------------------------------------


def test_wins_ties_and_losses_are_counted_separately():
    """Two draws where both treat nobody are ties. They are not half a win each."""
    frame = results({OURS: [0, 0, 5, 5, -3], "lg_primary": [0, 0, 1, 9, -8]})
    c = compare(frame, OURS, "lg_primary")
    assert (c["wins"], c["ties"], c["losses"]) == (2, 2, 1)


def test_the_win_rate_is_taken_over_the_draws_that_differ():
    frame = results({OURS: [0, 0, 5, 5, -3], "lg_primary": [0, 0, 1, 9, -8]})
    c = compare(frame, OURS, "lg_primary")
    assert c["rate"] == pytest.approx(2 / 3)
    assert (c["low"], c["high"]) == pytest.approx(exact_interval(2, 3))


def test_the_mean_gap_counts_every_draw_including_ties():
    frame = results({OURS: [0, 0, 5, 5, -3], "lg_primary": [0, 0, 1, 9, -8]})
    assert compare(frame, OURS, "lg_primary")["mean_gap"] == pytest.approx((4 - 4 + 5) / 5)


def test_when_every_draw_is_a_tie_there_is_no_win_rate():
    frame = results({OURS: [0, 0, 0], "lg_primary": [0, 0, 0]})
    c = compare(frame, OURS, "lg_primary")
    assert c["ties"] == 3 and np.isnan(c["rate"])


def test_a_policy_that_was_not_run_gives_no_comparison():
    assert np.isnan(compare(results({OURS: [1, 2]}), OURS, "lg_primary")["rate"])


def test_treating_nobody_is_not_counted_as_beating_doing_nothing():
    """Zero is not greater than zero. A rule that declines has tied with inaction."""
    row = by_policy(results({OURS: [0, 0, 0, 4]})).iloc[0]
    assert row["beats_nothing"] == pytest.approx(0.25)
    assert row["treats_nobody"] == pytest.approx(0.75)
    assert (row["beats_low"], row["beats_high"]) == pytest.approx(exact_interval(1, 4))


# --- what is printed --------------------------------------------------------------


def test_the_report_shows_every_policy_and_keeps_ties_visible(draw):
    text = report(draw)
    for name in (OURS, RANKING, *(c.name for c in (*CONFIGS, *SENSITIVITY))):
        assert name in text
    assert "tied" in text and "treats nobody" in text


def test_the_report_marks_the_runs_that_were_not_pre_registered(draw):
    text = report(draw)
    for config in SENSITIVITY:
        line = next(ln for ln in text.splitlines() if ln.strip().startswith(config.name))
        assert "not pre-registered" in line


def test_an_empty_sweep_says_so():
    assert report(pd.DataFrame()) == "No usable draws."


def test_a_draw_too_small_to_use_contributes_nothing():
    assert run_draw(20, SEED) == []


# --- the sweep ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def small_sweep():
    return sweep(sizes=(300,), draws=3)


def test_the_sweep_uses_the_pre_registered_seeds(small_sweep):
    assert sorted(small_sweep["seed"].unique()) == [1000, 1001, 1002]


def test_running_draws_side_by_side_changes_no_number(small_sweep):
    pd.testing.assert_frame_equal(small_sweep, sweep(sizes=(300,), draws=3, jobs=2))


def test_an_interrupted_sweep_resumes_to_the_same_result(small_sweep, tmp_path):
    """Stop after one draw, start again: the finished draw is read back, not re-run,
    and the whole is what an uninterrupted sweep gives."""
    saved = tmp_path / "draws.csv"
    first = sweep(sizes=(300,), draws=1, resume=saved)
    assert len(pd.read_csv(saved)) == len(first)
    whole = sweep(sizes=(300,), draws=3, resume=saved)
    pd.testing.assert_frame_equal(whole, small_sweep, check_dtype=False)
    assert len(pd.read_csv(saved)) == len(small_sweep)


def test_a_finished_sweep_runs_nothing_when_resumed(small_sweep, tmp_path, monkeypatch):
    saved = tmp_path / "draws.csv"
    small_sweep.to_csv(saved, index=False)

    def refuse(*_):
        raise AssertionError("a draw was run again")

    monkeypatch.setattr("retainiq.experiments.baseline.run_draw", refuse)
    pd.testing.assert_frame_equal(sweep(sizes=(300,), draws=3, resume=saved), small_sweep,
                                  check_dtype=False)


def test_saved_draws_from_a_larger_design_are_not_mixed_in(small_sweep, tmp_path):
    """Resuming a two-draw sweep from a file holding three must report two."""
    saved = tmp_path / "draws.csv"
    small_sweep.to_csv(saved, index=False)
    assert sorted(sweep(sizes=(300,), draws=2, resume=saved)["seed"].unique()) == [1000, 1001]


def test_the_report_can_be_printed_from_saved_draws(small_sweep, tmp_path, capsys):
    from retainiq.experiments.baseline import main

    saved = tmp_path / "draws.csv"
    small_sweep.to_csv(saved, index=False)
    assert main(["--from-draws", str(saved)]) == 0
    out = capsys.readouterr().out.strip()
    # A table printed from a file must say so, and must otherwise be the same table.
    marker = "RE-READ from draws.csv, not re-run"
    assert marker in out and marker not in report(small_sweep)
    assert out.replace(marker + "\n", "") == report(small_sweep)
