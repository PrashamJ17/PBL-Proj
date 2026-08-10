"""CSV worklists: the rows a business can actually act on.

The Autopsy is an argument. It is read once, forwarded to a co-founder, and closed. What
somebody then has to do on Monday is work through a *list*, and a list belongs in a
spreadsheet, where they can sort it, filter it, assign it and tick it off.

So these are not the report in another format. Exporting a narrative with charts to Excel
makes it worse, not better. These are the specific customers behind the two findings that
need no model at all, with the money attached.

**Everything here is descriptive, and that is a constraint rather than a limitation.**
Every column is a fact already in the client's own billing export: this invoice failed,
this subscription ended, this is what it was worth. Nothing is predicted. That matters
commercially as much as scientifically -- a list titled "customers likely to churn" would
be claiming exactly what D-054 and D-058 say we cannot deliver, and it is also the list a
prospect is most likely to check against their own intuition and find wanting. A list of
payments that genuinely failed is checkable, and being checkable is the point.

The two lists, and why these two:

**Unrecovered failures.** Payments that failed and were never collected, flagged by
whether that customer is still subscribed. That flag selects between two different jobs:
chase money the business has already earned, or accept that the failure is why somebody
left and fix the billing so it stops happening. Either way it needs a billing fix rather
than a retention offer, and it is the finding that pays for the engagement.

**Departures.** Who left, when, what they were worth, and whether an unrecovered payment
failure preceded it. The second column is the one most businesses have never seen, because
their tooling counts cancellations and failures separately and never joins them.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from keel.report.autopsy import INVOLUNTARY_WINDOW_DAYS

__all__ = ["unrecovered_failures", "departures", "write_worklists"]


def _as_date(col: pd.Series) -> pd.Series:
    """Dates as plain `YYYY-MM-DD` for a spreadsheet.

    pandas writes a nanosecond-resolution timestamp as `2024-04-01 07:40:48.000000000`,
    which is noise in a client-facing sheet and makes the column awkward to sort in
    Excel. Nobody chasing a failed payment needs the second it happened.
    """
    return pd.to_datetime(col, errors="coerce").dt.strftime("%Y-%m-%d")


def _failures(data) -> pd.DataFrame:
    """Unpaid invoice attempts, with a `recovered` flag, or an empty frame."""
    inv = data.invoices
    if inv.empty:
        return pd.DataFrame()
    failed = inv[inv["status"].astype("string").str.lower().isin(["failed", "uncollectible"])]
    if failed.empty:
        return pd.DataFrame()
    out = failed.copy()
    # A failure is recovered if that customer later has a paid invoice of the same value.
    paid = inv[inv["paid_at"].notna()][["customer_id", "amount", "paid_at"]]
    if paid.empty:
        out["recovered"] = False
        return out
    merged = out.merge(paid, on="customer_id", how="left", suffixes=("", "_paid"))
    close = (merged["amount_paid"] - merged["amount"]).abs() <= 0.01
    later = merged["paid_at_paid"] >= merged["attempted_at"]
    merged["hit"] = close & later
    rec = merged.groupby("invoice_id")["hit"].any()
    out["recovered"] = out["invoice_id"].map(rec).fillna(False).astype(bool)
    return out


def unrecovered_failures(data) -> pd.DataFrame:
    """Payments that failed and were never collected.

    Named for what it contains rather than what we would like it to contain. The first
    draft called this "recoverable", and on the sample every single row turned out to be
    a customer who had already left -- so the total recoverable from active customers was
    zero and the title was a promise the data did not keep.

    `still_subscribed` is therefore the column that matters, because it selects between
    two different jobs: chase the payment, or accept the failure cost you the customer
    and fix the billing so it stops happening. Sorted with the still-subscribed first,
    then by amount, because that is the order somebody with a finite morning should work
    through it in.
    """
    fails = _failures(data)
    if fails.empty:
        return pd.DataFrame(columns=[
            "customer_id", "amount", "failed_on", "decline_reason", "attempt_number",
            "still_subscribed", "suggested_action",
        ])

    open_fails = fails[~fails["recovered"]].copy()
    active = set(data.subscriptions.loc[data.subscriptions["ended_at"].isna(), "customer_id"])
    open_fails["still_subscribed"] = open_fails["customer_id"].isin(active)

    open_fails["suggested_action"] = [
        _action(code, still)
        for code, still in zip(open_fails["failure_code"].astype("string").fillna("unknown"),
                               open_fails["still_subscribed"], strict=True)
    ]
    open_fails["amount"] = open_fails["amount"].round(2)
    open_fails["attempted_at"] = _as_date(open_fails["attempted_at"])
    out = open_fails.rename(columns={
        "attempted_at": "failed_on", "failure_code": "decline_reason",
    })[[
        "customer_id", "amount", "failed_on", "decline_reason", "attempt_number",
        "still_subscribed", "suggested_action",
    ]]
    # Still-subscribed first: that money is collectable without winning anyone back.
    return out.sort_values(["still_subscribed", "amount"], ascending=[False, False])


def _action(code: str, still_subscribed: bool) -> str:
    """What to do, which depends on the decline reason *and* on whether they are still
    a customer. The same expired card is a collection job if they stayed and a winback
    plus a billing fix if it is why they left."""
    fix = {
        "insufficient_funds": "retry on their next salary date, not a fixed offset",
        "expired_card": "the card cannot be charged again; ask for a new one",
        "do_not_honor": "the issuer refused; retrying rarely works, ask for another method",
        "lost_card": "the card is dead; ask for a new one",
        "stolen_card": "the card is dead; ask for a new one",
        "processing_error": "transient, so a straightforward retry usually clears it",
    }.get(str(code), "unclassified decline; check the processor's own reason")
    if still_subscribed:
        return f"Still a customer, so collect: {fix}."
    return f"Already gone, and this failure may be why. Win back, and {fix}."


def departures(data) -> pd.DataFrame:
    """Who left, what they were worth, and whether a failed payment preceded it."""
    subs = data.subscriptions
    ended = subs[subs["ended_at"].notna()].copy()
    cols = ["customer_id", "plan", "mrr", "started_at", "ended_at",
            "months_subscribed", "annual_value_lost", "preceded_by_failed_payment"]
    if ended.empty:
        return pd.DataFrame(columns=cols)

    ended["months_subscribed"] = (
        (ended["ended_at"] - ended["started_at"]).dt.total_seconds() / 86400.0 / 30.44
    ).round(1)
    ended["annual_value_lost"] = (ended["mrr"] * 12).round(2)
    ended["mrr"] = ended["mrr"].round(2)

    ended["preceded_by_failed_payment"] = False
    fails = _failures(data)
    if not fails.empty:
        unrec = fails[~fails["recovered"]][["customer_id", "attempted_at"]]
        if not unrec.empty:
            m = ended[["customer_id", "ended_at"]].merge(unrec, on="customer_id", how="inner")
            gap = (m["ended_at"] - m["attempted_at"]).dt.total_seconds() / 86400.0
            flagged = set(m.loc[(gap >= -1) & (gap <= INVOLUNTARY_WINDOW_DAYS), "customer_id"])
            ended["preceded_by_failed_payment"] = ended["customer_id"].isin(flagged)

    out = ended[cols].sort_values("annual_value_lost", ascending=False)
    # Formatted last, after every date has been used as a date. Doing it earlier turned
    # `ended_at` into a string before the failed-payment join needed to subtract it.
    out["started_at"] = _as_date(out["started_at"])
    out["ended_at"] = _as_date(out["ended_at"])
    return out


def write_worklists(data, outdir: Path | str = ".", prefix: str = "") -> list[Path]:
    """Write both lists as CSV. Returns the paths written.

    CSV rather than xlsx: it opens in Excel, Sheets and Numbers without a converter and
    without adding a dependency to a project whose core is numpy/pandas/scipy
    (invariant 7). Nothing here needs formatting or formulas -- it needs to be sortable.
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, frame in (("unrecovered_failed_payments", unrecovered_failures(data)),
                        ("departures", departures(data))):
        path = outdir / f"{prefix}{name}.csv"
        frame.to_csv(path, index=False)
        written.append(path)
    return written
