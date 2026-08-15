"""SubSim -- the subscription lifecycle simulator.

Runs a stochastic month-by-month simulation of a small subscription business and
emits a person-period panel of *observable* features only: the things a real Stripe
plus product-analytics integration would actually give you.

The latents that generated the data are returned alongside, but strictly separated,
for oracle analysis and validation. Models must never touch them.

Voluntary and involuntary churn are modelled as distinct processes, because they are
distinct businesses problems with distinct fixes: voluntary churn needs a causal
retention policy, involuntary churn needs better retry timing. Conflating them --
as most published churn work does -- makes 20-40% of the outcome variable
unaddressable by the model that is supposed to explain it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from retainiq.sim.config import SimConfig
from retainiq.sim.hazard import HazardState, expit, hazard_logit
from retainiq.sim.latents import Latents, draw_latents


@dataclass
class SimResult:
    """Output of a SubSim run."""

    panel: pd.DataFrame
    """Person-period panel, one row per (customer_id, month) while at risk.

    Observable columns only -- this is what models are allowed to see."""

    customers: pd.DataFrame
    """One row per customer: static attributes and final outcome."""

    latents: Latents
    """Ground-truth latents. ORACLE USE ONLY -- never as model input."""

    hidden_state: pd.DataFrame
    """Per (customer_id, month) hazard state. ORACLE USE ONLY.

    Needed so the counterfactual window can reconstruct exact hazard trajectories
    from a decision point. Kept out of `panel` because several of these -- notably
    `budget_shock` -- are not observable to the vendor in real life."""

    config: SimConfig

    def snapshot(self, month: int) -> pd.DataFrame:
        """Observable feature vector for every customer still active at `month`.

        This is the decision point: what you would know at the moment you decide
        who to target.
        """
        snap = self.panel[self.panel["month"] == month]
        return snap.reset_index(drop=True)


def simulate(cfg: SimConfig | None = None) -> SimResult:
    """Run the full stochastic simulation."""
    cfg = cfg or SimConfig()
    rng = np.random.default_rng(cfg.seed)
    lat = draw_latents(cfg, rng)
    n = cfg.n_customers
    hp = cfg.hazard

    # --- persistent state -----------------------------------------------------
    active = np.ones(n, dtype=bool)
    tenure = np.zeros(n)
    champion_lost = np.zeros(n)
    budget_shock = np.zeros(n)
    support_pain = np.zeros(n)
    cum_payment_failures = np.zeros(n)
    engagement_prev = lat.engagement_base.copy()

    churn_month = np.full(n, -1, dtype=int)
    churn_kind = np.array(["none"] * n, dtype=object)

    rows: list[pd.DataFrame] = []
    hidden_rows: list[pd.DataFrame] = []

    for t in range(cfg.n_months):
        if not active.any():
            break

        # --- evolve state ------------------------------------------------------
        # Engagement decays geometrically from its base level toward a *floor*
        # rather than toward zero. The floor is set by habit strength: a customer
        # with an embedded routine keeps using the product at some baseline level
        # indefinitely. Without this floor every customer eventually saturates the
        # hazard and 24-month retention collapses to near zero, which is both
        # unrealistic and destroys the censoring that survival analysis needs.
        floor = lat.habit_strength * 0.55 * lat.engagement_base
        engagement = floor + (lat.engagement_base - floor) * (1.0 - lat.engagement_decay) ** t
        engagement = np.clip(engagement + rng.normal(0, 0.03, n), 0.0, 1.0)

        # Feature adoption ramps early then plateaus at the customer's ceiling.
        # The Prime lesson: breadth of adoption is strongly protective.
        adopted = lat.feature_adoption_breadth * (1.0 - np.exp(-(t + 1) / 3.0))

        # Champion turnover (B2B). Absorbing: once lost, stays lost.
        champ_leaves = rng.random(n) < (
            cfg.champion_turnover_monthly * (1.0 - lat.champion_stability)
        )
        champion_lost = np.maximum(champion_lost, champ_leaves.astype(float))

        # Budget shocks are transient but sticky for a few months.
        new_shock = rng.random(n) < (cfg.budget_shock_monthly * lat.budget_fragility * 3.0)
        budget_shock = np.maximum(budget_shock * 0.7, new_shock.astype(float))

        # Support friction accumulates when people are stuck (low adoption) and
        # decays as issues resolve.
        ticket_rate = 0.25 * (1.0 - adopted) + 0.15 * (engagement < 0.2)
        new_tickets = rng.poisson(np.clip(ticket_rate, 0, None))
        support_pain = np.clip(support_pain * 0.6 + 0.25 * new_tickets, 0.0, 1.0)

        # Price pressure: how expensive this feels relative to value received.
        # Paying a lot while using little is the canonical "too expensive" story.
        norm_mrr = lat.mrr / np.median(lat.mrr)
        price_pressure = np.clip(0.35 * norm_mrr * (1.0 - engagement), 0.0, 1.0)

        state = HazardState(
            tenure_months=tenure,
            engagement=engagement,
            adopted_fraction=adopted,
            champion_lost=champion_lost,
            budget_shock=budget_shock,
            support_pain=support_pain,
            price_pressure=price_pressure,
        )
        h = expit(hazard_logit(state, lat, hp))

        # --- involuntary churn -------------------------------------------------
        # A failed invoice that is never recovered ends the subscription. This is
        # a separate process from the customer *deciding* to leave.
        failed = rng.random(n) < cfg.payments.monthly_failure_rate
        recovered = rng.random(n) < cfg.payments.passive_recovery_rate
        involuntary = failed & ~recovered & active
        cum_payment_failures += failed.astype(float)

        # --- voluntary churn ---------------------------------------------------
        voluntary = (rng.random(n) < h) & active & ~involuntary

        # --- record observables BEFORE applying churn --------------------------
        idx = np.flatnonzero(active)
        rows.append(
            pd.DataFrame(
                {
                    "customer_id": idx,
                    "month": t,
                    # --- observable features (what a real integration provides) ---
                    "tenure_months": tenure[idx],
                    "mrr": lat.mrr[idx],
                    "sessions_30d": np.round(engagement[idx] * 40).astype(int),
                    "engagement_trend": np.where(
                        engagement_prev[idx] > 1e-6,
                        engagement[idx] / np.maximum(engagement_prev[idx], 1e-6),
                        1.0,
                    ),
                    "features_used": np.round(adopted[idx] * 12).astype(int),
                    "support_tickets_90d": new_tickets[idx],
                    "unresolved_pain": support_pain[idx],
                    "payment_failures_ltd": cum_payment_failures[idx],
                    "seats_active_ratio": np.clip(
                        adopted[idx] * 0.6 + engagement[idx] * 0.4, 0, 1
                    ),
                    "champion_departed": champion_lost[idx],
                    "price_to_median": norm_mrr[idx],
                    # --- outcomes ---
                    "churn_voluntary": voluntary[idx].astype(int),
                    "churn_involuntary": involuntary[idx].astype(int),
                }
            )
        )

        # Oracle-only state, needed to reconstruct exact counterfactual hazards.
        hidden_rows.append(
            pd.DataFrame(
                {
                    "customer_id": idx,
                    "month": t,
                    "engagement": engagement[idx],
                    "adopted_fraction": adopted[idx],
                    "champion_lost": champion_lost[idx],
                    "budget_shock": budget_shock[idx],
                    "support_pain": support_pain[idx],
                    "price_pressure": price_pressure[idx],
                    "hazard": h[idx],
                }
            )
        )

        # --- apply churn -------------------------------------------------------
        just_churned = voluntary | involuntary
        churn_month[just_churned & (churn_month < 0)] = t
        churn_kind[voluntary] = "voluntary"
        churn_kind[involuntary] = "involuntary"
        active &= ~just_churned

        tenure = tenure + active.astype(float)
        engagement_prev = engagement

    # `rows` is empty only in degenerate configs (zero customers or zero months);
    # build an empty frame with the right columns so downstream code stays uniform.
    panel = (
        pd.concat(rows, ignore_index=True)
        if rows
        else pd.DataFrame(columns=_PANEL_COLUMNS)
    )
    hidden = (
        pd.concat(hidden_rows, ignore_index=True)
        if hidden_rows
        else pd.DataFrame(columns=_HIDDEN_COLUMNS)
    )

    customers = pd.DataFrame(
        {
            "customer_id": np.arange(n),
            "mrr": lat.mrr,
            "churn_month": churn_month,
            "churn_kind": churn_kind,
            # Right-censored: still active at the end of the observation window.
            # These are NOT negatives -- treating them as such is the classic error
            # that survival analysis exists to prevent.
            "censored": churn_month < 0,
        }
    )

    return SimResult(
        panel=panel, customers=customers, latents=lat, hidden_state=hidden, config=cfg
    )


_PANEL_COLUMNS = [
    "customer_id", "month", "tenure_months", "mrr", "sessions_30d",
    "engagement_trend", "features_used", "support_tickets_90d", "unresolved_pain",
    "payment_failures_ltd", "seats_active_ratio", "champion_departed",
    "price_to_median", "churn_voluntary", "churn_involuntary",
]

_HIDDEN_COLUMNS = [
    "customer_id", "month", "engagement", "adopted_fraction", "champion_lost",
    "budget_shock", "support_pain", "price_pressure", "hazard",
]
