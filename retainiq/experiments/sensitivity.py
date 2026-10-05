"""Why the Phase 4 gate failed: a sensitivity, not a recalibration.

Phase 4 (D-054) found that abstention beats ranking on 65-80% of draws (93% once the rule
was corrected, D-057) but never beats doing nothing. This module asks *why*, and the
answer turns out to be arithmetic rather than decision theory.

Treating customer *i* pays iff ``-tau_i * CLV_i > cost_i``, so the break-even effect
size is ``cost_i / CLV_i``. Under the calibrated simulator and the reference offer that
threshold is **0.040** against a mean effect of **0.010** -- a factor of four. Only 5.8%
of customers are worth treating *at all*. No decision rule can profit from a population
where the intervention is, on average, four times too weak to pay for itself: the best
achievable policy is close to treating nobody, which is exactly what the abstention rule
converges to as alpha tightens.

Two axes are swept, and the distinction between them matters:

**Effect size** (`effect_size_sensitivity`) is the axis requested, and it is the *weaker*
of the two, for a reason that must be stated rather than buried. Raising
`saveability_scale` while holding `salience_scale` fixed does not merely make the offer
better -- it dilutes the sleeping-dog mechanism, which falls from 26.6% of customers at
the default to 1.5% at `saveability_scale = -12`. A setting where the gate passes because
sleeping dogs no longer exist is a setting where this project's thesis does not apply.
The sweep therefore reports the sleeping-dog share in every row, and flags the rows that
leave the calibration band of invariant 4.

**Offer choice** (`offer_sensitivity`) is the stronger axis and costs nothing, because
the ladder already exists. Phase 4 was run on `discount_20_3mo`, whose 32-unit cost is
the *most expensive rung the ladder has bar one*. `feature_nudge` costs 0.10 and clears
break-even for 70% of customers. Nothing is being tuned here: the ladder was defined in
Phase 0 and is unchanged. The comparator was chosen badly, and this axis says so.

**Nothing here changes a default.** `SimConfig` and `REFERENCE_OFFER` are untouched; the
Phase 4 headline stands as reported. This module measures how far the conclusion travels.

**Every table is printed under two decision rules** (D-057, D-069, D-070). `CORRECTED`
decides on money and is printed first. `LEGACY` multiplied a log-odds effect by money; it
is the rule D-055 and D-056 were run on, so it is printed second, under a heading that
says so, and its figures are unchanged. Each draw records both rules, so one sweep serves
both tables. The numbered findings below were written from the `LEGACY` tables; D-070
records which of them the `CORRECTED` tables bear out.

What it found (D-055, D-056), and what the corrected rule does to each (D-070):

1. Under `LEGACY` the gate *does* flip -- ``saveability_scale = -5`` beats do-nothing on
   57% of draws -- but only at the very edge of the calibration band, and by then the
   sleeping-dog share has fallen from 27% to 7% and blanket treatment wins 68% of draws on
   its own. Under `CORRECTED` it does not flip inside the band at all: 40% at -5, and
   above half only at -8, which is outside it.
2. **The two win rates move in opposite directions.** Beating ranking and beating
   inaction are not jointly achievable anywhere in the swept range: at no setting is
   either rate significantly above chance while the other also is. The gate as written
   asked for two things that trade off, so it could not have been passed. True under
   both rules (`CORRECTED`: 90% falling to 48%, against 5% rising to 68%).
3. A minimax-regret reading of (2) was proposed and then **failed** its out-of-sample
   test on the ladder (D-056). It is recorded as refuted, not quietly dropped. It was
   formed on the effect-size axis and tested on the ladder, which is why regret is
   printed by axis. Under `CORRECTED` it fails on the ladder too, and would not have been
   suggested in the first place: ranking has the lower maximum regret on the effect-size
   axis.
4. That failure localised a real defect: **a fixed alpha ignores payoff asymmetry.**
   `alpha_by_offer` shows the best threshold moving from 0.49 on a 0.10 nudge to 0.05 on
   a 33-unit discount, under both rules. This is the Phase 5 correction, and it is *not*
   applied here -- diagnosing a flaw and fixing it in the same commit is how a
   sensitivity turns into the tuning it was supposed to guard against.
"""

from __future__ import annotations

from dataclasses import replace
from functools import cache

import numpy as np
import pandas as pd

from retainiq.experiments.abstention import CORRECTED, LEGACY, Rule, summarise, sweep
from retainiq.sim import SimConfig, simulate
from retainiq.sim.counterfactual import LADDER, REFERENCE_OFFER, Offer, potential_outcomes

#: Bounds of the calibration gate on mean tau (invariant 4). Rows outside this band
#: describe a simulator this project has not calibrated and does not stand behind.
TAU_BAND = (-0.05, 0.0)

