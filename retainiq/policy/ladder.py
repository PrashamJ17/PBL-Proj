"""Choosing *which* offer, not just whether to make one.

Phases 0-4 all asked the same question with one offer held fixed: given this discount,
who should get it? D-055 showed that question usually has a degenerate answer. When the
offer is nearly free and helps on average, treating everyone wins and targeting adds
nothing; when it is expensive enough to matter, nothing beats leaving the money alone.
The interesting decision lives between those, and it is **which rung of the ladder**.

That reframing is the point of the ladder (plan section 5.1): interventions ordered by
margin cost, discounts last. A feature nudge costs 0.10 and a 40% discount costs 130,
and the same customer can be worth nudging and not worth discounting. A policy that can
only say yes or no to one offer cannot express that.

What this costs, and why it is charged honestly
-----------------------------------------------
Effects are **rung-specific and must be learned per rung**, from a pilot that randomised
across arms. A model fitted on discount data cannot tell you what a nudge would do; the
simulator knows, via `saveability_multiplier`, but a real business does not, and helping
ourselves to it would be exactly the kind of oracle knowledge this project refuses
(D-012). So the pilot is split `K + 1` ways, and at n = 500 each arm holds roughly 35
people. Learning six offers from a small business's data is *harder* than learning one,
not easier, and the results say so.

Partial pooling across rungs is what makes it survivable at all. The rungs are not
unrelated treatments: they are ordered by intensity, and a customer who responds to a
check-in call is more likely to respond to a downgrade than a coin flip would suggest.
`pool_across_tenants` already implements exactly this shrinkage for firms (D-041); the
same mechanism is applied here across arms, which is the cross-tenant machinery earning
its keep a phase early.

Selection rule
--------------
For each rung `k` the posterior over net benefit is `B_ik` (in currency, via
`economics.benefit_posterior`, so the D-057 units error cannot recur). The rule picks

    argmax_k  E[B_ik] - lambda * SD[B_ik]      subject to that quantity being > 0

and abstains when no rung clears zero. `lambda = 0` is risk-neutral expected value;
larger values demand a margin proportional to how uncertain the estimate is. The
parameter is swept rather than chosen, because D-056 established that a single fixed
confidence level cannot be right across offers whose downside differs by three orders of
magnitude, and replacing one arbitrary constant with another would not be progress.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from retainiq.models.uplift.bayesian import HierarchicalCATE, pool_across_tenants
from retainiq.policy.economics import benefit_posterior

__all__ = ["LadderOptimiser", "Recommendation", "ABSTAIN"]

#: Rung index meaning "make no offer". Rung 0 of the plan's ladder is the absence of an
#: offer, not an offer, so it is represented as a sentinel rather than an arm.
ABSTAIN = -1


@dataclass
class Recommendation:
    """What to do for each customer, and what we expect it to earn."""

    rung: np.ndarray
    """Index into the offer list, or `ABSTAIN`."""
    expected_value: np.ndarray
    """Risk-adjusted expected money of the chosen action. Zero where abstaining."""
    confidence: np.ndarray
    """`P(net benefit > 0)` for the chosen rung. Zero where abstaining."""
    value_by_rung: np.ndarray
    """`(n, K)` risk-adjusted value of every rung, for reason codes and audit."""
    budget_trimmed: np.ndarray
    """Boolean: a rung *did* clear zero for this customer, but the budget was spent on
    someone worth more. An owner told 'no action' deserves to know which of the two
    happened, because one is a verdict about the customer and the other is a verdict
    about the budget."""

    @property
    def n_treated(self) -> int:
        return int((self.rung != ABSTAIN).sum())

    def counts(self, names: list[str]) -> dict[str, int]:
        """How many customers each rung was chosen for, abstentions included."""
        out = {"abstain": int((self.rung == ABSTAIN).sum())}
        for k, nm in enumerate(names):
            out[nm] = int((self.rung == k).sum())
        return out


class LadderOptimiser:
    """Fit one effect model per rung, then pick the best rung per customer.

    Parameters
    ----------
    risk_aversion:
        `lambda` in the selection rule. `0` maximises expected value; higher values
        require the expected gain to exceed a multiple of its own uncertainty.
    budget:
        Optional cap on the fraction of customers treated. A ceiling, never a quota --
        the rule may and does spend less (the Phase 4 asymmetry, preserved).
    pool_across_rungs:
        Shrink each rung's average effect toward the across-rung mean. This is the only
        thing that makes a `K`-way split of a small pilot workable.
    """

    def __init__(
        self,
        risk_aversion: float = 0.0,
        budget: float | None = None,
        pool_across_rungs: bool = True,
        n_samples: int = 400,
        seed: int | None = 0,
    ):
        if risk_aversion < 0:
            raise ValueError(f"risk_aversion must be >= 0, got {risk_aversion}")
        if budget is not None and not 0.0 <= budget <= 1.0:
            raise ValueError(f"budget must be a fraction in [0, 1], got {budget}")
        self.risk_aversion = risk_aversion
        self.budget = budget
        self.pool_across_rungs = pool_across_rungs
        self.n_samples = n_samples
        self.seed = seed
        self.models_: list[HierarchicalCATE | None] = []
        self.n_rungs_ = 0

    def fit(self, X, arm: np.ndarray, y: np.ndarray, n_rungs: int) -> LadderOptimiser:
        """Fit from a multi-arm pilot.

        `arm` is 0 for the untreated control and `k + 1` for the customers who received
        rung `k`. Each rung is fitted against the *shared* control arm, which is what
        makes the effects comparable across rungs and is the reason a single control
        group is worth more than K separate two-arm tests.
        """
        arm = np.asarray(arm)
        y = np.asarray(y)
        if len(arm) != len(y) or len(arm) != len(X):
            raise ValueError("X, arm and y must have the same length")
        if not (arm == 0).any():
            raise ValueError(
                "no control arm (arm == 0); treatment effects need untreated customers "
                "to compare against. A pilot with every customer treated cannot work."
            )
        self.n_rungs_ = int(n_rungs)

        control = arm == 0
        first: list[HierarchicalCATE | None] = []
        for k in range(n_rungs):
            keep = control | (arm == k + 1)
            Xi, ti, yi = X[keep], (arm[keep] == k + 1).astype(int), y[keep]
            # A rung the pilot never tried, or one whose arm produced a single outcome
            # value, is not estimable. Recorded as None and never recommended -- the
            # alternative, silently falling back to another rung's effect, would invent
            # evidence.
            try:
                first.append(HierarchicalCATE().fit(Xi, ti, yi))
            except (ValueError, RuntimeError):
                first.append(None)

        fitted = [m for m in first if m is not None]
        if not fitted:
            raise ValueError(
                "no rung produced an estimable effect; the pilot is too small or too "
                "unbalanced for any arm to support one."
            )

        if self.pool_across_rungs and len(fitted) > 1:
            prior = pool_across_tenants(fitted)
            second: list[HierarchicalCATE | None] = []
            for k in range(n_rungs):
                if first[k] is None:
                    second.append(None)
                    continue
                keep = control | (arm == k + 1)
                Xi, ti, yi = X[keep], (arm[keep] == k + 1).astype(int), y[keep]
                try:
                    second.append(HierarchicalCATE(tenant_prior=prior).fit(Xi, ti, yi))
                except (ValueError, RuntimeError):
                    second.append(first[k])
            self.models_ = second
        else:
            self.models_ = first
        return self

    def recommend(self, X, value: np.ndarray, costs: np.ndarray) -> Recommendation:
        """Choose a rung per customer.

        `costs` is `(n, K)` -- the price of each rung for each customer, since a
        percentage discount costs more for a larger account.
        """
        if not self.models_:
            raise RuntimeError("fit() first")
        value = np.asarray(value, dtype=float)
        costs = np.atleast_2d(np.asarray(costs, dtype=float))
        n = len(value)
        if costs.shape != (n, self.n_rungs_):
            raise ValueError(
                f"costs must be ({n}, {self.n_rungs_}), got {costs.shape}"
            )

        # -inf rather than 0 for unestimable rungs: 0 would tie with abstaining and
        # could be selected by argmax on a rung we know nothing about.
        adjusted = np.full((n, self.n_rungs_), -np.inf)
        confidence = np.zeros((n, self.n_rungs_))
        for k, model in enumerate(self.models_):
            if model is None:
                continue
            mp = benefit_posterior(model, X, value, costs[:, k],
                                   n_samples=self.n_samples, seed=self.seed)
            adjusted[:, k] = mp.mean - self.risk_aversion * mp.sd
            confidence[:, k] = mp.prob_positive()

        best = np.argmax(adjusted, axis=1)
        best_val = adjusted[np.arange(n), best]
        rung = np.where(best_val > 0, best, ABSTAIN)
        trimmed = np.zeros(n, dtype=bool)

        if self.budget is not None:
            k_max = int(round(self.budget * n))
            treated = rung != ABSTAIN
            if treated.sum() > k_max:
                # Same asymmetry as Phase 4: the gate is value, the ranking is money.
                order = np.argsort(-np.where(treated, best_val, -np.inf))
                keep = np.zeros(n, dtype=bool)
                keep[order[:k_max]] = True
                trimmed = treated & ~keep
                rung = np.where(keep, rung, ABSTAIN)

        chosen = rung != ABSTAIN
        return Recommendation(
            rung=rung,
            expected_value=np.where(chosen, best_val, 0.0),
            confidence=np.where(chosen, confidence[np.arange(n), best], 0.0),
            value_by_rung=adjusted,
            budget_trimmed=trimmed,
        )
