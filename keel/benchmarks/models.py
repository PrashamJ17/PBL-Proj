"""Targeting models, with a common interface.

Two families, and the distinction between them is the whole point:

**Outcome models** estimate *who will do the thing* — the direct analogue of a churn
score. This is what most practitioners actually deploy.

**Uplift models** estimate *how much treatment changes what someone does*. Positive,
zero, or negative per person.

Hand-rolled on scikit-learn rather than pulled from econml/causalml. Three reasons:
these estimators are a few lines each, the dependency stays out of the Phase 0/1 core,
and a referee can read the implementation. The heavier libraries arrive in Phase 4 when
the estimators genuinely get hard.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier


def _clf(seed: int):
    return HistGradientBoostingClassifier(
        max_iter=150, learning_rate=0.06, max_depth=3, random_state=seed
    )


class Targeter(ABC):
    """Anything that can rank customers for treatment."""

    name: str = "targeter"
    is_uplift: bool = False

    @abstractmethod
    def fit(self, X: pd.DataFrame, t: np.ndarray, y: np.ndarray) -> Targeter: ...

    @abstractmethod
    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Higher means treat sooner. For uplift models this is an estimate of the
        treatment effect and is directly interpretable; for outcome models it is
        merely a propensity and carries no causal meaning."""


# --- outcome models (the "churn score" analogue) ----------------------------


class OutcomePropensity(Targeter):
    """P(Y=1 | X), fitted on everyone regardless of arm.

    The closest analogue to a churn model: it learns who does the thing, from all
    available history, with no notion of intervention.
    """

    name = "outcome_propensity"

    def __init__(self, seed: int = 0):
        self.model = _clf(seed)

    def fit(self, X, t, y):
        self.model.fit(X, y.astype(int))
        return self

    def score(self, X):
        return self.model.predict_proba(X)[:, 1]


class ResponseModel(Targeter):
    """P(Y=1 | X, treated), fitted on the treated arm only.

    The classic direct-marketing response model: "among people we contacted, who
    responded?" then contact people who look like them. Widely deployed, and it
    conflates responding *because of* the contact with responding anyway.
    """

    name = "response_model"

    def __init__(self, seed: int = 0):
        self.model = _clf(seed)

    def fit(self, X, t, y):
        mask = t == 1
        self.model.fit(X[mask], y[mask].astype(int))
        return self

    def score(self, X):
        return self.model.predict_proba(X)[:, 1]


# --- uplift models ----------------------------------------------------------


class TLearner(Targeter):
    """Two separate models, differenced: P(Y|X,T=1) - P(Y|X,T=0).

    Simple and unbiased, but each model sees only half the data and their errors do
    not cancel -- which is exactly the weakness that bites at small n.
    """

    name = "t_learner"
    is_uplift = True

    def __init__(self, seed: int = 0):
        self.treated = _clf(seed)
        self.control = _clf(seed + 1)

    def fit(self, X, t, y):
        self.treated.fit(X[t == 1], y[t == 1].astype(int))
        self.control.fit(X[t == 0], y[t == 0].astype(int))
        return self

    def score(self, X):
        return self.treated.predict_proba(X)[:, 1] - self.control.predict_proba(X)[:, 1]


class SLearner(Targeter):
    """One model with treatment as a feature; score is the counterfactual difference.

    Uses all the data, but a flexible learner will often ignore a single binary
    feature, shrinking estimated effects toward zero.
    """

    name = "s_learner"
    is_uplift = True

    def __init__(self, seed: int = 0):
        self.model = _clf(seed)

    def fit(self, X, t, y):
        Z = X.copy()
        Z["__treatment"] = t.astype(float)
        self.model.fit(Z, y.astype(int))
        return self

    def score(self, X):
        one, zero = X.copy(), X.copy()
        one["__treatment"], zero["__treatment"] = 1.0, 0.0
        return self.model.predict_proba(one)[:, 1] - self.model.predict_proba(zero)[:, 1]


class ClassTransform(Targeter):
    """Lai / Jaskowski class transformation.

    Relabel Z = 1 when (treated and responded) or (control and did not), then fit a
    single classifier. For a balanced trial, uplift is a monotone function of P(Z|X),
    so ranking by it is equivalent to ranking by uplift.

    Assumes roughly equal treatment probability. Hillstrom's arms are balanced by
    design; the propensity correction below keeps it honest when they are not.
    """

    name = "class_transform"
    is_uplift = True

    def __init__(self, seed: int = 0):
        self.model = _clf(seed)
        self.p_treat = 0.5

    def fit(self, X, t, y):
        self.p_treat = float(np.mean(t))
        z = ((t == 1) & (y == 1)) | ((t == 0) & (y == 0))
        self.model.fit(X, z.astype(int))
        return self

    def score(self, X):
        p = self.model.predict_proba(X)[:, 1]
        # 2p - 1 under balance; generalised for unbalanced assignment.
        return p / max(self.p_treat, 1e-6) - (1 - p) / max(1 - self.p_treat, 1e-6)


ALL_TARGETERS: list[type[Targeter]] = [
    OutcomePropensity,
    ResponseModel,
    TLearner,
    SLearner,
    ClassTransform,
]
