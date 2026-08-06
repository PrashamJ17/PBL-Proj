"""Figure generation.

Figure 1 is the load-bearing artifact of this project: paper figure 1, pitch slide 3,
and sales-deck opener. It has to show both the *outcome* (churn-score targeting loses
money) and the *mechanism* (because the top of the churn ranking is dense in sleeping
dogs). An outcome without a mechanism reads as a simulation artifact; the mechanism is
what makes it an argument.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from keel.experiments.kill_test import budget_curve, train_churn_model
from keel.sim import SimConfig, simulate
from keel.sim.counterfactual import potential_outcomes

FIG_DIR = Path(__file__).resolve().parents[2] / "papers" / "figures"

QUADRANT_COLOURS = {
    "persuadable": "#2E7D32",
    "sure_thing": "#90A4AE",
    "lost_cause": "#546E7A",
    "sleeping_dog": "#C62828",
}


def _mean_budget_curve(cfg: SimConfig, n_seeds: int, **kw) -> pd.DataFrame:
    """Average the budget curve over seeds so the figure is not one lucky draw."""
    frames = [
        budget_curve(simulate(replace(cfg, seed=cfg.seed + s)), seed=s, **kw)
        for s in range(n_seeds)
    ]
    out = frames[0][["budget_fraction"]].copy()
    for col in ("churn_score", "oracle_uplift", "random"):
        stacked = np.vstack([f[col].to_numpy() for f in frames])
        out[col] = stacked.mean(axis=0)
        out[col + "_sd"] = stacked.std(axis=0)
    return out


def _quadrant_mix_by_decile(cfg: SimConfig, decision_month: int, horizon: int) -> pd.DataFrame:
    """True quadrant composition within each decile of PREDICTED churn risk.

    This is the mechanism panel. If the top risk decile is disproportionately
    sleeping dogs, then ranking by churn score is not merely uninformative for the
    targeting decision -- it is anti-informative.
    """
    sim = simulate(cfg)
    po = potential_outcomes(sim, decision_month=decision_month, horizon=horizon)
    risk, _ = train_churn_model(sim, decision_month)
    po = po.assign(risk=risk)

    # Decile 1 = highest predicted risk, i.e. who a churn-score campaign targets first.
    po["decile"] = pd.qcut(po["risk"].rank(method="first", ascending=False), 10, labels=range(1, 11))
    mix = (
        po.groupby("decile", observed=True)["quadrant"]
        .value_counts(normalize=True)
        .unstack(fill_value=0.0)
    )
    for q in QUADRANT_COLOURS:
        if q not in mix:
            mix[q] = 0.0
    return mix[list(QUADRANT_COLOURS)]


def figure_1(
    cfg: SimConfig | None = None,
    n_seeds: int = 6,
    decision_month: int = 6,
    horizon: int = 6,
    out: Path | None = None,
) -> Path:
    """The kill-test figure: outcome (left) and mechanism (right)."""
    cfg = cfg or SimConfig(n_customers=6000, n_months=24, seed=7)
    curve = _mean_budget_curve(cfg, n_seeds, decision_month=decision_month, horizon=horizon)
    mix = _quadrant_mix_by_decile(cfg, decision_month, horizon)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    # --- left: money vs budget ------------------------------------------------
    x = curve["budget_fraction"] * 100
    styles = {
        "oracle_uplift": ("#2E7D32", "Oracle uplift (upper bound)", "-"),
        "random": ("#78909C", "Random targeting", "--"),
        "churn_score": ("#C62828", "Churn-score targeting", "-"),
    }
    for col, (colour, label, ls) in styles.items():
        ax1.plot(x, curve[col] / 1000, color=colour, lw=2.4, ls=ls, label=label, zorder=3)
        ax1.fill_between(
            x,
            (curve[col] - curve[col + "_sd"]) / 1000,
            (curve[col] + curve[col + "_sd"]) / 1000,
            color=colour, alpha=0.13, lw=0, zorder=2,
        )

    ax1.axhline(0, color="#263238", lw=1.2, zorder=4)
    ax1.annotate(
        "do nothing",
        xy=(x.iloc[-1], 0), xytext=(-6, 5), textcoords="offset points",
        ha="right", fontsize=9, color="#263238",
    )
    ax1.set_xlabel("Retention budget (% of customer base treated)")
    ax1.set_ylabel("Expected incremental value (thousands)")
    ax1.set_title(
        "Churn-score targeting destroys value\nat every budget level", fontsize=12, pad=10
    )
    ax1.legend(frameon=False, fontsize=9.5, loc="lower left")
    ax1.grid(alpha=0.25, lw=0.6)
    ax1.set_axisbelow(True)

    # Mark the gap at a representative budget.
    i20 = int(np.argmin(np.abs(curve["budget_fraction"] - 0.20)))
    lo, hi = curve["churn_score"].iloc[i20] / 1000, curve["oracle_uplift"].iloc[i20] / 1000
    ax1.annotate(
        "",
        xy=(20, hi), xytext=(20, lo),
        arrowprops=dict(arrowstyle="<->", color="#37474F", lw=1.4),
    )
    ax1.annotate(
        f"{hi - lo:,.0f}k gap\nat 20% budget",
        xy=(20, (hi + lo) / 2), xytext=(9, 0), textcoords="offset points",
        fontsize=9, color="#37474F", va="center",
    )

    # --- right: mechanism -----------------------------------------------------
    bottom = np.zeros(len(mix))
    labels = {
        "persuadable": "Persuadable (worth paying for)",
        "sure_thing": "Sure Thing (wasted spend)",
        "lost_cause": "Lost Cause (unreachable)",
        "sleeping_dog": "Sleeping Dog (harmed by contact)",
    }
    for q, colour in QUADRANT_COLOURS.items():
        vals = mix[q].to_numpy() * 100
        ax2.bar(mix.index.astype(int), vals, bottom=bottom, color=colour, label=labels[q], width=0.82)
        bottom += vals

    ax2.set_xlabel("Predicted-churn-risk decile  (1 = targeted first)")
    ax2.set_ylabel("Share of decile (%)")
    ax2.set_title(
        "Why: the customers a churn model ranks highest\nare the ones an offer harms",
        fontsize=12, pad=10,
    )
    ax2.set_xticks(range(1, 11))
    ax2.set_ylim(0, 100)
    ax2.legend(frameon=False, fontsize=8.5, loc="lower left", ncol=1)
    ax2.set_axisbelow(True)

    top_sd = mix["sleeping_dog"].iloc[0] * 100
    bot_sd = mix["sleeping_dog"].iloc[-1] * 100
    fig.suptitle(
        f"A churn score is not a targeting policy   "
        f"(sleeping dogs: {top_sd:.0f}% of decile 1 vs {bot_sd:.0f}% of decile 10)",
        fontsize=13.5, y=1.02,
    )
    fig.tight_layout()

    out = out or (FIG_DIR / "fig01_kill_test.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


if __name__ == "__main__":
    print(figure_1())
