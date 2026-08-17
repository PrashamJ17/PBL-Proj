"""Deciding what reaches the digest, and in what order.

This is the "filter out the content" half of the job. A weekly email listing four
hundred saves is the same problem as an unread Watch Later, so the ranking is as
load-bearing as the summarising.

Two separate decisions:

* **Placement** — a dead or expired save is reported as a single footer line, not
  given a full entry. It is never silently dropped: "3 saves no longer exist" is
  information, and a save that quietly disappears is indistinguishable from a bug.
* **Order** — by how long the item has been rotting, adjusted for whether it is
  still valid, actionable and substantive. Age leads because the whole point is to
  surface the eight-month-old thing, not last week's.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from saveddigest.store import Item, Liveness, Verdict


class Placement(StrEnum):
    """Where an item goes in the rendered digest."""

    BODY = "body"
    #: One footer line: the link is gone.
    GONE = "gone"
    #: One footer line: the deadline or event has passed.
    EXPIRED = "expired"
    #: Held back: nothing usable was ever fetched for it.
    NO_CONTENT = "no_content"


#: Verdicts that still deserve a full entry, in descending usefulness.
_VERDICT_WEIGHT: dict[str, float] = {
    Verdict.STILL_VALID.value: 1.0,
    Verdict.NOT_APPLICABLE.value: 1.0,  # evergreen; never needed checking
    Verdict.PARTLY_OUTDATED.value: 0.7,
    Verdict.SUPERSEDED.value: 0.5,
    Verdict.UNVERIFIED.value: 0.6,
    Verdict.EXPIRED.value: 0.0,
}

_QUALITY_WEIGHT: dict[str, float] = {
    "substantive": 1.0,
    "unclear": 0.6,
    "thin": 0.35,
    "promotional": 0.1,
}

#: Age contribution saturates at a year: a two-year-old save is not twice as
#: urgent as a one-year-old one, and without a cap ancient items would crowd out
#: everything else for ever.
_AGE_SATURATION_DAYS = 365.0


@dataclass
class DigestEntry:
    """An item prepared for rendering, with its placement and score resolved."""

    item: Item
    placement: Placement
    score: float
    reason: str = ""
    #: True when nobody actually checked this against the web.
    unchecked: bool = False

    @property
    def summary(self) -> dict[str, Any]:
        return self.item.summary or {}

    @property
    def verdict(self) -> dict[str, Any]:
        return self.item.verdict or {}


@dataclass
class Digest:
    """The whole rendered payload: entries plus the footer counts."""

    entries: list[DigestEntry] = field(default_factory=list)
    gone: list[DigestEntry] = field(default_factory=list)
    expired: list[DigestEntry] = field(default_factory=list)
    no_content: list[DigestEntry] = field(default_factory=list)
    #: Items that qualified for the body but did not fit under the per-send limit.
    held_back: int = 0
    generated_at: str = ""

    @property
    def total_considered(self) -> int:
        return (
            len(self.entries)
            + len(self.gone)
            + len(self.expired)
            + len(self.no_content)
            + self.held_back
        )

    @property
    def is_empty(self) -> bool:
        return not (self.entries or self.gone or self.expired or self.no_content)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def has_expired(item: Item, *, today: date) -> bool:
    """True when the content named a date and that date has passed.

    Read from the coerced `expiry_date`, which is already validated as
    `YYYY-MM-DD` — a malformed date is None here, never a false expiry.
    """
    expiry = _parse_date(item.expiry_date)
    return expiry is not None and expiry < today


def classify(item: Item, *, today: date | None = None) -> tuple[Placement, str]:
    """Where this item belongs, and a one-line reason for the footer.

    Order of checks is the priority order: gone beats expired beats
    unsummarisable, because a deleted video's expiry no longer matters.
    """
    today = today or datetime.now(UTC).date()

    if item.liveness is Liveness.DEAD:
        return Placement.GONE, "no longer available"

    verdict_value = (item.verdict or {}).get("verdict")
    if verdict_value == Verdict.EXPIRED.value:
        return Placement.EXPIRED, "the deadline or event has passed"

    if has_expired(item, today=today):
        return Placement.EXPIRED, f"dated {item.expiry_date}, now past"

    summary = item.summary or {}
    if not summary.get("tldr") and not summary.get("detailed_summary"):
        return Placement.NO_CONTENT, "nothing could be read from this link"

    return Placement.BODY, ""


def relevance_score(item: Item, *, today: date | None = None) -> float:
    """Ranking score. Higher sorts first.

    Age dominates by design, then usefulness modulates it:

        score = age_factor * verdict_weight * quality_weight + actionability

    `unverified` deliberately outranks `superseded`: "we could not check this" is
    more likely to still be worth your attention than "this has been replaced".
    """
    now = datetime.now(UTC) if today is None else datetime.combine(today, datetime.min.time(), UTC)
    age_days = item.days_since_saved(now)
    age_factor = min(age_days / _AGE_SATURATION_DAYS, 1.0)
    # Floor so a save from yesterday is not scored at exactly zero.
    age_factor = max(age_factor, 0.05)

    verdict_value = (item.verdict or {}).get("verdict", Verdict.UNVERIFIED.value)
    verdict_weight = _VERDICT_WEIGHT.get(verdict_value, 0.5)

    summary = item.summary or {}
    quality_weight = _QUALITY_WEIGHT.get(summary.get("content_quality", "unclear"), 0.6)

    actionability = 0.15 if summary.get("actionable_steps") else 0.0

    return age_factor * verdict_weight * quality_weight + actionability


def is_unchecked(item: Item) -> bool:
    """True when no web check actually happened for a time-sensitive item.

    Drives the "not checked" label. `not_applicable` is *not* unchecked — it was
    correctly judged not to need checking.
    """
    verdict = item.verdict or {}
    if verdict.get("verdict") == Verdict.UNVERIFIED.value:
        return True
    return item.liveness is Liveness.UNVERIFIABLE and not verdict


def build_digest(
    items: Iterable[Item],
    *,
    limit: int | None = None,
    today: date | None = None,
    generated_at: str = "",
) -> Digest:
    """Sort, filter and truncate items into a renderable digest.

    `limit` caps only the body. Footer lines are cheap and complete: the count of
    what vanished should not depend on how many entries fitted.
    """
    today = today or datetime.now(UTC).date()
    digest = Digest(generated_at=generated_at)

    body: list[DigestEntry] = []
    for item in items:
        placement, reason = classify(item, today=today)
        entry = DigestEntry(
            item=item,
            placement=placement,
            score=relevance_score(item, today=today),
            reason=reason,
            unchecked=is_unchecked(item),
        )
        if placement is Placement.BODY:
            body.append(entry)
        elif placement is Placement.GONE:
            digest.gone.append(entry)
        elif placement is Placement.EXPIRED:
            digest.expired.append(entry)
        else:
            digest.no_content.append(entry)

    # Highest score first; ties broken by age then id so the order is total and
    # stable across runs.
    body.sort(
        key=lambda e: (-e.score, -e.item.days_since_saved(), e.item.id or 0),
    )

    if limit is not None and len(body) > limit:
        digest.entries = body[:limit]
        digest.held_back = len(body) - limit
    else:
        digest.entries = body

    for bucket in (digest.gone, digest.expired, digest.no_content):
        bucket.sort(key=lambda e: -e.item.days_since_saved())

    return digest


def summarise_counts(digest: Digest) -> dict[str, int]:
    """Counts for the subject line and for logging."""
    return {
        "shown": len(digest.entries),
        "held_back": digest.held_back,
        "gone": len(digest.gone),
        "expired": len(digest.expired),
        "no_content": len(digest.no_content),
        "unchecked": sum(1 for e in digest.entries if e.unchecked),
        "superseded": sum(
            1
            for e in digest.entries
            if e.verdict.get("verdict") == Verdict.SUPERSEDED.value
        ),
    }


def subject_line(digest: Digest, counts: Sequence[int] | None = None) -> str:
    """Email subject naming what is inside, so it is scannable unopened."""
    stats = summarise_counts(digest)
    if digest.is_empty:
        return "Saved digest: nothing new"

    bits = [f"{stats['shown']} saved item{'s' if stats['shown'] != 1 else ''}"]
    if stats["superseded"]:
        bits.append(f"{stats['superseded']} superseded")
    if stats["expired"]:
        bits.append(f"{stats['expired']} expired")
    if stats["gone"]:
        bits.append(f"{stats['gone']} gone")
    return "Saved digest: " + ", ".join(bits)
