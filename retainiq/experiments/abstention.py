"""The Phase 4 gate: does abstention beat ranking on realised money at small n?

The question Section 8 of the paper poses, stated so it can fail:

    Does Equation 8, with *estimated* posteriors, beat both ranking and doing nothing
    on realised money at n in [250, 2000] -- and on what proportion of draws?

Three things make this an honest test rather than a demonstration.

**Ground truth is never given to any policy.** The Phase 0 precursor (209 contacts
beating 718) used oracle effects and is an upper bound on what an estimated rule can
do, not evidence for one. Here every policy sees only what a business would see.

**The comparator is the strong version.** It ranks by expected money from the *same*
estimator and the same customer values, and fills the budget. So the comparison isolates
**abstention** -- the decision to spend less than the budget -- and not the fact that
customers are worth different amounts, which would flatter us for a reason that has
nothing to do with the contribution.

**Two rules are recorded on every draw, and only one of them is the result** (D-057,
D-069). `CORRECTED` converts the log-odds effect to a change in probability before
multiplying by money. `LEGACY` is the rule as Phase 4 first ran it, which multiplied the
log-odds effect by money directly. `LEGACY` is kept so that D-054, D-055 and D-056 stay
reproducible, and it is printed second, under a heading that says what it is. For a
while this module printed only `LEGACY`, under the Phase 4 heading, after every document
had moved to quoting `CORRECTED`.

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


@dataclass(frozen=True)
class Rule:
    """A decision rule and the comparator it is scored against, as `run_once` names them."""

    name: str
    ours: str
    comparator: str


#: The rule as it has stood since D-057: both policies decide on a posterior over money.
#: This is the Phase 4 result.
CORRECTED = Rule("corrected", ours="abstention_money", comparator="top_k_money")

#: The rule as Phase 4 first ran it (D-054): a log-odds effect multiplied by money as
#: though it were a probability difference. Kept for reproducibility. Not a result.
LEGACY = Rule("legacy", ours="abstention", comparator="top_k_expected_value")


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


@dataclass
class Pilot:
    """One simulated business, cut into what a policy may learn from and what it is scored on.

    `train` is the randomised pilot: `treated` says who got the offer and `churned` is the
    outcome observed for the arm each customer was in. `test` carries both potential
    outcomes and is only ever used to score a decision.
    """

    train: pd.DataFrame
    test: pd.DataFrame
    treated: np.ndarray
    churned: np.ndarray
    rng: np.random.Generator
    """The draw's generator, positioned after the split and the assignment, so that a
    caller continuing the draw uses the same random numbers as before this was factored
    out of `run_once`."""


def draw_pilot(
    n_customers: int,
    seed: int,
    decision_month: int = 6,
    horizon: int = 6,
    train_fraction: float = 0.5,
    config: SimConfig | None = None,
    offer: Offer = REFERENCE_OFFER,
) -> Pilot | None:
    """Simulate one business and run its pilot. None when the draw is unusable.

    Shared by every experiment that compares decision rules, so that they are compared
    on the same customers, the same assignment and the same outcomes (D-075).
    """
    cfg = config or SimConfig()
    sim = simulate(replace(cfg, n_customers=n_customers, n_months=24, seed=seed))
    frame = _experiment_frame(sim, decision_month, horizon, offer)
    if len(frame) < 60:
        return None

    rng = np.random.default_rng(seed + 7717)
    is_train = rng.random(len(frame)) < train_fraction
    train, test = frame[is_train], frame[~is_train]
    if len(train) < 30 or len(test) < 30 or train.empty:
        return None

    # The pilot: half the training customers were treated at random. Their observed
    # outcome is y1 if treated and y0 if not -- exactly what a real holdout yields.
    t_train = (rng.random(len(train)) < 0.5).astype(int)
    y_train = np.where(t_train == 1, train["y1"].to_numpy(), train["y0"].to_numpy())
    if len(np.unique(y_train)) < 2:
        return None
    return Pilot(train=train, test=test, treated=t_train, churned=y_train, rng=rng)


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
    pilot = draw_pilot(n_customers, seed, decision_month, horizon, train_fraction,
                       config, offer)
    if pilot is None:
        return {}
    train, test, rng = pilot.train, pilot.test, pilot.rng
    t_train, y_train = pilot.treated, pilot.churned

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


def summarise(frame: pd.DataFrame, rule: Rule) -> pd.DataFrame:
    """Win rate against the strong comparator, per size, under one decision rule.

    `rule` has no default on purpose. Which rule a table shows is the difference between
    the Phase 4 result and a superseded one, so every caller states it (D-069).

    The headline is `beats_topk` -- the proportion of draws on which abstention
    earned more than ranking-and-filling-the-budget did. Means are reported beside
    it, not instead of it.

    `abstain_positive` and `abstain_ties` must be read together. A draw where the rule
    treats nobody scores exactly zero, which is not `> 0` -- so a policy that correctly
    declines an unprofitable population is indistinguishable from one that loses money
    if only the first is reported. Separating them is what makes the safety property
    (D-054) measurable rather than merely asserted.
    """
    ours, comparator = rule.ours, rule.comparator
    rows = []
    for n, g in frame.groupby("n_customers"):
        wide = g.pivot(index="seed", columns="policy", values="value")
        treated = g.pivot(index="seed", columns="policy", values="n_treated")
        if ours not in wide or comparator not in wide:
            continue
        rows.append({
            "n_customers": n,
            "seeds": len(wide),
            "abstain_mean": wide[ours].mean(),
            "topk_mean": wide[comparator].mean(),
            "random_mean": wide.filter(like="random").mean(axis=1).mean(),
            "beats_topk": (wide[ours] > wide[comparator]).mean(),
            "beats_random": (wide[ours] > wide.filter(like="random").mean(axis=1)).mean(),
            "abstain_positive": (wide[ours] > 0).mean(),
            "abstain_ties": (wide[ours] == 0).mean(),
            "abstain_not_worse": (wide[ours] >= 0).mean(),
            "topk_positive": (wide[comparator] > 0).mean(),
            "treat_all_mean": wide["treat_all"].mean() if "treat_all" in wide else np.nan,
            "treat_all_positive": (
                (wide["treat_all"] > 0).mean() if "treat_all" in wide else np.nan
            ),
            "abstain_treated": treated[ours].mean(),
            "topk_treated": treated[comparator].mean(),
        })
    return pd.DataFrame(rows)


HEADINGS = {
    CORRECTED.name: (
        "PHASE 4 GATE -- abstention vs ranking, realised money, ground truth withheld",
        "Decision rule as corrected in D-057: both policies decide on money.",
    ),
    LEGACY.name: (
        "BEFORE THE D-057 CORRECTION -- the same draws, under the rule as Phase 4 first ran it",
        "A log-odds effect was multiplied by money. Kept so that D-054 to D-056 stay\n"
        "reproducible. These are not the Phase 4 result and should not be quoted as it.",
    ),
}


def report(summary: pd.DataFrame, rule: Rule, legend: bool = True) -> str:
    title, note = HEADINGS[rule.name]
    width = 102
    lines = [title, note, "=" * width]
    if summary.empty:
        # Never print an empty table under a heading: that reads as "nothing happened".
        lines.append(f"no draws recorded for {rule.ours!r} against {rule.comparator!r}")
        return "\n".join(lines)
    lines += [
        f"{'n':>6}{'seeds':>7}{'abstain':>10}{'ranking':>10}{'random':>10}"
        f"{'beats rank':>12}{'beats 0':>9}{'ties 0':>8}{'rank>0':>8}{'treated':>16}",
        "-" * width,
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"{int(r.n_customers):>6}{int(r.seeds):>7}{r.abstain_mean:>10,.0f}"
            f"{r.topk_mean:>10,.0f}{r.random_mean:>10,.0f}"
            f"{r.beats_topk:>12.0%}{r.abstain_positive:>9.0%}{r.abstain_ties:>8.0%}"
            f"{r.topk_positive:>8.0%}{r.abstain_treated:>7.0f} vs{r.topk_treated:>6.0f}"
        )
    lines.append("-" * width)
    draws = summary["seeds"].sum()
    wins = (summary["beats_topk"] * summary["seeds"]).sum()
    ours = (summary["abstain_mean"] * summary["seeds"]).sum() / draws
    theirs = (summary["topk_mean"] * summary["seeds"]).sum() / draws
    lines.append(
        f"all sizes: beats ranking on {wins:.0f} of {draws:.0f} draws ({wins / draws:.0%});"
        f" mean realised {ours:,.0f} vs {theirs:,.0f} for ranking"
    )
    if legend:
        lines.append(LEGEND)
    return "\n".join(lines)


LEGEND = (
        "beats rank = share of draws where abstention earned more than ranking.\n"
        "beats 0 / rank>0 = share of draws where the policy beat doing nothing.\n"
        "ties 0 = share of draws where abstention treated nobody and scored exactly zero;\n"
        "         read it with beats 0, or a rule that correctly declines looks like a loss.\n"
        "treated = customers contacted, abstention vs ranking, at the same budget cap."
)


def render(frame: pd.DataFrame) -> str:
    """Both rules from one sweep: the result first, the superseded rule second."""
    return "\n\n\n".join(
        report(summarise(frame, rule), rule, legend=rule is CORRECTED)
        for rule in (CORRECTED, LEGACY)
    )


if __name__ == "__main__":
    print(render(sweep()))
