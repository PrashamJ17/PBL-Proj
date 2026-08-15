"""Tests for the money conversion and the offer-ladder optimiser (D-057, D-058).

The first half of this file exists because Phase 4 multiplied a log-odds ratio by a
currency amount for an entire phase without anything catching it. The tests that would
have caught it are the ones that check a *known* answer rather than an internal
consistency property: the estimator was self-consistent throughout, and the decision
rule's own tests passed, because none of them ever asked what the number meant.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit, logit

from retainiq.models.uplift import AbstentionPolicy, HierarchicalCATE
from retainiq.policy.economics import (
    MoneyPosterior,
    benefit_posterior,
    probability_effect,
)
from retainiq.policy.ladder import ABSTAIN, LadderOptimiser


def _data(n=800, het=0.9, seed=0, p=4):
    r = np.random.default_rng(seed)
    X = pd.DataFrame(r.normal(size=(n, p)), columns=[f"x{i}" for i in range(p)])
    t = r.integers(0, 2, n)
    tau = -0.8 + het * X["x0"].to_numpy()
    eta = -0.5 + 0.6 * X["x1"].to_numpy() + t * tau
    y = (r.random(n) < expit(eta)).astype(int)
    return X, t, y


# --- the conversion, against arithmetic done by hand ------------------------


def test_probability_effect_matches_the_definition():
    """A known answer, not a self-consistency check. p0 = 0.25 shifted by -0.8 in
    log-odds lands at 0.13027, so delta_p is -0.11973 -- not -0.8."""
    p0 = 0.25
    dp = probability_effect(np.array([logit(p0)]), np.array([-0.8]))
    assert dp[0] == pytest.approx(expit(logit(0.25) - 0.8) - 0.25, abs=1e-12)
    assert dp[0] == pytest.approx(-0.11973, abs=1e-5)
    assert abs(dp[0]) < 0.8, "the log-odds shift is not the probability change"


def test_the_distortion_is_worst_for_low_risk_customers():
    """The reason D-057 mattered rather than merely being untidy. Treating log-odds as
    probability overstates the benefit by ~1/(p0(1-p0)), so it inflates the value of
    treating people who were never going to leave -- the Sure Thing quadrant."""
    tau = np.array([-0.5])
    ratios = []
    for p0 in (0.5, 0.2, 0.05):
        dp = probability_effect(np.array([logit(p0)]), tau)[0]
        ratios.append(abs(tau[0]) / abs(dp))
    assert ratios[0] < ratios[1] < ratios[2]
    assert ratios[0] < 5 and ratios[2] > 15


def test_zero_effect_is_zero_money_at_any_baseline():
    eta0 = np.linspace(-4, 4, 50)
    assert np.allclose(probability_effect(eta0, np.zeros_like(eta0)), 0.0, atol=1e-12)


def test_benefit_posterior_is_in_currency_and_respects_cost():
    X, t, y = _data()
    m = HierarchicalCATE().fit(X, t, y)
    value = np.full(len(X), 500.0)
    cheap = benefit_posterior(m, X, value, 1.0, n_samples=200)
    dear = benefit_posterior(m, X, value, 400.0, n_samples=200)
    # Same effect, higher price: benefit must drop by exactly the price difference.
    assert np.allclose(cheap.mean - dear.mean, 399.0, atol=1e-6)
    assert (dear.prob_positive() <= cheap.prob_positive()).all()


def test_benefit_scales_linearly_with_customer_value():
    X, t, y = _data()
    m = HierarchicalCATE().fit(X, t, y)
    a = benefit_posterior(m, X, np.full(len(X), 100.0), 0.0, n_samples=200)
    b = benefit_posterior(m, X, np.full(len(X), 200.0), 0.0, n_samples=200)
    assert np.allclose(2 * a.mean, b.mean, rtol=1e-9)


def test_delta_p_stays_a_probability():
    """expit differences are bounded by construction; a rule thresholding money built
    from something outside [-1, 1] would be meaningless."""
    X, t, y = _data()
    m = HierarchicalCATE().fit(X, t, y)
    mp = benefit_posterior(m, X, np.full(len(X), 300.0), 5.0, n_samples=200)
    assert (mp.delta_p >= -1.0).all() and (mp.delta_p <= 1.0).all()


def test_joint_samples_are_correlated_not_independent():
    """Baseline and effect come from one coefficient vector. Drawing them separately
    would misstate the spread of delta_p, which is the quantity being thresholded."""
    X, t, y = _data()
    m = HierarchicalCATE().fit(X, t, y)
    eta0, tau = m.joint_samples(X, n_samples=400, seed=1)
    assert eta0.shape == tau.shape == (len(X), 400)
    # Per-customer correlation across draws should be non-trivial for most customers.
    c = [np.corrcoef(eta0[i], tau[i])[0, 1] for i in range(0, len(X), 40)]
    assert np.mean(np.abs(c)) > 0.05


def test_joint_samples_reproduce_the_marginal_posterior():
    """Sampling must agree with the closed form it replaces, or the correction traded
    one wrong number for another."""
    X, t, y = _data()
    m = HierarchicalCATE().fit(X, t, y)
    _, tau = m.joint_samples(X, n_samples=4000, seed=2)
    closed = m.posterior(X)
    assert np.corrcoef(tau.mean(axis=1), closed.mean)[0, 1] > 0.99
    assert tau.std(axis=1).mean() == pytest.approx(closed.sd.mean(), rel=0.10)


def test_money_posterior_rejects_bad_input():
    X, t, y = _data(n=300)
    m = HierarchicalCATE().fit(X, t, y)
    with pytest.raises(ValueError, match="cannot be negative"):
        benefit_posterior(m, X, np.full(len(X), -1.0), 1.0)
    with pytest.raises(ValueError, match="cost cannot be negative"):
        benefit_posterior(m, X, np.full(len(X), 10.0), -1.0)
    with pytest.raises(ValueError, match="same shape"):
        MoneyPosterior(samples=np.zeros((3, 2)), delta_p=np.zeros((3, 5)))


def test_decide_money_treats_a_certain_bargain_and_refuses_a_certain_loss():
    n = 6
    win = MoneyPosterior(samples=np.full((n, 50), 100.0), delta_p=np.zeros((n, 50)))
    lose = MoneyPosterior(samples=np.full((n, 50), -100.0), delta_p=np.zeros((n, 50)))
    assert AbstentionPolicy(alpha=0.3).decide_money(win).treat.all()
    assert not AbstentionPolicy(alpha=0.3, budget=1.0).decide_money(lose).treat.any()


def test_decide_money_budget_keeps_the_most_valuable():
    rng = np.random.default_rng(0)
    means = np.array([10.0, 900.0, 800.0])
    s = means[:, None] + rng.normal(0, 1.0, (3, 400))
    mp = MoneyPosterior(samples=s, delta_p=np.zeros_like(s))
    d = AbstentionPolicy(alpha=0.4, budget=1 / 3).decide_money(mp)
    assert d.treat[1] and not d.treat[0]


# --- the ladder optimiser ----------------------------------------------------


def _multi_arm(n=900, K=3, seed=0):
    r = np.random.default_rng(seed)
    X = pd.DataFrame(r.normal(size=(n, 3)), columns=["x0", "x1", "x2"])
    arm = r.integers(0, K + 1, n)
    # Rung k has effect -(k+1)*0.6: later rungs help more, as the ladder intends.
    tau = np.where(arm == 0, 0.0, -(arm) * 0.6)
    eta = -0.6 + 0.5 * X["x0"].to_numpy() + tau
    y = (r.random(n) < expit(eta)).astype(int)
    return X, arm, y, K


def test_optimiser_prefers_the_rung_that_actually_works_when_costs_are_equal():
    """With identical costs the choice is driven purely by effect, and the strongest
    rung should win. If this fails the optimiser is not reading its own models."""
    X, arm, y, K = _multi_arm()
    opt = LadderOptimiser(risk_aversion=0.0).fit(X, arm, y, K)
    rec = opt.recommend(X, np.full(len(X), 400.0), np.zeros((len(X), K)))
    treated = rec.rung[rec.rung != ABSTAIN]
    assert len(treated) > 0
    assert np.bincount(treated, minlength=K).argmax() == K - 1


def test_optimiser_abstains_when_every_rung_costs_more_than_it_returns():
    X, arm, y, K = _multi_arm()
    opt = LadderOptimiser(risk_aversion=0.0).fit(X, arm, y, K)
    rec = opt.recommend(X, np.full(len(X), 10.0), np.full((len(X), K), 10_000.0))
    assert rec.n_treated == 0
    assert (rec.expected_value == 0).all()


def test_cheaper_rung_wins_when_effects_are_equal():
    """The ladder's whole premise: prefer the cheapest thing that works."""
    X, arm, y, K = _multi_arm()
    opt = LadderOptimiser(risk_aversion=0.0).fit(X, arm, y, K)
    # Make the strongest rung expensive and an equal-effect alternative free.
    costs = np.zeros((len(X), K))
    costs[:, K - 1] = 300.0
    rec = opt.recommend(X, np.full(len(X), 400.0), costs)
    assert (rec.rung == K - 1).sum() < (rec.rung != ABSTAIN).sum() / 2


