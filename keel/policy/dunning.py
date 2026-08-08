"""Retry policies for failed payments.

A policy answers three questions, and most processors only answer the first badly:

1. **When** to retry.
2. **Whether** to retry at all -- some decline codes cannot be fixed by retrying, and
   attempts spent on them are pure waste plus customer irritation.
3. **When to stop**, because every dunning email is also a reminder that the customer
   is paying you (D-032).

The default processor behaviour is a fixed schedule applied uniformly to every decline
reason. That is the baseline to beat, and it is beatable without any machine learning
at all -- simply by conditioning on the decline code, which the processor already told
you.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from keel.sim.dunning import DunningConfig, retry_success_prob


@dataclass
class RetryPolicy:
    """A retry schedule, optionally conditioned on the decline code."""

    name: str
    schedule: tuple[float, ...] = ()
    """Default retry offsets in days after the failure."""
    per_code: dict[str, tuple[float, ...]] = field(default_factory=dict)
    """Overrides by decline code. Empty tuple means 'do not retry this code'."""
    snap_to_payday: frozenset[str] = frozenset()
    """Codes whose retries are moved to the next payday rather than a fixed offset."""
    email_attempts: frozenset[int] = frozenset({1, 2, 3})
    """Which attempt numbers also send the customer an email."""
    doc: str = ""

    def offsets_for(self, code: str) -> tuple[float, ...]:
        return self.per_code.get(code, self.schedule)


def next_payday(
    timestamps: pd.DatetimeIndex, cfg: DunningConfig, min_delay_days: float = 1.0
) -> pd.DatetimeIndex:
    """The next salary date at least `min_delay_days` away, at mid-morning.

    Retrying `insufficient_funds` is a waiting game: the question is not "how long
    should we wait" but "when does the money arrive".
    """
    base = pd.DatetimeIndex(timestamps) + pd.Timedelta(days=min_delay_days)
    paydays = sorted(cfg.payday_days)

    out = []
    for ts in base:
        candidates = [
            ts.replace(day=d, hour=10, minute=0, second=0, microsecond=0)
            for d in paydays
            if d <= ts.days_in_month
        ]
        future = [c for c in candidates if c >= ts]
        if future:
            out.append(future[0])
        else:
            nxt = (ts + pd.offsets.MonthBegin(1)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            out.append(nxt.replace(day=min(paydays[0], nxt.days_in_month)))
    return pd.DatetimeIndex(out)


# --- the policies -----------------------------------------------------------

NO_RETRY = RetryPolicy(
    "no_retry", schedule=(), email_attempts=frozenset(),
    doc="Lose every failed payment. The honest floor.",
)

PROCESSOR_DEFAULT = RetryPolicy(
    "processor_default", schedule=(1.0, 3.0, 5.0, 7.0),
    doc="A fixed schedule applied to every decline reason alike. What most small "
        "businesses get by default, and the baseline worth beating.",
)

FIXED_SMART = RetryPolicy(
    "fixed_smart", schedule=(0.02, 2.0, 6.0, 12.0, 20.0),
    doc="Still code-blind, but better spaced: one immediate attempt for transient "
        "faults, then widening gaps to straddle a salary cycle.",
)

CODE_AWARE = RetryPolicy(
    "code_aware",
    schedule=(1.0, 4.0, 10.0),
    per_code={
        # Transient: retry at once, then give up quickly.
        "processing_error": (0.01, 0.5, 2.0),
        # Timing problem: handled by payday snapping below.
        "insufficient_funds": (1.0, 2.0, 3.0, 4.0),
        # Retrying the same expired card cannot work. Email instead of burning
        # attempts, and let the account updater (if any) do the work.
        "expired_card": (2.0, 9.0),
        # Effectively unrecoverable. One attempt as a formality, then stop --
        # further contact costs goodwill and buys nothing.
        "lost_or_stolen_card": (1.0,),
        "do_not_honor": (2.0, 7.0, 14.0),
    },
    snap_to_payday=frozenset({"insufficient_funds"}),
    doc="Conditions on the decline code the processor already gave us. No machine "
        "learning involved -- this is the free win.",
)

QUIET_CODE_AWARE = RetryPolicy(
    "code_aware_quiet",
    schedule=CODE_AWARE.schedule,
    per_code=dict(CODE_AWARE.per_code),
    snap_to_payday=CODE_AWARE.snap_to_payday,
    email_attempts=frozenset({1, 3}),
    doc="The same schedule, emailing less. Tests whether recovery survives lower "
        "contact volume -- because the emails carry the fatigue cost.",
)

AGGRESSIVE = RetryPolicy(
    "aggressive",
    schedule=(0.5, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0),
    email_attempts=frozenset(range(1, 9)),
    doc="Retry and email at every opportunity. Recovers the most payments and is "
        "included to show what that costs in customers.",
)

ALL_POLICIES: list[RetryPolicy] = [
    NO_RETRY, PROCESSOR_DEFAULT, FIXED_SMART, CODE_AWARE, QUIET_CODE_AWARE, AGGRESSIVE,
]


# --- applying a policy ------------------------------------------------------


def apply_policy(
    failures: pd.DataFrame,
    policy: RetryPolicy,
    cfg: DunningConfig | None = None,
    rng: np.random.Generator | None = None,
) -> pd.DataFrame:
    """Run a retry policy against a population of failed payments.

    Returns one row per failure with whether it was recovered, how many attempts and
    emails it took, and how long it took.
    """
    cfg = cfg or DunningConfig()
    rng = rng or np.random.default_rng(0)

    n = len(failures)
    if n == 0:
        return failures.assign(
            recovered=[], attempts=[], emails=[], days_to_recovery=[], fatigue=[]
        )

    codes = failures["code"].to_numpy()
    code_idx = failures["code_idx"].to_numpy()
    failed_at = pd.DatetimeIndex(failures["failed_at"])

    recovered = np.zeros(n, dtype=bool)
    attempts = np.zeros(n, dtype=int)
    emails = np.zeros(n, dtype=int)
    days_to_recovery = np.full(n, np.nan)

    max_len = max((len(policy.offsets_for(c)) for c in set(codes)), default=0)
    max_len = min(max_len, cfg.max_attempts)

    for step in range(max_len):
        # Which failures still have an attempt scheduled at this step?
        offsets = np.full(n, np.nan)
        for code in np.unique(codes):
            sched = policy.offsets_for(code)
            if step < len(sched):
                offsets[codes == code] = sched[step]

        due = (~recovered) & np.isfinite(offsets)
        if not due.any():
            break

        retry_at = failed_at + pd.to_timedelta(np.nan_to_num(offsets), unit="D")

        # Payday snapping: for codes where the money simply is not there yet, the
        # scheduled offset is a lower bound on the wait, not the wait itself.
        snap = due & np.isin(codes, list(policy.snap_to_payday))
        if snap.any():
            snapped = next_payday(failed_at[snap], cfg, min_delay_days=float(np.nanmin(
                offsets[snap]
            )))
            retry_at = retry_at.to_numpy().copy()
            retry_at[snap] = snapped.to_numpy()
            retry_at = pd.DatetimeIndex(retry_at)

        attempt_no = attempts + 1
        p = retry_success_prob(code_idx, attempt_no, retry_at, cfg)

        success = due & (rng.random(n) < p)

        attempts = np.where(due, attempts + 1, attempts)
        sends_email = due & np.isin(attempt_no, list(policy.email_attempts))
        emails = np.where(sends_email, emails + 1, emails)

        elapsed = (retry_at - failed_at).total_seconds().to_numpy() / 86400.0
        days_to_recovery = np.where(success, elapsed, days_to_recovery)
        recovered |= success

    return failures.assign(
        recovered=recovered,
        attempts=attempts,
        emails=emails,
        days_to_recovery=days_to_recovery,
        # Fatigue is what the emails cost: an increment to the customer's voluntary
        # churn hazard. Recovering the payment and losing the customer is not a win.
        fatigue=emails * cfg.contact_fatigue_per_email,
    )
