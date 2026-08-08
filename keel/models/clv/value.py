"""Customer lifetime value, computed from a survival curve.

For a **contractual** business -- which is the vertical (CLAUDE.md; e-commerce and
BTYD are Phase 7) -- CLV needs no probabilistic transaction model. Churn is observed,
billing is periodic, and the whole quantity is:

    CLV = sum_{t=1..H} margin * S(t) / (1 + d)^t

`S(t)` comes from the survival model, `margin` is monthly contribution (not revenue),
`d` is the monthly discount rate, and `H` is the horizon.

Three choices in that formula are not incidental
------------------------------------------------
**Margin, not revenue.** Revenue-based CLV overstates every customer by the cost of
serving them, and it overstates the expensive ones most -- which are exactly the ones
a retention budget would then chase.

**Discounting.** A subscription is an annuity. Without discounting, a customer who
churns in month 40 instead of month 39 gains full face value, and every long-horizon
comparison is dominated by cash that may never arrive.

**A finite horizon, capped at the observed data (D-046).** This is the one that
matters most and the one most CLV implementations get wrong. The standard formula
`ARPU / churn_rate` is the sum of an infinite geometric series: it assumes a constant
hazard forever. Retention hazards decline with tenure (D-004), so a constant-hazard
extrapolation is not merely uncertain, it is biased -- and the survival model has
*no information at all* about periods beyond its training window. `clv()` therefore
refuses a horizon longer than the observed support unless the caller says so
explicitly, in which case the assumption is theirs and it is visible in the code.
"""

from __future__ import annotations

import numpy as np


class ExtrapolationError(ValueError):
    """Raised when a CLV horizon runs past the data that could support it."""


def monthly_discount(annual_rate: float) -> float:
    """Convert an annual discount rate to the equivalent monthly one.

    Compounding, not `annual/12`: at 12% annual the two differ by ~5% of the rate,
    which compounds again over a multi-year horizon.
    """
    if annual_rate <= -1.0:
        raise ValueError("annual discount rate must be > -100%")
    return (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0


def _discount_factors(horizon: int, annual_rate: float) -> np.ndarray:
    d = monthly_discount(annual_rate)
    return 1.0 / (1.0 + d) ** np.arange(1, horizon + 1)


def clv(
    survival: np.ndarray,
    margin: np.ndarray | float,
    annual_discount_rate: float = 0.12,
    observed_support: int | None = None,
    allow_extrapolation: bool = False,
) -> np.ndarray:
    """Expected discounted contribution over the horizon implied by `survival`.

    Parameters
    ----------
    survival:
        `(n, H)` -- S(t) for t = 1..H, conditional on being alive now. This is
        *residual* value: a customer's already-collected revenue is sunk and is not
        part of what a retention decision is worth.
    margin:
        Monthly contribution margin per customer -- scalar or length-n.
    observed_support:
        The longest duration actually observed in the training data. When given, a
        horizon beyond it raises unless `allow_extrapolation=True`. Pass it. The
        guard exists because the failure is silent otherwise: the survival curve
        keeps returning numbers past the end of its evidence.
    """
    survival = np.atleast_2d(np.asarray(survival, dtype=float))
    horizon = survival.shape[1]

    if observed_support is not None and horizon > observed_support and not allow_extrapolation:
        raise ExtrapolationError(
            f"horizon {horizon} exceeds the observed support of {observed_support} "
            f"periods. The survival model has no evidence past period "
            f"{observed_support}; extending it assumes the tail hazard rather than "
            "estimating it. Shorten the horizon, or pass allow_extrapolation=True "
            "and state the assumption where the number is reported."
        )

    m = np.asarray(margin, dtype=float)
    if m.ndim == 0:
        m = np.full(survival.shape[0], float(m))
    return (survival * _discount_factors(horizon, annual_discount_rate)).sum(axis=1) * m


def expected_remaining_months(survival: np.ndarray) -> np.ndarray:
    """Undiscounted expected periods of survival remaining, capped at the horizon.

    `sum_t S(t)` is the standard identity for expected residual lifetime in discrete
    time. Reported alongside CLV because it is the number a founder can sanity-check
    against their own intuition, where a discounted money figure is not.
    """
    return np.asarray(survival, dtype=float).sum(axis=1)


def value_at_risk(clv_values: np.ndarray, hazard_next: np.ndarray) -> np.ndarray:
    """Expected value lost in the coming period: `CLV * P(churn next period)`.

    This is the quantity that a naive churn score is a *proxy* for, and stating it
    this way makes the proxy's failure visible: ranking by `hazard_next` alone
    ignores `clv_values` entirely, so it treats a departing $9 customer as equal to a
    departing $900 one. It is still not a targeting rule -- money at risk is not the
    same as money you can *save*, which needs a treatment effect (D-026). That is
    Phase 4.
    """
    return np.asarray(clv_values, dtype=float) * np.asarray(hazard_next, dtype=float)


def value_shortfall_by_cause(
    cumulative_incidence: dict[int, np.ndarray],
    margin: np.ndarray | float,
    annual_discount_rate: float = 0.12,
) -> dict[int, np.ndarray]:
    """Discounted value lost to each competing cause, over the horizon.

    Exact rather than apportioned. Writing `F(t) = 1 - S(t) = sum_k CIF_k(t)`, the
    gap between perfect retention and actual expected value is

        V0 - V = sum_t discount^t * margin * F(t)
               = sum_k [ sum_t discount^t * margin * CIF_k(t) ]

    so the causes decompose the shortfall additively with no residual. That identity
    is asserted in `test_cause_shortfalls_sum_to_the_total_shortfall`.

    Why it matters commercially: this is the number that says whether the money is
    leaking through the billing system or through the product. They have different
    fixes and different costs, and a single blended churn figure cannot tell you
    which you have (D-001).
    """
    any_cif = next(iter(cumulative_incidence.values()))
    horizon = np.atleast_2d(any_cif).shape[1]
    factors = _discount_factors(horizon, annual_discount_rate)

    m = np.asarray(margin, dtype=float)
    if m.ndim == 0:
        m = np.full(np.atleast_2d(any_cif).shape[0], float(m))

    return {
        cause: (np.atleast_2d(np.asarray(cif, dtype=float)) * factors).sum(axis=1) * m
        for cause, cif in cumulative_incidence.items()
    }


def treatment_value(
    clv_values: np.ndarray, tau: np.ndarray, cost: float | np.ndarray
) -> np.ndarray:
    """Net value of treating a customer: `(-tau) * CLV - cost`.

    Sign convention follows the rest of the project: `tau = P(churn | treated) -
    P(churn | control)`, so a **negative** tau is a treatment that helps and
    invariant 4 requires the mean to stay negative.

    This is the bridge Phase 3 exists to build. Phase 4's estimate of `tau` is a
    probability; a decision needs money, and money is `tau` multiplied by what the
    customer is worth. Treating a high-risk customer worth $12 and a low-risk one
    worth $1,200 are not comparable acts, and no amount of churn-model accuracy
    tells them apart.

    It is deliberately a plain function of an *estimated* tau. It does not decide
    anything: the abstention rule needs the posterior width of tau, not its point
    estimate, and that is Phase 4.
    """
    return -np.asarray(tau, dtype=float) * np.asarray(clv_values, dtype=float) - np.asarray(
        cost, dtype=float
    )
