"""Tests for the re-implementation of Lemmens & Gupta (2020) (D-075).

Their method is the baseline the abstention rule is compared with, so a mistake here
would decide the comparison. Each piece is therefore tested against an answer worked out
by hand or a property stated in their paper, on data small enough to check on paper.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from retainiq.policy.baseline_lg import (
    MIN_ARM,
    FirstStage,
    ProfitLossBoosting,
    choose_fraction,
    profit_curve,
    top_fraction,
)

# Six customers, already in ranking order. Treated and control alternate.
SCORES = np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0])
TREATED = np.array([1, 0, 1, 0, 1, 0])
#            treated stays, control leaves | treated stays, control stays | both leave
CHURNED = np.array([0, 1, 0, 0, 1, 1])
VALUE = np.full(6, 100.0)


def curve(cost=10.0, min_arm=1, **kw):
    return profit_curve(SCORES, TREATED, CHURNED, VALUE, cost, min_arm=min_arm, **kw)


# --- the profit of a campaign of size S (their Equations 8b and 9) -----------


def test_profit_of_the_top_two_matches_the_hand_calculation():
    """Top 2: the treated customer stayed (100), the control left (0), the offer costs 10.
    Per customer 100 - 0 - 10 = 90; two customers, 180."""
    assert curve().set_index("size").loc[2, "profit"] == pytest.approx(180.0)


def test_profit_of_the_top_four_matches_the_hand_calculation():
    """Top 4: treated kept 100 and 100, mean 100; controls kept 0 and 100, mean 50.
    Per customer 100 - 50 - 10 = 40; four customers, 160."""
    assert curve().set_index("size").loc[4, "profit"] == pytest.approx(160.0)


def test_profit_of_everyone_matches_the_hand_calculation():
    """All 6: treated kept 100, 100, 0, mean 66.67; controls kept 0, 100, 0, mean 33.33.
    Per customer 33.33 - 10 = 23.33; six customers, 140."""
    assert curve().set_index("size").loc[6, "profit"] == pytest.approx(140.0)


def test_the_cost_is_charged_on_every_targeted_customer():
    """An unconditional offer: paid whether the customer stays or not, and whether the
    trial happened to treat them or not, because the campaign would treat them all."""
    cheap, dear = curve(cost=0.0), curve(cost=10.0)
    gap = (cheap["profit"] - dear["profit"]).dropna()
    assert gap.to_numpy() == pytest.approx(10.0 * cheap["size"].to_numpy()[gap.index])


def test_a_per_customer_cost_is_averaged_over_the_customers_targeted():
    cost = np.array([0.0, 20.0, 0.0, 0.0, 0.0, 0.0])
    assert curve(cost=cost).set_index("size").loc[2, "profit"] == pytest.approx(2 * (100 - 10))


def test_a_size_with_an_empty_arm_has_no_estimate():
    """Top 1 is one treated customer and no control. There is nothing to compare, and
    the estimate is missing, not zero."""
    assert np.isnan(curve().set_index("size").loc[1, "profit"])


def test_a_size_is_only_estimated_with_enough_customers_in_both_arms():
    c = curve(min_arm=2).set_index("size")
    assert c.loc[[1, 2, 3], "profit"].isna().all()
    assert c.loc[[4, 5, 6], "profit"].notna().all()


def test_the_pre_registered_minimum_arm_is_ten():
    assert MIN_ARM == 10


def test_the_ranking_is_by_score_not_by_position():
    shuffled = np.array([3, 0, 5, 1, 4, 2])
    c = profit_curve(SCORES[shuffled], TREATED[shuffled], CHURNED[shuffled], VALUE, 10.0,
                     min_arm=1)
    assert c["profit"].to_numpy() == pytest.approx(curve()["profit"].to_numpy(), nan_ok=True)


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_a_customer_who_cannot_be_ranked_is_refused(bad):
    scores = SCORES.copy()
    scores[2] = bad
    with pytest.raises(ValueError, match="finite"):
        profit_curve(scores, TREATED, CHURNED, VALUE, 10.0)


def test_inputs_of_different_lengths_are_refused():
    with pytest.raises(ValueError, match="same length"):
        profit_curve(SCORES, TREATED[:4], CHURNED, VALUE, 10.0)


# --- choosing the size --------------------------------------------------------


def test_profit_of_the_top_three_matches_the_hand_calculation():
    """Top 3: two treated customers, both stayed (mean 100); one control, who left (0).
    Per customer 100 - 0 - 10 = 90; three customers, 270."""
    assert curve().set_index("size").loc[3, "profit"] == pytest.approx(270.0)


def test_the_chosen_size_is_the_one_with_the_highest_estimated_profit():
    """Profits are 180, 270, 160, 33.3 and 140 for sizes 2 to 6. The top three wins."""
    fraction, profit = choose_fraction(SCORES, TREATED, CHURNED, VALUE, 10.0, min_arm=1)
    assert fraction == pytest.approx(3 / 6)
    assert profit == pytest.approx(270.0)


def test_when_no_size_is_estimated_to_pay_nobody_is_targeted():
    """Their enumeration starts at one customer. Allowing zero lets their rule decline,
    as the abstention rule can. A cost of 200 makes every size a loss."""
    assert choose_fraction(SCORES, TREATED, CHURNED, VALUE, 200.0, min_arm=1) == (0.0, 0.0)


def test_when_no_size_can_be_estimated_nobody_is_targeted():
    """Six customers cannot give ten per arm. No estimate is not a reason to act."""
    assert choose_fraction(SCORES, TREATED, CHURNED, VALUE, 10.0) == (0.0, 0.0)


def test_a_budget_cap_limits_the_sizes_considered():
    """The best size is three of six. Capped at a third of the customers, three is off
    the table and the best size within the cap, two, is chosen."""
    fraction, profit = choose_fraction(SCORES, TREATED, CHURNED, VALUE, 10.0,
                                       max_fraction=1 / 3, min_arm=1)
    assert fraction == pytest.approx(2 / 6)
    assert profit == pytest.approx(180.0)


def test_the_chosen_size_depends_only_on_the_ranking():
    """Their footnote 12: the rule is insensitive to the scale of the scores."""
    base = choose_fraction(SCORES, TREATED, CHURNED, VALUE, 10.0, min_arm=1)
    for transformed in (SCORES * 1000, SCORES - 500, np.exp(SCORES), SCORES ** 3):
        assert choose_fraction(transformed, TREATED, CHURNED, VALUE, 10.0, min_arm=1) == base


def test_top_fraction_treats_exactly_the_share_asked_for():
    assert top_fraction(SCORES, 2 / 6).tolist() == [True, True, False, False, False, False]
    assert not top_fraction(SCORES, 0.0).any()
    assert top_fraction(SCORES, 1.0).all()


def test_top_fraction_follows_the_scores():
    assert top_fraction(SCORES[::-1], 1 / 3).tolist() == [False, False, False, False, True, True]


# --- the first stage ------------------------------------------------------------


def trial(n=1200, seed=0):
    """An offer that cuts churn for customers with x > 0 and raises it for the rest."""
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({"x": rng.normal(size=n), "noise": rng.normal(size=n)})
    treated = rng.integers(0, 2, n)
    p = 0.35 - 0.20 * treated * np.sign(X["x"].to_numpy())
    churned = (rng.random(n) < p).astype(int)
    return X, treated, churned


def test_first_stage_finds_who_the_offer_helps():
    X, treated, churned = trial()
    lift = FirstStage.fit(X, treated, churned).profit_lift(X, np.full(len(X), 100.0), 0.0)
    helped, harmed = X["x"] > 0.3, X["x"] < -0.3
    assert lift[helped].mean() > 5 > -5 > lift[harmed].mean()


def test_first_stage_subtracts_the_cost_of_the_offer():
    X, treated, churned = trial()
    stage = FirstStage.fit(X, treated, churned)
    free = stage.profit_lift(X, np.full(len(X), 100.0), 0.0)
    assert stage.profit_lift(X, np.full(len(X), 100.0), 7.0) == pytest.approx(free - 7.0)


def test_a_pilot_with_one_arm_is_refused():
    X, _, churned = trial(200)
    with pytest.raises(ValueError, match="only one arm"):
        FirstStage.fit(X, np.ones(len(X), dtype=int), churned)


def test_an_arm_with_a_single_outcome_falls_back_to_its_rate():
    """Forty customers can leave an arm in which nobody churned. No classifier can be
    fitted to that; the arm's rate is the estimate, the same for everyone."""
    X, treated, churned = trial(40)
    churned = np.where(treated == 1, 0, churned)
    churned[treated == 0] = np.resize([0, 1], int((treated == 0).sum()))
    stage = FirstStage.fit(X, treated, churned)
    assert np.ptp(stage.treatment(X)) == 0.0
    assert stage.treatment(X)[0] == 0.0


