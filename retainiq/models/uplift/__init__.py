"""Phase 4 — treatment-effect estimation with a posterior, and the rule that uses it."""

from retainiq.models.uplift.abstention import AbstentionPolicy, Decision
from retainiq.models.uplift.bayesian import (
    CATEPosterior,
    HierarchicalCATE,
    pool_across_tenants,
)

__all__ = [
    "AbstentionPolicy",
    "CATEPosterior",
    "Decision",
    "HierarchicalCATE",
    "pool_across_tenants",
]