#: Effect sizes to sweep. The first is the default; the last two deliberately exit the
#: band so the reader can see what buying the gate would actually cost.
SCALES = (-2.0, -3.0, -4.0, -5.0, -6.0, -8.0)


@cache
def _sweep(sizes, seeds, alpha=0.30, budget=0.30, config=None, offer=REFERENCE_OFFER):
    """`sweep`, remembered for the length of the run.

    A sweep is a deterministic function of these arguments and every draw records both
    decision rules, so the second rule's tables cost nothing. The regret matrix and the
    alpha table also revisit settings the two axes have already run. Callers read the
    frame and must not modify it.
    """
    return sweep(sizes=sizes, seeds=seeds, alpha=alpha, budget=budget,
                 config=config, offer=offer)


def economics(
    n_customers: int = 5000,
    seed: int = 7,
    config: SimConfig | None = None,
    offer: Offer = REFERENCE_OFFER,
    decision_month: int = 6,
    horizon: int = 6,
) -> dict[str, float]:
    """The arithmetic that decides whether *any* policy can profit here.

    `pays_for` is the ceiling: the share of customers an oracle -- one that knew every
    tau_i exactly -- would choose to treat. A gate that requires beating do-nothing is
    asking the estimated policy to find profit inside that share.
    """
    cfg = replace(config or SimConfig(), n_customers=n_customers, seed=seed)
    po = potential_outcomes(simulate(cfg), decision_month=decision_month,
                            horizon=horizon, offer=offer)
    break_even = po["offer_cost"] / po["clv"]
    oracle = po["value_of_treating"] > 0
    return {
        "mean_tau": float(po["tau_true"].mean()),
        "p10_tau": float(po["tau_true"].quantile(0.10)),
        "break_even": float(break_even.median()),
        "pays_for": float(oracle.mean()),
        "sleeping_dog": float((po["tau_true"] > 0).mean()),
        "mean_value": float(po["value_of_treating"].mean()),
        "oracle_value": float(po.loc[oracle, "value_of_treating"].sum()),
        "median_cost": float(po["offer_cost"].median()),
        "in_band": bool(TAU_BAND[0] <= po["tau_true"].mean() <= TAU_BAND[1]),
    }


def _gate(sizes, seeds, rule: Rule, config=None, offer=REFERENCE_OFFER, alpha=0.30,
          budget=0.30):
    """Run the Phase 4 gate under one setting and reduce it to the two headline rates.

    `rule` has no default, for the reason given in `abstention.summarise` (D-069).
    """
    s = summarise(_sweep(tuple(sizes), seeds, alpha=alpha, budget=budget,
                         config=config, offer=offer), rule)
    cols = ["beats_topk", "beats_nothing", "ties_nothing", "treat_all_wins",
            "abstain_mean", "treated"]
    if s.empty:
        return dict.fromkeys(cols, np.nan)
    return {
        "beats_topk": float(s["beats_topk"].mean()),
        "beats_nothing": float(s["abstain_positive"].mean()),
        # Treating nobody scores exactly zero. Without this column a rule that
        # correctly declines is scored identically to one that loses money.
        "ties_nothing": float(s["abstain_ties"].mean()),
        # The comparator that matters when the offer is nearly free: if blanket
        # treatment already wins, the decision layer is solving a problem nobody has.
        "treat_all_wins": float(s["treat_all_positive"].mean()),
        "abstain_mean": float(s["abstain_mean"].mean()),
        "treated": float(s["abstain_treated"].mean()),
    }


def effect_size_sensitivity(
    rule: Rule,
    scales: tuple[float, ...] = SCALES,
    sizes: tuple[int, ...] = (500, 1000),
    seeds: int = 20,
) -> pd.DataFrame:
    """Axis 1: does the gate pass if the offer simply works better?

    Reports `sleeping_dog` beside the win rates because the two move together. A row
    that passes the gate at 3% sleeping dogs has not vindicated the decision rule; it
    has removed the problem the decision rule addresses.
    """
    rows = []
    for s in scales:
        cfg = SimConfig()
        cfg = replace(cfg, intervention=replace(cfg.intervention, saveability_scale=s))
        econ = economics(config=cfg)
        rows.append({"saveability_scale": s, "is_default": s == -2.0,
                     **econ, **_gate(sizes, seeds, rule, config=cfg)})
    return pd.DataFrame(rows)


def offer_sensitivity(
    rule: Rule,
    sizes: tuple[int, ...] = (500, 1000),
    seeds: int = 20,
) -> pd.DataFrame:
    """Axis 2: does the gate pass on a rung the business would actually pull first?

    The ladder is ordered by margin cost (plan section 5.1), and its whole premise is
    that discounts are the last resort. Phase 4 evaluated the last resort.
    """
    rows = []
    for off in LADDER:
        econ = economics(offer=off)
        rows.append({"offer": off.name, "rung": off.rung,
                     "is_phase4_default": off.name == REFERENCE_OFFER.name,
                     **econ, **_gate(sizes, seeds, rule, offer=off)})
    return pd.DataFrame(rows)


