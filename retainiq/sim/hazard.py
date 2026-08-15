"""The monthly churn-hazard function.

Isolated into its own module because it is used in two different regimes:

  1. the stochastic historical simulation (`subsim.simulate`), and
  2. the semi-analytic forward window that produces exact ground-truth treatment
     effects (`counterfactual.potential_outcomes`).

Having one definition serve both is what guarantees the ground-truth tau is
consistent with the data a model trains on. If these ever diverge, every causal
result in the project becomes meaningless -- so they share this function.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from retainiq.sim.config import HazardParams
from retainiq.sim.latents import Latents


@dataclass
class HazardState:
    """Time-varying customer state feeding the hazard. All arrays shape (n,)."""

    tenure_months: np.ndarray
    engagement: np.ndarray
    """Current engagement level in [0,1]."""
    adopted_fraction: np.ndarray
    """Fraction of product surface in active use, [0,1]."""
    champion_lost: np.ndarray
    """1.0 if the B2B champion has left, else 0.0. May be fractional in the
    semi-analytic regime, where it carries the *probability* of loss."""
    budget_shock: np.ndarray
    """1.0 if under an exogenous budget shock, else 0.0. May be fractional."""
    support_pain: np.ndarray
    """[0,1] unresolved support friction."""
    price_pressure: np.ndarray
    """[0,1] how expensive this feels relative to perceived value."""


def hazard_logit(state: HazardState, lat: Latents, p: HazardParams) -> np.ndarray:
    """Monthly voluntary-churn hazard on the logit scale.

    Note `engagement` enters as a *deficit* (1 - engagement): low engagement raises
    the hazard. This is the dominant observable signal, and -- by design -- it is
    correlated with `attention`, the latent that governs sleeping-dog behaviour.
    That confound is the entire point of the simulator.
    """
    early_tenure = np.exp(-state.tenure_months / p.tenure_decay_months)

    return (
        p.intercept
        + p.beta_price * lat.price_sensitivity * state.price_pressure
        + p.beta_habit * lat.habit_strength
        + p.beta_adoption * state.adopted_fraction
        + p.beta_engagement_decay * (1.0 - state.engagement)
        + p.beta_champion_lost * state.champion_lost
        + p.beta_budget_shock * state.budget_shock
        + p.beta_tenure_early * early_tenure
        + p.beta_support_pain * state.support_pain
    )


def expit(x: np.ndarray) -> np.ndarray:
    """Numerically stable logistic function."""
    out = np.empty_like(x, dtype=float)
    pos = x >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-x[pos]))
    ex = np.exp(x[~pos])
    out[~pos] = ex / (1.0 + ex)
    return out
