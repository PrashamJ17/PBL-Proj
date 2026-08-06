"""Ground-truth counterfactuals: the reason SubSim exists.

Real data never contains the counterfactual. You observe what happened to the
customer you treated, never what would have happened had you left them alone. That is
the fundamental problem of causal inference, and it means an uplift model evaluated on
real data can only ever be scored on group-level proxies (Qini, AUUC) that assume you
rank-and-treat-top-k.

Here we know both potential outcomes exactly, so we can score an uplift model against
the *true individual* treatment effect, and evaluate policies on realised net revenue.

Two regimes, deliberately
-------------------------
1. **Exact analytic tau.** The forward window evolves state along its *expected*
   trajectory rather than a sampled one, so survival probabilities -- and therefore
   tau -- are computed in closed form with zero Monte Carlo error. This is the
   ground truth an uplift model should be scored against.

2. **Realised outcomes under common random numbers.** The same uniform draws are
   applied to both arms, giving correctly *paired* potential outcomes Y(0), Y(1).
   This is what a perfect (infinitely large, perfectly randomised) experiment would
   have observed, and it is what a policy's realised revenue is computed from.

Using common random numbers across arms is a standard variance-reduction technique;
without it, per-customer differences would be swamped by simulation noise.

The four quadrants
------------------
             |  stays if treated     |  churns if treated
  -----------+-----------------------+------------------------
  stays if   |  Sure Thing           |  SLEEPING DOG
  untreated  |  (don't waste money)  |  (treating CAUSES churn)
  -----------+-----------------------+------------------------
  churns if  |  PERSUADABLE          |  Lost Cause
  untreated  |  (the only ones worth |  (let go)
             |   paying for)         |
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from keel.sim.config import SimConfig
from keel.sim.hazard import HazardState, expit, hazard_logit
from keel.sim.latents import Latents
from keel.sim.subsim import SimResult


@dataclass(frozen=True)
class Offer:
    """A retention intervention.

    Rung ordering matches the margin-cost ladder in the plan: cheap, non-monetary
    interventions first, discounts last.
    """

    name: str
    rung: int
    discount_pct: float
    discount_months: int
    contact_cost: float = 0.50
    saveability_multiplier: float = 1.0
    """How effective this offer is at addressing a price objection, relative to
    the reference discount."""
    salience_multiplier: float = 1.0
    """How much this offer wakes a dormant payer. An in-product nudge is far less
    salient than an email saying 'we noticed you haven't been using your
    subscription'."""


# The ladder, ordered by margin cost. Rung 0 (abstain) is not an Offer -- it is the
# absence of one, which the policy layer must be able to choose.
LADDER: list[Offer] = [
    Offer("feature_nudge", 1, 0.00, 0, 0.10, saveability_multiplier=0.35, salience_multiplier=0.30),
    Offer("checkin_call", 2, 0.00, 0, 6.00, saveability_multiplier=0.70, salience_multiplier=0.55),
    Offer("pause_offer", 4, 0.00, 0, 0.50, saveability_multiplier=0.85, salience_multiplier=1.15),
    Offer("downgrade_offer", 5, 0.00, 0, 0.50, saveability_multiplier=0.90, salience_multiplier=1.10),
    Offer("discount_20_3mo", 7, 0.20, 3, 0.50, saveability_multiplier=1.00, salience_multiplier=1.00),
    Offer("discount_40_6mo", 8, 0.40, 6, 0.50, saveability_multiplier=1.25, salience_multiplier=1.00),
]

REFERENCE_OFFER = LADDER[4]  # discount_20_3mo


@dataclass
class ForwardTrajectory:
    """Expected state path over the counterfactual window."""

    hazard_control: np.ndarray  # (n, horizon)
    hazard_treated: np.ndarray  # (n, horizon)
    engagement: np.ndarray  # (n, horizon)


