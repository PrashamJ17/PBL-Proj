"""When is uplift modelling worth it? The governing quantity.

Two real datasets gave apparently contradictory answers. On Hillstrom, uplift models
clearly beat outcome models. On Criteo, they clearly lost -- at every training size.
Neither is a fluke, and the reconciliation is the most useful result in this project.

The governing quantity is **corr(treatment effect, outcome propensity)**.

An outcome model ranks customers by how likely they are to respond. An uplift model
ranks them by how much treatment *changes* their response. When those two orderings
coincide, the outcome model wins -- not because it is measuring the right thing, but
because it solves an easier estimation problem. Estimating one probability is far more
stable than estimating a difference between two, and at small n that variance advantage
dominates.

    corr high  (Criteo, +0.61)     outcome model wins; uplift costs variance and
                                   buys nothing
    corr ~0    (Hillstrom, +0.07)  orderings diverge; uplift wins modestly
    corr < 0   (churn, -0.19)      orderings actively conflict; the outcome model
                                   selects customers it will harm, and does worse
                                   than random

This reframes the project's claim. It is not "uplift modelling is better" -- that is
false in the advertising setting and we can show it. It is that **retention has an
adversarial structure that advertising does not**, and the correlation is what
distinguishes them.

It also sharpens the argument for abstention: a practitioner cannot tell in advance
which regime they are in, and choosing wrongly is expensive in both directions. A method
that quantifies its own uncertainty and declines to act is the honest response to that.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from keel.benchmarks.datasets import load_criteo, load_hillstrom
from keel.benchmarks.evaluate import evaluate_policy
from keel.benchmarks.models import (
    ClassTransform,
    OutcomePropensity,
    ResponseModel,
    SLearner,
    TLearner,
)
from keel.benchmarks.run import split

FIG_DIR = Path(__file__).resolve().parents[2] / "papers" / "figures"

UPLIFT_MODELS = [TLearner, SLearner, ClassTransform]
OUTCOME_MODELS = [OutcomePropensity, ResponseModel]


@dataclass
class Point:
    name: str
    domain: str
    correlation: float
    """corr(estimated treatment effect, estimated outcome propensity)."""
    uplift_advantage: float
    """(best uplift - best outcome) / |best outcome|, as a percentage."""
    negative_share: float
    n: int


def measure(rct, budget_fraction: float = 0.30, seed: int = 0) -> tuple[float, float, float]:
    """Correlation, uplift advantage, and share predicted negative, on held-out data.

    The correlation and the negative share are measured on the **T-learner
    specifically**, not on whichever uplift model happened to score best.

    That is deliberate. A T-learner's output is a difference of two probabilities, so
    it lives on the treatment-effect scale and "negative" means "predicted to be
    harmed". `ClassTransform` does not: its score is
    ``p/p_treat - (1-p)/(1-p_treat)``, which under Criteo's 85/15 assignment is
    negative unless ``p > 0.85`` — so nearly every customer scores negative even
    though the *ranking* is perfectly good. Using it here produced a spurious
    correlation of 1.00 and a "100% predicted negative" reading that meant nothing.

    The ranking-quality comparison still uses the best of each family, since there
    the scale is irrelevant and only the ordering matters.
    """
    train, test = split(rct, seed=seed)

    def best(classes):
        vals = []
        for cls in classes:
            scores = cls(seed=seed).fit(train.X, train.treatment, train.outcome).score(test.X)
            vals.append(
                evaluate_policy(cls.name, scores, test, budget_fraction, n_boot=60,
                                seed=seed).incremental_outcome
            )
        return max(vals)

    tau_hat = TLearner(seed=seed).fit(train.X, train.treatment, train.outcome).score(test.X)
    propensity = (
        OutcomePropensity(seed=seed).fit(train.X, train.treatment, train.outcome).score(test.X)
    )

    up_val, out_val = best(UPLIFT_MODELS), best(OUTCOME_MODELS)
    corr = float(np.corrcoef(tau_hat, propensity)[0, 1])
    advantage = 100.0 * (up_val - out_val) / max(abs(out_val), 1e-9)
    return corr, advantage, float((tau_hat < 0).mean())


def subsim_point() -> Point:
    """The churn setting, from the simulator.

    Uses ground-truth tau rather than an estimate, because SubSim knows it. Sign
    convention: tau < 0 means the offer reduces churn, so *benefit* is -tau, and
    that is what gets correlated against churn risk.
    """
    from keel.experiments.kill_test import run as kill_run
    from keel.experiments.kill_test import train_churn_model
    from keel.sim import SimConfig, simulate
    from keel.sim.counterfactual import potential_outcomes

    sim = simulate(SimConfig(n_customers=6000, n_months=24, seed=7))
    po = potential_outcomes(sim, decision_month=6, horizon=6)
    risk, _ = train_churn_model(sim, 6)

    corr = float(np.corrcoef(-po["tau_true"].to_numpy(), risk)[0, 1])

    results, _, _ = kill_run(sim, decision_month=6, horizon=6, budget_fraction=0.30)
    by = {r.name: r.expected_value for r in results}
    churn_score = next(v for k, v in by.items() if k.startswith("churn_score"))
    oracle = next(v for k, v in by.items() if k.startswith("oracle_uplift_top"))
    advantage = 100.0 * (oracle - churn_score) / max(abs(churn_score), 1e-9)

    return Point(
        name="SubSim (churn)", domain="subscription retention",
        correlation=corr, uplift_advantage=advantage,
        negative_share=float((po["tau_true"] > 0).mean()), n=len(po),
    )


def collect() -> list[Point]:
    points = []
    for label, domain, rct in [
        ("Criteo", "advertising", load_criteo(sample_rows=1_500_000, seed=0)),
        ("Hillstrom (mens)", "promotional email", load_hillstrom("mens")),
        ("Hillstrom (womens)", "promotional email", load_hillstrom("womens")),
    ]:
        corr, adv, neg = measure(rct)
        points.append(Point(label, domain, corr, adv, neg, len(rct)))
    points.append(subsim_point())
    return points


def figure_3(points: list[Point] | None = None, out: Path | None = None) -> Path:
    points = points or collect()
    fig, ax = plt.subplots(figsize=(10.5, 6.2))

    colours = {
        "advertising": "#C62828",
        "promotional email": "#EF6C00",
        "subscription retention": "#2E7D32",
    }

    ax.axhline(0, color="#263238", lw=1.3, zorder=2)
    ax.axvline(0, color="#90A4AE", lw=1.0, ls=":", zorder=1)

    # Hand-placed label offsets: Criteo and Hillstrom(mens) sit almost on top of
    # each other at corr ~0.6, so automatic placement collides.
    offsets = {
        "SubSim (churn)": (55, -6),
        "Hillstrom (womens)": (0, 26),
        "Criteo": (-135, 4),
        "Hillstrom (mens)": (-30, 30),
    }
    for p in points:
        ax.scatter(p.correlation, p.uplift_advantage, s=190,
                   color=colours[p.domain], zorder=5, edgecolor="white", lw=1.6)
        dx, dy = offsets.get(p.name, (0, 22))
        ax.annotate(
            f"{p.name}\n({p.negative_share:.0%} predicted negative)",
            xy=(p.correlation, p.uplift_advantage),
            xytext=(dx, dy), textcoords="offset points",
            ha="left" if dx > 0 else "center", va="center", fontsize=9.5,
        )

    ax.set_ylim(-14, 125)
    ax.set_xlim(-0.32, 0.78)

    ax.axvspan(-0.32, 0.0, color="#2E7D32", alpha=0.06, lw=0, zorder=0)
    ax.annotate("uplift PAYS\norderings conflict", xy=(-0.295, 62),
                fontsize=10, color="#2E7D32", ha="left", weight="bold")
    ax.annotate("uplift barely helps\nsame ordering, harder to estimate", xy=(0.16, 22),
                fontsize=10, color="#C62828", ha="left")

    ax.set_xlabel("corr( treatment effect , outcome propensity )", fontsize=11)
    ax.set_ylabel("Uplift model's advantage over outcome model (%)", fontsize=11)
    ax.set_title(
        "When is uplift modelling worth it?\n"
        "Retention is the adversarial case — and it is the only one where it matters much",
        fontsize=12.5, pad=14,
    )
    ax.grid(alpha=0.25, lw=0.6)
    ax.set_axisbelow(True)
    # Four points is a contrast, not a fitted relationship. Deliberately no trend line.
    ax.text(
        0.5, -0.19,
        "Four settings, not a fitted curve: the ordering among the three positive-correlation "
        "points is within noise.\nThe signal is the order-of-magnitude gap at negative correlation.",
        transform=ax.transAxes, ha="center", fontsize=8.5, color="#546E7A",
    )

    handles = [
        plt.Line2D([], [], marker="o", ls="", color=c, ms=9, label=d)
        for d, c in colours.items()
    ]
    ax.legend(handles=handles, frameon=False, fontsize=9.5, loc="upper right")

    fig.tight_layout()
    out = out or (FIG_DIR / "fig03_when_uplift_pays.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def report(points: list[Point]) -> str:
    lines = [
        "When does uplift modelling pay?",
        "=" * 84,
        f"{'dataset':<22}{'domain':<24}{'corr':>8}{'uplift adv':>13}{'% negative':>13}",
        "-" * 84,
    ]
    for p in sorted(points, key=lambda q: -q.correlation):
        lines.append(
            f"{p.name:<22}{p.domain:<24}{p.correlation:>8.2f}"
            f"{p.uplift_advantage:>12.1f}%{p.negative_share:>12.1%}"
        )
    lines.append("-" * 84)
    lines.append(
        "High correlation => outcome model ranks the same customers, via an easier\n"
        "estimation problem, so uplift modelling costs variance and buys nothing.\n"
        "Negative correlation => the outcome model actively selects customers it harms."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    pts = collect()
    print(report(pts))
    print()
    print(figure_3(pts))
