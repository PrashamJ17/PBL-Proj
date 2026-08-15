"""Point-in-time feature store.

Computes features as they would have looked at a past moment, using only facts that
were *knowable* at that moment.

Why this module exists
----------------------
The most common serious error in churn work is training a model on information that
did not exist when the prediction would have been made. It produces spectacular
backtest numbers and a model that collapses in production. It is easy to do by
accident and almost impossible to spot by reading the results, because the results
look *better*.

Two distinct forms, both handled here:

**Outcome leakage.** A feature that is a consequence of the outcome. "Opened a support
ticket about refunds" predicts churn superbly, because the customer opened it while
cancelling. At prediction time it does not exist.

**Availability leakage.** The subtler one. A fact that happened before the prediction
but was not *knowable* until after it. A card decline settles two days later; a nightly
sentiment batch scores yesterday's tickets this morning. Filtering on when things
happened rather than when they became visible silently grants the model a look ahead.

The guarantee is structural, not procedural
-------------------------------------------
Every feature reads its source rows through exactly one function, `_visible`, which
filters on ``available_at <= as_of``. There is no way to add a feature that bypasses
it, because there is no other path to the data. Guarantees that depend on remembering
to do the right thing are not guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from retainiq.core.schema import TABLES, Dataset


@dataclass(frozen=True)
class FeatureSpec:
    """Declarative definition of one feature.

    Declarative rather than a function so that features can be *audited* -- we can
    ask which source rows a feature is permitted to touch without running it. A
    lambda cannot be interrogated that way.
    """

    name: str
    table: str
    kind: str
    """count | sum | mean | max | nunique | recency_days | age_days | constant"""
    column: str | None = None
    window_days: int | None = None
    """Lookback window. None means all history up to `as_of`."""
    where: dict[str, str] | None = None
    """Equality filters, e.g. {'status': 'failed'}."""
    fill: float = 0.0
    """Value when no source rows match. For recency features prefer a large
    sentinel -- 'never happened' is not the same as 'happened today'."""
    doc: str = ""


class LeakageError(RuntimeError):
    """Raised when a feature computation would have used unknowable data."""


class FeatureStore:
    """Builds point-in-time-correct feature vectors from a canonical `Dataset`."""

    #: The only safe value. The others exist solely to quantify what the safeguard
    #: buys, and are used by `retainiq.experiments.leakage_penalty`.
    SAFE = "available_at"
    #: Filter on when facts *happened*, ignoring when they became knowable. The
    #: subtle bug: correct-looking, and wrong by exactly the settlement lag.
    UNSAFE_OCCURRED_ONLY = "occurred_at"
    #: No temporal filter at all -- aggregate over the entire dataset. The common
    #: catastrophic bug, and the one that produces 0.9+ AUC in a doomed backtest.
    UNSAFE_NO_FILTER = "none"

    def __init__(self, dataset: Dataset, strict: bool = True, mode: str = SAFE):
        self.data = dataset
        self.strict = strict
        """When True (default), every build re-verifies that no row used was
        unknowable at `as_of`. Costs a little time and has caught real bugs."""
        if mode not in (self.SAFE, self.UNSAFE_OCCURRED_ONLY, self.UNSAFE_NO_FILTER):
            raise ValueError(f"unknown mode {mode!r}")
        self.mode = mode
        """Which temporal filter to apply. **Only `SAFE` is correct.** The unsafe
        modes are deliberately available so that the cost of getting this wrong can
        be measured rather than merely asserted -- see
        `retainiq.experiments.leakage_penalty`. Nothing in the production path may
        construct a store with anything other than the default; a test enforces it."""

    # --- the single gate through which all source data passes ----------------

    def _visible(self, table_name: str, as_of: pd.Timestamp) -> pd.DataFrame:
        """Rows of `table_name` that were knowable at `as_of`.

        **This is the only path to source data in this module.** Every feature is
        computed from its output. Filtering on `available_at` rather than
        `occurred_at` is what prevents availability leakage.
        """
        frame = getattr(self.data, table_name)
        table = TABLES[table_name]

        if frame.empty:
            return frame

        if not table.is_fact:
            # Dimension tables: use the row's own creation time where present.
            if "created_at" in frame.columns:
                return frame[frame["created_at"] <= as_of]
            return frame

        if self.mode == self.UNSAFE_NO_FILTER:
            return frame
        if self.mode == self.UNSAFE_OCCURRED_ONLY:
            return frame[frame[table.occurred_at] <= as_of]

        visible = frame[frame[table.available_at] <= as_of]

        if self.strict:
            # Belt and braces. `validate()` guarantees available_at >= occurred_at,
            # so this should be unreachable -- which is exactly why it is worth
            # asserting. If it ever fires, an adapter is writing bad timestamps and
            # every point-in-time guarantee downstream is void.
            future = visible[visible[table.occurred_at] > as_of]
            if not future.empty:
                raise LeakageError(
                    f"{table_name}: {len(future)} rows are marked available at "
                    f"{as_of} but occur after it. An ingest adapter has confused "
                    f"occurred_at with available_at."
                )
        return visible

    # --- feature computation -------------------------------------------------

    def build(
        self,
        as_of: pd.Timestamp,
        customer_ids: np.ndarray | list[str],
        specs: list[FeatureSpec],
    ) -> pd.DataFrame:
        """Feature vectors for `customer_ids` as of a single moment."""
        as_of = pd.Timestamp(as_of)
        out = pd.DataFrame({"customer_id": list(customer_ids), "as_of": as_of})

        for spec in specs:
            out[spec.name] = self._compute(spec, as_of, out["customer_id"]).to_numpy()
        return out

    def build_panel(
        self,
        as_of_times: list[pd.Timestamp],
        customers_at: dict[pd.Timestamp, np.ndarray],
        specs: list[FeatureSpec],
    ) -> pd.DataFrame:
        """Feature vectors across many moments -- a training set.

        `customers_at` gives the at-risk population per timestamp, so churned
        customers correctly drop out rather than contributing phantom rows.

        Deliberately a loop over timestamps: each is an independent point-in-time
        computation. A vectorised as-of join would be faster and would make it far
        easier to leak across the time boundary by accident. Correctness first;
        this is not the bottleneck at Phase 1 scale.
        """
        frames = [
            self.build(t, customers_at[t], specs)
            for t in as_of_times
            if len(customers_at.get(t, ()))
        ]
        if not frames:
            return pd.DataFrame(columns=["customer_id", "as_of", *[s.name for s in specs]])
        return pd.concat(frames, ignore_index=True)

    def _compute(
        self, spec: FeatureSpec, as_of: pd.Timestamp, customer_ids: pd.Series
    ) -> pd.Series:
        rows = self._visible(spec.table, as_of)
        table = TABLES[spec.table]

        if spec.where and not rows.empty:
            for col, val in spec.where.items():
                rows = rows[rows[col] == val]

        if spec.window_days is not None and not rows.empty and table.is_fact:
            cutoff = as_of - pd.Timedelta(days=spec.window_days)
            rows = rows[rows[table.occurred_at] > cutoff]

        index = pd.Index(customer_ids, name="customer_id")

        if rows.empty:
            return pd.Series(spec.fill, index=index, dtype=float)

        grouped = rows.groupby("customer_id")

        if spec.kind == "count":
            values = grouped.size()
        elif spec.kind == "sum":
            values = grouped[spec.column].sum()
        elif spec.kind == "mean":
            values = grouped[spec.column].mean()
        elif spec.kind == "max":
            values = grouped[spec.column].max()
        elif spec.kind == "nunique":
            values = grouped[spec.column].nunique()
        elif spec.kind == "recency_days":
            last = grouped[table.occurred_at].max()
            values = (as_of - last).dt.total_seconds() / 86400.0
        elif spec.kind == "age_days":
            first = grouped[spec.column or table.occurred_at].min()
            values = (as_of - first).dt.total_seconds() / 86400.0
        elif spec.kind == "constant":
            values = grouped[spec.column].last()
        else:
            raise ValueError(f"unknown feature kind {spec.kind!r}")

        return values.reindex(index).fillna(spec.fill).astype(float)


def ratio(
    frame: pd.DataFrame, name: str, numerator: str, denominator: str, fill: float = 1.0
) -> pd.DataFrame:
    """Add a ratio of two already-computed features.

    Kept as a post-step rather than a feature `kind` because both inputs must be
    computed point-in-time first; deriving it inside the engine would invite
    computing one side from a different vintage than the other.
    """
    den = frame[denominator].to_numpy()
    num = frame[numerator].to_numpy()
    frame[name] = np.where(den > 0, num / np.maximum(den, 1e-9), fill)
    return frame


# --- the standard feature set ----------------------------------------------

STANDARD_FEATURES: list[FeatureSpec] = [
    # Tenure. Early-tenure hazard is elevated (failure to activate).
    FeatureSpec("tenure_days", "subscriptions", "age_days", column="started_at",
                doc="Days since the subscription began."),
    FeatureSpec("mrr", "subscriptions", "max", column="mrr",
                doc="Current monthly recurring revenue."),

    # Engagement. The dominant observable signal -- and the one correlated with
    # sleeping-dog risk, which is why it must never be used for targeting alone.
    FeatureSpec("sessions_30d", "events", "count", window_days=30,
                where={"name": "session_start"}),
    FeatureSpec("sessions_prev_30d", "events", "count", window_days=60,
                where={"name": "session_start"},
                doc="60-day count; combined with the 30-day count to form a trend."),
    FeatureSpec("days_since_last_session", "events", "recency_days", window_days=365,
                where={"name": "session_start"}, fill=365.0,
                doc="Sentinel 365 for 'never', which is not the same as 'today'."),
    FeatureSpec("distinct_features_30d", "events", "nunique", column="name", window_days=30,
                doc="Breadth of product surface used. The Prime attach-rate effect."),

    # Billing health. Involuntary churn is a separate process from voluntary.
    FeatureSpec("payment_failures_90d", "invoices", "count", window_days=90,
                where={"status": "failed"}),
    FeatureSpec("payment_failures_ltd", "invoices", "count", where={"status": "failed"}),
    FeatureSpec("days_since_last_failure", "invoices", "recency_days",
                where={"status": "failed"}, fill=999.0),
    FeatureSpec("amount_paid_180d", "invoices", "sum", column="amount", window_days=180,
                where={"status": "paid"}),

    # Support friction.
    FeatureSpec("tickets_90d", "tickets", "count", window_days=90),
    FeatureSpec("days_since_last_ticket", "tickets", "recency_days", fill=999.0),

    # Contact fatigue. Repeatedly messaging someone is itself a churn risk, and a
    # policy that ignores it will over-contact the same customers every cycle.
    FeatureSpec("interventions_ltd", "interventions", "count", where={"arm": "treatment"}),
    FeatureSpec("days_since_last_intervention", "interventions", "recency_days",
                where={"arm": "treatment"}, fill=999.0),
]

FEATURE_NAMES: list[str] = [s.name for s in STANDARD_FEATURES] + ["engagement_trend"]


def build_standard(
    store: FeatureStore,
    as_of_times: list[pd.Timestamp],
    customers_at: dict[pd.Timestamp, np.ndarray],
) -> pd.DataFrame:
    """The standard feature set, including derived ratios."""
    frame = store.build_panel(as_of_times, customers_at, STANDARD_FEATURES)
    if frame.empty:
        return frame
    # Recent activity relative to the preceding period. Falling engagement is a
    # stronger signal than low engagement -- a customer who was always quiet is
    # different from one who just went quiet.
    frame["prior_30d"] = (frame["sessions_prev_30d"] - frame["sessions_30d"]).clip(lower=0)
    frame = ratio(frame, "engagement_trend", "sessions_30d", "prior_30d", fill=1.0)
    return frame.drop(columns=["prior_30d"])
