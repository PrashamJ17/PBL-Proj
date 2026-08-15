"""Reason codes: why this customer, why this offer, and how sure we are.

The last piece of Phase 5's gate -- "an owner can act without asking us". An owner
handed a ranked list and a probability cannot act on it; they need to know what the
recommendation rests on and when to ignore it.

**This explains a decision, not a prediction.** The usual pattern in this space is SHAP
over a churn classifier, producing "87% risk because days-since-purchase = 400". That
answers a question nobody needs answered: the owner can see the customer has not bought
in 400 days. What they cannot see is whether *doing something about it* pays, which is
the only question that spends money. So the explanation here decomposes the money:

    expected money  =  -delta_p * V  -  c

every term of which is separately meaningful to a business -- how much the offer moves
this person, what keeping them is worth, and what the offer costs -- and each of which
suggests a different response when it is the binding one.

**The attribution is exact, not approximated.** `tau_i = tau_0 + x_i'gamma` is linear,
and for a linear model the Shapley value of feature `j` is exactly
`gamma_j (x_ij - E[x_j])`. Features are standardised, so it is `gamma_j * xs_ij`. There
is nothing to sample and no SHAP dependency (invariant 7). The intercept is excluded on
purpose: "the offer works on people in general" explains the *policy*, not the customer.

**Every reason carries its own reliability.** D-058 measured this optimiser beating the
achievable alternative on 58% of draws, CI [0.42, 0.72] -- not distinguishable from
chance. A reason code that read "contact this customer, it will earn 340" would be
overclaiming by exactly the margin this project spent five phases refusing to overclaim.
So `Reason.caveat` is populated whenever the recommendation is thin, and `render` prints
it. The explanation layer is where an honest system is most tempted to lie, because it
is the only layer the customer reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from retainiq.policy.ladder import ABSTAIN, Recommendation

__all__ = ["Reason", "explain", "render", "FEATURE_PHRASES"]

#: Plain-language names for the observable features SubSim exposes. Anything absent
#: falls back to the raw column name, so an unknown tenant schema degrades to something
#: readable rather than raising.
FEATURE_PHRASES: dict[str, tuple[str, str]] = {
    # column: (noun phrase, direction word for a HIGH value)
    "tenure_months": ("how long they have been a customer", "longer"),
    "mrr": ("what they pay each month", "higher"),
    "sessions_30d": ("how often they logged in last month", "more"),
    "engagement_trend": ("whether their usage is rising or falling", "rising"),
    "features_used": ("how much of the product they use", "more"),
    "support_tickets_90d": ("how much support they have needed", "more"),
    "unresolved_pain": ("unresolved support problems", "more"),
    "payment_failures_ltd": ("past failed payments", "more"),
    "seats_active_ratio": ("how many of their seats are actually used", "more"),
    "champion_departed": ("whether the person who bought it has left", "yes"),
    "price_to_median": ("what they pay relative to similar customers", "higher"),
}

#: Below this, an expected gain is not worth an owner's attention even if positive.
_MATERIALITY = 1.0


@dataclass
class Reason:
    """Why one customer got one recommendation."""

    index: int
    action: str
    """Offer name, or ``"no offer"``."""
    expected_value: float
    confidence: float
    """`P(this offer makes money)`, from the posterior."""
    drivers: list[str] = field(default_factory=list)
    """Plain-language reasons this customer responds differently from average."""
    economics: str = ""
    """The money identity, stated in currency."""
    runner_up: str = ""
    """Why this rung and not the next best."""
    caveat: str = ""
    """Populated when the recommendation should not be trusted on its own."""

    @property
    def is_action(self) -> bool:
        return self.action != "no offer"


def _phrase(col: str, contribution: float, standardised: float) -> str:
    """One driver, in words.

    Two independent signs, and conflating them produces nonsense. `standardised` says
    whether the customer is above or below typical on this feature; `contribution` says
    whether that pushes the offer's effect in the helpful direction (negative `tau`).
    """
    noun, high_word = FEATURE_PHRASES.get(col, (col.replace("_", " "), "higher"))
    where = f"{high_word} than typical" if standardised >= 0 else "lower than typical"
    verb = ("makes the offer more likely to work" if contribution < 0
            else "makes it less likely to work")
    return f"{noun} ({where}) {verb}"


def explain(
    rec: Recommendation,
    model,
    X: pd.DataFrame,
    offer_names: list[str],
    value: np.ndarray,
    costs: np.ndarray,
    baseline_risk: np.ndarray | None = None,
    delta_p: np.ndarray | None = None,
    top_k: int = 3,
    reliability_note: str | None = None,
) -> list[Reason]:
    """One `Reason` per customer.

    `baseline_risk` and `delta_p` are the estimated churn probability if untreated and
    the estimated change under the chosen offer. They come from
    `economics.benefit_posterior`, and are optional only so the explainer can be used
    with a model that does not supply them.
    """
    if len(rec.rung) != len(X):
        raise ValueError(f"recommendation has {len(rec.rung)} rows, X has {len(X)}")
    if costs.shape[1] != len(offer_names):
        raise ValueError(
            f"{costs.shape[1]} cost columns but {len(offer_names)} offer names"
        )

    contrib = model.effect_contributions(X)
    xs = model.standardised_features(X)
    cols = list(X.columns)
    out: list[Reason] = []

    # How much of the effect is personal at all. `tau_0` is the average effect; when
    # heterogeneity collapses (D-058: sigma_gamma goes to zero at these sample sizes)
    # every row of `contrib` is near zero and the recommendation is driven by the
    # average effect and the customer's value, not by anything about them. Saying so is
    # the difference between an explanation and a decoration.
    p = model.n_features_
    tau_0 = float(model.theta_[p + 1])
    personal_scale = np.abs(contrib).sum(axis=1)

    for i in range(len(X)):
        k = int(rec.rung[i])

        if k == ABSTAIN:
            if rec.budget_trimmed[i]:
                why = ("the budget was spent on customers where it earns more -- "
                       "this one was worth treating, just not first")
            else:
                best = float(np.max(rec.value_by_rung[i]))
                why = (f"no offer we can measure pays for itself here "
                       f"(best of {len(offer_names)} is {best:,.0f})")
            out.append(Reason(index=i, action="no offer", expected_value=0.0,
                              confidence=0.0, economics=why))
            continue

        # Drivers: the largest exact contributions to this customer's effect.
        order = np.argsort(-np.abs(contrib[i]))[:top_k]
        drivers = [_phrase(cols[j], contrib[i, j], xs[i, j]) for j in order
                   if abs(contrib[i, j]) > 1e-9]

        # Two ways the per-customer signal fails to justify the action, both of which a
        # list of confident-looking feature attributions would paper over.
        if personal_scale[i] < 0.1 * abs(tau_0):
            drivers = ["nothing specific to this customer drives it -- the case rests "
                       "on what they are worth, and on the offer working on average"]
        elif drivers and contrib[i, order].sum() > 0:
            drivers.append("on balance their profile argues *against* the offer; it is "
                           "recommended because they are valuable enough to try anyway")

        econ = ""
        if baseline_risk is not None and delta_p is not None:
            econ = (
                f"worth {value[i]:,.0f} if kept; without contact we put their risk of "
                f"leaving at {baseline_risk[i]:.0%}, and this offer moves that by "
                f"{delta_p[i] * 100:+.1f} points, at a cost of {costs[i, k]:,.2f}"
            )

        runner = ""
        vals = rec.value_by_rung[i].copy()
        finite = np.isfinite(vals)
        if finite.sum() > 1:
            vals[k] = -np.inf
            j = int(np.argmax(np.where(finite, vals, -np.inf)))
            gap = rec.value_by_rung[i, k] - rec.value_by_rung[i, j]
            if np.isfinite(gap):
                runner = (
                    f"next best is {offer_names[j]}, worth {gap:,.0f} less"
                    if gap > _MATERIALITY else
                    f"{offer_names[j]} is worth about the same -- either is defensible"
                )

        caveat = ""
        if rec.confidence[i] < 0.6:
            caveat = (f"thin evidence: only a {rec.confidence[i]:.0%} chance this makes "
                      f"money at all. Treat as a suggestion, not a finding")
        elif rec.expected_value[i] < _MATERIALITY:
            caveat = "the expected gain is too small to be worth anyone's attention"
        if reliability_note:
            caveat = f"{caveat}. {reliability_note}" if caveat else reliability_note

        out.append(Reason(
            index=i, action=offer_names[k],
            expected_value=float(rec.expected_value[i]),
            confidence=float(rec.confidence[i]),
            drivers=drivers, economics=econ, runner_up=runner, caveat=caveat,
        ))
    return out


def render(reasons: list[Reason], limit: int | None = None, ids=None) -> str:
    """Plain text an owner can read without us in the room.

    Actions are listed before abstentions and sorted by money, because that is the order
    someone with a finite morning should work through them in.
    """
    acts = sorted([r for r in reasons if r.is_action],
                  key=lambda r: -r.expected_value)
    skips = [r for r in reasons if not r.is_action]

    lines = [
        "RETENTION RECOMMENDATIONS",
        "=" * 78,
        f"{len(acts)} customers to contact, {len(skips)} to leave alone.",
        "",
    ]
    for r in acts[:limit]:
        who = f"customer {ids[r.index]}" if ids is not None else f"customer #{r.index}"
        lines.append(f"{who} -- {r.action.replace('_', ' ')}")
        lines.append(f"  expected gain   {r.expected_value:,.0f} "
                     f"({r.confidence:.0%} chance it pays)")
        if r.economics:
            lines.append(f"  why it pays     {r.economics}")
        for d in r.drivers:
            lines.append(f"  why them        {d}")
        if r.runner_up:
            lines.append(f"  why this offer  {r.runner_up}")
        if r.caveat:
            lines.append(f"  ! caution       {r.caveat}")
        lines.append("")

    if skips:
        lines.append("-" * 78)
        lines.append("Left alone:")
        shown = skips[: (limit or 5)]
        for r in shown:
            who = f"customer {ids[r.index]}" if ids is not None else f"customer #{r.index}"
            lines.append(f"  {who}: {r.economics}")
        if len(skips) > len(shown):
            lines.append(f"  ... and {len(skips) - len(shown)} more")
    return "\n".join(lines)
