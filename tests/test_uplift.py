"""Tests for the Phase 4 estimator and decision rule.

The tests that matter here pin the *mechanism*, because the Phase 4 result is a
partial negative (D-054) and a negative result is only worth anything if the thing
that produced it demonstrably works.

Specifically: that pooling collapses when heterogeneity is unsupported, that the
abstention rule reduces to a point threshold as the posterior concentrates and to
treating nobody as it widens, and that the posterior is a real posterior rather than
a point estimate with error bars attached.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from retainiq.models.uplift import (
    AbstentionPolicy,
    CATEPosterior,
    HierarchicalCATE,
    pool_across_tenants,
)
from retainiq.models.uplift.abstention import top_k_by_point_estimate


def _data(n=600, het=0.9, seed=0, p=4):
    """Logistic outcome with a treatment effect linear in x0."""
    r = np.random.default_rng(seed)
    X = pd.DataFrame(r.normal(size=(n, p)), columns=[f"x{i}" for i in range(p)])
    t = r.integers(0, 2, n)
    tau = -0.8 + het * X["x0"].to_numpy()
    eta = -0.5 + 0.6 * X["x1"].to_numpy() + t * tau
    y = (r.random(n) < 1.0 / (1.0 + np.exp(-eta))).astype(int)
    return X, t, y, tau


# --- the posterior is a posterior -------------------------------------------


def test_posterior_is_a_mixture_that_sums_to_one():
    X, t, y, _ = _data()
    po = HierarchicalCATE().fit(X, t, y).posterior(X)
    assert po.means.shape == po.sds.shape
    assert po.means.shape[1] > 1, "should retain the sigma_gamma grid, not collapse it"
    assert po.weights.sum() == pytest.approx(1.0)
    assert (po.sds > 0).all()


def test_mixture_moments_match_a_single_gaussian_when_there_is_one_component():
    m, s = np.array([0.0, -1.0]), np.array([1.0, 0.5])
    po = CATEPosterior(means=m[:, None], sds=s[:, None], weights=np.array([1.0]))
    assert np.allclose(po.mean, m)
    assert np.allclose(po.sd, s)
    lo, hi = po.interval(0.90)
    assert np.allclose(lo, stats.norm.ppf(0.05, m, s), atol=1e-6)
    assert np.allclose(hi, stats.norm.ppf(0.95, m, s), atol=1e-6)


def test_prob_below_is_a_valid_cdf():
    X, t, y, _ = _data()
    po = HierarchicalCATE().fit(X, t, y).posterior(X)
    assert ((po.prob_below(0.0) >= 0) & (po.prob_below(0.0) <= 1)).all()
    # Monotone in the threshold.
    assert (po.prob_below(-5.0) <= po.prob_below(0.0)).all()
    assert (po.prob_below(0.0) <= po.prob_below(5.0)).all()


def test_posterior_narrows_with_more_data():
    """The property the whole phase rests on: uncertainty must actually respond to
    how much evidence there is, or thresholding it means nothing."""
    sds = []
    for n in (250, 1000, 4000):
        X, t, y, _ = _data(n=n, seed=3)
        sds.append(HierarchicalCATE().fit(X, t, y).posterior(X).sd.mean())
    assert sds[0] > sds[1] > sds[2]


# --- the pooling mechanism --------------------------------------------------


def test_pooling_collapses_when_there_is_no_heterogeneity():
    """With a homogeneous effect the marginal likelihood should drive sigma_gamma to
    zero and every tau_i onto the same number.

    This is the mechanism that makes small n survivable: the model degrades into
    'estimate one average effect well' rather than 'estimate n effects badly'."""
    X, t, y, _ = _data(n=3000, het=0.0, seed=5)
    m = HierarchicalCATE().fit(X, t, y)
    po = m.posterior(X)
    assert m.sigma_gamma_ < 0.05, f"sigma_gamma={m.sigma_gamma_:.3f}, expected collapse"
    assert po.mean.std() < 0.05, "tau_i should be nearly constant"


def test_pooling_does_not_collapse_when_heterogeneity_is_real():
    """The complement. A model that always pooled would pass the test above for the
    wrong reason."""
    X, t, y, tau = _data(n=3000, het=1.2, seed=5)
    m = HierarchicalCATE().fit(X, t, y)
    assert m.sigma_gamma_ > 0.1
    assert np.corrcoef(m.posterior(X).mean, tau)[0, 1] > 0.8


def test_tenant_prior_shifts_the_average_effect():
    """Cross-tenant pooling (D-041): a firm with little data should be pulled toward
    what similar firms established."""
    X, t, y, _ = _data(n=200, seed=11)
    alone = HierarchicalCATE().fit(X, t, y)
    pulled = HierarchicalCATE(tenant_prior=(-2.0, 0.15)).fit(X, t, y)
    i = alone.n_features_ + 1
    assert pulled.theta_[i] < alone.theta_[i], "a strong prior should pull tau_0 down"


def test_pool_across_tenants_widens_for_disagreement():
    """The population prior must carry between-firm spread. Treating noisy per-firm
    estimates as known would understate it and make a new tenant over-confident --
    the failure this phase exists to avoid."""
    fits = [HierarchicalCATE().fit(*_data(n=800, seed=s)[:3]) for s in (1, 2, 3, 4)]
    mean, sd = pool_across_tenants(fits)
    assert np.isfinite(mean) and sd > 0

    for f, shift in zip(fits, (-3.0, 3.0, -3.0, 3.0), strict=True):
        f.theta_ = f.theta_.copy()
        f.theta_[f.n_features_ + 1] += shift
    _, wide_sd = pool_across_tenants(fits)
    assert wide_sd > sd, "disagreeing firms must produce a wider prior"


def test_pooling_refuses_an_empty_population():
    with pytest.raises(ValueError, match="no fitted tenants"):
        pool_across_tenants([])


# --- the decision rule ------------------------------------------------------


def _posterior(mean, sd):
    return CATEPosterior(
        means=np.asarray(mean, float)[:, None],
        sds=np.asarray(sd, float)[:, None],
        weights=np.array([1.0]),
    )


def test_confident_benefit_is_treated():
    po = _posterior([-1.0, -1.0], [0.01, 0.01])
    d = AbstentionPolicy(alpha=0.30).decide(po, value=np.array([100.0, 100.0]), cost=5.0)
    assert d.treat.all()


def test_confident_harm_is_never_treated():
    """tau > 0 is the sleeping-dog direction. No budget should tempt the rule."""
    po = _posterior([+1.0, +1.0], [0.01, 0.01])
    d = AbstentionPolicy(alpha=0.30, budget=1.0).decide(po, np.array([100.0, 100.0]), 5.0)
    assert not d.treat.any()


def test_wide_posterior_abstains():
    """Same mean, more uncertainty -- the rule must decline. This is the difference
    between the policy and a point-estimate threshold."""
    val, cost = np.array([100.0]), 5.0
    sharp = AbstentionPolicy(alpha=0.10).decide(_posterior([-0.2], [0.01]), val, cost)
    vague = AbstentionPolicy(alpha=0.10).decide(_posterior([-0.2], [5.00]), val, cost)
    assert sharp.treat[0]
    assert not vague.treat[0]


def test_rule_reduces_to_a_point_threshold_as_the_posterior_concentrates():
    """A stated property of the rule, not an accident of the parameters."""
    rng = np.random.default_rng(0)
    mean = rng.normal(-0.3, 0.4, 200)
    value = rng.uniform(50, 500, 200)
    cost = 20.0
    tight = AbstentionPolicy(alpha=0.30, budget=1.0).decide(
        _posterior(mean, np.full(200, 1e-6)), value, cost
    )
    point = (-mean * value - cost) > 0
    assert np.array_equal(tight.treat, point)


def test_cost_above_benefit_is_refused_however_certain():
    """Confidence in a small effect is not a reason to overpay."""
    po = _posterior([-0.01], [1e-6])
    d = AbstentionPolicy(alpha=0.50).decide(po, value=np.array([10.0]), cost=100.0)
    assert not d.treat[0]


def test_budget_is_a_ceiling_not_a_quota():
    """The core asymmetry. Top-k always spends its budget; this rule may spend less."""
    po = _posterior(np.full(100, +0.5), np.full(100, 0.01))   # everyone is harmed
    d = AbstentionPolicy(alpha=0.30, budget=0.5).decide(po, np.full(100, 100.0), 5.0)
    assert d.n_treated == 0

    top_k = top_k_by_point_estimate(np.full(100, +0.5), np.full(100, 100.0), 5.0, 0.5)
    assert top_k.sum() == 50, "the comparator always fills its budget"


def test_budget_keeps_the_most_valuable_not_the_most_certain():
    """Confidence gates; money ranks. Ranking on confidence would prefer certain
    trivialities over uncertain large wins."""
    mean = np.array([-0.5, -0.5, -0.5])
    sd = np.array([0.001, 0.10, 0.10])
    value = np.array([10.0, 1000.0, 900.0])
    d = AbstentionPolicy(alpha=0.40, budget=1 / 3).decide(_posterior(mean, sd), value, 1.0)
    assert d.treat[1], "should keep the highest expected value, not the most certain"
    assert not d.treat[0]


def test_alpha_monotonically_reduces_treatment():
    X, t, y, _ = _data(n=800, seed=4)
    po = HierarchicalCATE().fit(X, t, y).posterior(X)
    value = np.full(len(X), 300.0)
    counts = [
        AbstentionPolicy(alpha=a).decide(po, value, 20.0).n_treated
        for a in (0.50, 0.30, 0.10, 0.01)
    ]
    assert counts == sorted(counts, reverse=True)


def test_invalid_parameters_are_refused():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="alpha"):
            AbstentionPolicy(alpha=bad)
    with pytest.raises(ValueError, match="budget"):
        AbstentionPolicy(alpha=0.3, budget=1.5)


def test_negative_customer_value_is_refused():
    po = _posterior([-0.5], [0.1])
    with pytest.raises(ValueError, match="cannot be negative"):
        AbstentionPolicy(alpha=0.3).decide(po, np.array([-10.0]), 5.0)


def test_length_mismatch_is_refused():
    po = _posterior([-0.5, -0.5], [0.1, 0.1])
    with pytest.raises(ValueError, match="customers"):
        AbstentionPolicy(alpha=0.3).decide(po, np.array([100.0]), 5.0)


# --- edge cases -------------------------------------------------------------


def test_constant_outcome_is_refused_with_a_useful_message():
    """A pilot too small to have produced both outcomes. The error should say that,
    not name an optimiser (D-051)."""
    X, t, _, _ = _data(n=200)
    with pytest.raises(ValueError, match="outcome is constant"):
        HierarchicalCATE().fit(X, t, np.zeros(len(X)))


def test_unrandomised_pilot_is_refused():
    """Everyone treated means no counterfactual arm. Usually a sign the 'pilot' was
    a blanket campaign rather than an experiment."""
    X, _, y, _ = _data(n=200)
    with pytest.raises(ValueError, match="both arms"):
        HierarchicalCATE().fit(X, np.ones(len(X)), y)


def test_posterior_before_fit_is_refused():
    X, _, _, _ = _data(n=50)
    with pytest.raises(RuntimeError, match="fit"):
        HierarchicalCATE().posterior(X)


def test_feature_count_mismatch_is_refused():
    X, t, y, _ = _data(n=300)
    m = HierarchicalCATE().fit(X, t, y)
    with pytest.raises(ValueError, match="expected"):
        m.posterior(X[["x0", "x1"]])


def test_zero_value_customers_are_handled():
    """A customer worth nothing makes the benefit degenerate; the comparison is then
    deterministic rather than a division by zero."""
    po = _posterior([-1.0, -1.0], [0.5, 0.5])
    d = AbstentionPolicy(alpha=0.30).decide(po, np.array([0.0, 500.0]), 5.0)
    assert not d.treat[0]
    assert np.isfinite(d.confidence).all()
