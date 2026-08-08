"""Failed payments: decline codes, retry timing, and recovery.

Involuntary churn is 20-40% of all churn and most small businesses do nothing about
it beyond whatever their processor retries by default. It is the fastest route to
demonstrable revenue in this project, and unlike voluntary churn it needs almost no
causal machinery -- a retry either succeeds or it does not, and you observe which.

Why this is a separate module from `subsim`
--------------------------------------------
SubSim models involuntary churn as one Bernoulli draw per month at a fixed recovery
rate. That is adequate for calibrating overall churn and useless for studying *retry
policy*, which is entirely about which code failed and when you try again.

This module models the failure-to-recovery process in detail, and is calibrated so
that its **passive policy reproduces SubSim's aggregate recovery rate**. The two stay
consistent by construction rather than by coincidence, so adding this does not disturb
the Phase 0 calibration gates.

The three things that actually drive recovery
----------------------------------------------
**The decline code.** `insufficient_funds` is a timing problem -- the money arrives on
payday. `expired_card` is not a timing problem at all; retrying the same card in the
same month cannot work, and only a card update fixes it. Treating these identically,
which processor-default retry schedules do, wastes attempts on the second group and
mistimes the first.

**When you retry.** Salary cycles are real. A retry two days before payday and one two
days after have very different outcomes for the largest decline category.

**How many times you have already tried.** Success decays sharply with attempt number:
a card that failed three times is telling you something.

Dunning fatigue -- the connection to the rest of the project
-------------------------------------------------------------
Every dunning contact is also a message reminding the customer they are paying you.
Too many, and you recover the payment and lose the customer -- the same salience
mechanism that produces sleeping dogs in voluntary retention (D-002).

This does **not** violate the invariant that voluntary and involuntary churn stay
separate processes. They remain separate processes; this is a causal *link* from one
to the other, modelled explicitly rather than by summing them. See D-032.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DeclineCode:
    """One processor decline reason and how it behaves under retry."""

    name: str
    share: float
    """Prevalence among failures."""
    ceiling: float
    """Highest achievable single-retry success probability, under ideal timing and
    on the first attempt. A hard cap: no schedule beats the underlying reason."""
    attempt_decay: float
    """Multiplier applied per additional attempt."""
    payday_sensitive: bool = False
    """Whether success tracks salary cycles."""
    needs_new_card: bool = False
    """Retrying the same credentials cannot succeed; only a card update helps."""
    doc: str = ""


#: Shares and behaviours follow the published pattern of processor decline reasons:
#: insufficient funds dominates and is highly recoverable with correct timing;
#: expired cards are common and essentially unrecoverable by retry alone.
DECLINE_CODES: list[DeclineCode] = [
    DeclineCode(
        "insufficient_funds", 0.40, ceiling=0.72, attempt_decay=0.80,
        payday_sensitive=True,
        doc="The money is not there yet. A timing problem, and the biggest single win.",
    ),
    DeclineCode(
        # Steep decay, deliberately. Retrying a genuinely expired card cannot work:
        # the only recoveries come from the customer updating their card of their own
        # accord, and that does not become more likely because you retried again.
        # With a gentle decay the attempts compound and an expired card "recovers"
        # ~22% under aggressive retrying, which is not a thing that happens.
        "expired_card", 0.18, ceiling=0.13, attempt_decay=0.30, needs_new_card=True,
        doc="Retrying the same card cannot work. Needs an updater or the customer.",
    ),
    DeclineCode(
        "do_not_honor", 0.20, ceiling=0.38, attempt_decay=0.70,
        doc="Generic issuer refusal. Moderately recoverable, reason opaque.",
    ),
    DeclineCode(
        "generic_decline", 0.10, ceiling=0.30, attempt_decay=0.70,
        doc="Unspecified decline.",
    ),
    DeclineCode(
        "processing_error", 0.07, ceiling=0.88, attempt_decay=0.55,
        doc="Transient fault. An immediate retry usually works; waiting wastes time.",
    ),
    DeclineCode(
        "lost_or_stolen_card", 0.05, ceiling=0.02, attempt_decay=0.25, needs_new_card=True,
        doc="Effectively unrecoverable. Attempts here are pure waste.",
    ),
]

CODE_INDEX = {c.name: i for i, c in enumerate(DECLINE_CODES)}

#: Default start of the failure window. Module-level so it is not constructed in a
#: function default argument.
EPOCH = pd.Timestamp("2024-01-01")


@dataclass(frozen=True)
class DunningConfig:
    """Parameters of the failure-and-recovery process."""

    recovery_scale: float = 0.4764
    """Global multiplier on every success probability.

    NOT hand-picked: solved by `calibrate_recovery_scale` so the PASSIVE policy
    reproduces SubSim's `PaymentParams.passive_recovery_rate` (0.42), keeping this
    detailed model consistent with the aggregate one the Phase 0 calibration gates
    were tuned against. Re-run that solver after changing any code ceiling, decay,
    or the timing model."""

    payday_days: tuple[int, ...] = (1, 2, 3, 15, 16, 17)
    """Days of month when salary typically lands."""

    payday_boost: float = 1.45
    """Multiplier on payday-sensitive codes when retried near payday."""

    payday_penalty: float = 0.62
    """Multiplier when retried at the worst point in the salary cycle."""

    business_hours_boost: float = 1.12
    """Weekday daytime retries fare slightly better than weekend-night ones."""

    off_hours_penalty: float = 0.88

    account_updater: bool = False
    """Whether a card-updater service is in place. Raises the ceiling for
    `needs_new_card` codes, which are otherwise near-hopeless."""

    account_updater_ceiling: float = 0.55
    """Achievable recovery for expired cards once an updater is connected."""

    contact_fatigue_per_email: float = 0.055
    """Increment to the customer's voluntary-churn hazard (logit scale) per dunning
    email. This is the salience mechanism from D-002 appearing in the billing path:
    a payment-failure email is also a reminder that they are paying you."""

    max_attempts: int = 8
    """Guard rail. Beyond this, additional attempts are near-worthless and the
    fatigue cost dominates."""

    codes: tuple[DeclineCode, ...] = field(default_factory=lambda: tuple(DECLINE_CODES))


# --- generative process -----------------------------------------------------


def generate_failures(
    n_failures: int,
    cfg: DunningConfig | None = None,
    rng: np.random.Generator | None = None,
    start: pd.Timestamp | None = None,
    span_days: int = 365,
    mrr_mu: float = 4.0,
    mrr_sigma: float = 0.8,
) -> pd.DataFrame:
    """Generate a population of failed payments.

    Failure timestamps are spread uniformly across the span, so day-of-month and
    hour-of-day vary naturally -- which is what makes retry *timing* studiable.
    """
    cfg = cfg or DunningConfig()
    rng = rng or np.random.default_rng(0)
    start = start or EPOCH

    shares = np.array([c.share for c in cfg.codes], dtype=float)
    shares = shares / shares.sum()
    code_idx = rng.choice(len(cfg.codes), size=n_failures, p=shares)

    offsets = rng.uniform(0, span_days, n_failures)
    failed_at = start + pd.to_timedelta(offsets, unit="D")

    return pd.DataFrame({
        "failure_id": np.arange(n_failures),
        "customer_id": np.arange(n_failures),
        "code": [cfg.codes[i].name for i in code_idx],
        "code_idx": code_idx,
        "failed_at": failed_at,
        "amount": rng.lognormal(mrr_mu, mrr_sigma, n_failures),
    })


def timing_multiplier(
    timestamps: pd.Series | pd.DatetimeIndex,
    payday_sensitive: np.ndarray,
    cfg: DunningConfig,
) -> np.ndarray:
    """How much better or worse this moment is for a retry.

    Two effects, and the first is much larger than the second:

    **Salary cycles** dominate `insufficient_funds`, the single biggest decline
    category. Retrying just after payday works; retrying just before does not.

    **Business hours** matter mildly for everything -- weekday daytime attempts fare
    slightly better than weekend-night ones.
    """
    ts = pd.DatetimeIndex(timestamps)
    day = ts.day.to_numpy()
    hour = ts.hour.to_numpy()
    weekday = ts.dayofweek.to_numpy()

    # Distance to the nearest payday, in days, wrapping around the month.
    paydays = np.array(cfg.payday_days)
    dist = np.min(
        np.minimum(np.abs(day[:, None] - paydays[None, :]),
                   31 - np.abs(day[:, None] - paydays[None, :])),
        axis=1,
    )
    # Full boost on payday, decaying to the penalty a week out.
    payday_factor = cfg.payday_penalty + (
        cfg.payday_boost - cfg.payday_penalty
    ) * np.exp(-dist / 2.5)
    payday_factor = np.where(payday_sensitive, payday_factor, 1.0)

    in_hours = (weekday < 5) & (hour >= 9) & (hour < 18)
    hours_factor = np.where(in_hours, cfg.business_hours_boost, cfg.off_hours_penalty)

    return payday_factor * hours_factor


def retry_success_prob(
    code_idx: np.ndarray,
    attempt: np.ndarray,
    timestamps: pd.Series | pd.DatetimeIndex,
    cfg: DunningConfig,
) -> np.ndarray:
    """Probability that one retry attempt succeeds.

    `ceiling x decay^(attempt-1) x timing x scale`, clipped to a probability.
    """
    codes = cfg.codes
    ceilings = np.array([c.ceiling for c in codes])
    decays = np.array([c.attempt_decay for c in codes])
    needs_card = np.array([c.needs_new_card for c in codes])
    payday = np.array([c.payday_sensitive for c in codes])

    base = ceilings[code_idx].copy()
    if cfg.account_updater:
        # A card updater turns the hopeless codes into merely difficult ones.
        base = np.where(needs_card[code_idx], cfg.account_updater_ceiling, base)

    p = (
        base
        * decays[code_idx] ** np.maximum(attempt - 1, 0)
        * timing_multiplier(timestamps, payday[code_idx], cfg)
        * cfg.recovery_scale
    )
    return np.clip(p, 0.0, 0.98)


# --- calibration ------------------------------------------------------------

#: Published recovery bands. Processor-native retries alone put most operators in the
#: first band; dedicated dunning with code-aware retry timing and multi-touch email
#: reaches the second. These are targets to be *matched*, not results to be claimed.
PASSIVE_RECOVERY_BAND = (0.30, 0.45)
SMART_RECOVERY_BAND = (0.55, 0.70)


def measure_recovery(
    policy, cfg: DunningConfig | None = None, n: int = 40_000, seed: int = 0
) -> float:
    """Recovery rate achieved by a policy on a fresh failure population."""
    from keel.policy.dunning import apply_policy

    cfg = cfg or DunningConfig()
    failures = generate_failures(n, cfg, np.random.default_rng(seed))
    out = apply_policy(failures, policy, cfg, np.random.default_rng(seed + 1))
    return float(out["recovered"].mean())


def calibrate_recovery_scale(
    target: float = 0.42,
    cfg: DunningConfig | None = None,
    n: int = 30_000,
    tol: float = 0.004,
    max_iter: int = 20,
) -> float:
    """Solve for `recovery_scale` so the PASSIVE policy hits a target recovery rate.

    The target defaults to SubSim's `PaymentParams.passive_recovery_rate`, which keeps
    this detailed model consistent with the aggregate one the Phase 0 calibration gates
    were tuned against. Changing it here without changing it there would silently put
    the two simulators into disagreement.

    Bisection: recovery is monotone in the scale, so convergence is guaranteed.
    Hand-tuning is avoided for the same reason as the hazard intercept (D-005).
    """
    from dataclasses import replace

    from keel.policy.dunning import PROCESSOR_DEFAULT

    cfg = cfg or DunningConfig()
    lo, hi = 0.05, 3.0
    best = cfg.recovery_scale

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        got = measure_recovery(PROCESSOR_DEFAULT, replace(cfg, recovery_scale=mid), n=n)
        best = mid
        if abs(got - target) < tol:
            break
        if got > target:
            hi = mid
        else:
            lo = mid
    return best
