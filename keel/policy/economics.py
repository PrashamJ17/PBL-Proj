"""Turning a treatment effect into money, correctly.

This module exists because Phase 4 did it wrong (D-057). `HierarchicalCATE` estimates
`tau_i` on the **log-odds** scale, and `AbstentionPolicy` multiplied it by a customer's
lifetime value as if it were a difference in probability. A log-odds ratio times a
currency amount is not money, and comparing that product to an offer cost is not a
decision.

The conversion needs the baseline. For a customer who churns with probability `p0` if
left alone, a log-odds shift `tau` moves them to `expit(logit(p0) + tau)`, so

    delta_p = expit(eta0 + tau) - expit(eta0),      eta0 = logit(p0)
    benefit = -delta_p * V - c

Two properties of that expression drove the whole Phase 4 failure and are worth stating
plainly, because they are not obvious from the algebra.

**The error is largest where it is most dangerous.** `d(delta_p)/d(tau)` is about
`p0 (1 - p0)`, so treating log-odds as probability overstates the benefit by roughly
`1 / (p0(1-p0))` -- a factor of 4 at `p0 = 0.5`, but 25 at `p0 = 0.05`. The inflation is
worst for customers who were **never going to leave**. That is the Sure Thing quadrant,
and inflating its apparent value is precisely the failure this project exists to
characterise. Phase 4 reintroduced it inside its own decision rule.

**The conversion is nonlinear, so the closed form is gone.** Equation 8 was cheap because
a Gaussian `tau` scaled by a constant stays Gaussian. `expit` is not a constant scaling,
so the posterior over `benefit` has no analytic form and is obtained by sampling the
joint posterior over `(eta0, tau)`. They must be drawn *jointly*: both come from one
coefficient vector and are correlated, and drawing them independently would misstate the
spread of the thing being thresholded.

The rule built on top of this consumes a `MoneyPosterior` and nothing else, which makes
the original bug unrepresentable: there is no way to hand it a log-odds quantity.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["MoneyPosterior", "benefit_posterior", "probability_effect"]


def _expit(z: np.ndarray) -> np.ndarray:
    """Stable logistic. `np.exp` overflows for the tails a wide posterior reaches."""
    out = np.empty_like(z, dtype=float)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    e = np.exp(z[~pos])
    out[~pos] = e / (1.0 + e)
    return out


def probability_effect(eta0: np.ndarray, tau: np.ndarray) -> np.ndarray:
    """`delta_p = P(churn | treated) - P(churn | not treated)`, elementwise.

    Negative means the offer helps, matching the project-wide sign convention (D-013).
    """
    return _expit(eta0 + tau) - _expit(eta0)


@dataclass
class MoneyPosterior:
    """Posterior over the net benefit of treating each customer, **in currency.**

    One row per customer, one column per posterior draw. Everything downstream reads
    money, so the units cannot be got wrong by accident.
    """

    samples: np.ndarray
    """`(n, n_samples)` draws of `-delta_p_i * V_i - c_i`."""
    delta_p: np.ndarray
    """`(n, n_samples)` draws of the probability effect, kept for reason codes."""

    def __post_init__(self) -> None:
        if self.samples.ndim != 2:
            raise ValueError(f"samples must be 2-D (n, draws), got {self.samples.shape}")
        if self.samples.shape != self.delta_p.shape:
            raise ValueError("samples and delta_p must have the same shape")

    def __len__(self) -> int:
        return int(self.samples.shape[0])

    @property
    def mean(self) -> np.ndarray:
        return self.samples.mean(axis=1)

    @property
    def sd(self) -> np.ndarray:
        return self.samples.std(axis=1, ddof=1) if self.samples.shape[1] > 1 \
            else np.zeros(len(self))

    @property
    def mean_delta_p(self) -> np.ndarray:
        return self.delta_p.mean(axis=1)

    def prob_positive(self) -> np.ndarray:
        """`P(net benefit > 0)` -- the quantity a confidence rule thresholds.

        The Monte Carlo analogue of Equation 8's closed form, and the reason the rule
        keeps working after the conversion made that form unavailable.
        """
        return (self.samples > 0).mean(axis=1)

    def quantile(self, q: float) -> np.ndarray:
        """Per-customer posterior quantile. `quantile(0.05)` is a lower bound on the
        money, which is what a risk-averse owner actually wants to see."""
        if not 0.0 <= q <= 1.0:
            raise ValueError(f"q must be in [0, 1], got {q}")
        return np.quantile(self.samples, q, axis=1)


def benefit_posterior(
    model,
    X,
    value: np.ndarray,
    cost: np.ndarray | float,
    n_samples: int = 500,
    seed: int | None = 0,
) -> MoneyPosterior:
    """Posterior over the money made by treating each customer.

    `model` is a fitted `HierarchicalCATE`; its baseline term supplies `eta0`, so no
    separate churn model is needed and the two halves of the conversion are guaranteed
    to come from the same fit. `value` is what the customer is worth if retained (CLV)
    and `cost` the price of the offer, in the same currency.
    """
    value = np.asarray(value, dtype=float)
    if value.ndim != 1:
        raise ValueError(f"value must be 1-D, got shape {value.shape}")
    if np.any(value < 0):
        raise ValueError("customer value cannot be negative")
    if np.any(~np.isfinite(value)):
        raise ValueError("customer value must be finite")

    cost = np.broadcast_to(np.asarray(cost, dtype=float), value.shape)
    if np.any(cost < 0):
        raise ValueError("offer cost cannot be negative")

    eta0, tau = model.joint_samples(X, n_samples=n_samples, seed=seed)
    if eta0.shape[0] != len(value):
        raise ValueError(
            f"model produced {eta0.shape[0]} customers, value has {len(value)}"
        )

    dp = probability_effect(eta0, tau)
    benefit = -dp * value[:, None] - cost[:, None]
    return MoneyPosterior(samples=benefit, delta_p=dp)
