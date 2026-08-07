"""Tests for the CSV ingest path.

This is how the Churn Autopsy diagnostic receives data, so it must tolerate the
shapes real exports arrive in -- while still refusing anything whose *meaning* is
ambiguous.
"""

from __future__ import annotations

import pandas as pd
import pytest

from keel.core.schema import CUSTOMERS, INVOICES, SUBSCRIPTIONS
from keel.ingest.csv_ingest import IngestError, load, load_table, normalise_columns


def _customers_frame(**overrides):
    base = pd.DataFrame({
        "customer_id": ["c1", "c2"],
        "created_at": ["2024-01-01", "2024-01-15"],
        "country": ["IN", "US"],
        "segment": ["smb", "smb"],
    })
    return base.rename(columns=overrides)


def _subs_frame():
    return pd.DataFrame({
        "subscription_id": ["s1", "s2"],
        "customer_id": ["c1", "c2"],
        "plan": ["pro", "pro"],
        "mrr": [500.0, 900.0],
        "interval": ["month", "month"],
        "started_at": ["2024-01-01", "2024-01-15"],
        "ended_at": [None, "2024-06-01"],
        "cancel_reason": [None, "too_expensive"],
        "status": ["active", "canceled"],
    })


def _invoices_frame():
    return pd.DataFrame({
        "invoice_id": ["i1", "i2"],
        "customer_id": ["c1", "c2"],
        "subscription_id": ["s1", "s2"],
        "amount": [500.0, 900.0],
        "currency": ["INR", "INR"],
        "status": ["paid", "failed"],
        "attempted_at": ["2024-02-01", "2024-02-01"],
        "paid_at": ["2024-02-01", None],
        "failure_code": [None, "insufficient_funds"],
        "attempt_number": [1, 1],
    })


# --- column aliasing --------------------------------------------------------


@pytest.mark.parametrize("alias", ["customer", "user_id", "account_id", "email"])
def test_customer_id_aliases_are_recognised(alias):
    frame = _customers_frame(customer_id=alias)
    assert "customer_id" in normalise_columns(frame, CUSTOMERS).columns


def test_matching_ignores_case_and_separators():
    """Exports arrive as 'Customer ID', 'customer-id', and 'CUSTOMER_ID' equally."""
    frame = _customers_frame().rename(
        columns={"customer_id": "Customer ID", "created_at": "Signup-Date"}
    )
    out = normalise_columns(frame, CUSTOMERS)
    assert {"customer_id", "created_at"} <= set(out.columns)


def test_churn_date_aliases_map_to_ended_at():
    subs = _subs_frame().rename(columns={"ended_at": "churn_date"})
    assert "ended_at" in normalise_columns(subs, SUBSCRIPTIONS).columns


def test_canonical_names_are_left_alone():
    frame = _customers_frame()
    assert list(normalise_columns(frame, CUSTOMERS).columns) == list(frame.columns)


# --- availability lag -------------------------------------------------------


def test_default_lag_is_applied_when_absent():
    """A CSV cannot say when a fact became knowable. Assuming zero would be a lie
    the feature store has no way to detect."""
    out = load_table(_invoices_frame(), INVOICES)
    expected = pd.Timestamp("2024-02-01") + pd.Timedelta(days=2)
    assert (out["available_at"] == expected).all()


def test_explicit_lag_overrides_the_default():
    out = load_table(_invoices_frame(), INVOICES, lag=pd.Timedelta(hours=1))
    assert (out["available_at"] == pd.Timestamp("2024-02-01 01:00")).all()


def test_zero_lag_is_honoured():
    out = load_table(_invoices_frame(), INVOICES, lag=pd.Timedelta(0))
    assert (out["available_at"] == out["attempted_at"]).all()


def test_supplied_available_at_is_kept():
    frame = _invoices_frame()
    frame["available_at"] = "2024-02-05"
    out = load_table(frame, INVOICES)
    assert (out["available_at"] == pd.Timestamp("2024-02-05")).all()


