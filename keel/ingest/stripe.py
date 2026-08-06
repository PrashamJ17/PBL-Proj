"""Stripe -> canonical schema.

Maps Stripe API objects into the canonical tables. Pure functions over already-fetched
JSON: no network calls and no API key required, so the mapping logic is fully testable
against fixtures. Fetching belongs to a separate concern and can be swapped for a
webhook consumer or a data-warehouse export without touching any of this.

Stripe details that matter and are easy to get wrong
-----------------------------------------------------
**Amounts are in the smallest currency unit.** 2000 means ₹20.00 or $20.00. Divide by
100 for two-decimal currencies -- but *not* for zero-decimal ones (JPY, KRW), where
2000 means ¥2000. Getting this wrong silently inflates every revenue figure 100x.

**Timestamps are Unix seconds, UTC.**

**Subscription intervals vary**, so MRR must be normalised: an annual plan at 120000
is 1000/month, not 120000/month. Mixing the two makes annual customers look 12x more
valuable and skews every CLV-weighted decision.

**`canceled_at` is not `ended_at`.** A customer can cancel on the 3rd with the
subscription running until period end on the 30th. The churn date is when service
actually stopped, otherwise you will label customers as churned while they are still
paying you.

**Availability lag is real here.** A charge's outcome is known immediately, but
disputes and some decline reasons settle later. Where Stripe gives us nothing better,
`available_at` falls back to the event time -- documented below, because assuming zero
lag is a choice, not a fact.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from keel.core.schema import (
    CUSTOMERS,
    EVENTS,
    INVOICES,
    SUBSCRIPTIONS,
    TICKETS,
    Dataset,
    empty,
)

# Currencies with no minor unit -- amounts are already whole.
# https://docs.stripe.com/currencies#zero-decimal
ZERO_DECIMAL = {
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga",
    "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
}

INTERVAL_MONTHS = {"day": 1 / 30.44, "week": 1 / 4.345, "month": 1.0, "year": 12.0}


def to_amount(minor: int | float | None, currency: str) -> float:
    """Convert a Stripe amount from its smallest unit to a decimal amount."""
    if minor is None:
        return 0.0
    if (currency or "").lower() in ZERO_DECIMAL:
        return float(minor)
    return float(minor) / 100.0


def to_ts(unix_seconds: int | float | None) -> pd.Timestamp:
    """Unix seconds -> naive UTC timestamp. Stripe emits UTC throughout."""
    if unix_seconds is None:
        return pd.NaT
    return pd.Timestamp(int(unix_seconds), unit="s")


def monthly_value(amount: float, interval: str, interval_count: int = 1) -> float:
    """Normalise a recurring amount to monthly.

    Without this, an annual subscriber appears twelve times more valuable than they
    are, and every CLV-weighted targeting decision is distorted in their favour.
    """
    months = INTERVAL_MONTHS.get(interval, 1.0) * max(interval_count, 1)
    return float(amount) / months if months else float(amount)


# --- object mappers ---------------------------------------------------------


def map_customers(objects: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "customer_id": str(o["id"]),
            "created_at": to_ts(o.get("created")),
            "country": (o.get("address") or {}).get("country"),
            "segment": (o.get("metadata") or {}).get("segment"),
        }
        for o in objects
    ]
    frame = pd.DataFrame(rows, columns=[c.name for c in CUSTOMERS.columns])
    for col in ("country", "segment"):
        frame[col] = frame[col].astype("string")
    frame["customer_id"] = frame["customer_id"].astype("string")
    return frame


def map_subscriptions(objects: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for o in objects:
        items = (o.get("items") or {}).get("data") or []
        mrr = 0.0
        interval = "month"
        for item in items:
            price = item.get("price") or {}
            recurring = price.get("recurring") or {}
            currency = price.get("currency", "usd")
            amount = to_amount(price.get("unit_amount"), currency)
            qty = item.get("quantity", 1) or 1
            interval = recurring.get("interval", "month")
            mrr += monthly_value(
                amount * qty, interval, recurring.get("interval_count", 1)
            )

        # `ended_at` is when service actually stopped. `canceled_at` is when the
        # customer *asked* -- they may still be paying until period end.
        ended = o.get("ended_at")
        if ended is None and o.get("status") == "canceled":
            ended = o.get("canceled_at")

        rows.append(
            {
                "subscription_id": str(o["id"]),
                "customer_id": str(o["customer"]),
                "plan": str((items[0].get("price") or {}).get("id") if items else "unknown"),
                "mrr": round(mrr, 4),
                "interval": interval,
                "started_at": to_ts(o.get("start_date") or o.get("created")),
                "ended_at": to_ts(ended),
                "cancel_reason": ((o.get("cancellation_details") or {}).get("reason")),
                "status": str(o.get("status", "active")),
                # Subscription state is known as soon as it changes.
                "available_at": to_ts(o.get("start_date") or o.get("created")),
            }
        )

    frame = pd.DataFrame(rows, columns=[c.name for c in SUBSCRIPTIONS.columns])
    for col in ("subscription_id", "customer_id", "plan", "interval", "cancel_reason", "status"):
        frame[col] = frame[col].astype("string")
    return frame


def map_invoices(objects: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Map Stripe invoices, deriving failure codes from the last payment attempt."""
    rows = []
    for o in objects:
        currency = o.get("currency", "usd")
        attempted = to_ts(o.get("created"))
        status = str(o.get("status", "open"))

        intent = o.get("payment_intent")
        last_error = (intent or {}).get("last_payment_error") if isinstance(intent, dict) else None
        failure_code = (last_error or {}).get("decline_code") or (last_error or {}).get("code")

        paid = status == "paid"
        failed = bool(failure_code) or status == "uncollectible" or (
            o.get("attempt_count", 0) > 0 and not paid and status != "open"
        )

        # Successful charges post immediately; decline reasons can settle later.
        # Stripe does not expose a settlement time, so absent better information we
        # assume same-instant availability and record that assumption here rather
        # than silently pretending there is no lag.
        available = to_ts(o.get("status_transitions", {}).get("finalized_at")) or attempted

        rows.append(
            {
                "invoice_id": str(o["id"]),
                "customer_id": str(o["customer"]),
                "subscription_id": str(o.get("subscription")) if o.get("subscription") else None,
                "amount": to_amount(o.get("amount_due"), currency),
                "currency": currency,
                "status": "paid" if paid else ("failed" if failed else status),
                "attempted_at": attempted,
                "paid_at": to_ts((o.get("status_transitions") or {}).get("paid_at")),
                "failure_code": failure_code,
                "attempt_number": int(o.get("attempt_count", 1) or 1),
                "available_at": max(available, attempted) if pd.notna(available) else attempted,
            }
        )

    frame = pd.DataFrame(rows, columns=[c.name for c in INVOICES.columns])
    for col in ("invoice_id", "customer_id", "subscription_id", "currency", "status", "failure_code"):
        frame[col] = frame[col].astype("string")
    frame["attempt_number"] = frame["attempt_number"].astype("int64")
    return frame


def to_canonical(
    customers: Iterable[dict],
    subscriptions: Iterable[dict],
    invoices: Iterable[dict],
) -> Dataset:
    """Build a validated `Dataset` from fetched Stripe objects.

    Events and tickets come from other systems (product analytics, a helpdesk) and
    are left empty. The system must be useful from billing alone -- that is the only
    integration most small businesses will finish.
    """
    return Dataset(
        customers=map_customers(customers),
        subscriptions=map_subscriptions(subscriptions),
        invoices=map_invoices(invoices),
        events=empty(EVENTS),
        tickets=empty(TICKETS),
    ).validate()
