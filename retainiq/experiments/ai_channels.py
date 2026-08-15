"""What happens when the actuator becomes almost free.

The commercial pitch for AI outreach is a cost argument: a human check-in call costs about
6 units of staff time, an AI voice call costs about 0.5, so make twelve times as many. The
same argument applies to LLM-written email against a templated blast.

**That argument optimises cost per contact, and cost per contact is not what causes the
harm.** The Phase 0 result is that contacting a dormant payer can *itself* trigger the
cancellation: the offer ladder carries a `salience_multiplier` precisely because an
intrusive channel wakes people who had half-forgotten they were paying. Making contact
cheaper does nothing to salience. If anything an unsolicited synthetic voice call is the
most salient channel available.

So the question this module asks is not "is AI outreach cheaper" -- it obviously is -- but:

    **At what salience does a nearly-free channel stop being worth using?**

We do not know an AI voice call's true salience, and nothing in this project measures it;
it would need a live experiment on real customers. So rather than assume a number, the
salience is **swept** and the break-even reported, which lets a business decide which side
of the threshold it believes it is on. Same discipline as D-055: when a parameter is
unknown, sweep it and report where the answer changes rather than picking a value that
flatters the conclusion.

Two comparisons matter:

**Human versus AI at matched salience.** If an AI call is no more intrusive than a human
one, twelve-times-cheaper should win outright. Does it?

**The volume play.** The automation case is implicitly `treat_all`, because a free actuator
removes the reason to select. Measuring `treat_all` at each salience level prices that
strategy directly.
"""

from __future__ import annotations

import pandas as pd

from retainiq.sim import SimConfig, simulate
from retainiq.sim.counterfactual import Offer, potential_outcomes

#: Salience levels swept for the AI voice channel. 0.55 is the human check-in call's
#: value, included so "no more intrusive than a person" is on the chart; the upper end
#: assumes an unsolicited synthetic voice is markedly more jarring.
SALIENCE_SWEEP = (0.55, 1.0, 1.5, 2.0, 2.5, 3.0)

#: Cost of one AI-driven contact, in the same units as the rest of the ladder. Generous
#: to the automation case: real per-call inference and telephony are cheaper still, and
#: making it cheaper only strengthens the finding below.
AI_CALL_COST = 0.50
AI_EMAIL_COST = 0.02

#: Effectiveness relative to the reference discount. An AI call is assumed slightly less
#: persuasive than a human one (0.55 against 0.70) because it cannot negotiate or
#: genuinely empathise; an LLM email slightly better than a generic nudge (0.40 vs 0.35).
AI_CALL_SAVEABILITY = 0.55
AI_EMAIL_SAVEABILITY = 0.40


def _score(sim, offer: Offer, decision_month: int = 6, horizon: int = 6) -> dict:
    """Ground-truth economics of one channel. No estimation anywhere."""
    po = potential_outcomes(sim, decision_month=decision_month, horizon=horizon, offer=offer)
    value = po["value_of_treating"]
    return {
        "channel": offer.name,
        "salience": offer.salience_multiplier,
        "cost": float(po["offer_cost"].median()),
        "mean_tau": float(po["tau_true"].mean()),
        "harmed_share": float((po["tau_true"] > 0).mean()),
        # The automation play: contact everyone, because contact is nearly free.
        "treat_all_value": float(value.sum()),
        "treat_all_per_customer": float(value.mean()),
        # The ceiling: what an oracle that knew every effect would earn, and on how few.
        "oracle_share": float((value > 0).mean()),
        "oracle_value": float(value[value > 0].sum()),
    }


def sweep(n_customers: int = 4000, seed: int = 7) -> pd.DataFrame:
    """Score the AI channels across the salience sweep, against human comparators."""
    sim = simulate(SimConfig(n_customers=n_customers, n_months=24, seed=seed))
    rows = [
        _score(sim, Offer("human_checkin_call", 2, 0.0, 0, 6.00,
                          saveability_multiplier=0.70, salience_multiplier=0.55)),
        _score(sim, Offer("ai_email", 1, 0.0, 0, AI_EMAIL_COST,
                          saveability_multiplier=AI_EMAIL_SAVEABILITY,
                          salience_multiplier=0.35)),
    ]
    rows += [
        _score(sim, Offer(f"ai_voice_call(sal={s})", 2, 0.0, 0, AI_CALL_COST,
                          saveability_multiplier=AI_CALL_SAVEABILITY,
                          salience_multiplier=s))
        for s in SALIENCE_SWEEP
    ]
    return pd.DataFrame(rows)


def break_even_salience(
    n_customers: int = 4000, seed: int = 7, lo: float = 0.2, hi: float = 6.0
) -> float:
    """The salience at which contacting everyone with a free AI channel breaks even.

    Bisection on `treat_all_per_customer`. Above this level the volume strategy destroys
    value however cheap the actuator becomes, because the loss is caused by the contact
    rather than by its price.
    """
    sim = simulate(SimConfig(n_customers=n_customers, n_months=24, seed=seed))

    def value_at(s: float) -> float:
        return _score(sim, Offer("probe", 2, 0.0, 0, AI_CALL_COST,
                                 saveability_multiplier=AI_CALL_SAVEABILITY,
                                 salience_multiplier=s))["treat_all_per_customer"]

    if value_at(lo) < 0:
        return float("nan")           # never pays, even at minimum salience
    if value_at(hi) > 0:
        return float("inf")           # always pays across the swept range
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if value_at(mid) > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def report(frame: pd.DataFrame, threshold: float) -> str:
    lines = [
        "AI OUTREACH CHANNELS -- does a nearly-free actuator change the answer?",
        "=" * 100,
        f"{'channel':>26}{'cost':>8}{'salience':>10}{'mean tau':>11}"
        f"{'harmed':>9}{'treat-all/cust':>16}{'oracle treats':>15}",
        "-" * 100,
    ]
    for _, r in frame.iterrows():
        lines.append(
            f"{r.channel:>26}{r.cost:>8.2f}{r.salience:>10.2f}{r.mean_tau:>+11.4f}"
            f"{r.harmed_share:>9.0%}{r.treat_all_per_customer:>16.2f}{r.oracle_share:>15.0%}"
        )
    lines += [
        "-" * 100,
        f"Break-even salience for contacting everyone: {threshold:.2f}",
        "",
        "treat-all/cust = value per customer if the channel is used on the whole base,",
        "                 which is the strategy a nearly-free actuator invites.",
        "oracle treats  = share an oracle knowing every effect would contact. The ceiling.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    f = sweep()
    print(report(f, break_even_salience()))
