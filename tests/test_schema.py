"""Tests for the canonical schema.

The load-bearing test here is `test_rejects_available_before_occurred`. Every
point-in-time guarantee downstream rests on the assumption that a fact cannot become
knowable before it happens. If a bad ingest adapter can write such a row, the feature
store's filtering is meaningless and nothing built on it can be trusted.
"""

from __future__ import annotations

import pandas as pd
import pytest

from keel.core.schema import (
    INVOICES,
    TABLES,
    Dataset,
    SchemaError,
    empty,
    validate,
)
from keel.ingest.subsim_adapter import to_canonical
from keel.sim import SimConfig, simulate

CFG = SimConfig(n_customers=300, n_months=12, seed=7)


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return to_canonical(simulate(CFG))


# --- structure --------------------------------------------------------------


def test_adapter_produces_a_valid_dataset(dataset):
    dataset.validate()


def test_every_fact_table_declares_both_timestamps():
    for table in TABLES.values():
        if table.is_fact:
            assert table.available_at, f"{table.name} is a fact table without available_at"
            assert table.occurred_at in table.names
            assert table.available_at in table.names


def test_empty_frames_carry_the_schema():
    for table in TABLES.values():
        frame = empty(table)
        assert list(frame.columns) == table.names
        validate(frame, table)


# --- validation catches real problems ---------------------------------------


def test_rejects_available_before_occurred(dataset):
    """A fact cannot be knowable before it occurs.

    This is the invariant the entire feature store depends on."""
    bad = dataset.invoices.copy()
    bad.loc[bad.index[0], "available_at"] = (
        bad.loc[bad.index[0], "attempted_at"] - pd.Timedelta(days=1)
    )
    with pytest.raises(SchemaError, match="knowable before it occurs"):
        validate(bad, INVOICES)


def test_rejects_duplicate_keys(dataset):
    bad = pd.concat([dataset.invoices, dataset.invoices.head(1)], ignore_index=True)
    with pytest.raises(SchemaError, match="duplicate"):
        validate(bad, INVOICES)


def test_rejects_missing_columns(dataset):
    with pytest.raises(SchemaError, match="missing columns"):
        validate(dataset.invoices.drop(columns=["status"]), INVOICES)


def test_rejects_nulls_in_non_nullable_columns(dataset):
    bad = dataset.invoices.copy()
    bad.loc[bad.index[0], "amount"] = None
    with pytest.raises(SchemaError, match="non-nullable"):
        validate(bad, INVOICES)


def test_allows_nulls_in_nullable_columns(dataset):
    """`ended_at` is null for active subscriptions -- that is right, not missing
    data. Conflating the two is how censored customers get mislabelled."""
    assert dataset.subscriptions["ended_at"].isna().any()
    dataset.validate()


def test_rejects_orphan_references(dataset):
    bad = dataset.invoices.copy()
    bad.loc[bad.index[0], "customer_id"] = "does_not_exist"
    ds = Dataset(
        customers=dataset.customers,
        subscriptions=dataset.subscriptions,
        invoices=bad,
        events=dataset.events,
        tickets=dataset.tickets,
    )
    with pytest.raises(SchemaError, match="unknown customers"):
        ds.validate()


# --- the adapter's semantics ------------------------------------------------


def test_churned_subscriptions_have_an_end_date(dataset):
    canceled = dataset.subscriptions[dataset.subscriptions["status"] == "canceled"]
    assert len(canceled) > 0
    assert canceled["ended_at"].notna().all()


def test_active_subscriptions_have_no_end_date(dataset):
    active = dataset.subscriptions[dataset.subscriptions["status"] == "active"]
    assert active["ended_at"].isna().all()


def test_availability_lag_is_actually_present(dataset):
    """If nothing arrived late, the point-in-time machinery would be untested --
    filtering on available_at and on occurred_at would give identical answers and a
    bug in that logic could never surface."""
    event_lag = dataset.events["available_at"] - dataset.events["occurred_at"]
    assert (event_lag > pd.Timedelta(0)).all()

    failed = dataset.invoices[dataset.invoices["status"] == "failed"]
    settle = failed["available_at"] - failed["attempted_at"]
    assert (settle > pd.Timedelta(hours=1)).all(), "decline codes should settle late"


def test_paid_invoices_settle_immediately(dataset):
    paid = dataset.invoices[dataset.invoices["status"] == "paid"]
    assert (paid["available_at"] == paid["attempted_at"]).all()


def test_adapter_is_deterministic():
    a = to_canonical(simulate(CFG), seed=1)
    b = to_canonical(simulate(CFG), seed=1)
    assert a.events.equals(b.events)
    assert a.invoices.equals(b.invoices)


# --- edge cases -------------------------------------------------------------


def test_adapter_handles_tiny_population():
    ds = to_canonical(simulate(SimConfig(n_customers=1, n_months=6, seed=3)))
    ds.validate()
    assert len(ds.customers) == 1


def test_adapter_handles_zero_customers():
    ds = to_canonical(simulate(SimConfig(n_customers=0, n_months=6, seed=3)))
    ds.validate()
    assert ds.customers.empty and ds.invoices.empty


def test_adapter_handles_no_events():
    """A tenant with billing but no product-usage integration. The system must
    still work -- most small businesses will never instrument their product."""
    from dataclasses import replace

    sim = simulate(replace(CFG, hazard=replace(CFG.hazard, intercept=-20.0)))
    ds = to_canonical(sim)
    ds.validate()
