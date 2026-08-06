"""SubSim -> canonical schema.

Lets the whole production pipeline be exercised end to end without a real billing
account, and lets leakage tests run against data whose ground truth we control.

The conversion runs *upward*: SubSim thinks in month indices, the canonical schema
thinks in timestamps, and this adapter expands the former into the latter. Aggregate
counts become individual timestamped events -- `sessions_30d = 12` becomes twelve
`session_start` rows spread across that month. Going the other way (letting the
canonical layer speak in months because the simulator does) would have made every real
integration fight the schema.

Realistic availability lag is injected deliberately
---------------------------------------------------
If every fact were knowable the instant it occurred, the point-in-time machinery would
be untested -- filtering on `available_at` and on `occurred_at` would give identical
answers and a bug in that logic would never show up. So the lags here mirror the real
sources:

- **Product events** upload minutes to hours late from clients.
- **Payment failures** settle up to two days after the attempt; the decline *code* in
  particular is not immediate.
- **Tickets** are visible at once, but their resolution is not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from keel.core.schema import Dataset
from keel.sim.subsim import SimResult

ANCHOR = pd.Timestamp("2024-01-01")
"""Month 0 of the simulation. Arbitrary but fixed, so runs are comparable."""


def _month_start(month: int) -> pd.Timestamp:
    return ANCHOR + pd.DateOffset(months=int(month))


def to_canonical(
    sim: SimResult, anchor: pd.Timestamp = ANCHOR, seed: int = 0
) -> Dataset:
    """Convert a simulation run into validated canonical tables."""
    rng = np.random.default_rng(seed)
    panel = sim.panel.sort_values(["customer_id", "month"]).reset_index(drop=True)
    cust = sim.customers

    def month_ts(m):
        return anchor + pd.to_timedelta(np.asarray(m, dtype=float) * 30.44, unit="D")

    # --- customers ----------------------------------------------------------
    # Every simulated customer starts at month 0, so they share a creation date.
    # Real tenants have staggered signups; the schema does not care, but anything
    # reasoning about cohorts should know this is degenerate here.
    customers = pd.DataFrame(
        {
            "customer_id": cust["customer_id"].astype(str),
            "created_at": anchor,
            "country": pd.Series(["--"] * len(cust), dtype="string"),
            "segment": pd.Series(["sim"] * len(cust), dtype="string"),
        }
    )

    # --- subscriptions ------------------------------------------------------
    churned = cust["churn_month"] >= 0
    subs = pd.DataFrame(
        {
            "subscription_id": "sub_" + cust["customer_id"].astype(str),
            "customer_id": cust["customer_id"].astype(str),
            "plan": pd.Series(["sim_monthly"] * len(cust), dtype="string"),
            "mrr": cust["mrr"].astype(float),
            "interval": pd.Series(["month"] * len(cust), dtype="string"),
            "started_at": anchor,
            "ended_at": pd.Series(
                np.where(churned, month_ts(cust["churn_month"].clip(lower=0)), pd.NaT),
                dtype="datetime64[ns]",
            ),
            "cancel_reason": pd.Series(
                np.where(churned, cust["churn_kind"], None), dtype="string"
            ),
            "status": pd.Series(
                np.where(churned, "canceled", "active"), dtype="string"
            ),
            "available_at": anchor,
        }
    )
    subs.loc[~churned, "ended_at"] = pd.NaT

    # --- invoices -----------------------------------------------------------
    # One billing attempt per active month. A failure is inferred from the
    # increment in the cumulative failure counter.
    inv = panel[["customer_id", "month", "mrr", "payment_failures_ltd"]].copy()
    inv["failed"] = (
        inv.groupby("customer_id")["payment_failures_ltd"].diff().fillna(
            inv["payment_failures_ltd"]
        )
        > 0
    )
    attempted = month_ts(inv["month"])
    # Decline reasons settle over the following days; successful charges post at once.
    settle_days = np.where(inv["failed"], rng.uniform(0.5, 2.0, len(inv)), 0.0)

    invoices = pd.DataFrame(
        {
            "invoice_id": "inv_" + inv["customer_id"].astype(str) + "_" + inv["month"].astype(str),
            "customer_id": inv["customer_id"].astype(str),
            "subscription_id": "sub_" + inv["customer_id"].astype(str),
            "amount": inv["mrr"].astype(float),
            "currency": pd.Series(["INR"] * len(inv), dtype="string"),
            "status": pd.Series(np.where(inv["failed"], "failed", "paid"), dtype="string"),
            "attempted_at": attempted,
            "paid_at": pd.Series(
                np.where(inv["failed"], pd.NaT, attempted), dtype="datetime64[ns]"
            ),
            "failure_code": pd.Series(
                np.where(
                    inv["failed"],
                    rng.choice(
                        ["insufficient_funds", "expired_card", "do_not_honor"],
                        size=len(inv),
                        p=[0.45, 0.30, 0.25],
                    ),
                    None,
                ),
                dtype="string",
            ),
            "attempt_number": np.ones(len(inv), dtype="int64"),
            "available_at": attempted + pd.to_timedelta(settle_days, unit="D"),
        }
    )

    # --- events -------------------------------------------------------------
    # Expand each month's session count into individual timestamped sessions.
    events = _expand_sessions(panel, month_ts, rng)

    # --- tickets ------------------------------------------------------------
    tickets = _expand_tickets(panel, month_ts, rng)

    return Dataset(
        customers=customers,
        subscriptions=subs,
        invoices=invoices,
        events=events,
        tickets=tickets,
    ).validate()


def _expand_sessions(panel, month_ts, rng) -> pd.DataFrame:
    counts = panel["sessions_30d"].to_numpy().astype(int)
    if counts.sum() == 0:
        from keel.core.schema import EVENTS, empty

        return empty(EVENTS)

    row_of = np.repeat(np.arange(len(panel)), counts)
    cid = panel["customer_id"].to_numpy().astype(str)[row_of]
    base = month_ts(panel["month"].to_numpy())[row_of]

    # Spread sessions uniformly through the month they belong to.
    offset = pd.to_timedelta(rng.uniform(0, 30.44, len(row_of)), unit="D")
    occurred = base + offset
    # Client-side events upload with a short, variable delay.
    available = occurred + pd.to_timedelta(rng.uniform(0.01, 0.25, len(row_of)), unit="D")

    return pd.DataFrame(
        {
            "event_id": ["ev_" + str(i) for i in range(len(row_of))],
            "customer_id": cid,
            "name": pd.Series(["session_start"] * len(row_of), dtype="string"),
            "occurred_at": occurred,
            "available_at": available,
            "value": np.full(len(row_of), np.nan),
        }
    )


def _expand_tickets(panel, month_ts, rng) -> pd.DataFrame:
    counts = panel["support_tickets_90d"].to_numpy().astype(int)
    if counts.sum() == 0:
        from keel.core.schema import TICKETS, empty

        return empty(TICKETS)

    row_of = np.repeat(np.arange(len(panel)), counts)
    cid = panel["customer_id"].to_numpy().astype(str)[row_of]
    base = month_ts(panel["month"].to_numpy())[row_of]
    opened = base + pd.to_timedelta(rng.uniform(0, 30.44, len(row_of)), unit="D")

    resolved_days = rng.exponential(3.0, len(row_of))
    unresolved = rng.random(len(row_of)) < 0.15

    return pd.DataFrame(
        {
            "ticket_id": ["tk_" + str(i) for i in range(len(row_of))],
            "customer_id": cid,
            "opened_at": opened,
            "resolved_at": pd.Series(
                np.where(unresolved, pd.NaT, opened + pd.to_timedelta(resolved_days, unit="D")),
                dtype="datetime64[ns]",
            ),
            "severity": pd.Series(
                rng.choice(["low", "normal", "high"], size=len(row_of), p=[0.5, 0.35, 0.15]),
                dtype="string",
            ),
            "available_at": opened,
        }
    )


def at_risk_at(sim: SimResult, month: int, anchor: pd.Timestamp = ANCHOR) -> np.ndarray:
    """Customer ids still active at a given simulation month.

    Needed because a training panel must only contain customers actually at risk --
    including churned customers as ongoing rows would be a different, quieter kind
    of leakage.
    """
    snap = sim.panel[sim.panel["month"] == month]
    return snap["customer_id"].astype(str).to_numpy()


def month_timestamps(months: list[int], anchor: pd.Timestamp = ANCHOR) -> list[pd.Timestamp]:
    return [anchor + pd.Timedelta(days=float(m) * 30.44) for m in months]
