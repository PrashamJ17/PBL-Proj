"""CSV -> canonical schema.

The delivery path for the "Churn Autopsy" diagnostic: a business exports data from
whatever they use and sends files. No API access, no integration work, no engineering
time on their side. That low barrier is the entire point -- it is the difference
between a prospect saying "send me the export" and "let me ask our developer".

Consequently this must be forgiving about *shape* and unforgiving about *meaning*.
Column names vary endlessly and are worth guessing at; a mislabelled churn date is
worth refusing outright, because it silently corrupts every downstream number.

Availability lag
----------------
A CSV export carries no record of when each fact became knowable. Assuming zero lag
would be a lie that the feature store cannot detect. Instead `default_lag` applies a
conservative uniform lag per table, and the assumption is recorded rather than hidden.
Where a tenant can tell us their real settlement delay, pass it explicitly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from keel.core.schema import (
    CUSTOMERS,
    EVENTS,
    INVOICES,
    SUBSCRIPTIONS,
    TICKETS,
    Dataset,
    Table,
    empty,
)

#: Common column spellings seen in real exports, mapped to canonical names.
ALIASES: dict[str, list[str]] = {
    "customer_id": ["customer", "cust_id", "user_id", "account_id", "id", "email"],
    "created_at": ["signup_date", "created", "join_date", "start_date", "registered_at"],
    "subscription_id": ["sub_id", "subscription"],
    "mrr": ["monthly_revenue", "amount", "price", "monthly_value", "revenue"],
    "started_at": ["subscription_start", "start", "begin_date"],
    "ended_at": ["churn_date", "canceled_at", "cancellation_date", "end_date", "churned_at"],
    "status": ["state", "subscription_status"],
    "attempted_at": ["invoice_date", "charge_date", "billed_at", "date"],
    "paid_at": ["payment_date", "settled_at"],
    "occurred_at": ["timestamp", "event_time", "time", "date"],
    "opened_at": ["ticket_date", "created_at", "submitted_at"],
}

#: Conservative default lag per table, applied when the export cannot tell us.
DEFAULT_LAG = {
    "invoices": pd.Timedelta(days=2),
    "events": pd.Timedelta(hours=6),
    "tickets": pd.Timedelta(0),
    "subscriptions": pd.Timedelta(0),
}


class IngestError(ValueError):
    """Raised when a file cannot be mapped to the canonical schema."""


def normalise_columns(frame: pd.DataFrame, table: Table) -> pd.DataFrame:
    """Rename columns onto canonical names using known aliases.

    Matching is case- and separator-insensitive, since exports arrive as
    "Customer ID", "customer-id", and "CUSTOMER_ID" with equal frequency.
    """
    def key(name: str) -> str:
        return str(name).strip().lower().replace(" ", "_").replace("-", "_")

    present = {key(c): c for c in frame.columns}
    rename: dict[str, str] = {}

    for canonical in table.names:
        if canonical in frame.columns:
            continue
        if canonical in present:
            rename[present[canonical]] = canonical
            continue
        for alias in ALIASES.get(canonical, []):
            if alias in present and present[alias] not in rename:
                rename[present[alias]] = canonical
                break

    return frame.rename(columns=rename)


def _coerce(frame: pd.DataFrame, table: Table) -> pd.DataFrame:
    """Cast columns to their declared dtypes, adding nullable ones if absent."""
    out = frame.copy()
    for col in table.columns:
        if col.name not in out.columns:
            if not col.nullable and col.name not in (table.available_at,):
                raise IngestError(
                    f"{table.name}: required column '{col.name}' not found. "
                    f"Columns present: {sorted(map(str, frame.columns))}"
                )
            out[col.name] = pd.Series([pd.NA] * len(out), dtype=col.dtype)
            continue

        if col.dtype == "datetime64[ns]":
            out[col.name] = pd.to_datetime(out[col.name], errors="coerce")
        elif col.dtype == "float64":
            out[col.name] = pd.to_numeric(out[col.name], errors="coerce").astype(float)
        elif col.dtype == "int64":
            out[col.name] = pd.to_numeric(out[col.name], errors="coerce").fillna(0).astype("int64")
        else:
            out[col.name] = out[col.name].astype("string")
    return out[table.names]


def load_table(
    path: str | Path | pd.DataFrame,
    table: Table,
    lag: pd.Timedelta | None = None,
) -> pd.DataFrame:
    """Load one canonical table from a CSV file or an already-loaded frame."""
    frame = path if isinstance(path, pd.DataFrame) else pd.read_csv(path)
    frame = normalise_columns(frame, table)
    frame = _coerce(frame, table)

    if table.is_fact:
        applied = DEFAULT_LAG.get(table.name, pd.Timedelta(0)) if lag is None else lag
        missing = frame[table.available_at].isna()
        frame.loc[missing, table.available_at] = frame.loc[missing, table.occurred_at] + applied
        # A conservative assumption must never produce an impossible fact.
        frame[table.available_at] = frame[[table.available_at, table.occurred_at]].max(axis=1)

    if frame[table.key].isna().any():
        raise IngestError(f"{table.name}: {int(frame[table.key].isna().sum())} rows have no key")

    return frame


def load(
    customers: str | Path | pd.DataFrame,
    subscriptions: str | Path | pd.DataFrame,
    invoices: str | Path | pd.DataFrame | None = None,
    events: str | Path | pd.DataFrame | None = None,
    tickets: str | Path | pd.DataFrame | None = None,
    lags: dict[str, pd.Timedelta] | None = None,
) -> Dataset:
    """Load a full dataset from CSV exports.

    Only customers and subscriptions are required. Most Churn Autopsy engagements
    begin with exactly those two files.
    """
    lags = lags or {}

    def maybe(src, table):
        return load_table(src, table, lags.get(table.name)) if src is not None else empty(table)

    return Dataset(
        customers=load_table(customers, CUSTOMERS),
        subscriptions=load_table(subscriptions, SUBSCRIPTIONS, lags.get("subscriptions")),
        invoices=maybe(invoices, INVOICES),
        events=maybe(events, EVENTS),
        tickets=maybe(tickets, TICKETS),
    ).validate()
