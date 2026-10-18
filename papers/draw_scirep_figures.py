"""Draw the five figures of the Scientific Reports manuscript to the journal's figure rules.

    python papers/draw_scirep_figures.py        # about two minutes; Figures 2 and 5 re-simulate

The journal's author instructions (read on 18 October 2026) ask for panels labelled with
lower-case bold letters in the same type size as the rest of the figure, one sans-serif
typeface at one size in every figure, sentence-case lettering, no line thinner than one
point, lettering legible after reduction, and line art as vector files. So every figure is
drawn at its printed width of 183 mm with 7-point Arial throughout, and written twice: as
a PDF, which is vector and is what the LaTeX source should include, and as a 300-dpi TIFF
for the submission system. No EPS is written: it cannot carry the transparent bands in
Figures 1, 2 and 5.

The numbers come from the same functions and saved runs as the manuscript's tables:

    Figure 1  small-sample win rates     --small-n, from `benchmarks.small_n --save-draws FILE`
    Figure 2  holdout estimator and MDE  re-simulated by `experiments.holdout_validation`
    Figure 3  risk-response correlation  --splits, from `benchmarks.spectrum_checks --save FILE`
    Figure 4  decision rules             --draws, from `experiments.baseline --save FILE`
    Figure 5  value of each policy       re-simulated by `experiments.figures`
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retainiq.benchmarks.small_n import METHODS, SmallNResult, win_rates  # noqa: E402
from retainiq.benchmarks.spectrum_checks import MARKERS, PANELS, summarise  # noqa: E402
from retainiq.experiments.baseline import OURS, RANKING, by_policy, compare  # noqa: E402
from retainiq.experiments.figures import (  # noqa: E402
    _mean_budget_curve,
    _quadrant_mix_by_decile,
)
from retainiq.experiments.holdout_validation import SIZES, power_table, validate  # noqa: E402
from retainiq.experiments.holdout_validation import summarise as holdout_summary  # noqa: E402
from retainiq.policy.holdout import required_holdout_size  # noqa: E402
from retainiq.sim import SimConfig  # noqa: E402

OUT = Path(__file__).resolve().parent / "figures" / "scirep"
RESULTS = ROOT / "data" / "results"
MM = 1 / 25.4
WIDTH = 183 * MM
THEIRS = "lg_primary"

STYLE = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "axes.linewidth": 1.0, "lines.linewidth": 1.5, "lines.markersize": 4,
    "xtick.major.width": 1.0, "ytick.major.width": 1.0,
    "xtick.minor.width": 1.0, "ytick.minor.width": 1.0,
    "xtick.major.size": 3, "ytick.major.size": 3,
    "patch.linewidth": 1.0, "errorbar.capsize": 2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titlepad": 4,
    "legend.frameon": False, "legend.handlelength": 2.2,
    "pdf.fonttype": 42, "ps.fonttype": 42,
}

#: Okabe-Ito colours, which stay distinct under the common forms of colour blindness. Each
#: series also has its own marker or line style, so a grey-scale print still separates them.
BLUE, SKY, GREEN, ORANGE, VERMILLION, PURPLE, GREY = (
    "#0072B2", "#56B4E9", "#009E73", "#E69F00", "#D55E00", "#CC79A7", "#7F7F7F")

METHOD_STYLE = {
    "s_learner": ("S-learner", BLUE, "o", "-"),
    "t_learner": ("T-learner", SKY, "s", "-"),
    "class_transform": ("Class transformation", PURPLE, "^", "--"),
    "response_model": ("Response model", GREEN, "D", "-."),
    "outcome_propensity": ("Outcome propensity", VERMILLION, "v", ":"),
}
SETTING_STYLE = {
    "Criteo": ("Criteo (advertising)", VERMILLION),
    "Hillstrom (mens)": ("Hillstrom, men's e-mail", ORANGE),
    "Lenta": ("Lenta (retail promotion)", GREEN),
    "Hillstrom (womens)": ("Hillstrom, women's e-mail", SKY),
    "SubSim (fitted)": ("Simulated retention trial", BLUE),
}
RULE_STYLE = {
    RANKING: ("Ranking, fills a 30% budget", VERMILLION, "s"),
    THEIRS: ("Lemmens–Gupta rule", ORANGE, "D"),
    OURS: ("Declining rule", BLUE, "o"),
}
QUADRANT_STYLE = {
    "persuadable": ("Persuadable", GREEN),
    "sure_thing": ("Sure thing", "#BDBDBD"),
    "lost_cause": ("Lost cause", "#5E5E5E"),
    "sleeping_dog": ("Sleeping dog", VERMILLION),
}


def log_axis(ax, ticks, axis: str = "x") -> None:
    """A log axis labelled only at the values that were run, each written in full."""
    which = ax.xaxis if axis == "x" else ax.yaxis
    (ax.set_xscale if axis == "x" else ax.set_yscale)("log")
    which.set_major_locator(FixedLocator(list(ticks)))
    which.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:,.0f}" if v >= 1 else f"{v:g}"))
    which.set_minor_locator(NullLocator())


def finish(fig, axes, name: str, top: float = 0.96) -> list[Path]:
    """Lay out, letter each panel at its top-left corner, and write the PDF and the TIFF."""
    fig.tight_layout(rect=(0, 0, 1, top), w_pad=2.0)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for letter, ax in zip("abcdef", axes, strict=False):
        box = ax.get_tightbbox(renderer).transformed(fig.transFigure.inverted())
        fig.text(max(box.x0, 0.0), min(box.y1 + 0.01, 0.995), letter, fontweight="bold",
                 fontsize=7, ha="left", va="bottom")
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [OUT / f"{name}.pdf", OUT / f"{name}.tif"]
    fig.savefig(paths[0], facecolor="white")
    fig.savefig(paths[1], dpi=300, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)
    return paths


def reliability(draws_csv: Path) -> list[Path]:
    """Figure 1: mean incremental visits, and the share of draws that beat random."""
    frame = pd.read_csv(draws_csv).drop(columns=["dataset"], errors="ignore")
    result = SmallNResult(dataset=draws_csv.name, frame=frame)
    summary, rates = result.summary(), win_rates(result)
    random_mean = float(frame.loc[frame["method"] == "random", "incremental"].mean())
    sizes = sorted(summary["train_size"].unique())

    fig, (a, b) = plt.subplots(1, 2, figsize=(WIDTH, 72 * MM))
    offsets = dict(zip(METHODS, (0.93, 0.965, 1.0, 1.035, 1.07), strict=True))
    for method, (label, colour, marker, ls) in METHOD_STYLE.items():
        s = summary[summary["method"] == method].sort_values("train_size")
        a.fill_between(s["train_size"], s["mean"] - s["std"], s["mean"] + s["std"],
                       color=colour, alpha=0.10, lw=0)
        a.plot(s["train_size"], s["mean"], color=colour, ls=ls, marker=marker, label=label)
        r = rates[rates["method"] == method].sort_values("train_size")
        b.errorbar(r["train_size"] * offsets[method], 100 * r["win_rate"],
                   yerr=[100 * (r["win_rate"] - r["low"]), 100 * (r["high"] - r["win_rate"])],
                   color=colour, ls=ls, marker=marker, elinewidth=1.0, capthick=1.0)
    a.axhline(random_mean, color="black", ls="--", lw=1.0, label="Random selection")
    b.axhline(50, color="black", ls=":", lw=1.0)
    b.text(sizes[-1] * 1.07, 51.5, "50%", ha="right", va="bottom")
    for ax in (a, b):
        log_axis(ax, sizes)
        ax.set_xlabel("Training customers")
    a.set_ylabel("Incremental visits, top 30% selected")
    b.set_ylabel("Draws beating random selection (%)")
    b.set_ylim(40, 102)
    handles, labels = a.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=6, bbox_to_anchor=(0.5, 0.995),
               handletextpad=0.4, columnspacing=1.2)
    return finish(fig, (a, b), "fig1_small_sample_reliability", top=0.90)


def measurement_floor() -> list[Path]:
    """Figure 2: the holdout estimator against the truth, and the minimum detectable effect."""
    frame = validate(seeds=60)
    summary = holdout_summary(frame)
    delivered = float(frame["true_lift"].mean())
    power = power_table()
    need = required_holdout_size(delivered)

    fig, (a, b) = plt.subplots(1, 2, figsize=(WIDTH, 62 * MM))
    n = summary["n_customers"].to_numpy(dtype=float)
    a.axhline(0, color=GREY, lw=1.0)
    a.axhline(delivered, color=GREEN, ls="--", lw=1.5, label=f"True effect ({delivered:.4f})")
    a.errorbar(n, summary["measured_lift"], yerr=summary["ci_width"] / 2, color=BLUE,
               marker="o", elinewidth=1.0, capthick=1.0, label="Measured lift, 95% interval")
    a.set_ylabel("Retention lift")
    a.set_xlabel("Customers in the business")
    a.legend(loc="upper right")

    pn = power["n_customers"].to_numpy(dtype=float)
    b.fill_between(pn, delivered, power["mde"], color=VERMILLION, alpha=0.10, lw=0)
    b.plot(pn, power["mde"], color=VERMILLION, marker="o", label="Minimum detectable effect")
    b.axhline(delivered, color=GREEN, ls="--", lw=1.5, label=f"Effect delivered ({delivered:.4f})")
    log_axis(b, (0.01, 0.02, 0.05, 0.1, 0.2), axis="y")
    b.set_ylim(0.008, 0.3)
    b.set_ylabel("Retention lift (log scale)")
    b.set_xlabel("Customers eligible for the offer")
    b.text(0.04, 0.30, f"Detecting the delivered effect needs\n{need:,} eligible customers",
           transform=b.transAxes, color=VERMILLION, ha="left", va="center")
    b.legend(loc="upper right")
    for ax in (a, b):
        log_axis(ax, SIZES)
    return finish(fig, (a, b), "fig2_measurement_floor")


def correlation(splits_csv: Path) -> list[Path]:
    """Figure 3: what an uplift model gains, against the correlation, on two scales."""
    frame = pd.read_csv(splits_csv)
    s = summarise(frame).set_index(["setting", "measure"])
    settings = list(dict.fromkeys(frame["setting"]))

    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 70 * MM), sharey=True)
    for ax, (measure, scale) in zip(axes, PANELS, strict=True):
        ax.axhline(0, color="black", lw=1.0)
        ax.axvline(0, color=GREY, lw=1.0, ls=":")
        for name in settings:
            label, colour = SETTING_STYLE[name]
            x, y = s.loc[(name, measure)], s.loc[(name, "gain_per_1000")]
            ax.errorbar(x["mean"], y["mean"],
                        xerr=[[x["mean"] - x["low"]], [x["high"] - x["mean"]]],
                        yerr=[[y["mean"] - y["low"]], [y["high"] - y["mean"]]],
                        fmt=MARKERS[name], ms=5, color=colour, ecolor=colour,
                        elinewidth=1.0, capthick=1.0, label=label)
        ax.set_xlim(-0.9, 0.9)
        ax.set_title(f"Correlation on the {scale}")
        ax.set_xlabel("Correlation between estimated benefit and estimated risk")
    axes[1].tick_params(labelleft=True)
    axes[0].set_ylabel("Gain of the uplift model over the outcome model\n"
                       "(outcomes per 1,000 customers)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=5, bbox_to_anchor=(0.5, 0.995),
               handletextpad=0.3, columnspacing=1.4)
    return finish(fig, axes, "fig3_correlation", top=0.90)


def decision_rules(draws_csv: Path) -> list[Path]:
    """Figure 4: mean money of three rules, and the declining rule against Lemmens-Gupta."""
    frame = pd.read_csv(draws_csv)
    table = by_policy(frame).set_index(["n_customers", "policy"])
    sizes = sorted(frame["n_customers"].unique())

    fig, (a, b) = plt.subplots(1, 2, figsize=(WIDTH, 64 * MM))
    a.axhline(0, color="black", lw=1.0)
    a.text(sizes[-1] * 1.25, 120, "Doing nothing", ha="right", va="bottom")
    for policy, (label, colour, marker) in RULE_STYLE.items():
        a.plot(sizes, [table.loc[(n, policy), "mean_value"] for n in sizes], color=colour,
               marker=marker, label=label)
    a.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:,.0f}"))
    a.set_ylim(top=700)
    a.set_ylabel("Mean money relative to doing nothing")
    a.legend(loc="lower left")

    b.axhline(50, color="black", ls=":", lw=1.0)
    b.text(sizes[-1] * 1.25, 51.5, "50%", ha="right", va="bottom")
    for n in sizes:
        c = compare(frame[frame["n_customers"] == n], OURS, THEIRS)
        rate, low, high = (100 * c[k] for k in ("rate", "low", "high"))
        b.errorbar([n], [rate], yerr=[[rate - low], [high - rate]], color=BLUE, marker="o",
                   elinewidth=1.0, capthick=1.0)
        b.annotate(f"{c['wins']} of {c['wins'] + c['losses']}", (n, rate), xytext=(5, 0),
                   textcoords="offset points", ha="left", va="center")
    b.set_ylim(0, 100)
    b.set_ylabel("Businesses where the declining\nrule earns more (%)")
    for ax in (a, b):
        log_axis(ax, sizes)
        ax.set_xlim(sizes[0] * 0.8, sizes[-1] * 1.3)
        ax.set_xlabel("Customers in the business")
    return finish(fig, (a, b), "fig4_decision_rules")


def policy_value() -> list[Path]:
    """Figure 5: expected value of each policy by budget, and who is in each risk tenth."""
    cfg = SimConfig(n_customers=6000, n_months=24, seed=7)
    curve = _mean_budget_curve(cfg, 6, decision_month=6, horizon=6)
    mix = _quadrant_mix_by_decile(cfg, 6, 6)

    fig, (a, b) = plt.subplots(1, 2, figsize=(WIDTH, 66 * MM))
    x = curve["budget_fraction"] * 100
    for col, label, colour, ls in (("oracle_uplift", "By true effect (upper bound)", GREEN, "-"),
                                   ("random", "At random", GREY, "--"),
                                   ("churn_score", "By churn score", VERMILLION, "-")):
        lo, hi = (curve[col] - curve[col + "_sd"]) / 1000, (curve[col] + curve[col + "_sd"]) / 1000
        a.fill_between(x, lo, hi, color=colour, alpha=0.15, lw=0)
        a.plot(x, curve[col] / 1000, color=colour, ls=ls, label=label)
    a.axhline(0, color="black", lw=1.0)
    a.text(100, 1.5, "Doing nothing", ha="right", va="bottom")
    a.set_xlabel("Eligible customers treated (%)")
    a.set_ylabel("Expected value relative to\ndoing nothing (thousands)")
    a.legend(loc="lower left")

    bottom = np.zeros(len(mix))
    deciles = mix.index.astype(int)
    for q, (label, colour) in QUADRANT_STYLE.items():
        vals = mix[q].to_numpy() * 100
        b.bar(deciles, vals, bottom=bottom, color=colour, width=0.8, lw=0, label=label)
        bottom += vals
    b.set_xticks(list(deciles))
    b.set_ylim(0, 100)
    b.set_xlabel("Tenth of predicted churn risk (1 = highest)")
    b.set_ylabel("Share of the tenth (%)")
    b.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=4, handlelength=1.2)
    return finish(fig, (a, b), "fig5_policy_value")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--small-n", type=Path,
                    default=RESULTS / "small_n_200_draws_fixed_stopping_2026-10-09.csv")
    ap.add_argument("--splits", type=Path,
                    default=RESULTS / "correlation_checks_30_splits_fixed_stopping_2026-10-09.csv")
    ap.add_argument("--draws", type=Path, default=RESULTS / "baseline_500_draws_2026-10-08.csv")
    args = ap.parse_args(argv)
    for f in (args.small_n, args.splits, args.draws):
        if not f.exists():
            sys.exit(f"{f} not found. The module docstring names the command that writes it.")
    with plt.rc_context(STYLE):
        for paths in (reliability(args.small_n), measurement_floor(), correlation(args.splits),
                      decision_rules(args.draws), policy_value()):
            print(*paths, sep="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
