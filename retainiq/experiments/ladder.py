"""The Phase 5 gate: is choosing *which* offer worth more than choosing *whether*?

Phase 4 asked whether a rule could pick the right customers for a fixed offer, and D-055
showed why that question is nearly degenerate: with the offer held fixed, the answer is
almost always "everyone" or "nobody". This asks the question the ladder was built for --
match a rung to a customer -- and it is a harder test than Phase 4's in two deliberate
ways.

**The pilot is split K + 1 ways.** Effects must be learned per rung from randomised arms,
because the simulator's `saveability_multiplier` is oracle knowledge a real business does
not have. At n = 500 that leaves roughly 35 customers per arm.

**The comparator is chosen with hindsight.** `best_uniform_rung` evaluates every rung on
the *realised* outcomes of the evaluation set and keeps the best one. No real business
could do that -- it requires knowing the answer -- and the optimiser is given no such
advantage. If the optimiser beats it, per-customer matching is worth something beyond
picking a good default offer. If it does not, the honest recommendation to a business is
to pick one good rung and skip the machine learning, and this experiment exists to say so
if that is what the numbers show.

Realised value uses SubSim's paired potential outcomes under common random numbers, so
`y0` is shared across rungs and `(y0 - y1_k)` is the true counterfactual difference for
the rung actually chosen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from retainiq.experiments.abstention import FEATURES
from retainiq.policy.ladder import ABSTAIN, LadderOptimiser
from retainiq.sim import SimConfig, simulate
from retainiq.sim.counterfactual import LADDER, potential_outcomes

#: Risk-aversion settings swept. 0 is risk-neutral expected value; larger values demand
#: the expected gain exceed a multiple of its own uncertainty (D-058).
LAMBDAS = (0.0, 0.5, 1.0)


def _multi_arm_frame(sim, decision_month: int, horizon: int, seed: int) -> pd.DataFrame:
    """One row per customer with `y1` and cost for **every** rung.

    Common random numbers mean `y0` is shared, so the rungs are directly comparable
    for the same person -- the property that makes an oracle over rungs well defined.
    """
    frames = []
    for k, off in enumerate(LADDER):
        po = potential_outcomes(sim, decision_month=decision_month, horizon=horizon,
                                offer=off, seed=seed)
        frames.append(po[["customer_id", "y1", "offer_cost", "tau_true"]]
                      .rename(columns={"y1": f"y1_{k}", "offer_cost": f"cost_{k}",
                                       "tau_true": f"tau_{k}"}))
    base = potential_outcomes(sim, decision_month=decision_month, horizon=horizon,
                              offer=LADDER[0], seed=seed)[["customer_id", "y0", "clv"]]
    out = base
    for f in frames:
        out = out.merge(f, on="customer_id", how="inner")
    snap = sim.snapshot(decision_month)[["customer_id", *FEATURES]]
    return out.merge(snap, on="customer_id", how="inner")


def _realised(frame: pd.DataFrame, rung: np.ndarray) -> float:
    """Money earned against doing nothing, for a per-customer rung assignment."""
    total = 0.0
    for k in range(len(LADDER)):
        m = rung == k
        if not m.any():
            continue
        g = frame[m]
        total += float(((g["y0"] - g[f"y1_{k}"]) * g["clv"] - g[f"cost_{k}"]).sum())
    return total


def run_once(
    n_customers: int,
    seed: int,
    risk_aversion: float = 0.0,
    budget: float | None = 0.30,
    decision_month: int = 6,
    horizon: int = 6,
    train_fraction: float = 0.5,
    pool: bool = True,
) -> dict[str, float] | None:
    """One business, one draw, one multi-arm pilot."""
    sim = simulate(SimConfig(n_customers=n_customers, n_months=24, seed=seed))
    frame = _multi_arm_frame(sim, decision_month, horizon, seed)
    if len(frame) < 120:
        return None

    rng = np.random.default_rng(seed + 4211)
    is_train = rng.random(len(frame)) < train_fraction
    train, test = frame[is_train], frame[~is_train]
    if len(train) < 70 or len(test) < 40:
        return None

    K = len(LADDER)
    # The randomised exploration phase: each pilot customer gets control or one rung.
    arm = rng.integers(0, K + 1, len(train))
    y_train = np.where(arm == 0, train["y0"].to_numpy(),
                       np.choose(np.clip(arm - 1, 0, K - 1),
                                 [train[f"y1_{k}"].to_numpy() for k in range(K)]))
    if len(np.unique(y_train)) < 2:
        return None

    Xtr, Xte = train[FEATURES], test[FEATURES]
    value = test["clv"].to_numpy()
    costs = np.column_stack([test[f"cost_{k}"].to_numpy() for k in range(K)])

    try:
        opt = LadderOptimiser(risk_aversion=risk_aversion, budget=budget,
                              pool_across_rungs=pool, seed=seed).fit(Xtr, arm, y_train, K)
    except ValueError:
        return None
    rec = opt.recommend(Xte, value, costs)

    out = {
        "do_nothing": 0.0,
        "optimiser": _realised(test, rec.rung),
        "n_treated": float(rec.n_treated),
        "n_abstain": float((rec.rung == ABSTAIN).sum()),
    }

    # Comparators. `uniform_k` applies one rung to everyone; the best of them is chosen
    # with hindsight and is therefore unbeatable by any honest method except by
    # matching rungs to people.
    uniform = [_realised(test, np.full(len(test), k)) for k in range(K)]
    out["best_uniform_hindsight"] = float(max(uniform))
    out["best_uniform_rung"] = float(int(np.argmax(uniform)))
    out["worst_uniform"] = float(min(uniform))

    # The comparator that actually matters commercially, because a business can do it:
    # measure each rung on the pilot, pick the winner, apply it to everyone. No model,
    # no per-customer estimate, no us. If the optimiser cannot beat this, the honest
    # product is a recommended default offer rather than a targeting engine.
    pilot = []
    for k in range(K):
        got = arm == k + 1
        ctrl = arm == 0
        if not got.any() or not ctrl.any():
            pilot.append(-np.inf)
            continue
        # Difference in means on the pilot, priced at the pilot's own average CLV.
        lift = train.loc[ctrl, "y0"].mean() - train.loc[got, f"y1_{k}"].mean()
        pilot.append(lift * train["clv"].mean() - train[f"cost_{k}"].mean())
    pilot_choice = int(np.argmax(pilot))
    out["uniform_from_pilot"] = (
        _realised(test, np.full(len(test), pilot_choice)) if np.isfinite(pilot[pilot_choice])
        else 0.0
    )
    out["pilot_chose_rung"] = float(pilot_choice)
    # A business that also allows itself to do nothing when the pilot says every rung
    # loses money -- the cheapest possible decision rule, and a real competitor.
    out["uniform_or_nothing"] = (
        out["uniform_from_pilot"] if max(pilot) > 0 else 0.0
    )

    # The oracle over rungs: knowing every tau, pick each customer's best action.
    per_rung_value = np.column_stack([
        (-test[f"tau_{k}"].to_numpy() * value - costs[:, k]) for k in range(K)
    ])
    orc = np.argmax(per_rung_value, axis=1)
    orc = np.where(per_rung_value[np.arange(len(test)), orc] > 0, orc, ABSTAIN)
    out["oracle_matched"] = _realised(test, orc)
    out["oracle_treated"] = float((orc != ABSTAIN).sum())
    return out


def sweep(
    sizes: tuple[int, ...] = (500, 1000, 2000),
    seeds: int = 15,
    lambdas: tuple[float, ...] = LAMBDAS,
    budget: float | None = 0.30,
) -> pd.DataFrame:
    rows = []
    for lam in lambdas:
        for n in sizes:
            for s in range(seeds):
                r = run_once(n, seed=1000 + s, risk_aversion=lam, budget=budget)
                if r is None:
                    continue
                rows.append({"lam": lam, "n_customers": n, "seed": s, **r})
    return pd.DataFrame(rows)


def report(frame: pd.DataFrame) -> str:
    lines = [
        "PHASE 5 GATE -- does matching a rung to a customer beat picking one good offer?",
        "=" * 104,
        f"{'lambda':>7}{'n':>7}{'optimiser':>11}{'pilot-pick':>12}{'hindsight':>11}"
        f"{'oracle':>10}{'>pilot':>8}{'>hind':>7}{'>zero':>7}{'treated':>9}",
        "-" * 104,
    ]
    for (lam, n), g in frame.groupby(["lam", "n_customers"]):
        lines.append(
            f"{lam:>7.1f}{int(n):>7}{g.optimiser.mean():>11,.0f}"
            f"{g.uniform_or_nothing.mean():>12,.0f}"
            f"{g.best_uniform_hindsight.mean():>11,.0f}{g.oracle_matched.mean():>10,.0f}"
            f"{(g.optimiser > g.uniform_or_nothing).mean():>8.0%}"
            f"{(g.optimiser > g.best_uniform_hindsight).mean():>7.0%}"
            f"{(g.optimiser > 0).mean():>7.0%}{g.n_treated.mean():>9.0f}"
        )
    lines += [
        "-" * 104,
        "pilot-pick = measure each rung on the pilot, apply the winner to EVERYONE, and",
        "             do nothing if none looked profitable. No model and no us. This is",
        "             the comparator that matters: it is what a business can actually do.",
        "hindsight  = best single rung chosen on the evaluation set itself. Unachievable;",
        "             included as an upper bound on 'pick one good offer'.",
        "oracle     = knows every tau and picks each customer's best rung. The ceiling.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(report(sweep()))
