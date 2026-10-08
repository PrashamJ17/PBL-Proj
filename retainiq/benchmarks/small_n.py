"""How targeting methods degrade when data is scarce.

This is the project's central research question, and unlike the worse-than-random
claim, Hillstrom **can** test it.

Every public uplift dataset is enormous by small-business standards -- Hillstrom has
64,000 customers, Criteo 14 million. The businesses this project targets have several
hundred. Published uplift results are therefore reported in a regime almost no
prospective user occupies.

The experiment: hold the evaluation set fixed and shrink only the *training* set, so
that any change in measured performance is attributable to estimation difficulty rather
than to evaluation noise. Repeat over many seeds, because at n=500 the variance across
draws is the finding, not a nuisance.

What to look for
----------------
1. **Where uplift models stop beating outcome models.** Estimating a difference of two
   probabilities is harder than estimating either one. Below some n the difference is
   pure noise, and the simpler model should win.
2. **Variance, not just the mean.** A method whose average is good but whose spread
   across seeds is enormous is unusable for a single business, which gets exactly one
   draw. This is the argument for abstention, and it is invisible if you report only
   means.

What this module prints (D-072, D-073)
--------------------------------------
The headline is a **win rate**: the share of draws on which a method beats random
targeting on the same split. Every win rate is printed with an exact 95% interval, and
the default number of draws is large enough for that interval to mean something.

For two months the documents quoted "75% at n = 500" and "55%, a coin flip". Those came
from twenty draws, were printed by no command, and had no interval beside them: 15 wins
in 20 is compatible with anything from 51% to 91%. At 200 draws the best method is at
72.5% [66%, 79%] and the "coin flip" is at 62.5%, which is not a coin flip.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta

from retainiq.benchmarks.datasets import RCT, load_hillstrom
from retainiq.benchmarks.evaluate import top_k_mask, uplift_of_set
from retainiq.benchmarks.models import ALL_TARGETERS
from retainiq.benchmarks.run import split

TRAIN_SIZES = (500, 1_000, 2_000, 5_000, 10_000, 20_000)

#: Draws per training size. At 200 a rate near 70% has an exact 95% interval about seven
#: points either side; at 20 it is about twenty points either side, which cannot separate
#: 75% from a coin toss. The full run takes roughly twenty minutes.
DRAWS = 200

#: The methods compared, in the order they are reported.
METHODS = ("outcome_propensity", "response_model", "t_learner", "s_learner", "class_transform")


def exact_interval(wins: int, draws: int, level: float = 0.95) -> tuple[float, float]:
    """Clopper-Pearson interval for a proportion.

    Exact, so it is valid at the small counts and the rates near 100% that this
    experiment produces, where the usual normal approximation is not.
    """
    if draws <= 0:
        raise ValueError("an interval needs at least one draw")
    if not 0 <= wins <= draws:
        raise ValueError(f"{wins} wins out of {draws} draws is not a count")
    tail = (1.0 - level) / 2.0
    low = 0.0 if wins == 0 else float(beta.ppf(tail, wins, draws - wins + 1))
    high = 1.0 if wins == draws else float(beta.ppf(1.0 - tail, wins + 1, draws - wins))
    return low, high


@dataclass
class SmallNResult:
    dataset: str
    frame: pd.DataFrame
    """One row per (train_size, method, seed)."""

    def summary(self) -> pd.DataFrame:
        """Mean and spread of incremental outcome by method and training size."""
        g = self.frame.groupby(["train_size", "method"])["incremental"]
        out = g.agg(["mean", "std", "min", "max"]).reset_index()
        out["cv"] = out["std"] / out["mean"].abs().clip(lower=1e-9)
        return out

    def pivot(self, value: str = "mean") -> pd.DataFrame:
        s = self.summary()
        return s.pivot(index="train_size", columns="method", values=value)


def run(
    rct: RCT | None = None,
    train_sizes: tuple[int, ...] = TRAIN_SIZES,
    budget_fraction: float = 0.30,
    n_seeds: int = DRAWS,
    test_size: float = 0.5,
) -> SmallNResult:
    """Shrink the training set; hold the evaluation set fixed."""
    rct = rct or load_hillstrom()
    rows = []

    for seed in range(n_seeds):
        full_train, test = split(rct, test_size=test_size, seed=seed)
        k = int(round(budget_fraction * len(test)))

        # Random targeting on this test split, as the per-seed reference point.
        rng = np.random.default_rng(1000 + seed)
        rand_vals = [
            uplift_of_set(test.treatment, test.outcome, top_k_mask(rng.random(len(test)), k))
            for _ in range(50)
        ]
        rand_u = float(np.nanmean(rand_vals))
        rows.append({
            "train_size": np.nan, "method": "random", "seed": seed,
            "uplift_per_contact": rand_u, "incremental": rand_u * k,
        })

        for n in train_sizes:
            if n > len(full_train):
                continue
            train = full_train.subsample(n, seed=seed)
            # A subsample can lose an entire arm or every positive outcome.
            if len(np.unique(train.treatment)) < 2 or len(np.unique(train.outcome)) < 2:
                continue

            for cls in ALL_TARGETERS:
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        model = cls(seed=seed).fit(train.X, train.treatment, train.outcome)
                        scores = model.score(test.X)
                except Exception:
                    # At n=500 a learner can fail outright on a degenerate draw.
                    # That is itself a result about small-sample reliability, so it
                    # is recorded as NaN rather than silently retried.
                    rows.append({
                        "train_size": n, "method": cls.name, "seed": seed,
                        "uplift_per_contact": np.nan, "incremental": np.nan,
                    })
                    continue

                u = uplift_of_set(test.treatment, test.outcome, top_k_mask(scores, k))
                rows.append({
                    "train_size": n, "method": cls.name, "seed": seed,
                    "uplift_per_contact": u, "incremental": u * k,
                })

    return SmallNResult(dataset=rct.name, frame=pd.DataFrame(rows))


def win_rates(result: SmallNResult) -> pd.DataFrame:
    """How often each method beats random *on the same draw*, with an exact interval.

    Paired: a method is compared with random targeting on the split it was evaluated
    on, never with random's average. A fit that failed outright is recorded as NaN by
    `run` and counts here as a draw that did not beat random, because a business whose
    model failed to fit has gained nothing from it.
    """
    frame = result.frame
    rand = frame[frame["method"] == "random"].set_index("seed")["incremental"]

    rows = []
    for n in sorted(frame[frame["train_size"].notna()]["train_size"].unique()):
        for method in METHODS:
            sub = frame[(frame["train_size"] == n) & (frame["method"] == method)]
            sub = sub.set_index("seed")["incremental"]
            common = sub.index.intersection(rand.index)
            if len(common) == 0:
                continue
            wins = int((sub.loc[common] > rand.loc[common]).sum())
            low, high = exact_interval(wins, len(common))
            rows.append({
                "train_size": n, "method": method, "wins": wins, "draws": len(common),
                "win_rate": wins / len(common), "low": low, "high": high,
            })
    return pd.DataFrame(rows)


def rate(wins: int, draws: int) -> str:
    """A win rate as it is always printed here: with its interval beside it."""
    low, high = exact_interval(wins, draws)
    return f"{wins / draws:.1%} [{low:.0%}, {high:.0%}]"


def report(result: SmallNResult) -> str:
    return _means_report(result) + "\n\n\n" + _win_rate_report(result)


def _win_rate_report(result: SmallNResult) -> str:
    wins = win_rates(result)
    if wins.empty:
        return "No draws to compare with random targeting."
    draws = int(wins["draws"].max())
    width = 9 + 22 * len(METHODS)
    lines = [
        f"Win rate against random targeting, paired on the same draw ({draws} draws)",
        "share of draws on which the method beat random, with an exact 95% interval",
        "=" * width,
        f"{'train n':>9}" + "".join(f"{m[:18]:>22}" for m in METHODS),
        "-" * width,
    ]
    for n in sorted(wins["train_size"].unique()):
        row = f"{int(n):>9}"
        for m in METHODS:
            cell = wins[(wins["train_size"] == n) & (wins["method"] == m)]
            row += f"{'--':>22}" if cell.empty else (
                f"{rate(int(cell['wins'].iloc[0]), int(cell['draws'].iloc[0])):>22}")
        lines.append(row)
    lines.append("-" * width)
    for n in sorted(wins["train_size"].unique()):
        at = wins[wins["train_size"] == n]
        best, worst = at.loc[at["win_rate"].idxmax()], at.loc[at["win_rate"].idxmin()]
        lines.append(
            f"n = {int(n):>6,}: best {best['method']} {int(best['wins'])} of "
            f"{int(best['draws'])}, {rate(int(best['wins']), int(best['draws']))};  "
            f"weakest {worst['method']} {rate(int(worst['wins']), int(worst['draws']))}"
        )
    lines.append(
        "\nA business gets one draw. Read the interval, not only the rate: a rate from few\n"
        "draws is compatible with a wide range, and one whose interval reaches 50% has not\n"
        "been shown to beat chance."
    )
    return "\n".join(lines)


def _means_report(result: SmallNResult) -> str:
    frame = result.frame
    rand = frame[frame["method"] == "random"]["incremental"].mean()
    s = result.summary()
    s = s[s["train_size"].notna()]

    methods = list(METHODS)
    lines = [
        f"Small-n degradation: {result.dataset}",
        f"(evaluation set held fixed; random baseline = {rand:.1f} incremental)",
        "=" * 92,
        f"{'train n':>9}" + "".join(f"{m[:16]:>17}" for m in methods),
        "-" * 92,
    ]

    for n in sorted(s["train_size"].unique()):
        row = f"{int(n):>9}"
        for m in methods:
            cell = s[(s["train_size"] == n) & (s["method"] == m)]
            if cell.empty:
                row += f"{'--':>17}"
            else:
                mean, sd = cell["mean"].iloc[0], cell["std"].iloc[0]
                row += f"{mean:>10.0f}±{sd:<6.0f}"
        lines.append(row)

    lines.append("-" * 92)
    lines.append("mean incremental outcome ± std across seeds. Higher is better.")

    # Where does uplift stop paying for itself?
    crossover = None
    for n in sorted(s["train_size"].unique()):
        best_uplift = s[(s["train_size"] == n) & (s["method"].isin(
            ["t_learner", "s_learner", "class_transform"]))]["mean"].max()
        best_outcome = s[(s["train_size"] == n) & (s["method"].isin(
            ["outcome_propensity", "response_model"]))]["mean"].max()
        if best_uplift is not None and best_outcome is not None and best_uplift < best_outcome:
            crossover = int(n)
    if crossover:
        lines.append(
            f"\nBelow n={crossover}, the best OUTCOME model beats the best UPLIFT model."
        )
    else:
        lines.append(
            "\nOn the MEAN, uplift models beat outcome models at every training size tested."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--draws", type=int, default=DRAWS,
                    help=f"draws per training size (default {DRAWS}, about twenty minutes)")
    ap.add_argument("--no-figure", action="store_true",
                    help="print the tables only; do not redraw the reliability figure")
    ap.add_argument("--save-draws", type=Path, metavar="CSV",
                    help="also write every draw's result to this file")
    ap.add_argument("--from-draws", type=Path, metavar="CSV",
                    help="print and draw from a file written by --save-draws instead of "
                         "running. The output says it was re-read, not re-run.")
    args = ap.parse_args(argv)

    if args.from_draws:
        frame = pd.read_csv(args.from_draws)
        name = str(frame["dataset"].iloc[0]) if "dataset" in frame and len(frame) else "unknown"
        # Named as re-read so that a table printed from a saved file is never mistaken
        # for the experiment having been run again (invariant 14).
        result = SmallNResult(dataset=f"{name}, RE-READ from {args.from_draws.name}, not re-run",
                              frame=frame.drop(columns=["dataset"], errors="ignore"))
    else:
        result = run(n_seeds=args.draws)
        if args.save_draws:
            args.save_draws.parent.mkdir(parents=True, exist_ok=True)
            result.frame.assign(dataset=result.dataset).to_csv(args.save_draws, index=False)
    print(report(result))
    if not args.no_figure:
        # Drawn from the same run that printed the tables, so the two cannot disagree.
        from retainiq.benchmarks.figures import figure_2

        print()
        print(figure_2(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
