"""The checks the risk-lift correlation owed (D-068).

`spectrum.py` measures one number per setting: the Pearson correlation, on the
probability scale, between a T-learner's estimated effect and an outcome model fitted on
both arms, from one split. Reading it beside Ascarza (2018, Web Appendix A3.4) raised
four questions that one number from one split cannot answer:

1. **Is it the coefficient?** Pearson measures linear association and is moved by a few
   extreme customers. Spearman measures agreement between the two *orderings*, which is
   what targeting uses.
2. **Is it the scale?** If an offer shifts everyone's log-odds by the same amount, the
   shift in probability is largest where the baseline is highest. A positive correlation
   on the probability scale can therefore be produced by arithmetic alone. Ascarza warns
   of this.
3. **Is it the definition of risk?** Her RISK is fitted on control customers only. With a
   T-learner that is the model whose prediction is *subtracted* to form the effect, so
   the two share estimation noise with opposite sign. Fitting the risk on customers the
   effect model never saw removes that.
4. **Is it the split?** One split has no interval.

And a fifth about the figure: the simulator's point compares an oracle with a churn
score. What does a *fitted* uplift model gain there?

The design and five predictions were committed before this module existed, in
`docs/PREREG-checks-and-baseline.md`. The answers are in D-074.

Nothing here changes what `spectrum.py` prints. That command still shows one split, and
this one shows how far one split can sit from the other twenty-nine. The figure drawn
here (`fig07`) is the one to use: every point on it is a fitted model on a randomised
trial, measured the same way, with the spread across splits drawn on both axes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from retainiq.benchmarks.datasets import RCT
from retainiq.benchmarks.evaluate import top_k_mask, uplift_of_set
from retainiq.benchmarks.models import TLearner, _clf
from retainiq.benchmarks.run import split
from retainiq.benchmarks.spectrum import OUTCOME_MODELS, UPLIFT_MODELS

#: Splits per setting. Fixed in the pre-registration.
SPLITS = 30

#: Probabilities are clipped to this distance from 0 and 1 before taking logits, so a
#: fitted probability of exactly 0 does not become an infinite log-odds.
CLIP = 1e-4

#: Customers in the trial drawn from the simulator: comparable with Hillstrom.
SIM_CUSTOMERS = 60_000

SCALES = ("prob", "logodds")
RISKS = ("pooled", "control_same", "control_indep")
COEFFICIENTS = ("pearson", "spearman")


@dataclass(frozen=True)
class Setting:
    """A randomised experiment and which way its outcome points.

    `benefit_sign` is +1 when the outcome is something the firm wants more of (a visit, a
    purchase) and -1 when it wants less (churn). Every effect is then reported as a
    *benefit*, positive when the treatment helps, which is Ascarza's LIFT. The outcome
    model's score is the propensity for the outcome either way: likeliest to respond, or
    likeliest to churn. That is what a naive policy targets in both cases.
    """

    name: str
    domain: str
    benefit_sign: int = 1


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), CLIP, 1.0 - CLIP)
    return np.log(p / (1.0 - p))


def _constant(x: np.ndarray) -> bool:
    """True when `x` does not vary beyond rounding error.

    An effect that is the same for everyone, computed as a difference of two logits,
    comes out as a constant plus noise in the sixteenth decimal place. Correlating that
    noise with anything returns a number, and the number means nothing.
    """
    return bool(np.ptp(x) <= 1e-9 * max(1.0, float(np.abs(x).max())))


def correlation(a: np.ndarray, b: np.ndarray, coefficient: str) -> float:
    """Pearson or Spearman, and NaN when either input does not vary.

    A constant input has no ordering and no linear association with anything. Returning
    0 would report "uncorrelated", which is a finding; NaN reports that there was
    nothing to correlate.
    """
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.size < 3 or _constant(a) or _constant(b):
        return float("nan")
    if coefficient == "pearson":
        return float(np.corrcoef(a, b)[0, 1])
    if coefficient == "spearman":
        return float(spearmanr(a, b).statistic)
    raise ValueError(f"unknown coefficient {coefficient!r}")


def benefits(p1: np.ndarray, p0: np.ndarray, sign: int) -> dict[str, np.ndarray]:
    """The effect of treatment as a benefit, on each scale."""
    return {"prob": sign * (p1 - p0), "logodds": sign * (logit(p1) - logit(p0))}


def risks_on(scale: str, risk: np.ndarray) -> np.ndarray:
    return risk if scale == "prob" else logit(risk)


def all_correlations(benefit: dict[str, np.ndarray], risk: np.ndarray) -> dict[str, float]:
    """Every coefficient on every scale, for one definition of risk."""
    return {
        f"{coefficient}_{scale}": correlation(benefit[scale], risks_on(scale, risk), coefficient)
        for scale in SCALES for coefficient in COEFFICIENTS
    }


def incremental(scores: np.ndarray, rct: RCT, budget_fraction: float, sign: int) -> float:
    """Extra good outcomes from treating the top of a ranking, estimated from the trial."""
    k = int(round(budget_fraction * len(rct)))
    mask = top_k_mask(scores, k)
    return sign * uplift_of_set(rct.treatment, rct.outcome, mask) * int(mask.sum())


def one_split(rct: RCT, seed: int, benefit_sign: int = 1,
              budget_fraction: float = 0.30) -> dict[str, float]:
    """Everything measured on one split of one experiment."""
    train, test = split(rct, seed=seed)
    X, t, y = train.X, train.treatment, train.outcome

    learner = TLearner(seed=seed).fit(X, t, y)
    p1 = learner.treated.predict_proba(test.X)[:, 1]
    p0 = learner.control.predict_proba(test.X)[:, 1]
    benefit = benefits(p1, p0, benefit_sign)

    row: dict[str, float] = {"seed": seed, "n_test": len(test)}

    # Risk fitted on both arms: what `spectrum.py` does.
    pooled = _clf(seed).fit(X, y.astype(int)).predict_proba(test.X)[:, 1]
    row |= {f"pooled_{k}": v for k, v in all_correlations(benefit, pooled).items()}

    # Risk fitted on control only, by the same model the effect subtracts.
    row |= {f"control_same_{k}": v for k, v in all_correlations(benefit, p0).items()}

    # Risk fitted on control only, on customers the effect model never saw. The training
    # half is cut in two: one part fits the effect, the other fits the risk.
    order = np.random.default_rng(50_000 + seed).permutation(len(train))
    a, b = order[: len(order) // 2], order[len(order) // 2:]
    control_b = b[t[b] == 0]
    usable = (
        len(np.unique(t[a])) == 2 and len(control_b) > 0
        and all(len(np.unique(y[a][t[a] == arm])) == 2 for arm in (0, 1))
        and len(np.unique(y[control_b])) == 2
    )
    if usable:
        effect_a = TLearner(seed=seed).fit(X.iloc[a], t[a], y[a])
        benefit_a = benefits(effect_a.treated.predict_proba(test.X)[:, 1],
                             effect_a.control.predict_proba(test.X)[:, 1], benefit_sign)
        risk_b = (_clf(seed + 2).fit(X.iloc[control_b], y[control_b].astype(int))
                  .predict_proba(test.X)[:, 1])
        found = all_correlations(benefit_a, risk_b)
    else:
        found = dict.fromkeys(all_correlations(benefit, p0), float("nan"))
    row |= {f"control_indep_{k}": v for k, v in found.items()}

    # The advantage of the best uplift model over the best outcome model, as
    # `spectrum.measure` computes it, without the bootstrap.
    def best(classes, sign_scores: int) -> float:
        return max(
            incremental(sign_scores * cls(seed=seed).fit(X, t, y).score(test.X), test,
                        budget_fraction, benefit_sign)
            for cls in classes
        )

    up, out = best(UPLIFT_MODELS, benefit_sign), best(OUTCOME_MODELS, 1)
    row["best_uplift"], row["best_outcome"] = up, out
    row["advantage_pct"] = 100.0 * (up - out) / max(abs(out), 1e-9)
    # Not in the pre-registration: the same gap per thousand customers. The percentage
    # divides by the outcome model's gain, which is small or negative in some settings.
    row["gain_per_1000"] = 1000.0 * (up - out) / len(test)
    row["predicted_negative"] = float((benefit["prob"] < 0).mean())
    return row


def run(rct: RCT, setting: Setting, splits: int = SPLITS) -> pd.DataFrame:
    rows = [one_split(rct, seed, setting.benefit_sign) for seed in range(splits)]
    return pd.DataFrame(rows).assign(setting=setting.name, domain=setting.domain)


# --- the simulator, measured the way the experiments are ----------------------


def subsim_trial(n_customers: int = SIM_CUSTOMERS, seed: int = 7) -> tuple[RCT, pd.DataFrame]:
    """A randomised trial drawn from the simulator, and the truth it was drawn from.

    Treatment is assigned by coin toss and each customer's outcome is observed for the
    arm they were assigned, which is all a real experiment would show. The truth is
    returned beside it and is never given to a model.
    """
    from retainiq.experiments.abstention import FEATURES
    from retainiq.sim import SimConfig, simulate
    from retainiq.sim.counterfactual import potential_outcomes

    sim = simulate(SimConfig(n_customers=n_customers, n_months=24, seed=seed))
    po = potential_outcomes(sim, decision_month=6, horizon=6)
    snap = sim.snapshot(6)[["customer_id", *FEATURES]]
    frame = po.merge(snap, on="customer_id", how="inner").reset_index(drop=True)

    treated = (np.random.default_rng(7_000 + seed).random(len(frame)) < 0.5).astype(int)
    churned = np.where(treated == 1, frame["y1"], frame["y0"]).astype(float)
    rct = RCT(name=f"subsim[{n_customers:,}]", X=frame[FEATURES].astype(float),
              treatment=treated, outcome=churned, outcome_name="churned")
    return rct, frame[["p_churn_control", "p_churn_treated", "tau_true"]]


def true_correlations(truth: pd.DataFrame) -> dict[str, float]:
    """The correlation between true benefit and true untreated risk, on both scales."""
    benefit = benefits(truth["p_churn_treated"].to_numpy(), truth["p_churn_control"].to_numpy(),
                       sign=-1)
    return all_correlations(benefit, truth["p_churn_control"].to_numpy())


# --- summarising ----------------------------------------------------------------


def interval(values: pd.Series) -> tuple[float, float, float]:
    """Mean, and the 2.5th and 97.5th percentiles across splits."""
    v = values.dropna().to_numpy()
    if v.size == 0:
        return float("nan"), float("nan"), float("nan")
    return float(v.mean()), float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def summarise(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per setting and measure: mean and split-to-split interval."""
    measures = [c for c in frame.columns
                if c not in {"seed", "n_test", "setting", "domain"}]
    rows = []
    for name, g in frame.groupby("setting", sort=False):
        for m in measures:
            mean, low, high = interval(g[m])
            rows.append({"setting": name, "measure": m, "mean": mean, "low": low,
                         "high": high, "splits": int(g[m].notna().sum())})
    return pd.DataFrame(rows)


