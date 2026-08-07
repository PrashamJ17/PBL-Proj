"""The external-validity experiment.

Question under test, stated so it can fail:

    On real randomised data, does targeting by an OUTCOME model (the churn-score
    analogue) underperform (a) uplift-based targeting, and (b) random targeting?

(a) is well established and we expect it. **(b) is our distinctive claim** and the
reason this experiment exists. If outcome-model targeting is merely mediocre on real
data rather than worse than random, then the simulator's worse-than-random result is an
artifact of the correlation we built into it, and the claim must be narrowed to the
churn setting where the mechanism -- dormant payers being reminded they are paying --
actually applies.

Honest expectation, recorded before running
--------------------------------------------
Hillstrom is email marketing, not churn retention. The harm mechanism there is
annoyance, which is weaker than "you reminded me I'm still paying you", and the
campaign's average effect on visits is strongly positive. So worse-than-random is a
high bar here and may well fail. That would be an informative result about *scope*,
not a refutation of the mechanism -- and saying so now, in the code, is what stops it
being rationalised afterwards.

Everything is fit on a training split and evaluated on a held-out split, so scores are
never evaluated on the rows that produced them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from keel.benchmarks.datasets import RCT, load_hillstrom
from keel.benchmarks.evaluate import (
    PolicyResult,
    evaluate_policy,
    qini_coefficient,
    qini_curve,
    random_baseline,
)
from keel.benchmarks.models import ALL_TARGETERS, Targeter


@dataclass
class BenchmarkRun:
    dataset: str
    n_train: int
    n_test: int
    budget_fraction: float
    results: list[PolicyResult]
    qini: dict[str, float]

    def table(self) -> pd.DataFrame:
        rows = [{
            "policy": r.name,
            "targeted": r.n_targeted,
            "uplift_per_1000": r.per_1000,
            "incremental": r.incremental_outcome,
            "ci_low": r.ci_low,
            "ci_high": r.ci_high,
            "qini": self.qini.get(r.name, np.nan),
        } for r in self.results]
        return pd.DataFrame(rows).sort_values("incremental", ascending=False)


def split(rct: RCT, test_size: float = 0.5, seed: int = 0) -> tuple[RCT, RCT]:
    """Stratified split on the treatment arm, so both halves stay balanced."""
    idx = np.arange(len(rct))
    tr, te = train_test_split(
        idx, test_size=test_size, random_state=seed, stratify=rct.treatment
    )

    def take(ix, tag):
        return RCT(
            name=f"{rct.name}/{tag}",
            X=rct.X.iloc[ix].reset_index(drop=True),
            treatment=rct.treatment[ix],
            outcome=rct.outcome[ix],
            outcome_name=rct.outcome_name,
            spend=None if rct.spend is None else rct.spend[ix],
        )

    return take(tr, "train"), take(te, "test")


def run(
    rct: RCT | None = None,
    budget_fraction: float = 0.30,
    seed: int = 0,
    n_boot: int = 400,
) -> BenchmarkRun:
    """Fit every targeter on a training split and evaluate on held-out data."""
    rct = rct or load_hillstrom()
    train, test = split(rct, seed=seed)

    results: list[PolicyResult] = [random_baseline(test, budget_fraction, seed=seed)]
    qini: dict[str, float] = {"random": 0.0}

    # Treating everyone: the honest upper bound on reach, and what most
    # small businesses actually do.
    all_sel = np.ones(len(test), dtype=bool)
    from keel.benchmarks.evaluate import uplift_of_set

    u_all = uplift_of_set(test.treatment, test.outcome, all_sel)
    results.append(PolicyResult(
        name="treat_all", n_targeted=len(test), budget_fraction=1.0,
        uplift_per_contact=u_all, incremental_outcome=u_all * len(test),
        ci_low=np.nan, ci_high=np.nan,
    ))

    for cls in ALL_TARGETERS:
        model: Targeter = cls(seed=seed)
        model.fit(train.X, train.treatment, train.outcome)
        scores = model.score(test.X)

        results.append(
            evaluate_policy(model.name, scores, test, budget_fraction, n_boot=n_boot, seed=seed)
        )
        qini[model.name] = qini_coefficient(qini_curve(scores, test))

    return BenchmarkRun(
        dataset=rct.name,
        n_train=len(train),
        n_test=len(test),
        budget_fraction=budget_fraction,
        results=results,
        qini=qini,
    )


def verdict(run_result: BenchmarkRun) -> str:
    """State plainly whether the distinctive claim survived."""
    by = {r.name: r for r in run_result.results}
    rand = by["random"].incremental_outcome
    lines = []

    for naive in ("outcome_propensity", "response_model"):
        if naive not in by:
            continue
        got = by[naive].incremental_outcome
        worse = got < rand
        lines.append(
            f"  {naive:<20} {got:>9.1f}  vs random {rand:>8.1f}   "
            f"{'WORSE than random' if worse else 'better than random'}"
        )

    best_uplift = max(
        (by[n] for n in ("t_learner", "s_learner", "class_transform") if n in by),
        key=lambda r: r.incremental_outcome,
        default=None,
    )
    if best_uplift:
        lines.append(
            f"  best uplift ({best_uplift.name}) {best_uplift.incremental_outcome:>9.1f}  "
            f"vs random {rand:>8.1f}"
        )
    return "\n".join(lines)


def report(run_result: BenchmarkRun) -> str:
    t = run_result.table()
    out = [
        f"Benchmark: {run_result.dataset}",
        f"train n={run_result.n_train:,}  test n={run_result.n_test:,}  "
        f"budget={run_result.budget_fraction:.0%}",
        "=" * 86,
        f"{'policy':<22}{'targeted':>9}{'uplift/1000':>13}{'incremental':>13}"
        f"{'95% CI':>22}{'qini':>8}",
        "-" * 86,
    ]
    for _, r in t.iterrows():
        ci = (
            f"[{r['ci_low']:.1f}, {r['ci_high']:.1f}]"
            if np.isfinite(r["ci_low"]) else "--"
        )
        out.append(
            f"{r['policy']:<22}{int(r['targeted']):>9}{r['uplift_per_1000']:>13.2f}"
            f"{r['incremental']:>13.1f}{ci:>22}{r['qini']:>8.1f}"
        )
    out += ["-" * 86, "Verdict on the distinctive claim:", verdict(run_result)]
    return "\n".join(out)


if __name__ == "__main__":
    r = run()
    print(load_hillstrom().summary())
    print()
    print(report(r))