def _expected_forward_states(
    lat: Latents,
    cfg: SimConfig,
    ids: np.ndarray,
    start_month: int,
    horizon: int,
    champion_lost0: np.ndarray,
    budget_shock0: np.ndarray,
    support_pain0: np.ndarray,
    tenure0: np.ndarray,
) -> list[HazardState]:
    """Evolve state along its expected trajectory for `horizon` months.

    Deterministic components (engagement, adoption) evolve exactly as in the
    simulation. Stochastic components (champion loss, budget shock, tickets) are
    propagated as *expectations* rather than sampled, which is what makes the
    resulting tau exact.
    """
    champion_lost = champion_lost0.copy()
    budget_shock = budget_shock0.copy()
    support_pain = support_pain0.copy()

    p_champ_leave = cfg.champion_turnover_monthly * (1.0 - lat.champion_stability[ids])
    p_new_shock = np.clip(cfg.budget_shock_monthly * lat.budget_fragility[ids] * 3.0, 0, 1)
    norm_mrr = lat.mrr[ids] / np.median(lat.mrr)

    floor = lat.habit_strength[ids] * 0.55 * lat.engagement_base[ids]
    states: list[HazardState] = []

    for k in range(horizon):
        t = start_month + k

        engagement = floor + (lat.engagement_base[ids] - floor) * (
            1.0 - lat.engagement_decay[ids]
        ) ** t
        engagement = np.clip(engagement, 0.0, 1.0)
        adopted = lat.feature_adoption_breadth[ids] * (1.0 - np.exp(-(t + 1) / 3.0))

        if k > 0:
            # Champion loss is absorbing: P(lost by t+1) = P(lost) + P(not)*P(leaves)
            champion_lost = champion_lost + (1.0 - champion_lost) * p_champ_leave
            # Shocks decay but can recur.
            budget_shock = p_new_shock + (1.0 - p_new_shock) * 0.7 * budget_shock
            ticket_rate = 0.25 * (1.0 - adopted) + 0.15 * (engagement < 0.2)
            support_pain = np.clip(0.6 * support_pain + 0.25 * ticket_rate, 0.0, 1.0)

        states.append(
            HazardState(
                tenure_months=tenure0 + k,
                engagement=engagement,
                adopted_fraction=adopted,
                champion_lost=champion_lost.copy(),
                budget_shock=budget_shock.copy(),
                support_pain=support_pain.copy(),
                price_pressure=np.clip(0.35 * norm_mrr * (1.0 - engagement), 0.0, 1.0),
            )
        )
    return states


def treatment_delta(
    lat: Latents,
    cfg: SimConfig,
    ids: np.ndarray,
    state: HazardState,
    offer: Offer,
    month_offset: int,
) -> np.ndarray:
    """Effect of an offer on the churn-hazard logit at `month_offset` after contact.

    Two opposing forces, and their *timing differs*, which matters:

    - **saveability** (protective): the offer addresses a real, addressable reason
      for leaving. Holds through the discount period, then tapers.
    - **salience** (harmful): contact reminds a dormant payer they are paying.
      This is a sharp, immediate spike that decays fast -- the damage is done at
      the moment of contact, not gradually.

    Saveability is damped toward zero when the churn cause is exogenous (champion
    departed, budget shock): those are Lost Causes, and no offer reaches them.
    """
    ip = cfg.intervention

    # --- saveability -------------------------------------------------------
    price_component = ip.price_match_weight * lat.price_sensitivity[ids] * state.price_pressure
    # "Reachable and genuinely at risk": engaged enough to read the offer, but
    # showing strain. Low-engagement customers are precisely the ones an offer
    # cannot reach -- which is the trap a churn-score policy walks into.
    risk_component = ip.risk_match_weight * state.engagement * (1.0 - state.adopted_fraction)

    exogenous = np.clip(np.maximum(state.champion_lost, state.budget_shock), 0.0, 1.0)
    damping = ip.unsaveable_damping + (1.0 - ip.unsaveable_damping) * (1.0 - exogenous)

    saveability = np.clip(price_component + risk_component, 0.0, 1.0) * damping
    saveability *= offer.saveability_multiplier

    # Holds during the discount, then tapers with a 2-month half-life.
    hold = max(offer.discount_months, 1)
    save_decay = 1.0 if month_offset < hold else np.exp(-(month_offset - hold) / 2.0)

    # --- salience (the sleeping-dog mechanism) -----------------------------
    # Loads on LOW attention and LOW engagement. Since low engagement is also the
    # strongest churn *predictor*, this is exactly the population a churn-score
    # ranking puts at the top of its list.
    salience = (1.0 - lat.attention[ids]) * (1.0 - state.engagement)
    salience *= offer.salience_multiplier
    salience_decay = np.exp(-month_offset / 0.8)  # sharp, immediate, fades fast

    return (
        ip.saveability_scale * saveability * save_decay
        + ip.salience_scale * salience * salience_decay
    )


