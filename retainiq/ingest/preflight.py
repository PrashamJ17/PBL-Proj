"""Check a prospect's export before anything is computed from it.

Phase 2's gate is a paying client, and the delivery motion is: a founder exports some
CSVs, we return a Churn Autopsy. The failure that ends that motion is not a crash --
a crash is recoverable and honest. It is **sending a confident report built on a
misread file**, because the prospect will find it, and a diagnostic that got their own
revenue wrong is unrecoverable.

So this runs first and answers one question: *is this file safe to compute from, and
what have we had to assume?* Nothing here models anything. It is a smoke alarm.

The check that motivates the module
-----------------------------------
**Stripe exports amounts in minor units.** A `Plan Amount` of 2900 is $29.00. Load it as
MRR and every money figure in the report is 100x too large, including the headline "churn
costs you X per year" -- which is the number the whole engagement is sold on. Nothing
downstream can detect it, because 100x of a plausible number is still a number.

This is D-057 in a different costume: a units error that is self-consistent everywhere
and therefore invisible to every test. It happened once inside our own decision rule. The
difference here is that the wrong number would be printed on a document with a prospect's
name on it.

The heuristic is deliberately noisy in the safe direction. It cannot *know* the units, so
it never silently converts -- it stops the run and makes a human answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from retainiq.core.schema import Dataset

__all__ = ["Preflight", "Check", "preflight", "render_preflight"]

#: Below this many customers, nothing in this project is reliable at all -- D-023 found
#: conventional methods beating random on 75% of draws at n=500, and Phase 3 found
#: nothing beating Kaplan-Meier below 250. A report is still honest work; a *model* is
#: not, and the distinction has to reach the operator before they promise one.
MIN_FOR_MODELLING = 250

#: Monthly prices above this are possible but rare in the SMB subscription market this
#: is aimed at, and are far more often minor units than genuine enterprise contracts.
IMPLAUSIBLE_MRR = 2_000.0


@dataclass
class Check:
    name: str
    level: str
    """``ok`` | ``warn`` | ``block``."""
    detail: str
    fix: str = ""


@dataclass
class Preflight:
    checks: list[Check] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    n_customers: int = 0
    n_subscriptions: int = 0
    window_months: float = 0.0

    @property
    def blocked(self) -> bool:
        return any(c.level == "block" for c in self.checks)

    @property
    def verdict(self) -> str:
        if self.blocked:
            return "BLOCKED — do not send a report from this file"
        if any(c.level == "warn" for c in self.checks):
            return "CHECK — answer the questions below before sending"
        return "READY"


def _money_units(subs: pd.DataFrame) -> Check:
    """Are these major units (29.00) or minor units (2900)?

    Two signals together, because either alone is weak: an implausibly large median, and
    every value being a whole number. Real prices in major units are routinely 29.99;
    minor units are integers by construction.
    """
    mrr = pd.to_numeric(subs["mrr"], errors="coerce").dropna()
    mrr = mrr[mrr > 0]
    if mrr.empty:
        return Check("currency units", "block", "every MRR is zero, missing or negative",
                     "Check the amount column was exported and is not blank.")

    median = float(mrr.median())
    all_integers = bool((mrr % 1 == 0).all())
    if median > IMPLAUSIBLE_MRR and all_integers:
        return Check(
            "currency units", "block",
            f"median MRR is {median:,.0f} and every value is a whole number — this "
            f"looks like minor units (cents/paise), i.e. {median / 100:,.2f} per month",
            "Stripe, Paddle, Chargebee and Razorpay all export amounts in minor units "
            "(cents/paise). Re-run with --divide-amounts-by 100. Do NOT guess: confirm "
            "with the business, because every figure in the report scales with this one.",
        )
    if median > IMPLAUSIBLE_MRR:
        return Check(
            "currency units", "warn",
            f"median MRR is {median:,.0f} per month, which is high for this market",
            "Confirm the amount column is a monthly price in major units, and not an "
            "annual total or a lifetime figure.",
        )
    return Check("currency units", "ok",
                 f"median MRR {median:,.2f} — plausible as a monthly price")


def _dates(subs: pd.DataFrame) -> list[Check]:
    out = []
    started = pd.to_datetime(subs["started_at"], errors="coerce")
    ended = pd.to_datetime(subs["ended_at"], errors="coerce")

    bad = int((ended.notna() & started.notna() & (ended < started)).sum())
    if bad:
        out.append(Check(
            "date order", "block",
            f"{bad:,} subscriptions end before they start",
            "Usually a day/month swap in one of the two columns, or a cancellation "
            "timestamp recorded against the wrong subscription.",
        ))

    if started.notna().any():
        # Backstop for a misparsed timestamp column. Razorpay exports epoch seconds and
        # pandas reads a bare integer as nanoseconds, which lands everything on
        # 1970-01-01. `_to_datetime` handles the common shapes; this catches whatever
        # it did not, because a date that old is never real billing history.
        ancient = int((started < pd.Timestamp("1990-01-01")).sum())
        ancient += int((ended < pd.Timestamp("1990-01-01")).sum())
        if ancient:
            out.append(Check(
                "date parsing", "block",
                f"{ancient:,} dates fall before 1990",
                "Almost always a Unix timestamp read as something else. Check whether "
                "the export stores dates as epoch seconds or milliseconds.",
            ))

        future = int((started > pd.Timestamp.now() + pd.Timedelta(days=1)).sum())
        if future:
            out.append(Check(
                "future dates", "warn", f"{future:,} subscriptions start in the future",
                "Scheduled or trialling subscriptions. Confirm whether they should count.",
            ))
        span = (started.max() - started.min()).days / 30.44
        if span < 6:
            out.append(Check(
                "history", "block",
                f"signups span only {span:.1f} months",
                "Retention curves need enough history for customers to have had the "
                "chance to leave. Under six months there is nothing to measure yet.",
            ))
        elif span < 12:
            out.append(Check(
                "history", "warn", f"signups span {span:.1f} months",
                "Anything about annual retention will be extrapolation. Say so in the "
                "report rather than quietly annualising.",
            ))
    return out


def _churn(subs: pd.DataFrame) -> Check:
    ended = pd.to_datetime(subs["ended_at"], errors="coerce")
    rate = float(ended.notna().mean())
    if rate == 0:
        return Check("churn signal", "block", "no subscription has an end date",
                     "Either nobody has ever cancelled (implausible) or the "
                     "cancellation column was not exported. Without it there is no "
                     "churn to analyse.")
    if rate > 0.9:
        return Check("churn signal", "warn",
                     f"{rate:.0%} of all subscriptions have ended",
                     "Check this is the full customer list and not an export already "
                     "filtered to cancelled accounts.")
    return Check("churn signal", "ok", f"{rate:.0%} of subscriptions have ended")


def _coverage(ds: Dataset) -> list[Check]:
    out = []
    cust_ids = set(ds.customers["customer_id"])
    sub_cust = set(ds.subscriptions["customer_id"])
    never = len(cust_ids - sub_cust)
    if never > 0.5 * max(len(cust_ids), 1):
        out.append(Check(
            "coverage", "warn",
            f"{never:,} of {len(cust_ids):,} customers have no subscription",
            "Often free-tier or lead records. Confirm whether they belong in the "
            "denominator; including them deflates every rate in the report.",
        ))

    # Duplicate keys are deliberately NOT checked here: `Dataset.validate` rejects them
    # during `load`, so a check at this level could never fire on the real path and
    # would imply a safety net that does not exist.

    n = len(cust_ids)
    if n < MIN_FOR_MODELLING:
        out.append(Check(
            "sample size", "warn",
            f"{n:,} customers — below the {MIN_FOR_MODELLING} where our own benchmarks "
            f"show any model beating a population average",
            "A descriptive Autopsy is still honest and useful at this size. Do not "
            "promise per-customer predictions from it.",
        ))
    return out


def preflight(ds: Dataset, assumptions: list[str] | None = None) -> Preflight:
    """Run every check against an already-loaded dataset."""
    checks: list[Check] = [_money_units(ds.subscriptions)]
    checks += _dates(ds.subscriptions)
    checks.append(_churn(ds.subscriptions))
    checks += _coverage(ds)

    started = pd.to_datetime(ds.subscriptions["started_at"], errors="coerce")
    window = 0.0
    if started.notna().any():
        window = float((started.max() - started.min()).days / 30.44)

    return Preflight(
        checks=checks,
        assumptions=list(assumptions or []),
        n_customers=int(ds.customers["customer_id"].nunique()),
        n_subscriptions=int(len(ds.subscriptions)),
        window_months=window,
    )


def render_preflight(p: Preflight) -> str:
    """Plain text for the operator. Blockers first, because they end the run."""
    icon = {"ok": "  ok  ", "warn": " CHECK", "block": " BLOCK"}
    lines = [
        "PREFLIGHT — is this export safe to compute from?",
        "=" * 78,
        f"  {p.n_customers:,} customers · {p.n_subscriptions:,} subscriptions · "
        f"{p.window_months:.0f} months of signups",
        "",
        f"  VERDICT: {p.verdict}",
        "",
    ]
    order = {"block": 0, "warn": 1, "ok": 2}
    for c in sorted(p.checks, key=lambda c: order[c.level]):
        lines.append(f"[{icon[c.level]}] {c.name}: {c.detail}")
        if c.fix and c.level != "ok":
            lines.append(f"          -> {c.fix}")
    if p.assumptions:
        lines += ["", "ASSUMPTIONS MADE FOR YOU (each one is a question for the client):"]
        lines += [f"  - {a}" for a in p.assumptions]
    lines += [
        "",
        "-" * 78,
        "Nothing here is modelled. This only asks whether the file means what it looks",
        "like it means -- because a report with the wrong revenue in it costs more than",
        "no report at all.",
    ]
    return "\n".join(lines)
