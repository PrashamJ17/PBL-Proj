"""Tests for the point-in-time feature store and the leakage suite.

**This file is Phase 1's gate.**

Two tests here matter more than the rest, and both are adversarial:

- `test_audit_catches_unsafe_modes` -- the detector must FAIL on deliberately
  leaked feature vintages. A detector that only ever passes is indistinguishable
  from one that checks nothing.
- `test_canary_is_caught` -- a planted leaked feature must be flagged.

A leakage suite that has never caught a leak is evidence of nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from keel.core.features import (
    FEATURE_NAMES,
    STANDARD_FEATURES,
    FeatureSpec,
    FeatureStore,
    build_standard,
)
from keel.core.leakage import (
    audit_availability,
    audit_time_travel,
    detect_suspicious_features,
    inject_canary,
    model_auc,
)
from keel.ingest.subsim_adapter import at_risk_at, month_timestamps, to_canonical
from keel.sim import SimConfig, simulate

CFG = SimConfig(n_customers=600, n_months=18, seed=7)
MONTHS = [4, 6, 8]


@pytest.fixture(scope="module")
def fixture():
    sim = simulate(CFG)
    ds = to_canonical(sim)
    ts = month_timestamps(MONTHS)
    customers_at = {t: at_risk_at(sim, m) for t, m in zip(ts, MONTHS, strict=False)}
    return sim, ds, ts, customers_at


# --- the guarantee is the default -------------------------------------------


def test_default_mode_is_safe():
    """Nothing in production may construct an unsafe store by accident."""
    store = FeatureStore(_tiny_dataset())
    assert store.mode == FeatureStore.SAFE
    assert store.strict is True


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="unknown mode"):
        FeatureStore(_tiny_dataset(), mode="whatever")


# --- point-in-time correctness ----------------------------------------------


def test_no_future_rows_are_visible(fixture):
    """The core guarantee, checked directly against the source tables."""
    _, ds, ts, _ = fixture
    store = FeatureStore(ds)
    for as_of in ts:
        for table_name in ("invoices", "events", "tickets"):
            rows = store._visible(table_name, as_of)
            if rows.empty:
                continue
            assert (rows["available_at"] <= as_of).all()


def test_availability_audit_passes_on_correct_mode(fixture):
    _, ds, ts, _ = fixture
    store = FeatureStore(ds)
    for as_of in ts:
        report = audit_availability(store, as_of, STANDARD_FEATURES)
        assert report.passed, report.summary()
        assert report.checks_run > 0, "an audit that checked nothing is not a pass"


def test_audit_catches_unsafe_modes(fixture):
    """The detector must have teeth.

    Both unsafe vintages leak by construction, so the audit is required to fail on
    them. If this test passes trivially, the audit is not checking anything."""
    _, ds, ts, _ = fixture
    as_of = ts[1]

    for mode in (FeatureStore.UNSAFE_OCCURRED_ONLY, FeatureStore.UNSAFE_NO_FILTER):
        store = FeatureStore(ds, mode=mode, strict=False)
        report = audit_availability(store, as_of, STANDARD_FEATURES)
        assert not report.passed, f"audit failed to catch mode={mode}"
        assert report.violations


def test_strict_mode_is_enabled_by_default_and_checks(fixture):
    _, ds, ts, _ = fixture
    store = FeatureStore(ds)
    assert store.strict
    store._visible("invoices", ts[0])  # must not raise on valid data


def test_time_travel_consistency(fixture):
    """Features as-of T must not change when later data arrives.

    Built by truncating the dataset at T and comparing against the full dataset.
    If values differ, a feature depends on dataset state rather than history."""
    _, ds, ts, customers_at = fixture
    as_of = ts[1]
    ids = customers_at[as_of]

    from keel.core.schema import Dataset

    def truncate(frame, col):
        return frame[frame[col] <= as_of] if not frame.empty else frame

    truncated = Dataset(
        customers=ds.customers,
        subscriptions=ds.subscriptions,
        invoices=truncate(ds.invoices, "available_at"),
        events=truncate(ds.events, "available_at"),
        tickets=truncate(ds.tickets, "available_at"),
        interventions=ds.interventions,
    )

    report = audit_time_travel(
        FeatureStore(truncated), as_of, ids, STANDARD_FEATURES, FeatureStore(ds)
    )
    assert report.passed, report.summary()


def test_window_features_respect_their_window(fixture):
    """A 30-day count must not include a session from 60 days ago."""
    _, ds, ts, customers_at = fixture
    as_of = ts[2]
    store = FeatureStore(ds)

    spec_30 = FeatureSpec("s30", "events", "count", window_days=30, where={"name": "session_start"})
    spec_all = FeatureSpec("sall", "events", "count", where={"name": "session_start"})

    ids = customers_at[as_of]
    f30 = store.build(as_of, ids, [spec_30])["s30"].sum()
    fall = store.build(as_of, ids, [spec_all])["sall"].sum()
    assert f30 < fall, "a windowed count should be strictly smaller than all history"


# --- the detector actually detects ------------------------------------------


def test_canary_is_caught(fixture):
    """Plant a leaked feature and require the detector to flag it."""
    sim, ds, ts, customers_at = fixture
    X = build_standard(FeatureStore(ds), ts, customers_at)
    y = _labels(sim, MONTHS)

    poisoned, canary_name = inject_canary(X, y, strength=0.9)
    report = detect_suspicious_features(poisoned, y, [*FEATURE_NAMES, canary_name])

    assert not report.passed, "detector missed a planted leak"
    assert canary_name in report.suspicious_features


def test_clean_features_are_not_flagged(fixture):
    """The complement of the canary test: no false alarm on honest features.

    Without this, a detector that flags everything would pass the canary test."""
    sim, ds, ts, customers_at = fixture
    X = build_standard(FeatureStore(ds), ts, customers_at)
    y = _labels(sim, MONTHS)

    report = detect_suspicious_features(X, y, FEATURE_NAMES)
    assert report.passed, report.summary()


def test_no_filter_mode_produces_inflated_auc(fixture):
    """Regression test on the Phase 1 finding.

    Aggregating without a temporal filter makes 'total sessions ever' encode the
    outcome: a customer who churned in month 4 generates no rows afterwards. The
    model looks excellent and has learned only who stopped producing data."""
    sim, ds, ts, customers_at = fixture
    y = _labels(sim, MONTHS)

    correct = model_auc(build_standard(FeatureStore(ds), ts, customers_at), y, FEATURE_NAMES)
    leaked = model_auc(
        build_standard(
            FeatureStore(ds, mode=FeatureStore.UNSAFE_NO_FILTER, strict=False),
            ts, customers_at,
        ),
        y, FEATURE_NAMES,
    )

    assert leaked > correct + 0.15, (
        f"expected substantial inflation from unfiltered features; "
        f"got correct={correct:.3f} leaked={leaked:.3f}"
    )
    assert correct < 0.85, "the correct vintage should not itself look suspicious"


# --- edge cases -------------------------------------------------------------


def test_build_on_empty_customer_list(fixture):
    _, ds, ts, _ = fixture
    out = FeatureStore(ds).build(ts[0], [], STANDARD_FEATURES)
    assert out.empty


def test_build_before_any_data_exists(fixture):
    """As-of a moment before the business had any customers."""
    _, ds, _, customers_at = fixture
    early = pd.Timestamp("2020-01-01")
    ids = next(iter(customers_at.values()))
    out = FeatureStore(ds).build(early, ids, STANDARD_FEATURES)
    assert len(out) == len(ids)
    assert out["sessions_30d"].eq(0).all()


def test_recency_features_use_sentinel_when_never(fixture):
    """'Never happened' must not look like 'happened today'."""
    _, ds, _, customers_at = fixture
    early = pd.Timestamp("2020-01-01")
    ids = next(iter(customers_at.values()))
    out = FeatureStore(ds).build(early, ids, STANDARD_FEATURES)
    assert out["days_since_last_failure"].eq(999.0).all()
    assert out["days_since_last_session"].eq(365.0).all()


def test_features_are_finite(fixture):
    _, ds, ts, customers_at = fixture
    X = build_standard(FeatureStore(ds), ts, customers_at)
    numeric = X.drop(columns=["customer_id", "as_of"])
    assert np.isfinite(numeric.to_numpy(dtype=float)).all()


def test_empty_panel_returns_schema(fixture):
    _, ds, _, _ = fixture
    out = build_standard(FeatureStore(ds), [], {})
    assert out.empty
    assert "customer_id" in out.columns


def test_detector_handles_single_class_outcome(fixture):
    _, ds, ts, customers_at = fixture
    X = build_standard(FeatureStore(ds), ts, customers_at)
    report = detect_suspicious_features(X, np.zeros(len(X), dtype=int), FEATURE_NAMES)
    assert report.passed


# --- helpers ----------------------------------------------------------------


def _labels(sim, months, horizon: int = 3) -> np.ndarray:
    from keel.experiments.leakage_penalty import _outcome

    lab = _outcome(sim, months, horizon=horizon)
    return np.concatenate([lab[m] for m in months])


def _tiny_dataset():
    return to_canonical(simulate(SimConfig(n_customers=20, n_months=4, seed=1)))