def potential_outcomes(
    sim: SimResult,
    decision_month: int = 6,
    horizon: int = 6,
    offer: Offer = REFERENCE_OFFER,
    clv_horizon: int = 36,
    seed: int | None = None,
) -> pd.DataFrame:
    """Compute exact ground-truth potential outcomes at a decision point.

    Returns one row per customer active at `decision_month`, with:

    ==========================  ================================================
    ``p_churn_control``         P(churn within horizon | untreated), exact
    ``p_churn_treated``         P(churn within horizon | treated), exact
    ``tau_true``                treated - control. **NEGATIVE = offer helps.**
    ``y0``, ``y1``              realised outcomes under common random numbers
    ``quadrant``                true type from tau and baseline risk
    ``quadrant_realised``       type implied by the realised (y0, y1) pair
    ``clv``                     expected residual margin, discounted
    ``offer_cost``              discount given + contact cost
    ``value_of_treating``       -tau * clv - cost. The quantity to maximise.
    ==========================  ================================================
    """
    cfg = sim.config
    lat = sim.latents
    rng = np.random.default_rng(cfg.seed + 9973 if seed is None else seed)

    snap = sim.snapshot(decision_month)
    if snap.empty:
        return pd.DataFrame(columns=_OUTCOME_COLUMNS)

    hs = sim.hidden_state
    hs = hs[hs["month"] == decision_month].set_index("customer_id")
    ids = snap["customer_id"].to_numpy()
    hs = hs.loc[ids]

    tenure0 = snap["tenure_months"].to_numpy()
    n = len(ids)

    # Long trajectory: `horizon` for the treatment effect, `clv_horizon` for CLV.
    span = max(horizon, clv_horizon)
    states = _expected_forward_states(
        lat, cfg, ids, decision_month, span,
        hs["champion_lost"].to_numpy(), hs["budget_shock"].to_numpy(),
        hs["support_pain"].to_numpy(), tenure0,
    )

    h_ctrl = np.empty((n, span))
    h_treat = np.empty((n, span))
    for k, st in enumerate(states):
        logit_c = hazard_logit(st, _subset(lat, ids), cfg.hazard)
        h_ctrl[:, k] = expit(logit_c)
        delta = treatment_delta(lat, cfg, ids, st, offer, k) if k < horizon else 0.0
        h_treat[:, k] = expit(logit_c + delta)

    # --- exact survival probabilities over the evaluation horizon ----------
    surv_c = np.prod(1.0 - h_ctrl[:, :horizon], axis=1)
    surv_t = np.prod(1.0 - h_treat[:, :horizon], axis=1)
    p0, p1 = 1.0 - surv_c, 1.0 - surv_t
    tau = p1 - p0  # negative => the offer reduces churn

    # --- realised outcomes under COMMON RANDOM NUMBERS ---------------------
    u = rng.random((n, horizon))
    y0 = (u < h_ctrl[:, :horizon]).any(axis=1).astype(int)
    y1 = (u < h_treat[:, :horizon]).any(axis=1).astype(int)

    # --- economics ---------------------------------------------------------
    ep = cfg.economics
    disc = 1.0 / (1.0 + ep.monthly_discount_rate) ** np.arange(clv_horizon)
    surv_path = np.cumprod(1.0 - h_ctrl[:, :clv_horizon], axis=1)
    clv = (lat.mrr[ids][:, None] * ep.gross_margin * surv_path * disc).sum(axis=1)

    offer_cost = offer.discount_pct * lat.mrr[ids] * offer.discount_months + offer.contact_cost

    return pd.DataFrame(
        {
            "customer_id": ids,
            "p_churn_control": p0,
            "p_churn_treated": p1,
            "tau_true": tau,
            "y0": y0,
            "y1": y1,
            "quadrant": _label_quadrants(tau, p0),
            "quadrant_realised": _label_realised(y0, y1),
            "clv": clv,
            "offer_cost": offer_cost,
            "value_of_treating": -tau * clv - offer_cost,
        }
    )


def _subset(lat: Latents, ids: np.ndarray) -> Latents:
    """View of the latents restricted to `ids`, preserving array alignment."""
    from dataclasses import fields, replace

    return replace(lat, **{f.name: getattr(lat, f.name)[ids] for f in fields(lat)})


def _label_quadrants(tau: np.ndarray, p0: np.ndarray, eps: float = 0.01) -> np.ndarray:
    """True customer type, from the exact treatment effect and baseline risk.

    More reliable than the realised (y0,y1) labelling, which is noisy at the
    individual level -- a Persuadable can still get a draw where they stay in both
    arms. Both are returned so the two can be compared.
    """
    out = np.full(len(tau), "sure_thing", dtype=object)
    out[(tau <= -eps)] = "persuadable"
    out[(tau >= eps)] = "sleeping_dog"
    out[(np.abs(tau) < eps) & (p0 > 0.5)] = "lost_cause"
    return out


def _label_realised(y0: np.ndarray, y1: np.ndarray) -> np.ndarray:
    out = np.empty(len(y0), dtype=object)
    out[(y0 == 0) & (y1 == 0)] = "sure_thing"
    out[(y0 == 1) & (y1 == 0)] = "persuadable"
    out[(y0 == 0) & (y1 == 1)] = "sleeping_dog"
    out[(y0 == 1) & (y1 == 1)] = "lost_cause"
    return out


_OUTCOME_COLUMNS = [
    "customer_id", "p_churn_control", "p_churn_treated", "tau_true", "y0", "y1",
    "quadrant", "quadrant_realised", "clv", "offer_cost", "value_of_treating",
]
