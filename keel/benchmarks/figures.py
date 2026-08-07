"""Figure 2: how targeting reliability collapses at small n.

Paper 2's central exhibit, and the first result in this project supported by real
randomised data rather than simulation.

The left panel shows the familiar view -- mean performance rising with training size.
The right panel shows the view that actually matters to a business, and the two tell
different stories. A method can have a good *average* across many hypothetical draws
while being unreliable on the single draw a real company gets. Reporting only the mean
hides exactly the risk that makes small-sample deployment dangerous.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from keel.benchmarks.small_n import SmallNResult, run

FIG_DIR = Path(__file__).resolve().parents[2] / "papers" / "figures"

STYLE = {
    "outcome_propensity": ("#C62828", "Outcome propensity (churn-score analogue)", "-"),
    "response_model": ("#EF6C00", "Response model", "-"),
    "t_learner": ("#1565C0", "Uplift: T-learner", "-"),
    "s_learner": ("#2E7D32", "Uplift: S-learner", "-"),
    "class_transform": ("#6A1B9A", "Uplift: class transform", "--"),
}


def win_rates(result: SmallNResult) -> pd.DataFrame:
    """Probability each method beats random *on the same seed*."""
    frame = result.frame
    rand = frame[frame["method"] == "random"].set_index("seed")["incremental"]

    rows = []
    for n in sorted(frame[frame["train_size"].notna()]["train_size"].unique()):
        for method in STYLE:
            sub = frame[(frame["train_size"] == n) & (frame["method"] == method)]
            sub = sub.set_index("seed")["incremental"]
            common = sub.index.intersection(rand.index)
            if len(common) == 0:
                continue
            rows.append({
                "train_size": n,
                "method": method,
                "win_rate": float((sub.loc[common] > rand.loc[common]).mean()),
            })
    return pd.DataFrame(rows)


def figure_2(
    result: SmallNResult | None = None, n_seeds: int = 20, out: Path | None = None
) -> Path:
    result = result or run(n_seeds=n_seeds)
    summary = result.summary()
    summary = summary[summary["train_size"].notna()]
    wins = win_rates(result)
    rand_mean = result.frame[result.frame["method"] == "random"]["incremental"].mean()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    # --- left: the usual view -------------------------------------------------
    for method, (colour, label, ls) in STYLE.items():
        s = summary[summary["method"] == method].sort_values("train_size")
        if s.empty:
            continue
        x, m, sd = s["train_size"], s["mean"], s["std"]
        ax1.plot(x, m, color=colour, lw=2.2, ls=ls, label=label, marker="o", ms=4)
        ax1.fill_between(x, m - sd, m + sd, color=colour, alpha=0.10, lw=0)

    ax1.axhline(rand_mean, color="#37474F", lw=1.6, ls=":", zorder=1)
    ax1.annotate(
        "random targeting", xy=(520, rand_mean), xytext=(0, 6),
        textcoords="offset points", fontsize=9, color="#37474F",
    )
    ax1.set_xscale("log")
    ax1.set_xlabel("Training-set size (customers)")
    ax1.set_ylabel("Incremental visits at 30% budget")
    ax1.set_title(
        "Mean performance rises with data\n(shaded: ±1 sd across seeds)", fontsize=12, pad=10
    )
    ax1.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax1.grid(alpha=0.25, lw=0.6)
    ax1.set_axisbelow(True)

    # --- right: the view that matters ----------------------------------------
    for method, (colour, label, ls) in STYLE.items():
        w = wins[wins["method"] == method].sort_values("train_size")
        if w.empty:
            continue
        ax2.plot(w["train_size"], w["win_rate"] * 100, color=colour, lw=2.2, ls=ls,
                 marker="o", ms=4, label=label)

    ax2.axhline(50, color="#B71C1C", lw=1.4, ls=":", zorder=1)
    ax2.annotate("coin flip", xy=(520, 50), xytext=(0, 5), textcoords="offset points",
                 fontsize=9, color="#B71C1C")
    ax2.axhline(100, color="#37474F", lw=1.0, alpha=0.5)
    ax2.set_xscale("log")
    ax2.set_ylim(35, 105)
    ax2.set_xlabel("Training-set size (customers)")
    ax2.set_ylabel("% of seeds where the method beats random")
    ax2.set_title(
        "But a business gets ONE draw —\nand below ~2,000 customers it is close to a gamble",
        fontsize=12, pad=10,
    )
    ax2.grid(alpha=0.25, lw=0.6)
    ax2.set_axisbelow(True)

    # Mark the regime this project exists to serve.
    ax2.axvspan(400, 2000, color="#FFC107", alpha=0.12, lw=0)
    ax2.annotate(
        "the regime small\nbusinesses occupy",
        xy=(900, 41), fontsize=8.5, color="#8D6E00", ha="center",
    )

    fig.suptitle(
        "Uplift modelling is unreliable at the scale small businesses actually operate at"
        "   (Hillstrom, real RCT)",
        fontsize=13, y=1.02,
    )
    fig.tight_layout()

    out = out or (FIG_DIR / "fig02_small_n_reliability.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


if __name__ == "__main__":
    print(figure_2())
