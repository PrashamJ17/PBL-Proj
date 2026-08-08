"""What is a dunning policy actually worth?

Recovery rate is the number every dunning vendor quotes, and on its own it is
misleading in two directions.

**It understates the prize.** Recovering a failed payment does not retain one invoice;
it retains a *customer*, whose remaining lifetime value is many multiples of the
payment. A 6-point recovery improvement is worth far more than 6% of one month's
billing.

**It ignores what the recovery cost.** Every dunning email is also a message telling
the customer they are paying you. Push hard enough and you recover the payment and lose
the customer — the salience mechanism from D-002, arriving through the billing path
instead of the marketing one (D-032). A policy compared on recovery rate alone will
always prefer "email them more", which is exactly the wrong lesson.

So the metric here is **net value**: lifetime value retained by recovered payments,
minus the lifetime value destroyed by the contact it took to get them, minus
operational cost.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from keel.policy.dunning import ALL_POLICIES, RetryPolicy, apply_policy
from keel.sim.dunning import DunningConfig, generate_failures


@dataclass(frozen=True)
class Economics:
    """Unit economics for converting recovery into money."""

    gross_margin: float = 0.80
    baseline_monthly_churn: float = 0.045
    """Voluntary churn hazard before any dunning contact. Used to convert a fatigue
    increment into expected lifetime-value loss."""
    cost_per_attempt: float = 0.10
    """Processor and operational cost of one retry."""
    cost_per_email: float = 0.02
    horizon_months: int = 36
    """Cap on expected remaining lifetime, so CLV cannot run away."""


def _expected_lifetime_months(hazard: np.ndarray | float, horizon: int) -> np.ndarray:
    """Expected remaining months under a constant monthly churn hazard, capped."""
    h = np.clip(np.asarray(hazard, dtype=float), 1e-6, 0.999)
    return (1.0 - (1.0 - h) ** horizon) / h


def _logit(p: float) -> float:
    return float(np.log(p / (1.0 - p)))


def _expit(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class DunningResult:
    name: str
    recovery_rate: float
    attempts_per_failure: float
    emails_per_failure: float
    clv_retained: float
    clv_lost_to_fatigue: float
    operational_cost: float

    @property
    def net_value(self) -> float:
        return self.clv_retained - self.clv_lost_to_fatigue - self.operational_cost


def evaluate(
    failures: pd.DataFrame,
    policy: RetryPolicy,
    cfg: DunningConfig,
    econ: Economics,
    rng: np.random.Generator,
) -> DunningResult:
    """Score one policy in money rather than recovery rate."""
    out = apply_policy(failures, policy, cfg, rng)

    mrr = out["amount"].to_numpy()
    margin = mrr * econ.gross_margin

    # A recovered payment retains the customer, not just the invoice.
    base_months = _expected_lifetime_months(econ.baseline_monthly_churn, econ.horizon_months)
    clv = margin * base_months
    retained = float(clv[out["recovered"].to_numpy()].sum())

    # Fatigue raises the voluntary-churn hazard, shortening expected lifetime. Only
    # customers still present can be lost this way, so it applies to the recovered
    # ones -- the unrecovered have already gone.
    fatigued_hazard = _expit(_logit(econ.baseline_monthly_churn) + out["fatigue"].to_numpy())
    fatigued_months = _expected_lifetime_months(fatigued_hazard, econ.horizon_months)
    clv_after = margin * fatigued_months
    lost = float((clv - clv_after)[out["recovered"].to_numpy()].sum())

    ops = float(
        out["attempts"].sum() * econ.cost_per_attempt + out["emails"].sum() * econ.cost_per_email
    )

    return DunningResult(
        name=policy.name,
        recovery_rate=float(out["recovered"].mean()),
        attempts_per_failure=float(out["attempts"].mean()),
        emails_per_failure=float(out["emails"].mean()),
        clv_retained=retained,
        clv_lost_to_fatigue=lost,
        operational_cost=ops,
    )


def run(
    n_failures: int = 40_000,
    cfg: DunningConfig | None = None,
    econ: Economics | None = None,
    policies: list[RetryPolicy] | None = None,
    account_updater: bool = False,
    seed: int = 0,
) -> list[DunningResult]:
    cfg = cfg or DunningConfig()
    if account_updater:
        cfg = replace(cfg, account_updater=True)
    econ = econ or Economics()
    policies = policies or ALL_POLICIES

    failures = generate_failures(n_failures, cfg, np.random.default_rng(seed))
    return [
        evaluate(failures, p, cfg, econ, np.random.default_rng(seed + 1 + i))
        for i, p in enumerate(policies)
    ]


def report(results: list[DunningResult], n_failures: int) -> str:
    baseline = next((r for r in results if r.name == "processor_default"), None)

    lines = [
        f"Dunning policy value  (n={n_failures:,} failed payments)",
        "=" * 94,
        f"{'policy':<20}{'recovery':>10}{'attempts':>10}{'emails':>9}"
        f"{'CLV kept':>13}{'fatigue':>11}{'net':>13}{'vs default':>12}",
        "-" * 94,
    ]
    for r in results:
        delta = ""
        if baseline and r.name != "processor_default":
            diff = r.net_value - baseline.net_value
            delta = f"{diff:+,.0f}"
        lines.append(
            f"{r.name:<20}{r.recovery_rate:>9.1%}{r.attempts_per_failure:>10.2f}"
            f"{r.emails_per_failure:>9.2f}{r.clv_retained:>13,.0f}"
            f"{-r.clv_lost_to_fatigue:>11,.0f}{r.net_value:>13,.0f}{delta:>12}"
        )
    lines.append("-" * 94)
    lines.append(
        "CLV kept = lifetime value of retained customers. fatigue = lifetime value\n"
        "destroyed by dunning contact. net = kept - fatigue - operational cost."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    n = 40_000
    res = run(n_failures=n)
    print(report(res, n))
