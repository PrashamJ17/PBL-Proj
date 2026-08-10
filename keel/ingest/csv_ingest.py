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

import re
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
#:
#: Ordered by specificity: the first alias that matches wins, so a more precise name
#: must precede a vaguer one. "plan_amount" before "amount" matters on a Stripe
#: subscription export, where both exist and mean different things.
ALIASES: dict[str, list[str]] = {
    "customer_id": ["customer", "cust_id", "user_id", "account_id", "id", "email"],
    "created_at": ["signup_date", "created", "join_date", "start_date", "registered_at"],
    "subscription_id": ["sub_id", "subscription"],
    "mrr": ["plan_amount", "monthly_revenue", "monthly_value", "amount", "price",
            "revenue", "plan_price", "subscription_amount"],
    "started_at": ["subscription_start", "current_period_start", "start_at",
                   "current_start", "start", "begin_date", "created"],
    "ended_at": ["churn_date", "canceled_at", "cancelled_at", "cancellation_date",
                 "end_date", "end_at", "churned_at", "ended"],
    "status": ["state", "subscription_status", "invoice_status", "payment_status"],
    "plan": ["plan_id", "plan_name", "plan_nickname", "product", "product_name",
             "price_id", "tier"],
    "interval": ["plan_interval", "billing_interval", "billing_period", "period",
                 "recurring_interval"],
    "amount": ["amount_paid", "total", "amount_due", "invoice_amount", "gross"],
    "currency": ["plan_currency", "invoice_currency", "iso_currency"],
    "attempt_number": ["attempt", "attempts", "retry_number", "attempt_count"],
    "failure_code": ["decline_code", "failure_reason", "error_code", "last_error_code"],
    "name": ["event", "event_name", "action", "type", "event_type"],
    "attempted_at": ["invoice_date", "charge_date", "billed_at", "date"],
    "paid_at": ["payment_date", "settled_at", "paid"],
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
        # Parenthetical suffixes are stripped because every Stripe dashboard export
        # ships "Created (UTC)" and "Canceled At (UTC)", which otherwise match nothing
        # and fail the load on the very first file a prospect sends.
        n = re.sub(r"\s*\([^)]*\)\s*", " ", str(name))
        n = n.strip().lower().replace(" ", "_").replace("-", "_")
        return re.sub(r"_+", "_", n).strip("_")

    present = {key(c): c for c in frame.columns}
    rename: dict[str, str] = {}
    taken: set[str] = set()

    def aliases_for(canonical: str) -> list[str]:
        """Aliases for one canonical column, resolved against *this* table.

        A bare ``id`` means the identifier of the entity the file is about: on a
        subscriptions export it is the subscription, on a customers export the
        customer. Treating it as a global alias for `customer_id` silently loaded
        Stripe subscription ids into the customer column and then failed two steps
        later complaining that `subscription_id` was missing.
        """
        listed = [a for a in ALIASES.get(canonical, []) if a != "id"]
        # `id` goes FIRST for the table's own key, not last: a column literally called
        # `id` on a file about that entity is the most authoritative signal there is.
        # Ordered the other way, `email` (a plausible customer identifier, and earlier
        # in the list) won over the real id column and every subscription then
        # referenced a customer that did not exist.
        return ["id", *listed] if canonical == table.key else listed

    # Exact canonical matches first, across every column, so a precise name is never
    # stolen by another column's alias.
    for canonical in table.names:
        if canonical in frame.columns:
            taken.add(canonical)
            continue
        if canonical in present:
            rename[present[canonical]] = canonical
            taken.add(present[canonical])

    for canonical in table.names:
        if canonical in frame.columns or present.get(canonical) in taken:
            continue
        if canonical in rename.values():
            continue
        for alias in aliases_for(canonical):
            src = present.get(alias)
            if src is not None and src not in taken:
                rename[src] = canonical
                taken.add(src)
                break

    return frame.rename(columns=rename)


#: Epoch bounds used to recognise Unix timestamps, as seconds and as milliseconds.
#: 1990-01-01 to 2050-01-01 -- wide enough for any real billing history, narrow enough
#: that an ordinary integer column will not be mistaken for one.
_EPOCH_S = (631_152_000, 2_524_608_000)


def _to_datetime(series: pd.Series) -> pd.Series:
    """Parse dates, recognising Unix timestamps.

    Razorpay's exports carry epoch **seconds**; pandas reads a bare integer as
    nanoseconds and silently returns 1970-01-01 for every row. Unlike a currency-unit
    mistake this one is not plausible, so it is safe to correct rather than refuse --
    and the magnitude test is unambiguous: a value inside the 1990-2050 window read as
    seconds cannot also be a sensible nanosecond count.
    """
    # Blanks count as absent, not as data. `ended_at` is legitimately sparse -- only
    # churned customers have one -- so testing what *fraction* of the column is numeric
    # rejected exactly the column that most needed converting, and every cancellation
    # date came back as 1970.
    present = series.notna() & (series.astype("string").str.strip() != "")
    if not present.any():
        return pd.to_datetime(series, errors="coerce")

    numeric = pd.to_numeric(series.where(present), errors="coerce")
    if numeric[present].isna().any():
        # Something present is not a number, so this is not an epoch column.
        return pd.to_datetime(series, errors="coerce")

    finite = numeric.dropna()
    lo, hi = _EPOCH_S
    if finite.between(lo, hi).all():
        return pd.to_datetime(numeric, unit="s", errors="coerce")
    if finite.between(lo * 1000, hi * 1000).all():
        return pd.to_datetime(numeric, unit="ms", errors="coerce")
    return pd.to_datetime(series, errors="coerce")


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
            out[col.name] = _to_datetime(out[col.name])
        elif col.dtype == "float64":
            out[col.name] = pd.to_numeric(out[col.name], errors="coerce").astype(float)
        elif col.dtype == "int64":
            out[col.name] = pd.to_numeric(out[col.name], errors="coerce").fillna(0).astype("int64")
        else:
            out[col.name] = out[col.name].astype("string")
    return out[table.names]


#: Required columns a real export routinely lacks, and what to put there instead.
#:
#: The split matters. A *label* that is absent costs nothing to invent -- nobody makes a
#: decision from a plan's name. A *measurement* that is absent must never be invented
#: quietly, which is why `interval` is here with a warning attached rather than a silent
#: default: assuming monthly when a book is annual overstates MRR by twelve, and every
#: number in the report inherits it.
SAFE_DEFAULTS: dict[str, tuple[object, str]] = {
    "plan": ("unknown", "no plan/product column found; plan-level breakdowns unavailable"),
    "currency": ("unknown", "no currency column found; amounts assumed to be one currency"),
    "attempt_number": (1, "no retry-attempt column found; every invoice treated as a "
                          "first attempt, so retry analysis will understate recovery"),
    "name": ("unknown", "no event-name column found"),
    "interval": ("month", "NO BILLING INTERVAL COLUMN FOUND -- every subscription is "
                          "assumed MONTHLY. If any plans are annual their MRR is "
                          "overstated 12x. Confirm this with the business before "
                          "sending anything."),
}


def _apply_defaults(
    frame: pd.DataFrame, table: Table, defaults: dict[str, object] | None
) -> tuple[pd.DataFrame, list[str]]:
    """Fill required-but-absent columns from `SAFE_DEFAULTS`, recording each one.

    Nothing here is silent. Every filled column produces a line the operator has to
    read before the report is sent, because an assumption a prospect discovers for
    themselves costs more than the engagement is worth.
    """
    out = frame.copy()
    supplied = defaults or {}
    filled: list[str] = []
    for col in table.columns:
        if col.nullable or col.name in out.columns or col.name == table.available_at:
            continue
        if col.name in supplied:
            out[col.name] = supplied[col.name]
            filled.append(f"{table.name}.{col.name}: set to {supplied[col.name]!r} (you told us)")
        elif col.name in SAFE_DEFAULTS:
            value, why = SAFE_DEFAULTS[col.name]
            out[col.name] = value
            filled.append(f"{table.name}.{col.name}: {why}")
    return out, filled


def load_table(
    path: str | Path | pd.DataFrame,
    table: Table,
    lag: pd.Timedelta | None = None,
    defaults: dict[str, object] | None = None,
    record: list[str] | None = None,
) -> pd.DataFrame:
    """Load one canonical table from a CSV file or an already-loaded frame."""
    frame = path if isinstance(path, pd.DataFrame) else pd.read_csv(path)
    frame = normalise_columns(frame, table)
    frame, filled = _apply_defaults(frame, table, defaults)
    frame = _coerce(frame, table)
    if record is not None:
        record.extend(filled)

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
    defaults: dict[str, object] | None = None,
    assumptions: list[str] | None = None,
) -> Dataset:
    """Load a full dataset from CSV exports.

    Only customers and subscriptions are required. Most Churn Autopsy engagements
    begin with exactly those two files.

    `defaults` supplies values for required columns the export does not contain --
    `{"interval": "year"}` for an annual-only book, say. Anything not supplied and not
    present falls back to `SAFE_DEFAULTS`. Pass a list as `assumptions` to collect every
    such fill; `preflight` uses it to show the operator what was invented before a
    report goes anywhere near a prospect.
    """
    lags = lags or {}
    record = assumptions if assumptions is not None else []

    def maybe(src, table):
        return (load_table(src, table, lags.get(table.name), defaults, record)
                if src is not None else empty(table))

    return Dataset(
        customers=load_table(customers, CUSTOMERS, None, defaults, record),
        subscriptions=load_table(subscriptions, SUBSCRIPTIONS, lags.get("subscriptions"),
                                 defaults, record),
        invoices=maybe(invoices, INVOICES),
        events=maybe(events, EVENTS),
        tickets=maybe(tickets, TICKETS),
    ).validate()
