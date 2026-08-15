"""CLV from the competing-risks survival model.

The point of computing lifetime value here is not to produce a nice number. It is
that **a retention decision is denominated in money and a churn model is denominated
in probability**, and nothing in Phases 0-2 converted between them. `treatment_value`
is where the two meet: the worth of an intervention is `(-tau) * CLV - cost`, so an
identical treatment effect is worth a hundred times more on one customer than on
another. No amount of churn-model accuracy tells those two customers apart.

Two things this experiment is designed to show, both of which are checks rather than
demonstrations:

**The value shortfall decomposes exactly by cause.** `sum_k shortfall_k` equals the
gap between perfect retention and expected value, with no residual. That splits the
leak into "money lost through the product" and "money lost through the billing
system" -- which have different fixes, different costs, and, per Phase 2, wildly
different effort-to-recovery ratios. A single blended churn number cannot express it.

**Ranking by value at risk is not the same as ranking by churn risk.** The overlap
between the two top deciles is reported because it is the cheapest possible
illustration of why a churn score is not a decision -- and, per D-026, neither is
value at risk on its own. Money at risk is not money you can *save*; that needs a
treatment effect, and that is Phase 4.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from retainiq.benchmarks.survival_data import subsim_survival
from retainiq.models.clv import (
    clv,
    expected_remaining_months,
    value_at_risk,
    value_shortfall_by_cause,
)
from retainiq.models.survival.discrete import CompetingRisksHazard

#: A stated assumption, not a finding. SMB SaaS gross margin is typically 70-80%;
#: the discount rate is a small private company's cost of capital. Both are inputs
#: the tenant should override, and both are printed with the results so the reader
#: can see what the number depends on (D-022's principle, applied to money).
DEFAULT_MARGIN_FRACTION = 0.75
DEFAULT_ANNUAL_DISCOUNT = 0.12


@dataclass
class ClvSummary:
    horizon: int
    observed_support: int
    mean_clv: float
    median_clv: float
    p90_clv: float
    mean_remaining_months: float
    total_clv: float
    shortfall_total: float
    shortfall_by_cause: dict[str, float]
    decile_overlap: float
    """Share of the top-value-at-risk decile that is also in the top churn-risk
    decile. 1.0 would mean money adds nothing to a risk ranking."""

    def report(self) -> str:
        lines = [
            f"horizon {self.horizon} months (observed support {self.observed_support})",
            f"  CLV per customer: mean {self.mean_clv:,.0f}  median {self.median_clv:,.0f}"
            f"  p90 {self.p90_clv:,.0f}",
            f"  expected remaining months: {self.mean_remaining_months:.1f}",
            f"  book value: {self.total_clv:,.0f}",
            f"  shortfall vs perfect retention: {self.shortfall_total:,.0f}",
        ]
        for cause, amount in self.shortfall_by_cause.items():
            share = amount / self.shortfall_total if self.shortfall_total else float("nan")
            lines.append(f"    {cause:<14} {amount:>12,.0f}  ({share:.1%})")
        lines.append(
            f"  top-value-at-risk decile overlaps top-churn-risk decile: "
            f"{self.decile_overlap:.0%}"
        )
        return "\n".join(lines)


def run(
    result,
    horizon: int | None = None,
    margin_fraction: float = DEFAULT_MARGIN_FRACTION,
    annual_discount: float = DEFAULT_ANNUAL_DISCOUNT,
    seed: int = 0,
) -> tuple[ClvSummary, pd.DataFrame]:
    """Fit the competing-risks hazard on SubSim and value every customer.

    Returns the summary and a per-customer frame, so the caller can inspect the
    distribution rather than only its moments -- CLV is heavily right-skewed and a
    mean on its own is close to meaningless.
    """
    data = subsim_survival(result)
    support = int(data.duration.max())
    horizon = horizon or support

    model = CompetingRisksHazard(data.cause_names, learner="logistic", pool_after=12,
                                 seed=seed).fit(data)

    survival = model.survival(data.X, horizon)
    cif = model.cumulative_incidence(data.X, horizon)
    margin = data.X["mrr"].to_numpy() * margin_fraction

    # `observed_support` is passed, so a horizon past the data raises rather than
    # silently extending the tail hazard (D-046).
    values = clv(survival, margin, annual_discount, observed_support=support)
    remaining = expected_remaining_months(survival)

    next_month = 1.0 - survival[:, 0]
    at_risk = value_at_risk(values, next_month)
    shortfalls = value_shortfall_by_cause(cif, margin, annual_discount)

    per_customer = pd.DataFrame({
        "customer_id": np.arange(len(data)),
        "mrr": data.X["mrr"].to_numpy(),
        "clv": values,
        "expected_remaining_months": remaining,
        "hazard_next_month": next_month,
        "value_at_risk": at_risk,
        **{f"shortfall_{data.cause_names[c]}": v for c, v in shortfalls.items()},
    })

    k = max(1, len(data) // 10)
    top_value = set(np.argsort(-at_risk)[:k].tolist())
    top_risk = set(np.argsort(-next_month)[:k].tolist())

    return (
        ClvSummary(
            horizon=horizon,
            observed_support=support,
            mean_clv=float(values.mean()),
            median_clv=float(np.median(values)),
            p90_clv=float(np.percentile(values, 90)),
            mean_remaining_months=float(remaining.mean()),
            total_clv=float(values.sum()),
            shortfall_total=float(sum(v.sum() for v in shortfalls.values())),
            shortfall_by_cause={
                data.cause_names[c]: float(v.sum()) for c, v in shortfalls.items()
            },
            decile_overlap=len(top_value & top_risk) / k,
        ),
        per_customer,
    )


def main() -> None:
    from retainiq.sim import SimConfig, simulate

    summary, frame = run(simulate(SimConfig(4000, 24, 7)))
    print(
        f"assumptions: margin {DEFAULT_MARGIN_FRACTION:.0%} of MRR, "
        f"discount {DEFAULT_ANNUAL_DISCOUNT:.0%}/yr -- both stated inputs, not findings\n"
    )
    print(summary.report())
    print("\nmost valuable customers by value at risk:")
    print(
        frame.nlargest(5, "value_at_risk")[
            ["customer_id", "mrr", "clv", "hazard_next_month", "value_at_risk"]
        ].to_string(index=False, float_format=lambda v: f"{v:,.2f}")
    )


if __name__ == "__main__":
    main()
