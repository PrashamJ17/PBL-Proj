"""The canonical schema.

Every data source -- Stripe, Chargebee, a CSV export, the simulator -- is translated
into these tables. Models and features only ever read from here, never from a
source-specific shape. That translation layer is unglamorous and it is where most
projects of this kind quietly die.

Two design decisions worth stating up front.

**Timestamp-native, not period-indexed.** Real billing data arrives as timestamped
events, so the canonical layer looks like reality. SubSim produces month indices and
its adapter converts *up* into timestamps. The simulator's convenience must not shape
the production schema -- if it did, every real integration would fight the model.

**Every fact carries two timestamps**, and conflating them is a subtle, devastating
form of leakage:

``occurred_at``
    When the thing happened in the world.

``available_at``
    When *we could first have known about it*.

They differ more often than people expect. A card payment is attempted at T, but the
decline reason may only settle at T+2 days. A support ticket is opened at T, but its
sentiment score is computed by a nightly batch and is not available until T+1. Product
events may upload hours late from a mobile client.

If you train on ``occurred_at`` but serve on data that arrives with lag, your model
learns from information it will not have at prediction time. Accuracy looks excellent
in backtests and collapses in production. `keel.core.features` therefore filters on
``available_at``, never on ``occurred_at``.

Convention: ``available_at`` is required. Where a source genuinely has no lag, the
adapter sets it equal to ``occurred_at`` explicitly. Making it implicit invites people
to forget it exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# --- column types -----------------------------------------------------------

STR = "string"
INT = "int64"
FLOAT = "float64"
TIME = "datetime64[ns]"
BOOL = "bool"


@dataclass(frozen=True)
class Column:
    name: str
    dtype: str
    nullable: bool = False
    doc: str = ""


@dataclass(frozen=True)
class Table:
    name: str
    key: str
    """Primary key column. Must be unique."""
    columns: list[Column]
    occurred_at: str | None = None
    """Column marking when the fact happened. None for dimension tables."""
    available_at: str | None = None
    """Column marking when the fact became knowable. Required on fact tables."""
    doc: str = ""

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def is_fact(self) -> bool:
        return self.occurred_at is not None


# --- the tables -------------------------------------------------------------

CUSTOMERS = Table(
    name="customers",
    key="customer_id",
    doc="One row per customer. A dimension table -- no event time.",
    columns=[
        Column("customer_id", STR, doc="Stable identifier, unique within a tenant."),
        Column("created_at", TIME, doc="When the customer relationship began."),
        Column("country", STR, nullable=True),
        Column("segment", STR, nullable=True, doc="Tenant-defined grouping, free text."),
    ],
)

SUBSCRIPTIONS = Table(
    name="subscriptions",
    key="subscription_id",
    occurred_at="started_at",
    available_at="available_at",
    doc=(
        "One row per subscription. A customer may hold several over time "
        "(cancel then resubscribe) or at once (multiple products)."
    ),
    columns=[
        Column("subscription_id", STR),
        Column("customer_id", STR),
        Column("plan", STR, doc="Plan or price identifier."),
        Column("mrr", FLOAT, doc="Normalised monthly recurring revenue, tenant currency."),
        Column("interval", STR, doc="'month' or 'year'. Annual terms defer the churn decision."),
        Column("started_at", TIME),
        Column("ended_at", TIME, nullable=True,
               doc="Null while active. NOT the same as 'did not churn'."),
        Column("cancel_reason", STR, nullable=True),
        Column("status", STR, doc="active | canceled | paused | past_due"),
        Column("available_at", TIME),
    ],
)

INVOICES = Table(
    name="invoices",
    key="invoice_id",
    occurred_at="attempted_at",
    available_at="available_at",
    doc=(
        "Billing attempts. The source of involuntary churn, which is 20-40% of all "
        "churn and the fastest route to demonstrable revenue."
    ),
    columns=[
        Column("invoice_id", STR),
        Column("customer_id", STR),
        Column("subscription_id", STR, nullable=True),
        Column("amount", FLOAT),
        Column("currency", STR),
        Column("status", STR, doc="paid | failed | open | refunded"),
        Column("attempted_at", TIME),
        Column("paid_at", TIME, nullable=True),
        Column(
            "failure_code",
            STR,
            nullable=True,
            doc=(
                "Processor decline code. Drives retry strategy: insufficient_funds "
                "wants a payday-aligned retry, do_not_honor wants a different card."
            ),
        ),
        Column("attempt_number", INT, doc="1 for the first try, incrementing per retry."),
        Column("available_at", TIME, doc="Decline reasons can settle days after the attempt."),
    ],
)

EVENTS = Table(
    name="events",
    key="event_id",
    occurred_at="occurred_at",
    available_at="available_at",
    doc="Product usage. Optional -- the system must be useful without it.",
    columns=[
        Column("event_id", STR),
        Column("customer_id", STR),
        Column("name", STR, doc="Event name, e.g. 'session_start', 'report_exported'."),
        Column("occurred_at", TIME),
        Column("available_at", TIME, doc="Client-side events can upload hours late."),
        Column("value", FLOAT, nullable=True, doc="Optional magnitude."),
    ],
)

TICKETS = Table(
    name="tickets",
    key="ticket_id",
    occurred_at="opened_at",
    available_at="available_at",
    doc="Support contacts. Beware: some ticket content is a CONSEQUENCE of deciding to leave.",
    columns=[
        Column("ticket_id", STR),
        Column("customer_id", STR),
        Column("opened_at", TIME),
        Column("resolved_at", TIME, nullable=True),
        Column("severity", STR, nullable=True),
        Column("available_at", TIME),
    ],
)

INTERVENTIONS = Table(
    name="interventions",
    key="intervention_id",
    occurred_at="sent_at",
    available_at="available_at",
    doc=(
        "Every retention action ever taken, INCLUDING deliberate non-actions.\n\n"
        "This is the most valuable table in the system and the one no competitor "
        "keeps. Without a record of what was tried, on whom, and who was "
        "deliberately held back, causal effects cannot be estimated at all -- you "
        "can only ever measure correlations and call them results.\n\n"
        "Holdout rows (arm='holdout') have no offer and cost nothing. They exist so "
        "that the effect of everything else is measurable."
    ),
    columns=[
        Column("intervention_id", STR),
        Column("customer_id", STR),
        Column("experiment_id", STR, doc="Groups interventions into a measurable campaign."),
        Column("arm", STR, doc="treatment | holdout. The holdout is what makes ROI provable."),
        Column("offer", STR, nullable=True, doc="Offer name; null for holdout rows."),
        Column("rung", INT, nullable=True, doc="Position on the margin-cost ladder, 0-8."),
        Column("cost", FLOAT, doc="Realised cost. Zero for holdout."),
        Column("sent_at", TIME),
        Column("available_at", TIME),
    ],
)

TABLES: dict[str, Table] = {
    t.name: t for t in (CUSTOMERS, SUBSCRIPTIONS, INVOICES, EVENTS, TICKETS, INTERVENTIONS)
}


# --- validation -------------------------------------------------------------


class SchemaError(ValueError):
    """Raised when a frame does not conform to its canonical table definition."""


@dataclass
class Dataset:
    """A validated set of canonical tables for one tenant."""

    customers: pd.DataFrame
    subscriptions: pd.DataFrame
    invoices: pd.DataFrame
    events: pd.DataFrame = field(default_factory=lambda: empty(EVENTS))
    tickets: pd.DataFrame = field(default_factory=lambda: empty(TICKETS))
    interventions: pd.DataFrame = field(default_factory=lambda: empty(INTERVENTIONS))

    def validate(self) -> Dataset:
        for name, table in TABLES.items():
            validate(getattr(self, name), table)
        self._check_referential_integrity()
        return self

    def _check_referential_integrity(self) -> None:
        known = set(self.customers["customer_id"])
        for name in ("subscriptions", "invoices", "events", "tickets", "interventions"):
            frame = getattr(self, name)
            if frame.empty:
                continue
            orphans = set(frame["customer_id"]) - known
            if orphans:
                raise SchemaError(
                    f"{name}: {len(orphans)} rows reference unknown customers, "
                    f"e.g. {sorted(orphans)[:3]}"
                )


def empty(table: Table) -> pd.DataFrame:
    """An empty frame with the right columns and dtypes."""
    return pd.DataFrame({c.name: pd.Series(dtype=c.dtype) for c in table.columns})


def validate(frame: pd.DataFrame, table: Table) -> pd.DataFrame:
    """Check a frame against its table definition. Raises `SchemaError`."""
    missing = set(table.names) - set(frame.columns)
    if missing:
        raise SchemaError(f"{table.name}: missing columns {sorted(missing)}")

    if frame.empty:
        return frame

    if frame[table.key].duplicated().any():
        n = int(frame[table.key].duplicated().sum())
        raise SchemaError(f"{table.name}: {n} duplicate values in key '{table.key}'")

    for col in table.columns:
        series = frame[col.name]
        if not col.nullable and series.isna().any():
            n = int(series.isna().sum())
            raise SchemaError(f"{table.name}.{col.name}: {n} nulls in a non-nullable column")

    # The invariant the whole feature store depends on. A fact cannot become
    # knowable before it happened; if it does, some upstream mapper has confused
    # the two timestamps and every point-in-time guarantee is void.
    if table.is_fact:
        occurred = frame[table.occurred_at]
        available = frame[table.available_at]
        bad = available < occurred
        if bad.any():
            raise SchemaError(
                f"{table.name}: {int(bad.sum())} rows have available_at earlier than "
                f"{table.occurred_at}. A fact cannot be knowable before it occurs."
            )
    return frame
