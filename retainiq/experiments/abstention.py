"""The Phase 4 gate: does abstention beat ranking on realised money at small n?

The question Section 8 of the paper poses, stated so it can fail:

    Does Equation 8, with *estimated* posteriors, beat both ranking and doing nothing
    on realised money at n in [250, 2000] -- and on what proportion of draws?

Three things make this an honest test rather than a demonstration.

**Ground truth is never given to any policy.** The Phase 0 precursor (209 contacts
beating 718) used oracle effects and is an upper bound on what an estimated rule can
do, not evidence for one. Here every policy sees only what a business would see.

**The comparator is the strong version.** `top_k_expected_value` ranks by
`-tau_hat * V - c`, using the *same* estimator's point estimate and the same customer
values. So the comparison isolates **abstention** -- the decision to spend less than the
budget -- and not the fact that customers are worth different amounts, which would
flatter us for a reason that has nothing to do with the contribution.

**Reported as a win rate, not a mean** (D-023). A business gets one draw. A policy with
a good average and a wide spread is a gamble, and averaging conceals exactly the risk
this phase exists to address.

Realised value is computed from SubSim's paired potential outcomes under common random
numbers, so `(y0 - y1)` is the actual counterfactual difference for that customer rather
than an estimate of it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from retainiq.models.uplift import AbstentionPolicy, HierarchicalCATE
from retainiq.models.uplift.abstention import (
    top_k_by_expected_money,
    top_k_by_point_estimate,
)
from retainiq.policy.economics import benefit_posterior
from retainiq.sim import SimConfig, simulate
from retainiq.sim.counterfactual import REFERENCE_OFFER, Offer, potential_outcomes

#: Features a real business would have at the decision point. Deliberately the same
#: observable set the Phase 0 kill test uses -- no latents, nothing post-treatment.
FEATURES = [
    "tenure_months", "mrr", "sessions_30d", "engagement_trend", "features_used",
    "support_tickets_90d", "unresolved_pain", "payment_failures_ltd",
    "seats_active_ratio", "champion_departed", "price_to_median",
]


@dataclass
class PolicyOutcome:
    name: str
    n_treated: int
    realised_value: float
    """Sum over treated of (y0 - y1) * CLV - cost. What actually happened."""
    n_harmed: int

    @property
    def share_treated(self) -> float:
        return self.n_treated / max(self.n_eligible, 1)

    n_eligible: int = 0


def _realised(po: pd.DataFrame, treat: np.ndarray) -> PolicyOutcome:
    """Score a treatment assignment against doing nothing (D-013)."""
    t = po[treat]
    if t.empty:
        return PolicyOutcome("", 0, 0.0, 0, len(po))
    value = float(((t["y0"] - t["y1"]) * t["clv"] - t["offer_cost"]).sum())
    harmed = int(((t["y0"] == 0) & (t["y1"] == 1)).sum())
    return PolicyOutcome("", int(len(t)), value, harmed, len(po))


def _experiment_frame(
    sim, decision_month: int, horizon: int, offer: Offer = REFERENCE_OFFER
) -> pd.DataFrame:
    """Join potential outcomes to the observable features a policy may use."""
    po = potential_outcomes(sim, decision_month=decision_month, horizon=horizon, offer=offer)
    snap = sim.snapshot(decision_month)[["customer_id", *FEATURES]]
    return po.merge(snap, on="customer_id", how="inner")


def run_once(
    n_customers: int,
    seed: int,
    alpha: float = 0.30,
    budget: float = 0.30,
    decision_month: int = 6,
    horizon: int = 6,
    train_fraction: float = 0.5,
    config: SimConfig | None = None,
    offer: Offer = REFERENCE_OFFER,
) -> dict[str, PolicyOutcome]:
    """One business, one draw. Every policy sees the same split.

    The training half stands for a randomised pilot the business already ran: it has
    treatment assignment and observed outcomes. The evaluation half is the population
    the policy must then decide about, and where realised value is measured.

    `config` and `offer` exist for the sensitivity analysis (D-055) and default to the
    calibrated simulator and the reference discount, so the Phase 4 headline numbers
    are reproduced exactly by calling this with neither.
    """
    cfg = config or SimConfig()
    sim = simulate(replace(cfg, n_customers=n_customers, n_months=24, seed=seed))
    frame = _experiment_frame(sim, decision_month, horizon, offer)
    if len(frame) < 60:
        return {}

    rng = np.random.default_rng(seed + 7717)
    is_train = rng.random(len(frame)) < train_fraction
    train, test = frame[is_train], frame[~is_train]
    if len(train) < 30 or len(test) < 30 or train.empty:
        return {}

    # The pilot: half the training customers were treated at random. Their observed
    # outcome is y1 if treated and y0 if not -- exactly what a real holdout yields.
    t_train = (rng.random(len(train)) < 0.5).astype(int)
    y_train = np.where(t_train == 1, train["y1"].to_numpy(), train["y0"].to_numpy())
    if len(np.unique(y_train)) < 2:
        return {}

    Xtr, Xte = train[FEATURES], test[FEATURES]
    value = test["clv"].to_numpy()
    cost = test["offer_cost"].to_numpy()

    model = HierarchicalCATE().fit(Xtr, t_train, y_train)
    post = model.posterior(Xte)

    out: dict[str, PolicyOutcome] = {}

    def record(name, mask):
        r = _realised(test, mask)
        out[name] = replace(r, name=name)

    record("do_nothing", np.zeros(len(test), dtype=bool))
    record("treat_all", np.ones(len(test), dtype=bool))

    k = int(round(budget * len(test)))
    rand_mask = np.zeros(len(test), dtype=bool)
    rand_mask[rng.choice(len(test), size=min(k, len(test)), replace=False)] = True
    record(f"random_{int(budget*100)}pct", rand_mask)

    # The strong comparator: same estimator, same values, ranks and fills the budget.
    record("top_k_expected_value",
           top_k_by_point_estimate(post.mean, value, cost, budget))

    # The contribution: same posterior, but permitted to spend less.
    record("abstention", AbstentionPolicy(alpha=alpha, budget=budget)
           .decide(post, value, cost).treat)
    record("abstention_no_budget", AbstentionPolicy(alpha=alpha)
           .decide(post, value, cost).treat)

    # --- the same two policies with the D-057 conversion corrected ------------
    # Both are corrected, not just ours: comparing a repaired policy against a
    # broken comparator would flatter abstention for a reason unrelated to it.
    money = benefit_posterior(model, Xte, value, cost, n_samples=500, seed=seed)
    record("top_k_money", top_k_by_expected_money(money.mean, budget))
    record("abstention_money", AbstentionPolicy(alpha=alpha, budget=budget)
           .decide_money(money).treat)
    record("abstention_money_no_budget", AbstentionPolicy(alpha=alpha)
           .decide_money(money).treat)

    return out


def sweep(
    sizes: tuple[int, ...] = (250, 500, 1000, 2000, 4000),
    seeds: int = 20,
    alpha: float = 0.30,
    budget: float = 0.30,
    config: SimConfig | None = None,
    offer: Offer = REFERENCE_OFFER,
) -> pd.DataFrame:
    """Every size, every seed. One row per (size, seed, policy)."""
    rows = []
    for n in sizes:
        for s in range(seeds):
            res = run_once(n, seed=1000 + s, alpha=alpha, budget=budget,
                           config=config, offer=offer)
            for name, r in res.items():
                rows.append({
                    "n_customers": n, "seed": s, "policy": name,
                    "value": r.realised_value, "n_treated": r.n_treated,
                    "n_harmed": r.n_harmed, "n_eligible": r.n_eligible,
                })
    return pd.DataFrame(rows)


def summarise(frame: pd.DataFrame) -> pd.DataFrame:
    """Win rate against the strong comparator, per size.

    The headline is `beats_topk` -- the proportion of draws on which abstention
    earned more than ranking-and-filling-the-budget did. Means are reported beside
    it, not instead of it.

    `abstain_positive` and `abstain_ties` must be read together. A draw where the rule
    treats nobody scores exactly zero, which is not `> 0` -- so a policy that correctly
    declines an unprofitable population is indistinguishable from one that loses money
    if only the first is reported. Separating them is what makes the safety property
    (D-054) measurable rather than merely asserted.
    """
    rows = []
    for n, g in frame.groupby("n_customers"):
        wide = g.pivot(index="seed", columns="policy", values="value")
        treated = g.pivot(index="seed", columns="policy", values="n_treated")
        if "abstention" not in wide or "top_k_expected_value" not in wide:
            continue
        rows.append({
            "n_customers": n,
            "seeds": len(wide),
            "abstain_mean": wide["abstention"].mean(),
            "topk_mean": wide["top_k_expected_value"].mean(),
            "random_mean": wide.filter(like="random").mean(axis=1).mean(),
            "beats_topk": (wide["abstention"] > wide["top_k_expected_value"]).mean(),
            "beats_random": (wide["abstention"] > wide.filter(like="random").mean(axis=1)).mean(),
            "abstain_positive": (wide["abstention"] > 0).mean(),
            "abstain_ties": (wide["abstention"] == 0).mean(),
            "abstain_not_worse": (wide["abstention"] >= 0).mean(),
            "topk_positive": (wide["top_k_expected_value"] > 0).mean(),
            "treat_all_mean": wide["treat_all"].mean() if "treat_all" in wide else np.nan,
            "treat_all_positive": (
                (wide["treat_all"] > 0).mean() if "treat_all" in wide else np.nan
            ),
            "abstain_treated": treated["abstention"].mean(),
            "topk_treated": treated["top_k_expected_value"].mean(),
        })
    return pd.DataFrame(rows)


def report(summary: pd.DataFrame) -> str:
    lines = [
        "PHASE 4 GATE -- abstention vs ranking, realised money, ground truth withheld",
        "=" * 96,
        f"{'n':>6}{'seeds':>7}{'abstain':>11}{'top-k':>11}{'random':>11}"
        f"{'beats topk':>12}{'abstain>0':>11}{'topk>0':>9}{'treated':>16}",
        "-" * 96,
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"{int(r.n_customers):>6}{int(r.seeds):>7}{r.abstain_mean:>11,.0f}"
            f"{r.topk_mean:>11,.0f}{r.random_mean:>11,.0f}"
            f"{r.beats_topk:>11.0%}{r.abstain_positive:>11.0%}{r.topk_positive:>9.0%}"
            f"{r.abstain_treated:>7.0f} vs{r.topk_treated:>6.0f}"
        )
    lines.append("-" * 96)
    lines.append(
        "beats topk = share of draws where abstention earned more than ranking.\n"
        "abstain>0 / topk>0 = share of draws where the policy beat doing nothing.\n"
        "treated = customers contacted, abstention vs top-k, at the same budget cap."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    s = summarise(sweep())
    print(report(s))
