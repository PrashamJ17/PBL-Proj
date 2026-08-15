"""Calibration targets for SubSim, and the check that verifies them.

Paper 1's contribution is not "we wrote a simulator" -- anyone can. It is "we wrote
a simulator whose aggregate behaviour matches published benchmarks, and here is the
procedure that verifies it." Without this, a reviewer's first and entirely fair
objection is that the simulator was tuned to flatter the proposed method.

Targets below are stated as ranges taken from published 2026 SMB-SaaS benchmark
aggregates. Ranges, not point values, because the underlying sources themselves
report spreads across industry and company size.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from retainiq.sim.subsim import SimResult


@dataclass(frozen=True)
class Target:
    name: str
    low: float
    high: float
    units: str
    source: str


TARGETS: list[Target] = [
    Target(
        "monthly_voluntary_churn",
        0.030,
        0.070,
        "fraction",
        "SMB B2B SaaS monthly logo churn band, 2026 benchmarks",
    ),
    Target(
        "involuntary_share_of_churn",
        0.20,
        0.40,
        "fraction",
        "Involuntary churn is 20-40% of total churn across most SaaS",
    ),
    Target(
        "month_24_retention",
        0.22,
        0.50,
        "fraction",
        "SMB SaaS 2-year cohort survival. NOTE: originally set to [0.30, 0.60], "
        "which was internally inconsistent with the churn bands above -- 40% "
        "retention at 24mo implies ~3.75% TOTAL monthly churn, contradicting a "
        "3-7% VOLUNTARY band before involuntary is even added. Widened to the "
        "range actually implied by the other two targets. Mid-market/enterprise "
        "would sit higher; this simulator models SMB.",
    ),
    Target(
        "early_late_hazard_ratio",
        1.15,
        3.00,
        "ratio",
        "Early-tenure hazard exceeds late-tenure: fragile customers leave first, "
        "so the surviving pool is progressively hardier",
    ),
]


QUADRANT_TARGETS: list[Target] = [
    Target(
        "sleeping_dog_share",
        0.08,
        0.22,
        "fraction",
        "Sleeping Dogs are a real but MINORITY segment in the uplift literature. "
        "If the simulator needs them to be a third of the base for the headline "
        "result to hold, the result is weak and a referee will say so.",
    ),
    Target(
        "persuadable_share",
        0.25,
        0.65,
        "fraction",
        "Persuadables must be the largest actionable group, or retention "
        "campaigns would not be worth running at all.",
    ),
    Target(
        "mean_tau",
        -0.05,
        0.0,
        "probability",
        "The average treatment effect must be BENEFICIAL. A blanket campaign that "
        "helps on average makes the demonstration harder and therefore stronger: "
        "any money lost by churn-score targeting is then attributable purely to "
        "targeting, not to a bad offer.",
    ),
]


def measure_quadrants(result: SimResult, decision_month: int = 6, horizon: int = 6) -> dict:
    """Quadrant composition and average treatment effect at a decision point."""
    from retainiq.sim.counterfactual import potential_outcomes

    po = potential_outcomes(result, decision_month=decision_month, horizon=horizon)
    if po.empty:
        return {"sleeping_dog_share": 0.0, "persuadable_share": 0.0, "mean_tau": 0.0}
    share = po["quadrant"].value_counts(normalize=True)
    return {
        "sleeping_dog_share": float(share.get("sleeping_dog", 0.0)),
        "persuadable_share": float(share.get("persuadable", 0.0)),
        "mean_tau": float(po["tau_true"].mean()),
    }


def check_quadrants(result: SimResult, verbose: bool = True) -> bool:
    stats = measure_quadrants(result)
    all_ok = True
    lines = []
    for t in QUADRANT_TARGETS:
        v = stats[t.name]
        ok = t.low <= v <= t.high
        all_ok &= ok
        lines.append(
            f"  [{'PASS' if ok else 'FAIL'}] {t.name:<24} "
            f"{v:>8.4f}   target [{t.low:.3f}, {t.high:.3f}]"
        )
    if verbose:
        print("Quadrant calibration")
        print("=" * 66)
        print("\n".join(lines))
        print(f"  RESULT: {'ALL TARGETS MET' if all_ok else 'OUT OF CALIBRATION'}")
    return all_ok


def measure(result: SimResult) -> dict[str, float]:
    """Compute the calibration statistics from a simulation run."""
    panel, customers = result.panel, result.customers

    vol = float(panel["churn_voluntary"].mean())
    invol = float(panel["churn_involuntary"].mean())
    n_vol = float(panel["churn_voluntary"].sum())
    n_invol = float(panel["churn_involuntary"].sum())

    # Retention at the end of the observation window.
    retention = float(customers["censored"].mean())

    # Hazard in the first 6 months vs months 12+. Uses the person-period panel, so
    # it is a true hazard (conditional on being at risk), not a naive proportion.
    early = panel[panel["month"] < 6]["churn_voluntary"].mean()
    late = panel[panel["month"] >= 12]["churn_voluntary"].mean()
    ratio = float(early / late) if late > 0 else float("inf")

    return {
        "monthly_voluntary_churn": vol,
        "monthly_involuntary_churn": invol,
        "involuntary_share_of_churn": n_invol / max(n_vol + n_invol, 1.0),
        "month_24_retention": retention,
        "early_late_hazard_ratio": ratio,
    }


def check(result: SimResult, verbose: bool = True) -> bool:
    """Verify a run against every target. Returns True iff all pass."""
    stats = measure(result)
    all_ok = True
    lines = []

    for t in TARGETS:
        v = stats[t.name]
        ok = t.low <= v <= t.high
        all_ok &= ok
        lines.append(
            f"  [{'PASS' if ok else 'FAIL'}] {t.name:<28} "
            f"{v:>7.3f}   target [{t.low:.3f}, {t.high:.3f}]"
        )

    if verbose:
        print("SubSim calibration")
        print("=" * 66)
        print("\n".join(lines))
        print("-" * 66)
        print(f"  (monthly involuntary churn: {stats['monthly_involuntary_churn']:.3f})")
        print(f"  RESULT: {'ALL TARGETS MET' if all_ok else 'OUT OF CALIBRATION'}")
    return all_ok


def calibrate_intercept(
    cfg,
    target_monthly_churn: float = 0.045,
    n_seeds: int = 3,
    tol: float = 0.002,
    max_iter: int = 18,
) -> float:
    """Solve for the hazard intercept that hits a target monthly voluntary churn.

    Bisection on the intercept. Monotone by construction -- raising the intercept
    raises every customer's hazard -- so bisection is guaranteed to converge.

    This exists so the simulator is never hand-tuned. Hand-tuning is how you end up
    accidentally fitting the generative process to favour your own method, which is
    the first thing a referee will suspect. Averaging over seeds keeps the solution
    from latching onto one lucky draw.
    """
    from dataclasses import replace

    from retainiq.sim.subsim import simulate

    def churn_at(intercept: float) -> float:
        c = replace(cfg, hazard=replace(cfg.hazard, intercept=intercept))
        vals = [
            measure(simulate(replace(c, seed=cfg.seed + s)))["monthly_voluntary_churn"]
            for s in range(n_seeds)
        ]
        return float(np.mean(vals))

    lo, hi = -8.0, 0.0
    best = cfg.hazard.intercept
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        v = churn_at(mid)
        best = mid
        if abs(v - target_monthly_churn) < tol:
            break
        if v > target_monthly_churn:
            hi = mid
        else:
            lo = mid
    return best


def sweep_seeds(cfg, n_seeds: int = 8) -> dict[str, tuple[float, float]]:
    """Run the calibration across seeds and report mean/std of each statistic.

    A simulator that only calibrates on one lucky seed is not calibrated.
    """
    from dataclasses import replace

    from retainiq.sim.subsim import simulate

    acc: dict[str, list[float]] = {}
    for s in range(n_seeds):
        stats = measure(simulate(replace(cfg, seed=cfg.seed + s)))
        for k, v in stats.items():
            acc.setdefault(k, []).append(v)
    return {k: (float(np.mean(v)), float(np.std(v))) for k, v in acc.items()}