def test_risk_aversion_monotonically_reduces_treatment():
    X, arm, y, K = _multi_arm()
    counts = []
    for lam in (0.0, 0.5, 2.0, 8.0):
        opt = LadderOptimiser(risk_aversion=lam).fit(X, arm, y, K)
        counts.append(opt.recommend(X, np.full(len(X), 400.0),
                                    np.full((len(X), K), 20.0)).n_treated)
    assert counts == sorted(counts, reverse=True)


def test_budget_is_a_ceiling():
    X, arm, y, K = _multi_arm()
    opt = LadderOptimiser(risk_aversion=0.0, budget=0.1).fit(X, arm, y, K)
    rec = opt.recommend(X, np.full(len(X), 400.0), np.zeros((len(X), K)))
    assert rec.n_treated <= int(round(0.1 * len(X))) + 1


def test_pilot_without_a_control_arm_is_refused():
    X, arm, y, K = _multi_arm()
    with pytest.raises(ValueError, match="no control arm"):
        LadderOptimiser().fit(X, np.maximum(arm, 1), y, K)


def test_an_untried_rung_is_never_recommended():
    """A rung absent from the pilot has no evidence. Falling back to another rung's
    effect would invent it."""
    X, arm, y, K = _multi_arm()
    arm = np.where(arm == K, 0, arm)          # rung K-1 was never administered
    opt = LadderOptimiser(risk_aversion=0.0).fit(X, arm, y, K)
    assert opt.models_[K - 1] is None
    rec = opt.recommend(X, np.full(len(X), 400.0), np.zeros((len(X), K)))
    assert not (rec.rung == K - 1).any()


def test_recommend_before_fit_is_refused():
    with pytest.raises(RuntimeError, match="fit"):
        LadderOptimiser().recommend(pd.DataFrame({"a": [1.0]}), np.array([1.0]),
                                    np.zeros((1, 1)))


def test_cost_matrix_shape_is_checked():
    X, arm, y, K = _multi_arm()
    opt = LadderOptimiser().fit(X, arm, y, K)
    with pytest.raises(ValueError, match="costs must be"):
        opt.recommend(X, np.full(len(X), 100.0), np.zeros((len(X), K + 2)))