# --- the second stage: the profit-based loss (their Equation 7) -----------------


def profit_data(n=600, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({"x": rng.normal(size=n), "noise": rng.normal(size=n)})
    profit = 40.0 * X["x"].to_numpy() + rng.normal(scale=5.0, size=n)
    return X, profit


def test_the_loss_ranks_profitable_customers_above_unprofitable_ones():
    X, profit = profit_data()
    score = ProfitLossBoosting(seed=1).fit(X, profit).score(X)
    assert score[profit > 20].mean() > 0 > score[profit < -20].mean()
    assert spearmanr(score, profit).statistic > 0.85


def test_the_ranking_holds_on_customers_it_was_not_fitted_on():
    X, profit = profit_data(seed=0)
    Z, future = profit_data(seed=99)
    score = ProfitLossBoosting(seed=1).fit(X, profit).score(Z)
    assert spearmanr(score, future).statistic > 0.85
    assert (np.sign(score) == np.sign(future)).mean() > 0.9


def test_a_higher_profit_lift_earns_a_higher_score_among_customers_the_offer_helps():
    """The property their paper states for the loss, and the reason the boosting step
    is a gradient step. Their campaign takes customers from the top of the ranking, so
    the order *within* the profitable ones decides who is left out."""
    X, profit = profit_data(seed=0)
    Z, future = profit_data(seed=99)
    helped = future > 0
    score = ProfitLossBoosting(seed=1).fit(X, profit).score(Z)
    assert spearmanr(score[helped], future[helped]).statistic > 0.5


def test_a_newton_step_ranks_the_least_helped_customers_first():
    """Why the other variant was not used. The loss's curvature grows with the cube of
    the profit lift, so a Newton step is about one over it: among customers the offer
    helps, the ranking comes out upside down. Recorded so the choice is not a mystery."""
    X, profit = profit_data(seed=0)
    Z, future = profit_data(seed=99)
    helped = future > 0
    score = ProfitLossBoosting(seed=1, newton=True).fit(X, profit).score(Z)
    assert spearmanr(score[helped], future[helped]).statistic < 0
    assert (np.sign(score) == np.sign(future)).mean() > 0.9, "it still finds who to target"


def test_a_customer_counts_in_proportion_to_the_money_at_stake():
    """Symmetric weights. Two kinds of customer share every feature: one stands to gain
    50, three stand to lose 10 each. The larger stake decides the sign of the score."""
    X = pd.DataFrame({"x": np.zeros(400)})
    profit = np.tile([50.0, -10.0, -10.0, -10.0], 100)
    assert ProfitLossBoosting(seed=0).fit(X, profit).score(X)[0] > 0
    assert ProfitLossBoosting(seed=0).fit(X, -profit).score(X)[0] < 0


def test_the_ranking_does_not_depend_on_the_currency():
    """Profit lifts are scaled before fitting, so rupees and paise give one ranking.

    A factor of 128 is exact in floating point, so the scores are identical. A factor of
    100 is not, the last bits of the gradients differ, and a tree can break a tie the
    other way; the ranking is then the same to four decimal places, not to the bit."""
    X, profit = profit_data()
    a = ProfitLossBoosting(seed=3).fit(X, profit).score(X)
    assert np.array_equal(a, ProfitLossBoosting(seed=3).fit(X, profit * 128.0).score(X))
    paise = ProfitLossBoosting(seed=3).fit(X, profit * 100.0).score(X)
    assert spearmanr(a, paise).statistic > 0.999


def test_identical_profit_lifts_give_no_ranking():
    X, _ = profit_data(100)
    assert not ProfitLossBoosting().fit(X, np.full(100, 12.0)).score(X).any()


def test_the_fit_is_reproducible():
    X, profit = profit_data()
    a = ProfitLossBoosting(seed=5).fit(X, profit).score(X)
    assert ProfitLossBoosting(seed=5).fit(X, profit).score(X) == pytest.approx(a)


def test_trees_have_at_most_eight_terminal_nodes_as_in_the_paper():
    X, profit = profit_data()
    model = ProfitLossBoosting(n_rounds=10).fit(X, profit)
    assert max(tree.get_n_leaves() for tree, _ in model._trees) <= 8


def test_large_profit_lifts_do_not_overflow():
    """Equation 7 puts the profit lift in an exponent. Unscaled, a lift of a few
    thousand in currency units overflows."""
    X, profit = profit_data()
    score = ProfitLossBoosting().fit(X, profit * 1e6).score(X)
    assert np.isfinite(score).all()


def test_a_missing_profit_lift_is_refused():
    X, profit = profit_data(50)
    profit[3] = np.nan
    with pytest.raises(ValueError, match="finite"):
        ProfitLossBoosting().fit(X, profit)


def test_one_profit_lift_per_customer_is_required():
    X, profit = profit_data(50)
    with pytest.raises(ValueError, match="per customer"):
        ProfitLossBoosting().fit(X, profit[:40])


def test_the_share_returned_never_exceeds_the_ceiling_by_a_rounding_step():
    """Seven customers and a 30% ceiling: the nearest whole size is two, and two of
    seven is 28.6%. With thirteen it is four, and four of thirteen is 30.8%. The share
    handed back is held to the ceiling so a later campaign cannot be a customer over."""
    n = 13
    treated = np.arange(n) % 2
    churned = np.where(treated == 1, 0.0, 1.0)      # the offer always works
    fraction, profit = choose_fraction(np.arange(n, 0, -1.0), treated, churned,
                                       np.full(n, 100.0), 1.0, max_fraction=0.30, min_arm=1)
    assert profit > 0
    assert fraction == pytest.approx(0.30) and fraction <= 0.30