def policies_for(rule: Rule) -> list[str]:
    """The policies compared under one rule, in the order they are reported.

    The three baselines do not depend on the rule; the ranking and abstention policies
    do. The two rules' policies are never mixed in one comparison.
    """
    return ["do_nothing", "treat_all", "random_30pct", rule.comparator, rule.ours]


def regret_matrix(settings: list[tuple[str, dict]], rule: Rule, sizes=(500, 1000),
                  seeds=20) -> pd.DataFrame:
    """Mean realised value of every policy under every setting, plus regret.

    Regret is normalised within a setting -- ``(best - this) / (best - worst)`` -- because
    absolute values are not comparable across settings whose effect sizes differ by a
    factor of eight. `max_regret` is then the honest summary: how bad is this policy when
    you guess the regime wrong?

    This exists because it *falsified* a hypothesis (D-056). Abstention has the lowest max
    regret across the effect-size axis, which suggested it was a minimax-regret hedge; the
    offer ladder, which was not used to form that idea, refused to reproduce it.
    """
    names = policies_for(rule)
    rows = []
    for name, kw in settings:
        frame = _sweep(tuple(sizes), seeds, **kw)
        per = frame.groupby("policy")["value"].mean()
        rows.append({"setting": name, **{p: float(per.get(p, np.nan)) for p in names}})
    out = pd.DataFrame(rows)
    vals = out[names]
    best, worst = vals.max(axis=1), vals.min(axis=1)
    spread = (best - worst).clip(lower=1e-9)
    for p in names:
        out[f"regret_{p}"] = (best - out[p]) / spread
    return out


