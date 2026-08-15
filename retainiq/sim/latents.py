"""Per-customer latent traits.

These are the *unobservable* drivers of behaviour. The simulation renders them into
observable features (usage, tickets, invoices); models only ever see the observables.
Keeping the two strictly separated is what makes SubSim a fair test bench -- a model
that peeked at latents would be cheating, and that would be an easy mistake to make if
they shared an object.

Design note on `attention`
--------------------------
`attention` is the trait that makes Sleeping Dogs exist. It represents how salient the
subscription is to the customer: a low-attention customer is a dormant payer who has
half-forgotten the charge. Contacting them raises salience and can trigger the
cancellation they were never going to get around to.

It is generated *correlated with* baseline engagement (see
`SimConfig.attention_engagement_corr`) through a Gaussian copula. That correlation is
the crux of the whole project: low engagement is simultaneously

  (a) the strongest observable predictor of churn, and
  (b) a marker for the customers a retention campaign actively harms.

A churn-score-ranked campaign therefore aims its budget at the people it hurts. This
is not a quirk of the simulator -- it is the documented reason uplift modelling was
invented in the telco industry.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from retainiq.sim.config import SimConfig


@dataclass
class Latents:
    """Latent traits for a population of customers. All arrays are shape (n,)."""

    price_sensitivity: np.ndarray
    """[0,1] -- how strongly price drives this customer's churn decision. Also
    determines how much a discount offer is able to help them."""

    habit_strength: np.ndarray
    """[0,1] -- protective. Embedded routine usage."""

    engagement_base: np.ndarray
    """[0,1] -- starting engagement level."""

    engagement_decay: np.ndarray
    """[0,1] -- monthly rate at which engagement erodes."""

    attention: np.ndarray
    """[0,1] -- salience of the subscription. LOW attention => sleeping-dog risk."""

    feature_adoption_breadth: np.ndarray
    """[0,1] -- fraction of product surface adopted (Prime 'attach rate' effect)."""

    champion_stability: np.ndarray
    """[0,1] -- B2B: likelihood the internal champion sticks around."""

    budget_fragility: np.ndarray
    """[0,1] -- exposure to exogenous budget shocks. Drives Lost Causes."""

    mrr: np.ndarray
    """Monthly recurring revenue for this customer."""

    def __len__(self) -> int:
        return len(self.price_sensitivity)


def _correlated_beta(
    rng: np.random.Generator,
    n: int,
    rho: float,
    ab_1: tuple[float, float],
    ab_2: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Draw two Beta-marginal variates with Spearman-like dependence `rho`.

    Gaussian copula: correlate on the normal scale, push through the normal CDF to
    get uniforms, then through the Beta inverse-CDF to get the desired marginals.
    Both transforms are strictly monotone, so the rank correlation induced on the
    normal scale survives intact.
    """
    rho = float(np.clip(rho, -0.99, 0.99))
    z1 = rng.standard_normal(n)
    z2 = rho * z1 + np.sqrt(1.0 - rho**2) * rng.standard_normal(n)

    u1, u2 = stats.norm.cdf(z1), stats.norm.cdf(z2)
    return stats.beta.ppf(u1, *ab_1), stats.beta.ppf(u2, *ab_2)


def draw_latents(cfg: SimConfig, rng: np.random.Generator | None = None) -> Latents:
    """Sample a customer population.

    Beta marginals are used for the [0,1] traits because real populations are not
    uniform -- most customers cluster in the middle with meaningful tails at both
    ends. Shape parameters are chosen so that, e.g., `engagement_decay` is
    right-skewed (most customers decay slowly, a minority fall off a cliff).
    """
    rng = rng or np.random.default_rng(cfg.seed)
    n = cfg.n_customers

    # `engagement_base` and `attention` are correlated by construction -- see the
    # module docstring. This is the mechanism that makes the naive policy fail.
    engagement_base, attention = _correlated_beta(
        rng, n, cfg.attention_engagement_corr, ab_1=(2.0, 2.0), ab_2=(2.2, 2.0)
    )

    return Latents(
        price_sensitivity=rng.beta(2.0, 3.0, n),
        # Left-skewed: a genuinely sticky core of habitual users, plus a churny
        # tail. A symmetric Beta(2.5,2.5) here produced a purely exponential
        # retention curve, whereas real cohort curves FLATTEN -- the fragile leave
        # first and the surviving pool is progressively hardier. That flattening is
        # a structural property worth reproducing, not a nuisance.
        habit_strength=rng.beta(2.2, 1.6, n),
        engagement_base=engagement_base,
        # Mean ~0.05/month. Most customers erode slowly; a right tail falls off a
        # cliff. Earlier shapes here decayed ~0.21/month, which drove everyone to
        # zero engagement by month 12 and saturated the hazard.
        engagement_decay=rng.beta(1.5, 28.0, n),
        attention=attention,
        feature_adoption_breadth=rng.beta(1.8, 3.5, n),
        champion_stability=rng.beta(4.0, 2.0, n),
        budget_fragility=rng.beta(1.5, 5.0, n),
        mrr=rng.lognormal(cfg.economics.mrr_lognormal_mu, cfg.economics.mrr_lognormal_sigma, n),
    )
