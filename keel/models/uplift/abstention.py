"""The decision rule: act only when the evidence justifies the spend.

Equation 8 of the paper. Treat customer `i` only when

    P( -tau_i * V_i > c  |  data )  >  1 - alpha

in words: only when we are confident enough that the *money* gained exceeds the money
spent. Not that the effect is positive -- that the effect is large enough, on a customer
valuable enough, to be worth the offer.

Three things this buys that a point estimate cannot
----------------------------------------------------
**It ranks on money, not on effect.** A large effect on a cheap customer loses to a
small effect on a valuable one, and `-tau_i * V_i` says so directly. Ranking on `tau`
alone is the same category error as ranking on churn risk, one level up.

**It abstains rather than filling the budget.** Every top-k rule spends its whole budget
by construction; there is no k at which it declines. When nothing clears the bar this
rule treats nobody, which was worth more than better ranking in the Phase 0 result
(209 contacts beating 718).

**It degrades correctly.** As the posterior concentrates, `P(...)` approaches an
indicator and the rule becomes the point-estimate threshold. As the posterior widens --
the small-n regime -- it treats nobody rather than acting on noise. Both limits are
properties of the rule, not special cases in the code, and both are tested.

Sign convention (D-013): `tau < 0` is the good direction. The offer *reduces* the
probability of churn, so the benefit of treating is `-tau_i * V_i`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from keel.models.uplift.bayesian import CATEPosterior


@dataclass
class Decision:
    """Who to treat, and why."""

    treat: np.ndarray
    """Boolean mask."""
    confidence: np.ndarray
    """P(net benefit > 0) per customer, the quantity thresholded."""
    expected_value: np.ndarray
    """Posterior mean of `-tau_i * V_i - c_i`. Ranking uses this, not `tau` alone."""

    @property
    def n_treated(self) -> int:
        return int(self.treat.sum())

    @property
    def share_treated(self) -> float:
        return float(self.treat.mean()) if len(self.treat) else 0.0


class AbstentionPolicy:
    """Treat only where the posterior says the spend clears the bar.

    Parameters
    ----------
    alpha:
        Tolerance for being wrong. `alpha = 0.30` requires 70% posterior confidence
        that treating pays. Lower is more cautious and treats fewer people.
    budget:
        Optional cap as a fraction of the population. Applied *after* the confidence
        filter, so the rule can and does spend less than the budget. That asymmetry
        is the point: a budget is a ceiling, never a quota.
    """

    def __init__(self, alpha: float = 0.30, budget: float | None = None):
        if not 0.0 < alpha < 1.0:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        if budget is not None and not 0.0 <= budget <= 1.0:
            raise ValueError(f"budget must be a fraction in [0, 1], got {budget}")
        self.alpha = alpha
        self.budget = budget

    def decide(
        self,
        posterior: CATEPosterior,
        value: np.ndarray,
        cost: np.ndarray | float,
    ) -> Decision:
        """Apply Equation 8.

        `value` is each customer's worth if retained (CLV), `cost` the price of the
        offer. Both in the same currency; the rule is scale-free in that currency but
        emphatically not scale-free between them.
        """
        value = np.asarray(value, dtype=float)
        cost = np.broadcast_to(np.asarray(cost, dtype=float), value.shape)

        if len(value) != len(posterior):
            raise ValueError(
                f"posterior has {len(posterior)} customers, value has {len(value)}"
            )
        if np.any(value < 0):
            raise ValueError("customer value cannot be negative")

        # Benefit = -tau * V. A Gaussian tau scaled by a constant stays Gaussian, so
        # the net benefit -tau*V - c is Gaussian with these moments -- no sampling.
        mean_benefit = -posterior.mean * value - cost
        sd_benefit = posterior.sd * value

        # Where the posterior is degenerate (a customer worth nothing) the comparison
        # is deterministic; treat it as such rather than dividing by zero.
        degenerate = sd_benefit <= 1e-12
        confidence = np.where(degenerate, (mean_benefit > 0).astype(float),
                              1.0 - stats.norm.cdf(0.0, loc=mean_benefit,
                                                   scale=np.maximum(sd_benefit, 1e-12)))

        treat = confidence > (1.0 - self.alpha)

        if self.budget is not None:
            k = int(round(self.budget * len(value)))
            if treat.sum() > k:
                # Over budget: keep the highest expected value among those that
                # already cleared the confidence bar. Confidence is a gate, money is
                # the ranking -- using confidence to rank would prefer certain
                # trivialities over uncertain large wins.
                order = np.argsort(-np.where(treat, mean_benefit, -np.inf))
                keep = np.zeros_like(treat)
                keep[order[:k]] = True
                treat = keep

        return Decision(treat=treat, confidence=confidence, expected_value=mean_benefit)


def top_k_by_point_estimate(
    tau: np.ndarray, value: np.ndarray, cost: np.ndarray | float, budget: float
) -> np.ndarray:
    """The comparator: rank by expected money and fill the budget.

    Deliberately the *strong* version of the conventional approach -- it uses value
    rather than ranking on `tau` alone, so the comparison isolates **abstention** and
    not merely the fact that customers are worth different amounts. A weaker
    comparator would flatter the policy for the wrong reason.
    """
    ev = -np.asarray(tau, dtype=float) * np.asarray(value, dtype=float) - np.asarray(cost)
    k = int(round(budget * len(ev)))
    mask = np.zeros(len(ev), dtype=bool)
    if k > 0:
        mask[np.argsort(-ev)[:k]] = True
    return mask
