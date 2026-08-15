"""Tests for reason codes (D-059).

An explanation layer is the easiest place in a system to lie, because it is the only
layer anyone reads and nothing downstream checks it. Most of what is pinned here is
therefore that the words match the arithmetic: that the attribution is exact rather than
plausible, that a feature described as "higher than typical" really is, and that a
recommendation with no per-customer evidence behind it says so instead of manufacturing
three confident-sounding drivers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

from retainiq.models.uplift import HierarchicalCATE
from retainiq.policy.ladder import ABSTAIN, LadderOptimiser, Recommendation
from retainiq.report.reasons import FEATURE_PHRASES, Reason, explain, render


def _fit(n=900, het=1.2, seed=0):
    r = np.random.default_rng(seed)
    X = pd.DataFrame(r.normal(size=(n, 3)),
                     columns=["mrr", "sessions_30d", "champion_departed"])
    t = r.integers(0, 2, n)
    tau = -0.8 + het * X["mrr"].to_numpy()
    y = (r.random(n) < expit(-0.5 + 0.6 * X["sessions_30d"].to_numpy() + t * tau)).astype(int)
    return X, HierarchicalCATE().fit(X, t, y)


# --- the attribution is exact ------------------------------------------------


def test_contributions_sum_to_the_deviation_from_the_average_effect():
    """The identity that makes this exact rather than approximate: rows sum to
    `tau_i - tau_0`. A SHAP implementation would only approach this."""
    X, m = _fit()
    contrib = m.effect_contributions(X)
    p = m.n_features_
    tau_0 = m.theta_[p + 1]
    assert np.allclose(contrib.sum(axis=1), m.posterior(X).mean - tau_0, atol=1e-9)


def test_contributions_are_zero_when_heterogeneity_collapses():
    """At small n the marginal likelihood drives sigma_gamma to zero and every customer
    gets the average effect. The attribution must then be empty, not noise."""
    X, m = _fit(n=400, het=0.0, seed=4)
    assert np.abs(m.effect_contributions(X)).max() < 0.05


def test_contributions_require_a_fit_and_matching_columns():
    X, m = _fit(n=300)
    with pytest.raises(ValueError, match="expected"):
        m.effect_contributions(X[["mrr", "sessions_30d"]])
    with pytest.raises(RuntimeError, match="fit"):
        HierarchicalCATE().effect_contributions(X)
    with pytest.raises(RuntimeError, match="fit"):
        HierarchicalCATE().standardised_features(X)


def test_standardised_features_are_centred():
    X, m = _fit()
    assert np.allclose(m.standardised_features(X).mean(axis=0), 0.0, atol=1e-9)


# --- the words match the arithmetic ------------------------------------------


def _rec(n, rung, value_by_rung, conf, trimmed=None, ev=None):
    return Recommendation(
        rung=np.asarray(rung),
        expected_value=np.asarray(ev if ev is not None else [100.0] * n),
        confidence=np.asarray(conf),
        value_by_rung=np.asarray(value_by_rung, dtype=float),
        budget_trimmed=np.asarray(trimmed if trimmed is not None else [False] * n),
    )


def test_direction_words_track_the_customers_actual_position():
    """The bug this test exists for: describing every driver as 'higher than typical'
    regardless of whether the customer is above or below average, which produced
    explanations that contradicted themselves."""
    X, m = _fit()
    xs = m.standardised_features(X)
    contrib = m.effect_contributions(X)
    # Pick the customer furthest below average on the feature that matters most.
    j = int(np.abs(contrib).mean(axis=0).argmax())
    i = int(xs[:, j].argmin())
    rec = _rec(len(X), np.zeros(len(X), int), np.zeros((len(X), 1)), np.full(len(X), 0.9))
    rs = explain(rec, m, X, ["nudge"], np.full(len(X), 500.0), np.zeros((len(X), 1)))
    joined = " ".join(rs[i].drivers)
    assert "lower than typical" in joined
    assert xs[i, j] < 0


def test_a_recommendation_with_no_personal_signal_admits_it():
    """When sigma_gamma has collapsed there is no per-customer evidence. Inventing
    three drivers anyway is what a SHAP-over-a-classifier explainer would do."""
    X, m = _fit(n=400, het=0.0, seed=4)
    n = len(X)
    rec = _rec(n, np.zeros(n, int), np.zeros((n, 1)), np.full(n, 0.9))
    rs = explain(rec, m, X, ["nudge"], np.full(n, 500.0), np.zeros((n, 1)))
    assert any("nothing specific" in d for d in rs[0].drivers)
    assert len(rs[0].drivers) == 1


def test_drivers_that_oppose_the_action_are_flagged_not_hidden():
    X, m = _fit()
    n = len(X)
    rec = _rec(n, np.zeros(n, int), np.zeros((n, 1)), np.full(n, 0.9))
    rs = explain(rec, m, X, ["nudge"], np.full(n, 500.0), np.zeros((n, 1)))
    contrib = m.effect_contributions(X)
    def _opposes(i):
        return contrib[i, np.argsort(-np.abs(contrib[i]))[:3]].sum() > 0

    opposing = [r for r in rs if _opposes(r.index)]
    assert opposing, "fixture should contain customers whose profile argues against"
    assert any("argues *against*" in d for d in opposing[0].drivers)


# --- abstention says which kind ----------------------------------------------


def test_budget_abstention_is_distinguished_from_unprofitable():
    n = 2
    rec = _rec(n, [ABSTAIN, ABSTAIN], [[50.0], [-9.0]], [0.0, 0.0],
               trimmed=[True, False], ev=[0.0, 0.0])
    X, m = _fit(n=n * 200)
    rs = explain(rec, m, X.iloc[:n], ["nudge"], np.full(n, 100.0), np.zeros((n, 1)))
    assert "budget" in rs[0].economics
    assert "pays for itself" in rs[1].economics
    assert not rs[0].is_action and not rs[1].is_action


# --- caveats -----------------------------------------------------------------


def test_thin_evidence_is_flagged():
    X, m = _fit()
    n = len(X)
    rec = _rec(n, np.zeros(n, int), np.zeros((n, 1)), np.full(n, 0.55))
    rs = explain(rec, m, X, ["nudge"], np.full(n, 500.0), np.zeros((n, 1)))
    assert "thin evidence" in rs[0].caveat


def test_immaterial_gain_is_flagged():
    X, m = _fit()
    n = len(X)
    rec = _rec(n, np.zeros(n, int), np.zeros((n, 1)), np.full(n, 0.95),
               ev=np.full(n, 0.01))
    rs = explain(rec, m, X, ["nudge"], np.full(n, 500.0), np.zeros((n, 1)))
    assert "too small" in rs[0].caveat


def test_reliability_note_reaches_every_recommendation():
    """D-058 measured 58% [0.42, 0.72]. A per-customer output that does not carry that
    is claiming more than the project demonstrated."""
    X, m = _fit()
    n = len(X)
    rec = _rec(n, np.zeros(n, int), np.zeros((n, 1)), np.full(n, 0.95))
    rs = explain(rec, m, X, ["nudge"], np.full(n, 500.0), np.zeros((n, 1)),
                 reliability_note="not proven")
    assert all("not proven" in r.caveat for r in rs if r.is_action)


# --- rendering ---------------------------------------------------------------


def test_render_puts_actions_first_and_orders_by_money():
    rs = [
        Reason(index=0, action="no offer", expected_value=0.0, confidence=0.0,
               economics="budget"),
        Reason(index=1, action="nudge", expected_value=10.0, confidence=0.8),
        Reason(index=2, action="call", expected_value=99.0, confidence=0.8),
    ]
    txt = render(rs)
    assert txt.index("call") < txt.index("nudge") < txt.index("Left alone")
    assert "1 customers to contact" not in txt      # two actions, one skip
    assert "2 customers to contact, 1 to leave alone." in txt


def test_render_uses_supplied_ids():
    rs = [Reason(index=0, action="nudge", expected_value=5.0, confidence=0.9)]
    assert "customer cust_42" in render(rs, ids=["cust_42"])


def test_unknown_features_degrade_to_readable_names():
    """A tenant schema we have never seen must not raise."""
    assert "weird_col" not in FEATURE_PHRASES
    r = np.random.default_rng(0)
    X = pd.DataFrame(r.normal(size=(400, 2)), columns=["weird_col", "mrr"])
    t = r.integers(0, 2, 400)
    y = (r.random(400) < expit(-0.4 + t * (-0.8 + X["weird_col"]))).astype(int)
    m = HierarchicalCATE().fit(X, t, y)
    rec = _rec(400, np.zeros(400, int), np.zeros((400, 1)), np.full(400, 0.9))
    rs = explain(rec, m, X, ["nudge"], np.full(400, 500.0), np.zeros((400, 1)))
    assert any("weird col" in d for r_ in rs for d in r_.drivers)


def test_shape_mismatches_are_refused():
    X, m = _fit(n=400)
    rec = _rec(400, np.zeros(400, int), np.zeros((400, 1)), np.full(400, 0.9))
    with pytest.raises(ValueError, match="rows"):
        explain(rec, m, X.iloc[:10], ["nudge"], np.full(10, 1.0), np.zeros((10, 1)))
    with pytest.raises(ValueError, match="offer names"):
        explain(rec, m, X, ["a", "b"], np.full(400, 1.0), np.zeros((400, 1)))


def test_end_to_end_from_the_optimiser():
    """The real path: a fitted ladder produces reasons for every customer, and every
    treated customer gets a rung name that exists."""
    r = np.random.default_rng(3)
    n, K = 900, 3
    X = pd.DataFrame(r.normal(size=(n, 3)),
                     columns=["mrr", "sessions_30d", "champion_departed"])
    arm = r.integers(0, K + 1, n)
    y = (r.random(n) < expit(-0.6 + 0.5 * X["mrr"].to_numpy() - 0.6 * arm)).astype(int)
    names = ["nudge", "call", "discount"]
    opt = LadderOptimiser(risk_aversion=0.0, budget=0.3).fit(X, arm, y, K)
    rec = opt.recommend(X, np.full(n, 800.0), np.tile([0.1, 6.0, 30.0], (n, 1)))
    rs = explain(rec, opt.models_[0], X, names, np.full(n, 800.0),
                 np.tile([0.1, 6.0, 30.0], (n, 1)))
    assert len(rs) == n
    assert all(r_.action in names or r_.action == "no offer" for r_ in rs)
    assert "RETENTION RECOMMENDATIONS" in render(rs, limit=3)
