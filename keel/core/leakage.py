"""Leakage detection.

Leakage is information reaching a model that would not have existed at prediction
time. It is the most common serious error in churn work and it is uniquely dangerous
because **it makes results look better**. Nobody investigates a metric that improved.

This module provides three independent checks. They are independent on purpose --
each catches things the others cannot.

1. **Availability audit** (structural). Verifies that no source row used to build a
   feature was unknowable at the time. Catches bugs in the feature engine itself.

2. **Time-travel consistency** (behavioural). Features computed as-of T must not
   change when more data arrives afterwards. Catches accidental dependence on
   dataset state rather than on history.

3. **Canary injection** (adversarial, and the important one). Deliberately plant a
   feature built from the future and confirm the detector flags it.

Point 3 deserves emphasis. **A leakage suite that has never caught a leak is
evidence of nothing.** It might be working, or it might be checking a condition that
is trivially true. Planting known leaks and requiring they be caught is the only way
to know the machinery has teeth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from keel.core.features import FeatureSpec, FeatureStore
from keel.core.schema import TABLES


@dataclass
class AuditReport:
    """Result of a leakage audit."""

    passed: bool
    checks_run: int
    violations: list[str] = field(default_factory=list)
    suspicious_features: dict[str, float] = field(default_factory=dict)
    """Feature name -> single-feature AUC, for anything implausibly predictive."""

    def __bool__(self) -> bool:
        return self.passed

    def summary(self) -> str:
        head = (
            f"{'PASS' if self.passed else 'FAIL'} "
            f"({self.checks_run} checks, {len(self.violations)} violations)"
        )
        if self.violations:
            head += "\n" + "\n".join("  - " + v for v in self.violations)
        if self.suspicious_features:
            head += "\n  suspicious features (single-feature AUC):"
            for name, auc in sorted(
                self.suspicious_features.items(), key=lambda kv: -kv[1]
            ):
                head += f"\n    {name:<32} {auc:.3f}"
        return head


def audit_availability(
    store: FeatureStore, as_of: pd.Timestamp, specs: list[FeatureSpec]
) -> AuditReport:
    """Verify that every source row reachable at `as_of` was knowable by then.

    Checks the tables the given specs actually read, rather than all of them, so
    the report reflects the features in question.
    """
    as_of = pd.Timestamp(as_of)
    violations: list[str] = []
    checked = 0

    for table_name in sorted({s.table for s in specs}):
        table = TABLES[table_name]
        if not table.is_fact:
            continue
        rows = store._visible(table_name, as_of)
        checked += 1
        if rows.empty:
            continue

        late = rows[rows[table.available_at] > as_of]
        if not late.empty:
            violations.append(
                f"{table_name}: {len(late)} rows became knowable after {as_of}"
            )
        future = rows[rows[table.occurred_at] > as_of]
        if not future.empty:
            violations.append(
                f"{table_name}: {len(future)} rows occur after {as_of}"
            )

    return AuditReport(passed=not violations, checks_run=checked, violations=violations)


def audit_time_travel(
    store: FeatureStore,
    as_of: pd.Timestamp,
    customer_ids: np.ndarray,
    specs: list[FeatureSpec],
    later_store: FeatureStore | None = None,
) -> AuditReport:
    """Features computed as-of T must not change when later data arrives.

    `later_store` holds a superset of the data (the same tenant, observed further
    into the future). If a feature's as-of-T value differs between the two, it
    depends on dataset state rather than on history alone -- which means the value
    used in training was never available in production.
    """
    if later_store is None:
        later_store = store

    before = store.build(as_of, customer_ids, specs).set_index("customer_id")
    after = later_store.build(as_of, customer_ids, specs).set_index("customer_id")

    violations = []
    for spec in specs:
        a = before[spec.name].to_numpy(dtype=float)
        b = after.loc[before.index, spec.name].to_numpy(dtype=float)
        if not np.allclose(a, b, equal_nan=True):
            n = int((~np.isclose(a, b, equal_nan=True)).sum())
            violations.append(
                f"{spec.name}: {n} values changed when later data was added"
            )

    return AuditReport(passed=not violations, checks_run=len(specs), violations=violations)


def detect_suspicious_features(
    features: pd.DataFrame,
    outcome: np.ndarray,
    feature_names: list[str],
    threshold: float = 0.85,
) -> AuditReport:
    """Flag features that predict the outcome implausibly well on their own.

    A single feature reaching 0.85+ AUC on churn is almost never a genuine signal.
    Real leading indicators of churn are individually weak; churn is driven by many
    small factors plus a great deal of noise. A lone feature that nails it is nearly
    always a consequence of the outcome rather than a cause of it.

    This is a heuristic and it produces false positives, so it reports rather than
    raises. Treat a hit as "explain this feature", not "delete this feature".
    """
    suspicious: dict[str, float] = {}
    y = np.asarray(outcome)

    if len(np.unique(y)) < 2:
        return AuditReport(passed=True, checks_run=0)

    for name in feature_names:
        if name not in features:
            continue
        x = features[name].to_numpy(dtype=float).reshape(-1, 1)
        if not np.isfinite(x).all() or np.std(x) < 1e-12:
            continue
        # AUC is symmetric under inversion, so a strongly *negative* association is
        # just as suspicious as a positive one.
        auc = roc_auc_score(y, x.ravel())
        auc = max(auc, 1.0 - auc)
        if auc >= threshold:
            suspicious[name] = float(auc)

    return AuditReport(
        passed=not suspicious,
        checks_run=len(feature_names),
        suspicious_features=suspicious,
        violations=[
            f"{n}: single-feature AUC {a:.3f} exceeds {threshold}"
            for n, a in suspicious.items()
        ],
    )


def inject_canary(
    features: pd.DataFrame, outcome: np.ndarray, strength: float = 0.9, seed: int = 0
) -> tuple[pd.DataFrame, str]:
    """Plant a deliberately leaked feature, for testing the detector.

    The canary is the outcome itself with `1 - strength` of the labels flipped, so
    it is strongly but not perfectly predictive -- a perfect copy would be caught by
    even a broken detector, which would prove nothing.

    Returns the frame with the canary added, and its column name.
    """
    rng = np.random.default_rng(seed)
    y = np.asarray(outcome).astype(float)
    flip = rng.random(len(y)) > strength
    canary = np.where(flip, 1.0 - y, y) + rng.normal(0, 0.01, len(y))

    out = features.copy()
    out["__canary_leaked_outcome"] = canary
    return out, "__canary_leaked_outcome"


def model_auc(
    features: pd.DataFrame, outcome: np.ndarray, feature_names: list[str], seed: int = 0
) -> float:
    """AUC of a simple model on the given features. Used to compare feature sets.

    Logistic regression rather than gradient boosting: the question here is how much
    signal the *features* carry, and a simpler model makes that comparison cleaner.
    """
    y = np.asarray(outcome)
    if len(np.unique(y)) < 2:
        return float("nan")

    cols = [c for c in feature_names if c in features]
    X = features[cols].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    # Standardise so the regulariser treats features comparably.
    X = (X - X.mean(axis=0)) / np.maximum(X.std(axis=0), 1e-9)

    model = LogisticRegression(max_iter=2000, random_state=seed)
    model.fit(X, y)
    return float(roc_auc_score(y, model.predict_proba(X)[:, 1]))
