"""Tests for the Stripe adapter.

Fixtures mirror the shape of real Stripe API objects. The mapper is pure, so these
run without an API key or network access -- which means the logic most likely to be
quietly wrong (money and time) is the part that is actually covered.
"""

from __future__ import annotations

import pandas as pd
import pytest

from keel.core.schema import validate, INVOICES, SUBSCRIPTIONS
from keel.ingest.stripe import (
    map_customers,
    map_invoices,
    map_subscriptions,
    monthly_value,
    to_amount,
    to_canonical,
    to_ts,
)

JAN_1 = 1704067200  # 2024-01-01 00:00:00 UTC
FEB_1 = 1706745600


def _customer(cid="cus_1", created=JAN_1, country="IN"):
    return {"id": cid, "created": created, "address": {"country": country}, "metadata": {}}


def _subscription(sid="sub_1", cid="cus_1", amount=50000, interval="month", status="active", **kw):
    return {
        "id": sid,
        "customer": cid,
        "status": status,
        "created": JAN_1,
        "start_date": JAN_1,
        "items": {"data": [{
            "quantity": 1,
            "price": {"id": "price_1", "unit_amount": amount, "currency": "inr",
                      "recurring": {"interval": interval, "interval_count": 1}},
        }]},
        **kw,
    }


def _invoice(iid="in_1", cid="cus_1", amount=50000, status="paid", **kw):
    return {
        "id": iid,
        "customer": cid,
        "subscription": "sub_1",
        "amount_due": amount,
        "currency": "inr",
        "status": status,
        "created": JAN_1,
        "attempt_count": 1,
        "status_transitions": {"paid_at": JAN_1 if status == "paid" else None},
        **kw,
    }


# --- money ------------------------------------------------------------------


def test_amounts_convert_from_minor_units():
    assert to_amount(50000, "inr") == 500.0
    assert to_amount(2000, "usd") == 20.0


def test_zero_decimal_currencies_are_not_divided():
    """JPY has no minor unit. Dividing by 100 would understate revenue 100x."""
    assert to_amount(2000, "jpy") == 2000.0
    assert to_amount(2000, "krw") == 2000.0
    assert to_amount(2000, "JPY") == 2000.0, "currency code must be case-insensitive"


def test_none_amount_is_zero():
    assert to_amount(None, "usd") == 0.0


@pytest.mark.parametrize(
    "interval,expected",
    [("month", 1200.0), ("year", 100.0), ("week", 1200.0 * 4.345), ("day", 1200.0 * 30.44)],
)
def test_intervals_normalise_to_monthly(interval, expected):
    assert monthly_value(1200.0, interval) == pytest.approx(expected, rel=1e-3)


def test_annual_subscription_mrr_is_normalised():
    """An annual plan must not look 12x more valuable than it is -- that would
    distort every CLV-weighted targeting decision toward annual customers."""
    subs = map_subscriptions([_subscription(amount=1200000, interval="year")])
    assert subs.loc[0, "mrr"] == pytest.approx(1000.0)


def test_quantity_multiplies_mrr():
    sub = _subscription()
    sub["items"]["data"][0]["quantity"] = 5
    assert map_subscriptions([sub]).loc[0, "mrr"] == pytest.approx(2500.0)


def test_multiple_items_sum():
    sub = _subscription()
    sub["items"]["data"].append({
        "quantity": 1,
        "price": {"id": "price_2", "unit_amount": 25000, "currency": "inr",
                  "recurring": {"interval": "month", "interval_count": 1}},
    })
    assert map_subscriptions([sub]).loc[0, "mrr"] == pytest.approx(750.0)


def test_interval_count_is_respected():
    """A price billed every 3 months is a quarterly plan."""
    sub = _subscription()
    sub["items"]["data"][0]["price"]["recurring"]["interval_count"] = 3
    assert map_subscriptions([sub]).loc[0, "mrr"] == pytest.approx(500.0 / 3)


# --- time -------------------------------------------------------------------


def test_timestamps_convert_from_unix_seconds():
    assert to_ts(JAN_1) == pd.Timestamp("2024-01-01")
    assert pd.isna(to_ts(None))


def test_canceled_at_is_not_ended_at():
    """A customer who cancels on the 1st but has service until the 31st has NOT
    churned yet. Using canceled_at would label them churned while still paying."""
    sub = _subscription(status="canceled", canceled_at=JAN_1, ended_at=FEB_1)
    assert map_subscriptions([sub]).loc[0, "ended_at"] == pd.Timestamp("2024-02-01")


def test_canceled_without_ended_at_falls_back():
    sub = _subscription(status="canceled", canceled_at=JAN_1)
    assert map_subscriptions([sub]).loc[0, "ended_at"] == pd.Timestamp("2024-01-01")


def test_active_subscription_has_no_end_date():
    assert pd.isna(map_subscriptions([_subscription()]).loc[0, "ended_at"])


def test_available_at_never_precedes_the_event():
    """The invariant the whole feature store rests on."""
    inv = map_invoices([_invoice(status="open", status_transitions={"finalized_at": JAN_1 - 999})])
    assert (inv["available_at"] >= inv["attempted_at"]).all()


# --- invoice status ---------------------------------------------------------


def test_failed_payment_carries_its_decline_code():
    """The decline code drives retry strategy: insufficient_funds wants a
    payday-aligned retry, do_not_honor wants a different card entirely."""
    inv = _invoice(iid="in_2", status="open", payment_intent={
        "last_payment_error": {"code": "card_declined", "decline_code": "insufficient_funds"}
    })
    out = map_invoices([inv])
    assert out.loc[0, "status"] == "failed"
    assert out.loc[0, "failure_code"] == "insufficient_funds"


def test_paid_invoice_is_paid():
    out = map_invoices([_invoice()])
    assert out.loc[0, "status"] == "paid"
    assert out.loc[0, "paid_at"] == pd.Timestamp("2024-01-01")


def test_open_invoice_is_not_marked_failed():
    """An invoice awaiting its first attempt has not failed."""
    out = map_invoices([_invoice(status="open", attempt_count=0)])
    assert out.loc[0, "status"] == "open"


# --- end to end -------------------------------------------------------------


def test_full_mapping_validates():
    ds = to_canonical(
        [_customer(), _customer("cus_2")],
        [_subscription(), _subscription("sub_2", "cus_2", interval="year", amount=1200000)],
        [_invoice(), _invoice("in_2", "cus_2", status="open", payment_intent={
            "last_payment_error": {"decline_code": "expired_card"}})],
    )
    ds.validate()
    assert len(ds.customers) == 2
    assert ds.subscriptions["mrr"].tolist() == pytest.approx([500.0, 1000.0])
    assert set(ds.invoices["status"]) == {"paid", "failed"}


def test_empty_input_produces_valid_empty_dataset():
    ds = to_canonical([], [], [])
    ds.validate()
    assert ds.customers.empty


def test_mapped_frames_satisfy_the_schema():
    validate(map_subscriptions([_subscription()]), SUBSCRIPTIONS)
    validate(map_invoices([_invoice()]), INVOICES)


def test_missing_optional_fields_are_tolerated():
    """Real Stripe payloads omit optional fields entirely rather than nulling them."""
    bare = {"id": "cus_x", "created": JAN_1}
    out = map_customers([bare])
    assert out.loc[0, "customer_id"] == "cus_x"
    assert pd.isna(out.loc[0, "country"])