def test_lag_never_produces_an_impossible_fact():
    """Even a supplied available_at earlier than the event must be corrected --
    otherwise schema validation would reject the whole load."""
    frame = _invoices_frame()
    frame["available_at"] = "2020-01-01"
    out = load_table(frame, INVOICES)
    assert (out["available_at"] >= out["attempted_at"]).all()


# --- coercion and errors ----------------------------------------------------


def test_dates_are_parsed_from_strings():
    """Date strings must become real datetimes.

    Checked with `is_datetime64_any_dtype` rather than an exact dtype comparison,
    because the *resolution* is not something this project depends on and it is not
    stable across pandas versions: pandas 2 parses "2024-01-01" to nanoseconds,
    pandas 3 infers microseconds. An exact `== "datetime64[ns]"` assertion passed
    locally on pandas 2.3 and failed in CI on pandas 3. Comparisons, ordering, and
    the schema's available_at >= occurred_at invariant all work across resolutions,
    so the resolution is genuinely not our business.
    """
    out = load_table(_customers_frame(), CUSTOMERS)
    assert pd.api.types.is_datetime64_any_dtype(out["created_at"])
    assert out["created_at"].iloc[0] == pd.Timestamp("2024-01-01")


def test_missing_required_column_is_rejected():
    frame = _subs_frame().drop(columns=["mrr"])
    with pytest.raises(IngestError, match="required column 'mrr'"):
        load_table(frame, SUBSCRIPTIONS)


def test_error_lists_the_columns_actually_present():
    """The person reading this error is a founder looking at their own export."""
    frame = _subs_frame().drop(columns=["mrr"])
    with pytest.raises(IngestError, match="Columns present"):
        load_table(frame, SUBSCRIPTIONS)


def test_rows_without_a_key_are_rejected():
    frame = _customers_frame()
    frame.loc[0, "customer_id"] = None
    with pytest.raises(IngestError, match="no key"):
        load_table(frame, CUSTOMERS)


def test_nullable_columns_may_be_absent():
    frame = _customers_frame().drop(columns=["country", "segment"])
    out = load_table(frame, CUSTOMERS)
    assert out["country"].isna().all()


# --- end to end -------------------------------------------------------------


def test_minimal_load_needs_only_two_files():
    """Most Churn Autopsy engagements start with exactly customers + subscriptions."""
    ds = load(_customers_frame(), _subs_frame())
    ds.validate()
    assert len(ds.customers) == 2
    assert ds.invoices.empty


def test_full_load_validates():
    ds = load(_customers_frame(), _subs_frame(), _invoices_frame())
    ds.validate()
    assert set(ds.invoices["status"]) == {"paid", "failed"}


def test_load_from_actual_csv_files(tmp_path):
    cust = tmp_path / "customers.csv"
    subs = tmp_path / "subs.csv"
    _customers_frame().to_csv(cust, index=False)
    _subs_frame().to_csv(subs, index=False)
    load(cust, subs).validate()


def test_orphan_rows_are_caught_end_to_end():
    from keel.core.schema import SchemaError

    inv = _invoices_frame()
    inv.loc[0, "customer_id"] = "ghost"
    with pytest.raises(SchemaError, match="unknown customers"):
        load(_customers_frame(), _subs_frame(), inv)


def test_loaded_data_works_with_the_feature_store():
    """The point of ingest is that everything downstream stops caring where data
    came from."""
    from keel.core.features import STANDARD_FEATURES, FeatureStore

    ds = load(_customers_frame(), _subs_frame(), _invoices_frame())
    out = FeatureStore(ds).build(pd.Timestamp("2024-03-01"), ["c1", "c2"], STANDARD_FEATURES)
    assert len(out) == 2
    assert out["payment_failures_ltd"].tolist() == [0.0, 1.0]
