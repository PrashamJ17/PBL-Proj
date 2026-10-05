"""When is uplift modelling worth it? The risk-lift correlation, measured.

Two real datasets gave apparently contradictory answers. On Hillstrom, uplift models
clearly beat outcome models. On Criteo, they clearly lost -- at every training size.
Neither is a fluke. What separates them is **corr(treatment effect, outcome propensity)**.

The quantity is not introduced here. Ascarza (2018, Web Appendix A3.4) sets the
correlation between churn risk and response to an offer in a simulation, from -1 to +1,
and places her two field studies at about +0.2 and -0.2. This module *measures* it from
fitted models on public randomised experiments and tabulates it against how much an
uplift model gains over an outcome model (D-026, scoped by D-068).

An outcome model ranks customers by how likely they are to respond. An uplift model
ranks them by how much treatment *changes* their response. When those two orderings
coincide, the outcome model wins -- not because it is measuring the right thing, but
because it solves an easier estimation problem. Estimating one probability is far more
stable than estimating a difference between two, and at small n that variance advantage
dominates. This is a statement about estimates from a finite sample: with the true
effect in hand, ranking by it cannot lose.

Values from the 15 Aug 2026 run (run the module for current ones):

    corr high  (Hillstrom mens +0.69, Criteo +0.58)   uplift loses or gains nothing
    corr low   (Hillstrom womens +0.19, Lenta +0.17)  uplift wins modestly
    corr < 0   (SubSim churn, -0.19)                  orderings conflict; the churn
                                                      score selects customers the
                                                      offer harms

The ordering among the four positive points is within noise, and the five points are
NOT measured the same way (D-068). Do not read the plot as one curve.

  * Real points: Pearson correlation between a T-learner's estimate and an outcome
    model fitted on BOTH arms pooled (Ascarza's RISK is fitted on control customers
    only). One seed, one split, no interval. The advantage compares the best
    *estimated* uplift model with the best outcome model. None of these datasets is a
    retention experiment.
  * SubSim point: correlation between the TRUE benefit and an estimated churn score;
    the advantage compares the ORACLE with the churn score. Part of its large gap is
    oracle-against-estimate, not the sign of the correlation.
  * SubSim's negative correlation follows from how the simulator is configured. It is
    an assumption, not evidence that retention has one.

Owed before this is claimed again (D-068): rank correlation beside Pearson, on the
probability and the log-odds scale; risk fitted on control only; many splits with an
interval; a like-for-like SubSim point.

The argument for abstention does not depend on who introduced the quantity: a
practitioner cannot tell in advance which regime they are in, and choosing wrongly is
expensive in both directions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from retainiq.benchmarks.datasets import load_criteo, load_hillstrom, load_lenta
from retainiq.benchmarks.evaluate import evaluate_policy
from retainiq.benchmarks.models import (
    ClassTransform,
    OutcomePropensity,
    ResponseModel,
    SLearner,
    TLearner,
)
from retainiq.benchmarks.run import split

FIG_DIR = Path(__file__).resolve().parents[2] / "papers" / "figures"

UPLIFT_MODELS = [TLearner, SLearner, ClassTransform]
OUTCOME_MODELS = [OutcomePropensity, ResponseModel]

ESTIMATED = "estimated"
ORACLE = "oracle"


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
    basis: str = ESTIMATED
    """How the point was measured. ``ESTIMATED``: two fitted models on a real
    experiment. ``ORACLE``: true effects and an oracle policy against a fitted score,
    which is an upper bound and not like-for-like with an estimated point (D-068)."""


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

    Known gaps (D-068): the correlation is Pearson, from one seed and one split, and
    `OutcomePropensity` is fitted on both arms pooled, where Ascarza's RISK is fitted
    on control customers only.
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

    NOT like-for-like with `measure` (D-068): the correlation here is true benefit
    against an estimated score, and the advantage is the ORACLE against the churn
    score, where `measure` compares two estimated models. Treat this point as an upper
    bound on what an estimated uplift model would gain.
    """
    from retainiq.experiments.kill_test import run as kill_run
    from retainiq.experiments.kill_test import train_churn_model
    from retainiq.sim import SimConfig, simulate
    from retainiq.sim.counterfactual import potential_outcomes

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
        basis=ORACLE,
    )


def collect() -> list[Point]:
    points = []
    for label, domain, rct in [
        ("Criteo", "advertising", load_criteo(sample_rows=1_500_000, seed=0)),
        ("Hillstrom (mens)", "promotional email", load_hillstrom("mens")),
        ("Hillstrom (womens)", "promotional email", load_hillstrom("womens")),
        # Added AFTER the principle was formulated, as an out-of-sample test:
        # retail promotion was predicted to fall between advertising and churn.
        ("Lenta", "retail promotion", load_lenta()),
    ]:
        corr, adv, neg = measure(rct)
        points.append(Point(label, domain, corr, adv, neg, len(rct)))
    points.append(subsim_point())
    return points


COLOURS = {
    "advertising": "#C62828",
    "promotional email": "#EF6C00",
    "retail promotion": "#1565C0",
    "subscription retention": "#2E7D32",
}

# Hand-placed label offsets, in points: (dx, dy, horizontal alignment). Criteo and
# Hillstrom (mens) sit close together near zero advantage, as do Lenta and Hillstrom
# (womens), so automatic placement collides.
LABEL_OFFSETS = {
    "SubSim (churn)": (16, 0, "left"),
    "Lenta": (-4, 32, "center"),
    "Hillstrom (womens)": (14, -2, "left"),
    "Criteo": (-12, 32, "center"),
    "Hillstrom (mens)": (-4, -32, "center"),
}


