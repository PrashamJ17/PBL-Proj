"""Holdout assignment and incrementality measurement (Phase 6).

Every claim this project makes about money rests on comparing what happened to what
would have happened. In simulation that comparison is free, because both potential
outcomes exist. In a real business it exists only if a randomised holdout was set aside
**before** the campaign ran, and kept.

This module is that discipline in code. It is deliberately the least clever thing in the
repository: three ideas, none of them novel, all of them load-bearing.

**Assignment is a deterministic hash, not a random draw.** `sha256(salt + customer_id)`
mapped to the unit interval. That makes membership reproducible without storing state,
stable when the customer list grows, and independent of row order -- three properties a
`random.shuffle` does not have. A customer who was in the holdout last month is in it
this month, which is what makes a longitudinal comparison mean anything.

**The ledger is append-only.** Once a customer is recorded as held out for an experiment,
nothing in the API can move them. The failure this prevents is the one that actually
happens in practice: a campaign under-performs, somebody quietly shrinks the holdout, and
the measurement silently becomes a comparison of self-selected groups. `HoldoutLedger`
raises rather than overwrite.

**Incrementality is a difference in means with an interval, not a save rate.** Save rate
among the treated is the number every retention vendor reports and it is uninterpretable:
it counts customers who would have stayed anyway. The estimator here is the difference in
retention between treated and held-out, priced in currency, with a confidence interval
that says how much of the result is noise.

The estimator is validated against SubSim's ground-truth effects in
`experiments/holdout_validation.py` (D-065), which also reports the **minimum detectable
effect** by holdout size -- the number a business needs before it agrees to give up
revenue to measurement.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

__all__ = [
    "assign_holdout",
    "HoldoutLedger",
    "Incrementality",
    "measure_incrementality",
    "minimum_detectable_effect",
    "required_holdout_size",
]


def assign_holdout(
    customer_ids, fraction: float = 0.10, salt: str = "retainiq-holdout-v1"
) -> np.ndarray:
    """Deterministic holdout membership. Returns a boolean mask.

    `sha256(salt + id)` scaled to [0, 1); a customer is held out when that value falls
    below `fraction`. Deterministic given the salt, so the same customer lands in the
    same arm on every run, in any process, without storing anything.

    Changing the salt reshuffles everybody, which is why the salt is versioned and
    belongs in the experiment record rather than in a caller's default argument.
    """
    if not 0.0 < fraction < 1.0:
        raise ValueError(f"fraction must be in (0, 1), got {fraction}")

    ids = pd.Series(list(customer_ids)).astype(str)
    if ids.duplicated().any():
        raise ValueError(
            f"{int(ids.duplicated().sum())} duplicate customer ids; holdout membership "
            "would be ambiguous. Deduplicate before assigning."
        )

    def u(cid: str) -> float:
        h = hashlib.sha256((salt + cid).encode("utf-8")).digest()
        # First 8 bytes as an unsigned integer, scaled to [0, 1).
        return int.from_bytes(h[:8], "big") / 2**64

    return np.array([u(c) < fraction for c in ids], dtype=bool)


@dataclass
class HoldoutLedger:
    """Append-only record of who was held out, for which experiment, and when.

    The guarantee is narrow and is the whole point: **a customer's arm cannot be changed
    once written.** Retention measurement fails in practice not because the statistics
    are hard but because the holdout erodes -- somebody adds a "just this once"
    exception, and by the time the results are read the two groups differ by more than
    the treatment.
    """

    records: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(
            columns=["experiment_id", "customer_id", "arm", "assigned_at"]
        )
    )

    def record(
        self,
        experiment_id: str,
        customer_ids,
        held_out: np.ndarray,
        assigned_at: pd.Timestamp | None = None,
    ) -> None:
        """Write assignments. Raises on any attempt to reassign an existing customer."""
        ids = pd.Series(list(customer_ids)).astype(str)
        held_out = np.asarray(held_out, dtype=bool)
        if len(ids) != len(held_out):
            raise ValueError("customer_ids and held_out must be the same length")

        new = pd.DataFrame({
            "experiment_id": experiment_id,
            "customer_id": ids.values,
            "arm": np.where(held_out, "holdout", "treated"),
            "assigned_at": assigned_at or pd.Timestamp.now(),
        })

        prior = self.records[self.records["experiment_id"] == experiment_id]
        if not prior.empty:
            clash = prior.merge(new, on="customer_id", suffixes=("_old", "_new"))
            moved = clash[clash["arm_old"] != clash["arm_new"]]
            if not moved.empty:
                raise ValueError(
                    f"refusing to reassign {len(moved)} customers already recorded in "
                    f"'{experiment_id}' (e.g. {moved['customer_id'].iloc[0]}). A holdout "
                    "that can be edited after the fact measures nothing."
                )
            new = new[~new["customer_id"].isin(prior["customer_id"])]

        # Guarded: concatenating onto an all-empty frame is deprecated in pandas and
        # would change the resulting dtypes.
        self.records = (
            new if self.records.empty
            else pd.concat([self.records, new], ignore_index=True)
        )

    def arm_of(self, experiment_id: str) -> pd.Series:
        """`customer_id -> arm` for one experiment."""
        r = self.records[self.records["experiment_id"] == experiment_id]
        return r.set_index("customer_id")["arm"]

    def summary(self) -> pd.DataFrame:
        if self.records.empty:
            return pd.DataFrame(columns=["experiment_id", "treated", "holdout"])
        g = self.records.groupby(["experiment_id", "arm"]).size().unstack(fill_value=0)
        for col in ("treated", "holdout"):
            if col not in g:
                g[col] = 0
        return g.reset_index()[["experiment_id", "treated", "holdout"]]


@dataclass
class Incrementality:
    """What the campaign earned, against what would have happened anyway."""

    n_treated: int
    n_holdout: int
    retention_treated: float
    retention_holdout: float
    lift: float
    """Difference in retention rate. Positive means the campaign helped."""
    lift_ci: tuple[float, float]
    incremental_value: float
    """Lift priced at mean customer value, minus the cost of treating."""
    value_ci: tuple[float, float]
    cost: float
    p_value: float

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05

    @property
    def verdict(self) -> str:
        if self.n_holdout < 30 or self.n_treated < 30:
            return "TOO SMALL — not enough customers in one arm to conclude anything"
        if not self.significant:
            return "NOT DISTINGUISHABLE FROM ZERO — the interval includes no effect"
        return "POSITIVE" if self.lift > 0 else "NEGATIVE — the campaign cost you money"


def measure_incrementality(
    retained: np.ndarray,
    held_out: np.ndarray,
    value: np.ndarray,
    cost_per_treated: float = 0.0,
    confidence: float = 0.95,
) -> Incrementality:
    """Difference in retention between treated and held-out, priced in currency.

    `retained` is the realised outcome (True if the customer is still subscribed at the
    horizon), `held_out` the arm, `value` what each customer is worth.

    Deliberately a difference in means rather than anything cleverer. Under randomised
    assignment it is unbiased for the average treatment effect, its variance is
    available in closed form, and every step is checkable by a business owner with a
    spreadsheet. A more efficient estimator that nobody can audit would be a poor trade
    for a measurement whose entire purpose is to be believed.
    """
    retained = np.asarray(retained, dtype=bool)
    held_out = np.asarray(held_out, dtype=bool)
    value = np.asarray(value, dtype=float)
    if not (len(retained) == len(held_out) == len(value)):
        raise ValueError("retained, held_out and value must be the same length")
    if np.any(value < 0):
        raise ValueError("customer value cannot be negative")

    n_t, n_h = int((~held_out).sum()), int(held_out.sum())
    if n_t == 0 or n_h == 0:
        raise ValueError(
            f"need both arms to measure anything (treated={n_t}, holdout={n_h}). "
            "Without a holdout there is no counterfactual and no incrementality."
        )

    p_t = float(retained[~held_out].mean())
    p_h = float(retained[held_out].mean())
    lift = p_t - p_h

    # Two-proportion standard error. Wald is adequate here and is what a reader can
    # reproduce; the arms are large enough that an exact interval would not change a
    # decision, and the CI is reported precisely so nobody over-reads a point estimate.
    se = float(np.sqrt(p_t * (1 - p_t) / n_t + p_h * (1 - p_h) / n_h))
    z = stats.norm.ppf(0.5 + confidence / 2)
    lo, hi = lift - z * se, lift + z * se

    mean_value = float(value.mean())
    total_cost = cost_per_treated * n_t
    incremental_value = lift * mean_value * n_t - total_cost

    p = 2 * (1 - stats.norm.cdf(abs(lift / se))) if se > 0 else 1.0

    return Incrementality(
        n_treated=n_t,
        n_holdout=n_h,
        retention_treated=p_t,
        retention_holdout=p_h,
        lift=lift,
        lift_ci=(lo, hi),
        incremental_value=incremental_value,
        value_ci=(lo * mean_value * n_t - total_cost, hi * mean_value * n_t - total_cost),
        cost=total_cost,
        p_value=float(p),
    )


def minimum_detectable_effect(
    n_total: int,
    holdout_fraction: float = 0.10,
    baseline_retention: float = 0.80,
    power: float = 0.80,
    alpha: float = 0.05,
) -> float:
    """Smallest retention lift a holdout of this size could detect.

    The question a business actually asks before agreeing to withhold revenue from a
    fraction of its customers: *what would I be able to learn?* Standard two-proportion
    power calculation.

    This is the number that makes the small-sample problem concrete. At the scale this
    project targets, the MDE is frequently larger than any plausible treatment effect,
    which means the honest answer to "should we run a holdout" is sometimes "not at this
    size, and here is the size you would need".
    """
    if not 0.0 < holdout_fraction < 1.0:
        raise ValueError("holdout_fraction must be in (0, 1)")
    n_h = n_total * holdout_fraction
    n_t = n_total - n_h
    if n_h < 1 or n_t < 1:
        return float("inf")

    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    p = baseline_retention
    var = p * (1 - p) * (1 / n_t + 1 / n_h)
    return float((z_a + z_b) * np.sqrt(var))


def required_holdout_size(
    effect: float,
    holdout_fraction: float = 0.10,
    baseline_retention: float = 0.80,
    power: float = 0.80,
    alpha: float = 0.05,
) -> int:
    """Total customers needed to detect `effect` at the given power. Inverse of the above."""
    if effect <= 0:
        raise ValueError("effect must be positive")
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    p = baseline_retention
    f = holdout_fraction
    # effect = (z_a+z_b) sqrt( p(1-p) (1/((1-f)N) + 1/(fN)) )  ->  solve for N
    n = p * (1 - p) * (1 / (1 - f) + 1 / f) * ((z_a + z_b) / effect) ** 2
    return int(np.ceil(n))
