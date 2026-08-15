"""The Churn Autopsy: what a business's own data says about its churn.

This is the first thing a real business receives. They export three CSVs from their
billing dashboard -- customers, subscriptions, invoices -- and get back a document with
money attached to every finding.

Two rules govern everything here, and both exist to keep the report honest when it is
the only thing standing between us and a fee.

**Every number is computed from their data, or labelled as an estimate.** Where a
finding depends on a published benchmark rather than their own history -- "you could
recover more" -- the report says so explicitly and shows the benchmark. A report that
blurs the two is a sales document, and the whole point of leading with this is that it
is not one.

**Findings are ranked by money, not by how interesting they are.** The most
statistically interesting thing in a churn dataset is rarely the most valuable. An
owner reading this has half an hour and one decision to make.

What can and cannot be computed from billing data alone
--------------------------------------------------------
Billing data supports: retention curves, revenue vs logo churn, the voluntary /
involuntary split, failed-payment economics, and decline-code mix. That is enough for a
useful report and it needs no engineering work from the customer.

It does **not** support anything causal. Nothing here says who to contact or what an
intervention would achieve -- that requires the intervention history nobody has yet
(see `docs/DECISIONS.md` D-026 on why targeting advice without it is worse than
useless).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from retainiq.core.schema import Dataset
from retainiq.sim.dunning import SMART_RECOVERY_BAND

#: A failed invoice counts as recovered if the customer pays within this window.
RECOVERY_WINDOW_DAYS = 30

#: A subscription ending within this long after an unrecovered failure is treated as
#: involuntary churn -- the customer never decided to leave, the card did.
INVOLUNTARY_WINDOW_DAYS = 45


@dataclass
class Finding:
    """One actionable conclusion, with money attached."""

    title: str
    annual_value: float
    """Estimated annual rupees at stake. Ranked on this."""
    measured: bool
    """True if computed entirely from their data. False if it leans on a published
    benchmark, in which case the report must say so."""
    detail: str
    action: str

    @property
    def confidence(self) -> str:
        return "measured from your data" if self.measured else "estimated from industry benchmarks"


@dataclass
class Autopsy:
    """Everything the report needs, computed once."""

    # --- scale ---
    n_customers: int
    n_active: int
    mrr_active: float
    window_days: float

    # --- churn ---
    monthly_logo_churn: float
    monthly_revenue_churn: float
    retention_curve: pd.DataFrame
    n_churned: int
    n_involuntary: int

    # --- payments ---
    n_failures: int
    failed_amount: float
    recovered_amount: float
    recovery_rate: float
    decline_mix: pd.DataFrame

    notes: list[str] = field(default_factory=list)
    """Caveats about what could not be computed, shown in the report."""

    @property
    def arr_active(self) -> float:
        return self.mrr_active * 12

    @property
    def involuntary_share(self) -> float:
        return self.n_involuntary / self.n_churned if self.n_churned else 0.0

    @property
    def annual_churn_cost(self) -> float:
        """Revenue lost per year at the current churn rate."""
        return self.mrr_active * self.monthly_revenue_churn * 12

    def findings(self) -> list[Finding]:
        """Ranked conclusions. Money first."""
        out: list[Finding] = []

        # --- 1. failed payments, measured against their own recovery rate --------
        if self.n_failures > 0:
            annual_failed = self._annualise(self.failed_amount)
            unrecovered = annual_failed * (1 - self.recovery_rate)

            target = SMART_RECOVERY_BAND[0]
            if self.recovery_rate < target:
                gain = annual_failed * (target - self.recovery_rate)
                out.append(Finding(
                    title="Failed payments are recoverable and you are leaving money on the table",
                    annual_value=gain,
                    measured=False,
                    detail=(
                        f"You lose about {_money(annual_failed)} a year to failed payments and "
                        f"recover {self.recovery_rate:.0%} of it. Operators with dedicated "
                        f"retry logic recover {SMART_RECOVERY_BAND[0]:.0%}-"
                        f"{SMART_RECOVERY_BAND[1]:.0%}. "
                        f"Closing that gap is worth roughly {_money(gain)} a year. "
                        f"Your recovery rate is measured from your invoices; the target is a "
                        f"published benchmark, not a promise."
                    ),
                    action=(
                        "Retry on the decline code rather than a fixed schedule: wait for payday "
                        "on insufficient_funds, and stop retrying expired cards entirely -- they "
                        "cannot succeed. Switch on your processor's card updater."
                    ),
                ))
            else:
                out.append(Finding(
                    title="Failed-payment recovery is already strong",
                    annual_value=unrecovered,
                    measured=True,
                    detail=(
                        f"You recover {self.recovery_rate:.0%} of "
                        f"{_money(annual_failed)} in annual "
                        f"failed payments, which is at or above the published top quartile. "
                        f"{_money(unrecovered)} a year still goes unrecovered, but the easy gains "
                        f"here are already taken."
                    ),
                    action="Focus effort on voluntary churn instead; this lever is close to spent.",
                ))

        # --- 2. involuntary share ------------------------------------------------
        if self.n_churned > 0 and self.involuntary_share > 0.15:
            value = self.annual_churn_cost * self.involuntary_share
            out.append(Finding(
                title=(
                    f"{self.involuntary_share:.0%} of your churn is a payments problem, "
                    "not a product problem"
                ),
                annual_value=value,
                measured=True,
                detail=(
                    f"{self.n_involuntary} of {self.n_churned} departures followed an unrecovered "
                    f"payment failure. Those customers did not decide to leave -- their card did. "
                    f"That is about {_money(value)} a year being lost to billing rather than to "
                    f"anything about your product or pricing."
                ),
                action=(
                    "Treat this as a billing engineering task, not a retention campaign. "
                    "Discounts and win-back emails do nothing for an expired card."
                ),
            ))

        # --- 3. the largest decline code ----------------------------------------
        if len(self.decline_mix):
            top = self.decline_mix.iloc[0]
            annual = self._annualise(float(top["amount"]))
            out.append(Finding(
                title=f"'{top['code']}' is your biggest single decline reason",
                annual_value=annual * (1 - float(top["recovery_rate"])),
                measured=True,
                detail=(
                    f"{int(top['n'])} failures worth {_money(annual)} a year, of which you "
                    f"recover {float(top['recovery_rate']):.0%}. "
                    + _code_advice(str(top["code"]))
                ),
                action=_code_action(str(top["code"])),
            ))

        # --- 4. overall churn cost ----------------------------------------------
        out.append(Finding(
            title="What churn costs you annually",
            annual_value=self.annual_churn_cost,
            measured=True,
            detail=(
                f"At {self.monthly_revenue_churn:.1%} monthly revenue churn on "
                f"{_money(self.mrr_active)} MRR, you lose about "
                f"{_money(self.annual_churn_cost)} a year. Logo churn is "
                f"{self.monthly_logo_churn:.1%} a month."
                + (
                    "  Revenue churn running above logo churn means you are losing your "
                    "larger customers first, which is the worse pattern."
                    if self.monthly_revenue_churn > self.monthly_logo_churn * 1.15 else ""
                )
            ),
            action=(
                "Fix the involuntary share first -- it is mechanical. Voluntary churn needs "
                "a causal approach and is a longer project."
            ),
        ))

        return sorted(out, key=lambda f: -f.annual_value)

    def _annualise(self, amount: float) -> float:
        """Scale an observed amount to an annual rate."""
        if self.window_days <= 0:
            return amount
        return amount * 365.0 / self.window_days


def _money(x: float) -> str:
    if abs(x) >= 1e7:
        return f"₹{x/1e7:.2f} crore"
    if abs(x) >= 1e5:
        return f"₹{x/1e5:.1f} lakh"
    return f"₹{x:,.0f}"


def _code_advice(code: str) -> str:
    return {
        "insufficient_funds": (
            "This is a timing problem, not a payment problem -- the money arrives on payday. "
            "Retrying two days after a failure usually means retrying before they are paid."
        ),
        "expired_card": (
            "Retrying an expired card cannot succeed, however many times you try. Every "
            "attempt is wasted and every reminder email is a reminder they are paying you."
        ),
        "do_not_honor": (
            "A generic issuer refusal. Moderately recoverable, but the reason is opaque and "
            "extra attempts decay quickly."
        ),
        "lost_or_stolen_card": (
            "Effectively unrecoverable by retry. Attempts here are pure waste."
        ),
        "processing_error": (
            "A transient fault. An immediate retry usually works; waiting is what loses these."
        ),
    }.get(code, "")


def _code_action(code: str) -> str:
    return {
        "insufficient_funds": "Move retries onto the next salary date rather than a fixed offset.",
        "expired_card": "Stop retrying. Switch on the card updater and ask for a new card once.",
        "do_not_honor": "Two or three well-spaced attempts, then stop.",
        "lost_or_stolen_card": "One attempt, then stop and ask for a new card.",
        "processing_error": "Retry within minutes, not days.",
    }.get(code, "Review this decline reason with your processor.")


# --- computation ------------------------------------------------------------


def analyse(data: Dataset) -> Autopsy:
    """Compute the autopsy from canonical tables."""
    data.validate()
    subs, inv = data.subscriptions, data.invoices
    notes: list[str] = []

    if subs.empty:
        raise ValueError("no subscriptions: nothing to analyse")

    started = pd.to_datetime(subs["started_at"])
    ended = pd.to_datetime(subs["ended_at"])
    window_start, window_end = started.min(), max(started.max(), ended.max())
    window_days = float((window_end - window_start).days) or 1.0

    active_mask = ended.isna()
    n_active = int(active_mask.sum())
    mrr_active = float(subs.loc[active_mask, "mrr"].sum())

    churned = subs[~active_mask]
    n_churned = len(churned)

    # --- churn rates ---------------------------------------------------------
    months = max(window_days / 30.44, 1.0)
    monthly_logo = (n_churned / len(subs)) / months if len(subs) else 0.0
    lost_mrr = float(churned["mrr"].sum())
    total_mrr = float(subs["mrr"].sum())
    monthly_rev = (lost_mrr / total_mrr) / months if total_mrr else 0.0

    # --- payments ------------------------------------------------------------
    failures, recovered_amount, decline_mix = _payment_analysis(inv, notes)
    n_failures = len(failures)
    failed_amount = float(failures["amount"].sum()) if n_failures else 0.0
    recovery_rate = recovered_amount / failed_amount if failed_amount else 0.0

    # --- involuntary churn ---------------------------------------------------
    n_involuntary = _count_involuntary(subs, failures, notes)

    return Autopsy(
        n_customers=len(data.customers),
        n_active=n_active,
        mrr_active=mrr_active,
        window_days=window_days,
        monthly_logo_churn=monthly_logo,
        monthly_revenue_churn=monthly_rev,
        retention_curve=_retention_curve(subs),
        n_churned=n_churned,
        n_involuntary=n_involuntary,
        n_failures=n_failures,
        failed_amount=failed_amount,
        recovered_amount=recovered_amount,
        recovery_rate=recovery_rate,
        decline_mix=decline_mix,
        notes=notes,
    )


def _payment_analysis(inv: pd.DataFrame, notes: list[str]):
    """Failed invoices, how much came back, and the decline-code breakdown.

    A failure counts as recovered if the same customer has a paid invoice within
    `RECOVERY_WINDOW_DAYS`. That is a heuristic -- billing exports rarely link a
    retry to the attempt it retried -- and it is stated as one in the report.
    """
    empty_mix = pd.DataFrame(columns=["code", "n", "amount", "recovery_rate"])
    if inv.empty:
        notes.append("No invoice data supplied, so failed-payment analysis was skipped.")
        return inv.head(0), 0.0, empty_mix

    failures = inv[inv["status"] == "failed"].copy()
    if failures.empty:
        notes.append("No failed payments found in the supplied invoices.")
        return failures, 0.0, empty_mix

    paid = inv[inv["status"] == "paid"][["customer_id", "attempted_at"]].copy()
    paid = paid.rename(columns={"attempted_at": "paid_at_"})

    merged = failures.merge(paid, on="customer_id", how="left")
    gap = (merged["paid_at_"] - merged["attempted_at"]).dt.total_seconds() / 86400.0
    merged["is_recovery"] = (gap > 0) & (gap <= RECOVERY_WINDOW_DAYS)

    recovered_ids = set(merged.loc[merged["is_recovery"], "invoice_id"])
    failures["recovered"] = failures["invoice_id"].isin(recovered_ids)
    recovered_amount = float(failures.loc[failures["recovered"], "amount"].sum())

    if failures["failure_code"].isna().all():
        notes.append(
            "Invoices carried no decline codes, so the per-reason breakdown is unavailable. "
            "Decline codes are the single most useful field for retry strategy -- worth "
            "including in the next export."
        )
        return failures, recovered_amount, empty_mix

    mix = (
        failures.assign(failure_code=failures["failure_code"].fillna("unknown"))
        .groupby("failure_code")
        .agg(n=("invoice_id", "size"), amount=("amount", "sum"),
             recovery_rate=("recovered", "mean"))
        .reset_index()
        .rename(columns={"failure_code": "code"})
        .sort_values("amount", ascending=False)
        .reset_index(drop=True)
    )
    return failures, recovered_amount, mix


def _count_involuntary(subs: pd.DataFrame, failures: pd.DataFrame, notes: list[str]) -> int:
    """Departures that followed an unrecovered payment failure.

    The customer did not decide to leave; the card did. Distinguishing these matters
    because they need a billing fix, and a retention offer does nothing for them.
    """
    ended = subs[subs["ended_at"].notna()]
    if ended.empty or failures.empty:
        return 0
    if "recovered" not in failures:
        return 0

    unrecovered = failures[~failures["recovered"]][["customer_id", "attempted_at"]]
    if unrecovered.empty:
        return 0

    merged = ended[["customer_id", "ended_at"]].merge(unrecovered, on="customer_id", how="inner")
    gap = (merged["ended_at"] - merged["attempted_at"]).dt.total_seconds() / 86400.0
    hit = merged[(gap >= -1) & (gap <= INVOLUNTARY_WINDOW_DAYS)]
    return int(hit["customer_id"].nunique())


def _retention_curve(subs: pd.DataFrame, max_months: int = 24) -> pd.DataFrame:
    """Share of customers still subscribed after n months.

    Kaplan-Meier style over pooled tenure rather than signup cohorts, because many
    small businesses have too few customers per month for cohort curves to be
    readable -- and because a cohort table with three customers in it invites
    conclusions it cannot support.
    """
    started = pd.to_datetime(subs["started_at"])
    ended = pd.to_datetime(subs["ended_at"])
    observed_end = max(started.max(), ended.max())

    tenure = np.where(
        ended.isna(),
        (observed_end - started).dt.total_seconds() / 86400.0 / 30.44,
        (ended - started).dt.total_seconds() / 86400.0 / 30.44,
    )
    churned = ended.notna().to_numpy()

    rows, surviving = [], 1.0
    for m in range(max_months + 1):
        at_risk = int((tenure >= m).sum())
        if at_risk == 0:
            break
        events = int(((tenure >= m) & (tenure < m + 1) & churned).sum())
        if m > 0:
            surviving *= 1.0 - (events / at_risk if at_risk else 0.0)
        rows.append({"month": m, "at_risk": at_risk, "churned": events,
                     "retention": surviving if m > 0 else 1.0})
    return pd.DataFrame(rows)
