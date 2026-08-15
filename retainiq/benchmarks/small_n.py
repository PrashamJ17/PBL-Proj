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
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from retainiq.benchmarks.datasets import RCT, load_hillstrom
from retainiq.benchmarks.evaluate import top_k_mask, uplift_of_set
from retainiq.benchmarks.models import ALL_TARGETERS
from retainiq.benchmarks.run import split

TRAIN_SIZES = (500, 1_000, 2_000, 5_000, 10_000, 20_000)


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
    n_seeds: int = 12,
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


def report(result: SmallNResult) -> str:
    frame = result.frame
    rand = frame[frame["method"] == "random"]["incremental"].mean()
    s = result.summary()
    s = s[s["train_size"].notna()]

    methods = ["outcome_propensity", "response_model", "t_learner", "s_learner", "class_transform"]
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
        lines.append("\nUplift models beat outcome models at every training size tested.")
    return "\n".join(lines)


if __name__ == "__main__":
    r = run()
    print(report(r))
