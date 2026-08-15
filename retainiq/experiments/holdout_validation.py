"""Does the holdout estimator recover an effect we already know? (D-065)

Phase 6 exists so that a real engagement can produce a defensible number. Before it is
pointed at a client it has to be pointed at a case where the answer is known, and the
simulator is the only place that case exists: SubSim carries exact per-customer potential
outcomes, so the true average treatment effect is available to compare against.

Three questions, in the order that matters.

**Is the estimator unbiased?** Run many simulated businesses, treat a random 90% and hold
out 10%, and compare the measured lift against the true ATE over the same population. The
mean error should be indistinguishable from zero. If it is not, every downstream claim
about incremental revenue is wrong by that amount.

**Does its confidence interval mean what it says?** A nominal 95% interval should contain
the truth about 95% of the time. Under-coverage would be the dangerous direction: a
business would conclude a campaign worked when the evidence does not support it.

**How large does a holdout have to be?** This is the question a client asks before
agreeing to withhold revenue from part of their base, and it is where the small-sample
theme of this project becomes concrete and unavoidable: the minimum detectable effect at
realistic sizes is often larger than any plausible treatment effect.

The third result is the one worth publishing. It converts "small businesses cannot
measure retention reliably" from an assertion into a number a founder can check against
their own customer count.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from retainiq.policy.holdout import (
    assign_holdout,
    measure_incrementality,
    minimum_detectable_effect,
    required_holdout_size,
)
from retainiq.sim import SimConfig, simulate
from retainiq.sim.counterfactual import potential_outcomes

#: Business sizes swept. The lower end is the segment this project targets; the upper end
#: is included so the reader can see where measurement becomes routine.
SIZES = (250, 500, 1000, 2000, 4000, 10_000)


def one_business(n_customers: int, seed: int, holdout_fraction: float = 0.10) -> dict | None:
    """Simulate one business, run a campaign with a holdout, measure, compare to truth.

    Everybody outside the holdout is treated, which is the cleanest possible test of the
    *estimator* -- it removes any question of which customers were selected and isolates
    whether the measurement machinery recovers a known number.
    """
    sim = simulate(SimConfig(n_customers=n_customers, n_months=24, seed=seed))
    po = potential_outcomes(sim, decision_month=6, horizon=6)
    if len(po) < 60:
        return None

    ids = po["customer_id"].astype(str).to_numpy()
    held = assign_holdout(ids, fraction=holdout_fraction, salt=f"validate-{seed}")
    if held.sum() < 2 or (~held).sum() < 2:
        return None

    # Realised outcome: the holdout gets its untreated outcome, everyone else the
    # treated one. Common random numbers make these the same customer's two futures.
    churned = np.where(held, po["y0"].to_numpy(), po["y1"].to_numpy()).astype(bool)
    retained = ~churned
    value = po["clv"].to_numpy()
    cost = float(po["offer_cost"].mean())

    est = measure_incrementality(retained, held, value, cost_per_treated=cost)

    # Ground truth on the same population: tau is P(churn|treated) - P(churn|control),
    # so the true retention lift is its negative.
    true_lift = float(-po["tau_true"].mean())

    return {
        "n_customers": n_customers,
        "seed": seed,
        "n_treated": est.n_treated,
        "n_holdout": est.n_holdout,
        "measured_lift": est.lift,
        "true_lift": true_lift,
        "error": est.lift - true_lift,
        "ci_lo": est.lift_ci[0],
        "ci_hi": est.lift_ci[1],
        "covered": bool(est.lift_ci[0] <= true_lift <= est.lift_ci[1]),
        "significant": est.significant,
        "p_value": est.p_value,
    }


def validate(sizes=SIZES, seeds: int = 60, holdout_fraction: float = 0.10) -> pd.DataFrame:
    rows = [
        r for n in sizes for s in range(seeds)
        if (r := one_business(n, seed=3000 + s, holdout_fraction=holdout_fraction))
    ]
    return pd.DataFrame(rows)


def summarise(frame: pd.DataFrame) -> pd.DataFrame:
    out = []
    for n, g in frame.groupby("n_customers"):
        out.append({
            "n_customers": n,
            "runs": len(g),
            "mean_holdout": g["n_holdout"].mean(),
            "true_lift": g["true_lift"].mean(),
            "measured_lift": g["measured_lift"].mean(),
            "bias": g["error"].mean(),
            "sd_error": g["error"].std(),
            "coverage": g["covered"].mean(),
            "significant": g["significant"].mean(),
            "ci_width": (g["ci_hi"] - g["ci_lo"]).mean(),
        })
    return pd.DataFrame(out)


def power_table(sizes=SIZES, holdout_fraction: float = 0.10,
                baseline_retention: float = 0.80) -> pd.DataFrame:
    """Minimum detectable effect by business size, against the effect actually delivered."""
    return pd.DataFrame([{
        "n_customers": n,
        "holdout": int(n * holdout_fraction),
        "mde": minimum_detectable_effect(n, holdout_fraction, baseline_retention),
    } for n in sizes])


def report(summary: pd.DataFrame, power: pd.DataFrame, delivered: float) -> str:
    lines = [
        "PHASE 6 -- does the holdout estimator recover a known effect?",
        "=" * 94,
        f"{'n':>7}{'holdout':>9}{'true lift':>11}{'measured':>10}{'bias':>10}"
        f"{'CI width':>10}{'coverage':>10}{'signif':>9}",
        "-" * 94,
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"{int(r.n_customers):>7}{r.mean_holdout:>9.0f}{r.true_lift:>+11.4f}"
            f"{r.measured_lift:>+10.4f}{r.bias:>+10.4f}{r.ci_width:>10.4f}"
            f"{r.coverage:>10.0%}{r.significant:>9.0%}"
        )
    lines += [
        "-" * 94,
        "",
        "MINIMUM DETECTABLE EFFECT (10% holdout, 80% power, alpha 0.05)",
        "=" * 94,
        f"{'n':>7}{'holdout':>9}{'MDE':>10}{'delivered effect':>19}{'detectable?':>14}",
        "-" * 94,
    ]
    for _, r in power.iterrows():
        lines.append(
            f"{int(r.n_customers):>7}{int(r.holdout):>9}{r.mde:>10.4f}"
            f"{delivered:>19.4f}{('YES' if delivered >= r.mde else 'no'):>14}"
        )
    need = required_holdout_size(delivered)
    lines += [
        "-" * 94,
        f"To detect the effect this offer actually delivers ({delivered:.4f}) at 80% power",
        f"a business needs about {need:,} customers with a 10% holdout.",
        "",
        "bias     = measured lift minus the simulator's true average effect.",
        "coverage = share of runs where the 95% interval contained the truth.",
        "signif   = share of runs the campaign looked statistically significant.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    frame = validate()
    delivered = float(frame["true_lift"].mean())
    print(report(summarise(frame), power_table(), delivered))
