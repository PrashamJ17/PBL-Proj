"""Phase 3 -- customer lifetime value from a survival curve.

Contractual CLV only. Non-contractual (BTYD) is Phase 7 and is a different estimand:
there, churn is never observed and has to be inferred from purchase gaps.
"""

from retainiq.models.clv.value import (
    ExtrapolationError,
    clv,
    expected_remaining_months,
    monthly_discount,
    treatment_value,
    value_at_risk,
    value_shortfall_by_cause,
)

__all__ = [
    "ExtrapolationError",
    "clv",
    "expected_remaining_months",
    "monthly_discount",
    "treatment_value",
    "value_at_risk",
    "value_shortfall_by_cause",
]
