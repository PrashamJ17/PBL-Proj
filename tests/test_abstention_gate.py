"""What `make abstention` computes and prints (D-069).

`run_once` records two decision rules on every draw: the rule as Phase 4 first ran it,
which multiplied a log-odds effect by money, and the rule as corrected in D-057. For a
while the command printed only the first, under the Phase 4 heading, while every
document quoted the second. These tests pin which rule is the result.
"""

from __future__ import annotations

import pandas as pd
import pytest

from retainiq.experiments.abstention import (
    CORRECTED,
    LEGACY,
    render,
    report,
    run_once,
    summarise,
)

#: Two draws on which the two rules disagree, so a summary can only be right by reading
#: the pair of policies it was asked for.
DRAWS = [
    {"abstention": 0.0, "top_k_expected_value": -5.0,
     "abstention_money": 2.0, "top_k_money": 9.0,
     "treat_all": 3.0, "random_30pct": -1.0},
    {"abstention": 4.0, "top_k_expected_value": -5.0,
     "abstention_money": 0.0, "top_k_money": -1.0,
     "treat_all": -2.0, "random_30pct": -1.0},
]


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"n_customers": 500, "seed": s, "policy": p, "value": v,
         "n_treated": 0, "n_harmed": 0, "n_eligible": 100}
        for s, vals in enumerate(DRAWS)
        for p, v in vals.items()
    ])


def test_run_once_records_both_decision_rules():
    """Every summary is built from these four names. If one is renamed here and not
    there, `summarise` skips the size and the printed table is silently empty."""
    recorded = run_once(400, seed=1001).keys()
    for rule in (CORRECTED, LEGACY):
        assert {rule.ours, rule.comparator} <= recorded


def test_the_corrected_summary_reads_the_money_policies(frame):
    s = summarise(frame, CORRECTED)
    assert s["beats_topk"].iloc[0] == pytest.approx(0.5)       # 2 < 9, then 0 > -1
    assert s["abstain_mean"].iloc[0] == pytest.approx(1.0)
    assert s["topk_mean"].iloc[0] == pytest.approx(4.0)
    assert s["abstain_ties"].iloc[0] == pytest.approx(0.5)


def test_the_legacy_summary_reads_the_legacy_policies(frame):
    s = summarise(frame, LEGACY)
    assert s["beats_topk"].iloc[0] == pytest.approx(1.0)       # 0 > -5, then 4 > -5
    assert s["abstain_mean"].iloc[0] == pytest.approx(2.0)
    assert s["topk_mean"].iloc[0] == pytest.approx(-5.0)


def test_a_summary_cannot_be_built_without_naming_the_rule(frame):
    """No default: which rule a table shows is the difference between the Phase 4
    result and a superseded one."""
    with pytest.raises(TypeError):
        summarise(frame)


def test_the_printed_output_leads_with_the_corrected_rule(frame):
    text = render(frame)
    assert text.index("PHASE 4 GATE") < text.index("BEFORE THE D-057 CORRECTION")


def test_each_printed_table_carries_its_own_rules_figures(frame):
    first, second = render(frame).split("BEFORE THE D-057 CORRECTION")
    assert "beats ranking on 1 of 2 draws (50%); mean realised 1 vs 4" in first
    assert "beats ranking on 2 of 2 draws (100%); mean realised 2 vs -5" in second


def test_the_superseded_table_is_labelled_as_not_the_result(frame):
    _, second = render(frame).split("BEFORE THE D-057 CORRECTION")
    assert "not the Phase 4 result" in second


def test_the_printed_table_shows_ties_beside_wins(frame):
    """D-054: a rule that correctly treats nobody scores exactly zero, which is not a
    win. Printed without the tie rate, declining reads as losing."""
    first, _ = render(frame).split("BEFORE THE D-057 CORRECTION")
    assert "ties 0" in first and "beats 0" in first


def test_a_rule_with_no_draws_says_so_instead_of_printing_an_empty_table(frame):
    only_baseline = frame[frame.policy == "treat_all"]
    text = report(summarise(only_baseline, CORRECTED), CORRECTED)
    assert "no draws recorded" in text