def _cell(summary: pd.DataFrame, setting: str, measure: str, fmt: str = "+.2f") -> str:
    r = summary[(summary["setting"] == setting) & (summary["measure"] == measure)]
    if r.empty or np.isnan(r["mean"].iloc[0]):
        return "n/a"
    mean, low, high = (r[c].iloc[0] for c in ("mean", "low", "high"))
    return f"{mean:{fmt}} [{low:{fmt}}, {high:{fmt}}]"


def report(frame: pd.DataFrame, truth: dict[str, float] | None = None,
           oracle_note: str | None = None, source: str | None = None) -> str:
    """The tables. `source` names a saved file when the splits were re-read, not re-run."""
    s = summarise(frame)
    settings = list(dict.fromkeys(frame["setting"]))
    splits = int(frame.groupby("setting").size().max())
    width = 118
    out = [
        "THE RISK-LIFT CORRELATION, CHECKED (D-068, D-074)",
        f"mean over {splits} splits, with the 2.5th and 97.5th percentiles across splits",
    ]
    if source:
        # Named as re-read so that a table printed from a saved file is never mistaken
        # for the experiment having been run again (invariant 14).
        out.append(f"RE-READ from {source}, not re-run")
    out.append("=" * width)

    def table(title: str, columns: list[tuple[str, str]], fmt: str = "+.2f") -> None:
        out.extend(["", title, "-" * width,
                    f"{'setting':<24}" + "".join(f"{h:>31}" for h, _ in columns)])
        for name in settings:
            out.append(f"{name:<24}" + "".join(f"{_cell(s, name, m, fmt):>31}"
                                               for _, m in columns))

    table("1. THE COEFFICIENT (probability scale, pooled risk)",
          [("Pearson", "pooled_pearson_prob"), ("Spearman", "pooled_spearman_prob")])
    table("2. THE SCALE (Pearson, pooled risk)",
          [("probability", "pooled_pearson_prob"), ("log-odds", "pooled_pearson_logodds")])
    table("   THE SCALE (Spearman, pooled risk)",
          [("probability", "pooled_spearman_prob"), ("log-odds", "pooled_spearman_logodds")])
    table("3. THE DEFINITION OF RISK (Pearson, probability scale)",
          [("pooled", "pooled_pearson_prob"), ("control, same data", "control_same_pearson_prob"),
           ("control, independent", "control_indep_pearson_prob")])
    table("4. WHAT THE UPLIFT MODEL GAINS over the best outcome model",
          [("advantage, %", "advantage_pct"), ("per 1,000 customers", "gain_per_1000")],
          fmt="+.1f")

    if truth is not None:
        out += ["", "5. THE SIMULATOR'S TRUTH (true benefit against true untreated risk)",
                "-" * width,
                "  " + "   ".join(f"{k.replace('_', ', ')}: {v:+.2f}" for k, v in truth.items())]
    if oracle_note:
        out += ["", oracle_note]
    out += [
        "", "-" * width,
        "Benefit is positive when treatment helps. Risk is the propensity for the outcome a",
        "naive policy targets: likeliest to respond, or likeliest to churn.",
        "control, same data  = risk from the model the effect subtracts: shares its noise.",
        "control, independent = risk and effect fitted on different customers.",
    ]
    return "\n".join(out)