def alpha_by_offer(rule: Rule, alphas=(0.05, 0.30, 0.49), sizes=(500, 1000),
                   seeds=20) -> pd.DataFrame:
    """Which confidence threshold is best on each rung of the ladder?

    The Phase 4 rule fixes alpha at 0.30 for every decision. If the best alpha *moves*
    with the offer, that constant is wrong by construction -- and it does move: the cheap
    rungs want alpha near 0.5 (act on the expected value; being wrong costs 0.10) and the
    discounts want 0.05 (being wrong costs 33). `pause_offer` is the case that shows the
    driver is not cost but payoff asymmetry: it is cheap yet wants 0.05, because its mean
    tau is positive and treating is harmful on average.
    """
    rows = []
    for off in LADDER:
        row = {"offer": off.name, "rung": off.rung, "cost": float(off.contact_cost
               + off.discount_pct * np.exp(4.0) * off.discount_months)}
        for a in alphas:
            f = _sweep(tuple(sizes), seeds, alpha=a, offer=off)
            row[f"alpha_{a}"] = float(f.loc[f.policy == rule.ours, "value"].mean())
            row["treat_all"] = float(f.loc[f.policy == "treat_all", "value"].mean())
        vals = [row[f"alpha_{a}"] for a in alphas]
        # Every alpha ties when the sample is too small for any of them to act: the
        # rule abstains throughout and each scores exactly zero. `max` would silently
        # return the first alpha and report a preference that the data does not
        # contain, so say so instead.
        row["determinate"] = float(np.ptp(vals)) > 1e-9
        row["best_alpha"] = (max(alphas, key=lambda a: row[f"alpha_{a}"])
                             if row["determinate"] else np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


def _fmt(frame: pd.DataFrame, key: str, label: str, extra: str) -> list[str]:
    lines = [
        f"{label:>17}{'cost':>8}{'mean tau':>10}{'brkeven':>9}{'oracle':>8}"
        f"{'dogs':>7}{'>topk':>7}{'>zero':>7}{'=zero':>7}{'all>0':>7}{'treat':>7}  {extra}",
        "-" * 112,
    ]
    for _, r in frame.iterrows():
        flag = ""
        if not r["in_band"]:
            flag = "OUTSIDE calibration band"
        elif r.get("is_default") or r.get("is_phase4_default"):
            flag = "<- Phase 4 ran here"
        lines.append(
            f"{str(r[key]):>17}{r.median_cost:>8.2f}{r.mean_tau:>+10.4f}"
            f"{r.break_even:>9.4f}{r.pays_for:>8.0%}{r.sleeping_dog:>7.0%}"
            f"{r.beats_topk:>7.0%}{r.beats_nothing:>7.0%}{r.ties_nothing:>7.0%}"
            f"{r.treat_all_wins:>7.0%}{r.treated:>7.0f}  {flag}"
        )
    return lines


HEADINGS = {
    CORRECTED.name: (
        "PHASE 4 SENSITIVITY -- where does the gate pass, and what does passing cost?",
        "Decision rule as corrected in D-057: both policies decide on money.",
    ),
    LEGACY.name: (
        "BEFORE THE D-057 CORRECTION -- the same sweeps, under the rule D-055 and D-056 "
        "were run on",
        "A log-odds effect was multiplied by money. Kept so that D-055 and D-056 stay\n"
        "reproducible. Where these tables differ from the ones above, the ones above are "
        "the result.",
    ),
}

LEGEND = [
    "oracle = share a policy knowing every tau exactly would treat. The CEILING.",
    "dogs   = share with tau > 0. On axis 1 this is the mechanism being traded",
    "         away to buy a passing gate -- read it before believing any win.",
    ">topk  = beats ranking.   >zero = beats do-nothing.   =zero = treats NOBODY",
    "         and ties, which is the safety property working, not a loss.",
    "all>0  = blanket treatment already profits. Where this is high the decision",
    "         layer is solving a problem the business does not have.",
    "The first six columns are computed from ground truth and do not depend on the rule.",
]


def report(effect: pd.DataFrame, offers: pd.DataFrame, rule: Rule, legend: bool = True) -> str:
    """The sensitivity, stated so a referee can see what it does and does not license."""
    title, note = HEADINGS[rule.name]
    out = [
        title,
        note,
        "=" * 108,
        "",
        "AXIS 1: EFFECT SIZE (saveability_scale). Reference offer; cost held fixed.",
        "",
    ]
    out += _fmt(effect, "saveability_scale", "sav_scale", "")
    out += [
        "",
        "AXIS 2: OFFER CHOICE. Default calibration; the Phase 0 ladder, unmodified.",
        "",
    ]
    out += _fmt(offers, "offer", "offer", "")
    if legend:
        out += ["", "=" * 112, *LEGEND]
    return "\n".join(out)


def block(rule: Rule, scales=SCALES, sizes=(500, 1000), seeds=20,
          alphas=(0.05, 0.30, 0.49)) -> str:
    """Everything this module prints, under one decision rule."""
    out = [report(effect_size_sensitivity(rule, scales, sizes, seeds),
                  offer_sensitivity(rule, sizes, seeds), rule, legend=rule is CORRECTED)]
    out.append(f"\n\nREGRET BY POLICY, {rule.name} rule "
               "(normalised within setting; max is the summary)")
    out.append("=" * 112)
    rm = regret_matrix(_regret_settings(scales), rule, sizes, seeds)
    ranked = sorted(policies_for(rule), key=lambda q: rm[f"regret_{q}"].max())
    for p in ranked:
        col = rm[f"regret_{p}"]
        out.append(f"  {p:>22}   max {col.max():>6.1%}   mean {col.mean():>6.1%}")
    # The minimax-regret reading was formed on one axis and tested on the other (D-056),
    # so the maximum over both hides the result. Regret is normalised within a setting,
    # which makes a maximum over either subset of settings meaningful on its own.
    on_effect_axis = rm["setting"].str.startswith(EFFECT_PREFIX)
    out.append("")
    out.append(f"  {'maximum regret by axis':>22}   {'effect size':>11}   {'offer ladder':>12}")
    for p in ranked:
        col = rm[f"regret_{p}"]
        out.append(f"  {p:>22}   {col[on_effect_axis].max():>11.1%}"
                   f"   {col[~on_effect_axis].max():>12.1%}")
    out.append(f"\n\nBEST ALPHA BY RUNG, {rule.name} rule "
               "-- if this column moves, a constant alpha is wrong")
    out.append("=" * 112)
    out.append(alpha_by_offer(rule, alphas, sizes, seeds).to_string(index=False))
    return "\n".join(out)


def render(**kw) -> str:
    """Both rules from the same sweeps: the result first, the superseded rule second."""
    return ("\n\n\n" + "#" * 112 + "\n").join(block(rule, **kw) for rule in (CORRECTED, LEGACY))


#: Prefix of the effect-size settings' names, which is how the two axes are told apart.
EFFECT_PREFIX = "sav="


def _regret_settings(scales=SCALES) -> list[tuple[str, dict]]:
    """The two axes as `regret_matrix` settings: effect size, then the ladder."""
    out = []
    for s in scales:
        cfg = SimConfig()
        cfg = replace(cfg, intervention=replace(cfg.intervention, saveability_scale=s))
        out.append((f"{EFFECT_PREFIX}{s}", {"config": cfg}))
    return out + [(o.name, {"offer": o}) for o in LADDER]


if __name__ == "__main__":
    print(render())
