"""Draw the paper's figure comparing the declining rule with Lemmens & Gupta's rule.

    python papers/draw_comparison_figure.py                    # runs 500 draws, about a minute
    python papers/draw_comparison_figure.py --from-draws FILE  # draws from saved draws

The numbers are those `make baseline` prints (D-075). This script only draws them: the
left panel is each rule's mean money against doing nothing, the right panel is how often
the declining rule earns more than theirs among the businesses where the two differ.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retainiq.experiments.baseline import OURS, RANKING, by_policy, compare, sweep  # noqa: E402

OUT = Path(__file__).resolve().parent / "figures" / "fig08_declining_rule_comparison.png"
THEIRS = "lg_primary"
LINES = {
    RANKING: ("Ranking, fills the budget", "#C62828", "s"),
    THEIRS: ("Lemmens-Gupta rule", "#EF6C00", "D"),
    OURS: ("Declining rule", "#1565C0", "o"),
}


def draw(frame: pd.DataFrame, out: Path = OUT) -> Path:
    table = by_policy(frame).set_index(["n_customers", "policy"])
    sizes = sorted(frame["n_customers"].unique())
    draws = int(frame.groupby("n_customers")["seed"].nunique().max())

    fig, (left, right) = plt.subplots(1, 2, figsize=(13.0, 5.4))

    left.axhline(0, color="#263238", lw=1.2)
    left.text(sizes[-1], 90, "doing nothing", ha="right", va="bottom", fontsize=9.5,
              color="#263238")
    for policy, (label, colour, marker) in LINES.items():
        means = [table.loc[(n, policy), "mean_value"] for n in sizes]
        left.plot(sizes, means, marker=marker, ms=7, lw=2, color=colour, label=label)
    left.set_xscale("log")
    left.set_xlim(sizes[0] * 0.8, sizes[-1] * 1.3)
    left.set_ylim(top=650)
    left.set_xticks(sizes, [f"{int(n):,}" for n in sizes])
    left.minorticks_off()
    left.set_xlabel("Customers in the business")
    left.set_ylabel("Mean money relative to doing nothing")
    left.set_title(f"Mean result of each rule ({draws} simulated businesses per size)",
                   fontsize=11.5)
    left.legend(frameon=False, loc="lower left", fontsize=10)
    left.grid(alpha=0.25, lw=0.6)

    right.axhline(50, color="#C62828", lw=1.0, ls=":")
    right.text(sizes[-1], 51.5, "even", ha="right", va="bottom", fontsize=9.5, color="#C62828")
    for n in sizes:
        c = compare(frame[frame["n_customers"] == n], OURS, THEIRS)
        rate, low, high = (100 * c[k] for k in ("rate", "low", "high"))
        right.errorbar(n, rate, yerr=[[rate - low], [high - rate]], fmt="o", ms=8,
                       color="#1565C0", ecolor="#1565C0", elinewidth=1.4, capsize=4)
        right.annotate(f"{c['wins']} of {c['wins'] + c['losses']}", (n, high),
                       xytext=(0, 7), textcoords="offset points", ha="center", fontsize=9.5)
    right.set_xscale("log")
    right.set_xlim(sizes[0] * 0.8, sizes[-1] * 1.3)
    right.set_xticks(sizes, [f"{int(n):,}" for n in sizes])
    right.minorticks_off()
    right.set_ylim(0, 100)
    right.set_xlabel("Customers in the business")
    right.set_ylabel("% of businesses where the declining rule earns more")
    right.set_title("Declining rule against the Lemmens-Gupta rule,\n"
                    "businesses where the two differ (bars: exact 95% interval)", fontsize=11.5)
    right.grid(alpha=0.25, lw=0.6)

    fig.text(
        0.5, 0.01,
        "A simulator in which an oracle would treat about 6% of customers. At 250 customers "
        "the Lemmens-Gupta rule, as configured here, had no campaign size open to it\n"
        "and treated nobody, so the first point compares the declining rule with doing "
        "nothing. Their rule is a re-implementation from the published paper.",
        ha="center", va="bottom", fontsize=8.8, color="#455A64", linespacing=1.45,
    )
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from-draws", type=Path, metavar="CSV",
                    help="draws saved by `python -m retainiq.experiments.baseline --save`")
    ap.add_argument("--jobs", type=int, default=6)
    args = ap.parse_args(argv)
    frame = pd.read_csv(args.from_draws) if args.from_draws else sweep(jobs=args.jobs)
    print(draw(frame))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