def marker_style(point: Point) -> dict:
    """Filled for an estimated point, hollow for an oracle one.

    The distinction is drawn from ``Point.basis`` and not from the point's name, so a
    point measured against true effects cannot be plotted as if it were an estimate.
    """
    colour = COLOURS.get(point.domain, "#455A64")
    if point.basis == ORACLE:
        return {"marker": "D", "s": 150, "facecolor": "white", "edgecolor": colour,
                "linewidth": 2.6}
    return {"marker": "o", "s": 190, "facecolor": colour, "edgecolor": "white",
            "linewidth": 1.6}


def point_label(point: Point) -> str:
    advantage = f"{point.uplift_advantage:+.1f}%".replace("-", "\u2212")
    # A share that rounds to zero is not zero: Hillstrom (mens) has 0.5% predicted
    # negative, and printing "0%" would say there are none.
    share = "<1%" if 0 < point.negative_share < 0.005 else f"{point.negative_share:.0%}"
    head = f"{point.name}  {advantage}"
    if point.basis == ORACLE:
        return (f"{head}\n{share} with a negative effect (known)\n"
                "oracle on true effects: an upper bound")
    return f"{head}\n{share} predicted negative"


def legend_entries(points: list[Point]) -> list[tuple[str, dict]]:
    """One legend entry per (domain, basis), in first-seen order.

    Two arms of one experiment share an entry. An oracle point never shares one with an
    estimated point, even in the same domain, and its entry says what it is.
    """
    entries, seen = [], set()
    for p in points:
        key = (p.domain, p.basis)
        if key in seen:
            continue
        seen.add(key)
        label = p.domain if p.basis == ESTIMATED else f"{p.domain} (simulator, oracle)"
        entries.append((label, marker_style(p)))
    return entries


def figure_3(points: list[Point] | None = None, out: Path | None = None) -> Path:
    points = points or collect()
    fig, ax = plt.subplots(figsize=(10.5, 6.6))

    ax.axhline(0, color="#263238", lw=1.3, zorder=2)
    ax.axvline(0, color="#90A4AE", lw=1.0, ls=":", zorder=1)

    for p in points:
        ax.scatter(p.correlation, p.uplift_advantage, zorder=5, **marker_style(p))
        dx, dy, ha = LABEL_OFFSETS.get(p.name, (0, 26, "center"))
        ax.annotate(
            point_label(p), xy=(p.correlation, p.uplift_advantage),
            xytext=(dx, dy), textcoords="offset points",
            ha=ha, va="center", fontsize=9.5, linespacing=1.25, zorder=6,
            # Opaque backing, so a label never has a grid or axis line through it.
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5, "alpha": 0.92},
        )

    ax.set_ylim(-30, 125)
    ax.set_xlim(-0.32, 0.82)

    ax.set_xlabel("corr( treatment effect , outcome propensity )", fontsize=10.5)
    ax.set_ylabel("Advantage of effect-based over outcome-based targeting (%)", fontsize=10.5)
    ax.set_title(
        "Advantage of effect-based targeting, against the risk\u2013lift correlation\n"
        "four settings from three public experiments, and one simulator",
        fontsize=12.5, pad=14,
    )
    ax.grid(alpha=0.25, lw=0.6)
    ax.set_axisbelow(True)

    # Five points are a contrast, not a fitted relationship. Deliberately no trend
    # line, and no shaded "uplift pays" region: the one point at negative correlation
    # is an oracle on a simulator configured to have that correlation (D-068).
    fig.text(
        0.5, 0.118,
        "Negative: the customers an outcome model ranks highest are the ones who benefit "
        "least.   Positive: they benefit most.",
        ha="center", va="bottom", fontsize=9.5, color="#263238",
    )
    fig.text(
        0.5, 0.012,
        "Filled: best fitted uplift model against best fitted outcome model on a public "
        "randomised experiment; one seed, one split, no interval.\n"
        "The ordering among the filled points is within noise. Hollow: a simulator whose "
        "negative correlation is configured; an oracle on true effects\n"
        "against a churn score, so an upper bound and not like-for-like. The correlation "
        "is the one varied in Ascarza (2018, Web Appendix A3.4).",
        ha="center", va="bottom", fontsize=8.5, color="#455A64", linespacing=1.45,
    )

    handles = [
        plt.Line2D(
            [], [], ls="", marker=style["marker"], ms=9 if style["facecolor"] == "white" else 11,
            markerfacecolor=style["facecolor"], markeredgecolor=style["edgecolor"],
            markeredgewidth=style["linewidth"], label=label,
        )
        for label, style in legend_entries(points)
    ]
    ax.legend(handles=handles, frameon=False, fontsize=9.5, loc="upper right")

    fig.tight_layout(rect=(0, 0.14, 1, 1))
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
        name = f"{p.name} *" if p.basis == ORACLE else p.name
        lines.append(
            f"{name:<22}{p.domain:<24}{p.correlation:>8.2f}"
            f"{p.uplift_advantage:>12.1f}%{p.negative_share:>12.1%}"
        )
    lines.append("-" * 84)
    lines.append(
        "High correlation => outcome model ranks the same customers, via an easier\n"
        "estimation problem, so uplift modelling costs variance and buys nothing.\n"
        "Negative correlation => the outcome model actively selects customers it harms."
    )
    if any(p.basis == ORACLE for p in points):
        lines.append(
            "* true effects, oracle vs churn score. An upper bound, not like-for-like\n"
            "  with the estimated rows (D-068)."
        )
    return "\n".join(lines)


if __name__ == "__main__":
    pts = collect()
    print(report(pts))
    print()
    print(figure_3(pts))
