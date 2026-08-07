"""Evaluating targeting policies on randomised-trial data.

The estimator
-------------
On real data you cannot observe what a targeted customer would have done untreated.
But when treatment was assigned *at random*, the control group is a valid
counterfactual for any subgroup selected on **pre-treatment covariates**. So for a
policy that selects set S by score:

    uplift(S) = mean(Y | treated, in S) - mean(Y | control, in S)
    incremental outcome if S were treated = |S| x uplift(S)

The randomisation is doing all the work. Selecting S on anything measured *after*
assignment would break it immediately, which is why `RCT.X` carries pre-treatment
covariates only.

Why the primary metric carries no prices
----------------------------------------
It would be easy to attach a value per visit and a cost per email and report money.
It would also be arbitrary -- Hillstrom records neither, and the conclusion would
follow from whatever numbers we invented. So the headline is **incremental outcome per
thousand contacts**, which needs no assumptions, and the economics enter separately as
a *sweep* over break-even thresholds (`abstention_sweep`). Anywhere a single price
appears it is a stated assumption, never a finding.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from keel.benchmarks.datasets import RCT


@dataclass
class PolicyResult:
    name: str
    n_targeted: int
    budget_fraction: float
    uplift_per_contact: float
    """Estimated change in outcome per targeted customer. Negative means harm."""
    incremental_outcome: float
    """Total outcome change if the selected set were treated."""
    ci_low: float
    ci_high: float
    """Bootstrap 95% interval on `incremental_outcome`."""

    @property
    def per_1000(self) -> float:
        return 1000.0 * self.uplift_per_contact

    @property
    def significant(self) -> bool:
        return self.ci_low > 0 or self.ci_high < 0


def uplift_of_set(t: np.ndarray, y: np.ndarray, selected: np.ndarray) -> float:
    """Estimated treatment effect within a selected subgroup.

    Returns NaN when either arm is empty inside the selection -- with no control
    counterpart there is nothing to compare against, and returning 0 would quietly
    understate rather than flag the gap.
    """
    st, sc = selected & (t == 1), selected & (t == 0)
    if st.sum() == 0 or sc.sum() == 0:
        return float("nan")
    return float(y[st].mean() - y[sc].mean())


def top_k_mask(scores: np.ndarray, k: int) -> np.ndarray:
    mask = np.zeros(len(scores), dtype=bool)
    if k > 0:
        mask[np.argsort(-scores, kind="stable")[:k]] = True
    return mask


def evaluate_policy(
    name: str,
    scores: np.ndarray,
    rct: RCT,
    budget_fraction: float,
    n_boot: int = 400,
    seed: int = 0,
) -> PolicyResult:
    """Estimate what a top-k policy would have achieved, with a bootstrap interval."""
    n = len(rct)
    k = int(round(budget_fraction * n))
    selected = top_k_mask(scores, k)
    t, y = rct.treatment, rct.outcome

    point = uplift_of_set(t, y, selected)

    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    idx_all = np.arange(n)
    for b in range(n_boot):
        idx = rng.choice(idx_all, size=n, replace=True)
        boots[b] = uplift_of_set(t[idx], y[idx], selected[idx])
    boots = boots[np.isfinite(boots)]

    lo, hi = (np.nan, np.nan) if boots.size == 0 else np.percentile(boots, [2.5, 97.5])

    return PolicyResult(
        name=name,
        n_targeted=int(selected.sum()),
        budget_fraction=budget_fraction,
        uplift_per_contact=point,
        incremental_outcome=point * selected.sum(),
        ci_low=lo * selected.sum(),
        ci_high=hi * selected.sum(),
    )


def qini_curve(scores: np.ndarray, rct: RCT, n_points: int = 21) -> pd.DataFrame:
    """The standard Qini curve: cumulative incremental outcome as budget grows.

    Reported for comparability with the uplift literature. Note its limitation --
    it assumes you rank and treat the top slice, with no budget constraint, no
    heterogeneous costs, and crucially **no option to abstain**. That last omission
    is why we also report realised outcome under a budget.
    """
    n = len(rct)
    rows = []
    for frac in np.linspace(0, 1, n_points):
        k = int(round(frac * n))
        sel = top_k_mask(scores, k)
        u = uplift_of_set(rct.treatment, rct.outcome, sel)
        rows.append({
            "budget_fraction": frac,
            "n_targeted": k,
            "uplift_per_contact": u,
            "incremental_outcome": (u * k) if np.isfinite(u) else np.nan,
        })
    return pd.DataFrame(rows)


def qini_coefficient(curve: pd.DataFrame) -> float:
    """Area between the Qini curve and the random-targeting diagonal.

    Positive means the ranking beats random; negative means it is worse than random,
    which is the outcome this whole project turns on.
    """
    x = curve["budget_fraction"].to_numpy()
    y = curve["incremental_outcome"].to_numpy()
    if not np.isfinite(y).any():
        return float("nan")
    total = y[np.isfinite(y)][-1]
    diagonal = x * total
    ok = np.isfinite(y)
    return float(np.trapezoid(y[ok] - diagonal[ok], x[ok]))


def abstention_sweep(
    scores: np.ndarray,
    rct: RCT,
    thresholds: np.ndarray | None = None,
) -> pd.DataFrame:
    """Treat only where estimated uplift exceeds a break-even threshold.

    A sweep rather than a single price, because the break-even point depends on
    economics Hillstrom does not record. Picking one number would make the
    conclusion a function of our own assumption.

    Only meaningful for uplift models: an outcome propensity is not on the same
    scale as a treatment effect, so thresholding it is not a break-even rule.
    """
    if thresholds is None:
        thresholds = np.quantile(scores, np.linspace(0.0, 0.95, 20))

    rows = []
    for thr in thresholds:
        sel = scores > thr
        u = uplift_of_set(rct.treatment, rct.outcome, sel)
        rows.append({
            "threshold": float(thr),
            "n_targeted": int(sel.sum()),
            "share_targeted": float(sel.mean()),
            "uplift_per_contact": u,
            "incremental_outcome": (u * sel.sum()) if np.isfinite(u) else np.nan,
        })
    return pd.DataFrame(rows)


def random_baseline(
    rct: RCT, budget_fraction: float, n_repeats: int = 200, seed: int = 0
) -> PolicyResult:
    """Random targeting, averaged over many draws.

    The single most important comparator in this project. A single random draw is
    far too noisy to compare against, so it is averaged -- and averaging also makes
    it the *fair* version of random rather than a lucky or unlucky one.
    """
    rng = np.random.default_rng(seed)
    n = len(rct)
    k = int(round(budget_fraction * n))

    vals = []
    for _ in range(n_repeats):
        sel = top_k_mask(rng.random(n), k)
        u = uplift_of_set(rct.treatment, rct.outcome, sel)
        if np.isfinite(u):
            vals.append(u)

    vals = np.asarray(vals)
    lo, hi = np.percentile(vals, [2.5, 97.5]) if vals.size else (np.nan, np.nan)
    point = float(vals.mean()) if vals.size else float("nan")

    return PolicyResult(
        name="random",
        n_targeted=k,
        budget_fraction=budget_fraction,
        uplift_per_contact=point,
        incremental_outcome=point * k,
        ci_low=lo * k,
        ci_high=hi * k,
    )