# --- the figure ---------------------------------------------------------------------

#: One marker per setting, so the two Hillstrom campaigns can be told apart.
MARKERS = {"Hillstrom (mens)": "o", "Hillstrom (womens)": "s", "Criteo": "D", "Lenta": "^",
           "SubSim (fitted)": "P"}

PANELS = (("pooled_pearson_prob", "probability scale"),
          ("pooled_pearson_logodds", "log-odds scale"))


def figure(frame: pd.DataFrame, out: Path | None = None) -> Path:
    """What the uplift model gains, against the correlation on each scale.

    Two panels with the same vertical axis. Only the scale the correlation is taken on
    differs between them, so a pattern present in one and absent in the other belongs to
    the scale. Every point is the mean over the splits, with the spread across splits
    drawn on both axes; no point is an oracle.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from retainiq.benchmarks.spectrum import COLOURS, FIG_DIR

    s = summarise(frame).set_index(["setting", "measure"])
    settings = list(dict.fromkeys(frame["setting"]))
    domain = frame.drop_duplicates("setting").set_index("setting")["domain"]
    splits = int(frame.groupby("setting").size().max())

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 6.6), sharey=True)
    for ax, (measure, scale) in zip(axes, PANELS, strict=True):
        ax.axhline(0, color="#263238", lw=1.3, zorder=2)
        ax.axvline(0, color="#90A4AE", lw=1.0, ls=":", zorder=1)
        for name in settings:
            x, y = s.loc[(name, measure)], s.loc[(name, "gain_per_1000")]
            colour = COLOURS.get(domain[name], "#455A64")
            ax.errorbar(
                x["mean"], y["mean"],
                xerr=[[x["mean"] - x["low"]], [x["high"] - x["mean"]]],
                yerr=[[y["mean"] - y["low"]], [y["high"] - y["mean"]]],
                fmt=MARKERS.get(name, "o"), ms=9, color=colour, ecolor=colour,
                elinewidth=1.3, capsize=3, markeredgecolor="white", markeredgewidth=0.8,
                zorder=5, label=name,
            )
        ax.set_xlim(-0.9, 0.9)
        ax.set_title(f"correlation taken on the {scale}", fontsize=11.5)
        ax.set_xlabel("corr( estimated benefit , estimated outcome propensity ),  Pearson",
                      fontsize=10)
        ax.grid(alpha=0.25, lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Extra good outcomes per 1,000 customers from ranking\n"
                       "by uplift instead of by the outcome model (top 30%)", fontsize=10)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=len(settings), frameon=False,
               fontsize=10, bbox_to_anchor=(0.5, 0.925))
    fig.suptitle("What an uplift model gains over an outcome model, against the "
                 "risk\u2013lift correlation", fontsize=13, y=0.985)
    fig.text(
        0.5, 0.012,
        f"Each point is the mean over {splits} random splits of one randomised trial; bars "
        "run from the 2.5th to the 97.5th percentile across splits.\n"
        "All points are fitted models, measured the same way. Left and right show the same "
        "gains; only the scale of the correlation differs,\n"
        "so a pattern on one side and not the other belongs to the scale. SubSim is a trial "
        f"of {SIM_CUSTOMERS:,} simulated customers whose negative\n"
        "correlation is configured, not observed. The correlation is the one varied in "
        "Ascarza (2018, Web Appendix A3.4).",
        ha="center", va="bottom", fontsize=8.8, color="#455A64", linespacing=1.45,
    )
    fig.tight_layout(rect=(0, 0.13, 1, 0.9))
    out = out or (FIG_DIR / "fig07_correlation_checked.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


SIM = Setting("SubSim (fitted)", "subscription retention", benefit_sign=-1)

ORACLE_NOTE = (
    "Row 'SubSim (fitted)' is what fitted models gain, in outcomes, on a trial drawn from the\n"
    "simulator. `python -m retainiq.benchmarks.spectrum` prints what an oracle gains there, in\n"
    "money net of the offer. The two are in different units and their percentages are not to\n"
    "be compared (D-074)."
)


def collect(splits: int = SPLITS, include: tuple[str, ...] = ()) -> tuple[pd.DataFrame, dict]:
    """Every setting. Loads the public datasets; the simulator needs none."""
    from retainiq.benchmarks.datasets import load_criteo, load_hillstrom, load_lenta

    loaders = [
        (Setting("Hillstrom (mens)", "promotional email"), lambda: load_hillstrom("mens")),
        (Setting("Criteo", "advertising"), lambda: load_criteo(sample_rows=1_500_000, seed=0)),
        (Setting("Hillstrom (womens)", "promotional email"), lambda: load_hillstrom("womens")),
        (Setting("Lenta", "retail promotion"), load_lenta),
    ]
    frames = [run(load(), setting, splits) for setting, load in loaders
              if not include or setting.name in include]

    truth: dict[str, float] = {}
    if not include or SIM.name in include:
        rct, facts = subsim_trial()
        frames.append(run(rct, SIM, splits))
        truth = true_correlations(facts)
    return pd.concat(frames, ignore_index=True), truth


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--splits", type=int, default=SPLITS)
    ap.add_argument("--only", action="append", default=[], metavar="SETTING",
                    help="run one setting by name; repeat for several")
    ap.add_argument("--save", type=Path, metavar="CSV", help="also write every split's row")
    ap.add_argument("--from-splits", type=Path, metavar="CSV",
                    help="print and draw from a file written by --save instead of running. "
                         "The output says it was re-read, not re-run.")
    ap.add_argument("--no-figure", action="store_true",
                    help="print the tables only; do not redraw the figure")
    args = ap.parse_args(argv)

    source = None
    if args.from_splits:
        frame = pd.read_csv(args.from_splits)
        source = args.from_splits.name
        # The truth is not in the file. It is a property of the simulator, not of any
        # split, and it is recomputed rather than trusted from a saved copy.
        has_sim = (frame["setting"] == SIM.name).any()
        truth = true_correlations(subsim_trial()[1]) if has_sim else {}
    else:
        frame, truth = collect(args.splits, tuple(args.only))
        if args.save:
            args.save.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(args.save, index=False)
    print(report(frame, truth or None, ORACLE_NOTE if truth else None, source))

    if args.no_figure:
        return 0
    if args.only:
        print("\nFigure not drawn: it shows every setting, and only some were run.")
        return 0
    # Drawn from the same splits that printed the tables, so the two cannot disagree.
    print()
    print(figure(frame))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
