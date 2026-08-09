"""Phase 4 — treatment-effect estimation with a posterior, and the rule that uses it."""

from keel.models.uplift.abstention import AbstentionPolicy, Decision
from keel.models.uplift.bayesian import (
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
