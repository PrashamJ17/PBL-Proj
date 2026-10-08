"""A re-implementation of Lemmens & Gupta (2020), as a baseline for the abstention rule.

Lemmens, A., & Gupta, S. (2020). Managing Churn to Maximize Profits. *Marketing Science*,
39(5), 956-973. Read from the authors' manuscript of December 2019.

**This is not their code.** It is written from the description in their paper, so that
their published method can stand beside this project's on the same data. Three pieces:

1. `profit_curve` and `choose_fraction` are their rule for **how many customers to
   target** (their Section 5.2, Equations 8 and 9). Rank a validation sample by the
   model's score; for every campaign size S, estimate the campaign's profit from the
   randomised data as S times the difference, among the top S, between the mean net
   outcome of the treated and the mean outcome of the controls; take the S with the
   highest estimate.
2. `ProfitLossBoosting` is their **profit-based loss** (Section 4.2, Equation 7) fitted
   by stochastic gradient boosting with symmetric weights.
3. `FirstStage` turns a randomised pilot into the expected profit lift per customer that
   the loss is fitted to (Section 5.1.1).

Where this departs from the paper, and each departure is stated in D-075:

- The first stage is a T-learner with gradient boosting. Theirs is an uplift random
  forest.
- Cash flow is the customer value supplied by the caller. Theirs is estimated by nearest
  neighbours.
- Expected profit lifts are divided by their standard deviation before the second stage
  is fitted. Equation 7 puts the profit lift in an exponent, and in currency units that
  overflows. Their target-size rule uses only the ranking, which scaling preserves.
- **A campaign of size zero is allowed**, with profit zero. Their enumeration starts at
  one. Zero lets their rule decline to act, which the abstention rule can.
- A size is considered only if `MIN_ARM` treated and `MIN_ARM` control customers fall in
  the top S. Below that the estimate is noise, and a maximum over sizes would select it.

The last two are in their favour and were fixed before any result was seen
(`docs/PREREG-checks-and-baseline.md`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.tree import DecisionTreeRegressor

#: Fewest treated, and fewest control, customers in the top S for that size to be
#: considered. Fixed in the pre-registration.
MIN_ARM = 10


# --- how many to target -------------------------------------------------------


def profit_curve(
    scores: np.ndarray,
    treated: np.ndarray,
    churned: np.ndarray,
    value: np.ndarray,
    cost: np.ndarray | float,
    min_arm: int = MIN_ARM,
) -> pd.DataFrame:
    """Estimated profit of targeting the top S customers, for every S.

    Their Equations 8b and 9, for an offer whose cost is paid whether or not the
    customer stays. Among the top S by score:

        per customer = mean over treated of (retained * value)
                     - mean over controls of (retained * value)
                     - mean cost
        profit(S)    = S * per customer

    `profit` is NaN where either arm has fewer than `min_arm` customers in the top S:
    there is then no comparison to make, and the caller must not treat a missing
    estimate as zero.
    """
    scores = np.asarray(scores, dtype=float)
    treated = np.asarray(treated).astype(bool)
    kept = (1.0 - np.asarray(churned, dtype=float)) * np.asarray(value, dtype=float)
    cost = np.broadcast_to(np.asarray(cost, dtype=float), scores.shape)
    if not (len(scores) == len(treated) == len(kept)):
        raise ValueError("scores, treated, churned and value must be the same length")
    if np.any(~np.isfinite(scores)):
        raise ValueError("scores must be finite: a customer who cannot be ranked "
                         "cannot be placed in a campaign")

    order = np.argsort(-scores, kind="stable")
    t, kept, cost = treated[order], kept[order], cost[order]
    size = np.arange(1, len(scores) + 1)
    n_t, n_c = np.cumsum(t), np.cumsum(~t)
    sum_t, sum_c = np.cumsum(np.where(t, kept, 0.0)), np.cumsum(np.where(t, 0.0, kept))

    with np.errstate(invalid="ignore", divide="ignore"):
        per_customer = sum_t / n_t - sum_c / n_c - np.cumsum(cost) / size
    enough = (n_t >= min_arm) & (n_c >= min_arm)
    profit = np.where(enough, size * per_customer, np.nan)
    return pd.DataFrame({"size": size, "n_treated": n_t, "n_control": n_c, "profit": profit})


def choose_fraction(
    scores: np.ndarray,
    treated: np.ndarray,
    churned: np.ndarray,
    value: np.ndarray,
    cost: np.ndarray | float,
    max_fraction: float | None = None,
    min_arm: int = MIN_ARM,
) -> tuple[float, float]:
    """The share of customers to target, and the profit their rule expects from it.

    Returns `(fraction, estimated_profit)`. The fraction is `S*/N` on the validation
    sample; zero when no size is estimated to make money, including when no size has
    enough customers in both arms to be estimated at all.

    `max_fraction` is a ceiling on the share. The sizes searched go up to the nearest
    whole customer, which on a small validation sample can be a fraction of a customer
    over the ceiling (37 of 122 is 30.3%), so the share returned is capped as well: a
    budget that one rule may exceed by rounding is not the same budget.
    """
    curve = profit_curve(scores, treated, churned, value, cost, min_arm)
    if max_fraction is not None:
        curve = curve[curve["size"] <= int(round(max_fraction * len(scores)))]
    curve = curve.dropna(subset=["profit"])
    if curve.empty:
        return 0.0, 0.0
    best = curve.loc[curve["profit"].idxmax()]
    if best["profit"] <= 0:
        return 0.0, 0.0
    fraction = float(best["size"]) / len(scores)
    if max_fraction is not None:
        fraction = min(fraction, max_fraction)
    return fraction, float(best["profit"])


def top_fraction(scores: np.ndarray, fraction: float) -> np.ndarray:
    """Treat the top share of a ranking. The share was chosen elsewhere."""
    scores = np.asarray(scores, dtype=float)
    k = int(round(fraction * len(scores)))
    mask = np.zeros(len(scores), dtype=bool)
    if k > 0:
        mask[np.argsort(-scores, kind="stable")[:k]] = True
    return mask


# --- the first stage: expected profit lift per customer -------------------------


def _probability_model(X: pd.DataFrame, y: np.ndarray, seed: int):
    """P(churn | X) for one arm, or the arm's churn rate when it cannot be modelled.

    At a few dozen customers an arm can contain a single outcome. A classifier cannot be
    fitted to that; the arm's rate is the honest estimate, and it is the same for
    everyone.
    """
    y = np.asarray(y).astype(int)
    if len(np.unique(y)) < 2:
        rate = float(y.mean()) if len(y) else 0.0
        return lambda Z: np.full(len(Z), rate)
    model = HistGradientBoostingClassifier(
        max_iter=150, learning_rate=0.06, max_depth=3, random_state=seed
    ).fit(X, y)
    return lambda Z: model.predict_proba(Z)[:, 1]


@dataclass
class FirstStage:
    """Churn probability with and without the offer, from a randomised pilot."""

    control: object
    treatment: object

    @classmethod
    def fit(cls, X: pd.DataFrame, treated: np.ndarray, churned: np.ndarray,
            seed: int = 0) -> FirstStage:
        treated = np.asarray(treated).astype(bool)
        if treated.all() or (~treated).all():
            raise ValueError("the pilot has only one arm: there is no effect to estimate")
        return cls(control=_probability_model(X[~treated], churned[~treated], seed + 1),
                   treatment=_probability_model(X[treated], churned[treated], seed))

    def profit_lift(self, X: pd.DataFrame, value: np.ndarray,
                    cost: np.ndarray | float) -> np.ndarray:
        """Expected money from treating each customer: the fall in churn probability
        times what the customer is worth, less the offer."""
        fall = self.control(X) - self.treatment(X)
        return fall * np.asarray(value, dtype=float) - np.asarray(cost, dtype=float)


# --- the second stage: their profit-based loss ----------------------------------


class ProfitLossBoosting:
    """Stochastic gradient boosting with the profit-based loss of their Equation 7.

        loss_i = w_i * log(1 + exp(-2 * E(pi_i) * F(x_i))),    w_i = |E(pi_i)|

    `E(pi_i)` is the customer's expected profit lift from the first stage and `F` is the
    score being learnt. Symmetric weights: a customer counts in proportion to the money
    at stake, whether it would be gained or lost.

    Trees have at most eight terminal nodes, as in the paper. Each round fits a tree to
    the negative gradient on a random half of the customers and moves each leaf by the
    mean negative gradient inside it, shrunk by the learning rate.

    **Why a gradient step and not a Newton step.** The paper says the loss "ensures that
    customers with a higher profit lift earn a higher score". A Newton step does not
    deliver that: the curvature of this loss grows with the cube of the profit lift, so
    the step is roughly one over it, and among customers the offer helps, the ones it
    helps *least* end up ranked first. The gradient step ranks by profit lift, which is
    what they describe and is the better case for their method. `newton=True` keeps the
    other variant so that the comparison can be shown not to depend on the choice. Their
    Web Appendix D, which would settle it, was not available.
    """

    def __init__(self, n_rounds: int = 150, learning_rate: float = 0.05,
                 max_leaf_nodes: int = 8, subsample: float = 0.5, seed: int = 0,
                 newton: bool = False):
        self.n_rounds, self.learning_rate = n_rounds, learning_rate
        self.max_leaf_nodes, self.subsample, self.seed = max_leaf_nodes, subsample, seed
        self.newton = newton
        self._trees: list[tuple[DecisionTreeRegressor, np.ndarray]] = []

    def fit(self, X: pd.DataFrame, profit_lift: np.ndarray) -> ProfitLossBoosting:
        X = np.asarray(X, dtype=float)
        profit = np.asarray(profit_lift, dtype=float)
        if len(X) != len(profit):
            raise ValueError("one expected profit lift per customer is required")
        if np.any(~np.isfinite(profit)):
            raise ValueError("expected profit lifts must be finite")

        self._trees = []
        scale = float(profit.std())
        if scale == 0.0 or len(profit) < 2:
            # Every customer has the same expected profit lift, so there is no ranking
            # to learn. The score is constant and says so by being zero.
            return self
        e = profit / scale
        w = np.abs(e)

        rng = np.random.default_rng(self.seed)
        n = len(e)
        take = min(n, max(int(round(self.subsample * n)), 2 * self.max_leaf_nodes))
        F = np.zeros(n)
        for b in range(self.n_rounds):
            z = np.clip(2.0 * e * F, -30.0, 30.0)
            gradient = w * 2.0 * e / (1.0 + np.exp(z))
            hessian = w * 4.0 * e * e * np.exp(z) / (1.0 + np.exp(z)) ** 2

            rows = rng.choice(n, size=take, replace=False)
            tree = DecisionTreeRegressor(
                max_leaf_nodes=self.max_leaf_nodes, random_state=self.seed + b
            ).fit(X[rows], gradient[rows])

            leaf_of_row = tree.apply(X[rows])
            step = np.zeros(tree.tree_.node_count)
            for leaf in np.unique(leaf_of_row):
                inside = leaf_of_row == leaf
                if self.newton:
                    step[leaf] = np.clip(
                        gradient[rows][inside].sum()
                        / max(hessian[rows][inside].sum(), 1e-12), -4.0, 4.0)
                else:
                    step[leaf] = gradient[rows][inside].mean()
            self._trees.append((tree, step))
            F += self.learning_rate * step[tree.apply(X)]
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Higher means target sooner. The scale carries no meaning; only the order does."""
        X = np.asarray(X, dtype=float)
        F = np.zeros(len(X))
        for tree, step in self._trees:
            F += self.learning_rate * step[tree.apply(X)]
        return F
