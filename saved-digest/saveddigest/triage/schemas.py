"""JSON schemas for the two Claude passes, plus defensive coercion of the results.

Structured outputs constrain the shape, not the semantics: the model can still
return an empty `detailed_summary`, an unrecognised enum from a future revision,
or a `superseded_by` that is prose rather than a URL. Everything the renderer
reads therefore goes through `coerce_*` first.

Two schema constraints worth remembering, both from the structured-outputs
contract:

* every object needs `additionalProperties: false` and a `required` list;
* string length/number range constraints are unsupported, so bounds are enforced
  here in Python instead.

`expiry_date` is a plain string with `""` for "none" rather than a nullable type,
because a `""` sentinel needs no union support and cannot trip a schema-compiler
edge case.
"""

from __future__ import annotations

import re
from typing import Any

from saveddigest.store import Staleness, Verdict

# --------------------------------------------------------------------------
# Pass A — detailed summary + staleness triage
# --------------------------------------------------------------------------
STALENESS_VALUES = tuple(s.value for s in Staleness)

QUALITY_VALUES = ("substantive", "thin", "promotional", "unclear")

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tldr": {
            "type": "string",
            "description": "One sentence. What this content is and why it mattered.",
        },
        "detailed_summary": {
            "type": "string",
            "description": (
                "Several paragraphs covering what the content actually says: the "
                "argument, the specifics, the numbers, the worked steps. Written so "
                "a reader who never watches the original still gets the substance."
            ),
        },
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The concrete claims or lessons, one per entry.",
        },
        "actionable_steps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Things the reader could actually do. Empty if none.",
        },
        "tools_mentioned": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Named products, libraries, services or versions.",
        },
        "prerequisites": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Knowledge or setup assumed by the content.",
        },
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Two to five short subject tags.",
        },
        "staleness_class": {
            "type": "string",
            "enum": list(STALENESS_VALUES),
            "description": (
                "evergreen: durable ideas, techniques, mental models. "
                "time_sensitive: depends on facts that change (prices, rankings, "
                "who runs what, what is currently recommended). "
                "version_bound: tied to a specific software or product version. "
                "dated_event: refers to a deadline, event or window."
            ),
        },
        "staleness_reason": {
            "type": "string",
            "description": "One sentence justifying the classification.",
        },
        "claims_to_verify": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Specific, independently checkable statements a web search could "
                "confirm or refute today. Empty for evergreen content."
            ),
        },
        "expiry_date": {
            "type": "string",
            "description": (
                "ISO date (YYYY-MM-DD) of any deadline or event named in the "
                "content. Empty string when there is none."
            ),
        },
        "content_quality": {
            "type": "string",
            "enum": list(QUALITY_VALUES),
            "description": (
                "substantive: real information. thin: little content. "
                "promotional: mostly an advert. unclear: could not tell."
            ),
        },
    },
    "required": [
        "tldr",
        "detailed_summary",
        "key_points",
        "actionable_steps",
        "tools_mentioned",
        "prerequisites",
        "topics",
        "staleness_class",
        "staleness_reason",
        "claims_to_verify",
        "expiry_date",
        "content_quality",
    ],
    "additionalProperties": False,
}


# --------------------------------------------------------------------------
# Pass B — web verification
# --------------------------------------------------------------------------
#: `unverified` is deliberately available to the model: "I searched and still
#: cannot tell" must be expressible, or it will pick a confident wrong answer.
VERDICT_VALUES = tuple(
    v.value
    for v in Verdict
    if v is not Verdict.NOT_APPLICABLE  # never model-assigned; set when Pass B is skipped
)

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": list(VERDICT_VALUES),
            "description": (
                "still_valid: the substance holds today. "
                "partly_outdated: mostly holds, specific details have moved. "
                "superseded: a newer version or replacement exists. "
                "expired: the deadline or event has passed. "
                "unverified: searching did not settle it — say this rather than guessing."
            ),
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "How well the sources actually support the verdict.",
        },
        "what_changed": {
            "type": "string",
            "description": (
                "Concretely what has changed since publication, or empty if nothing has."
            ),
        },
        "superseded_by": {
            "type": "string",
            "description": (
                "URL of the current equivalent, when one exists. Empty string otherwise."
            ),
        },
        "current_state": {
            "type": "string",
            "description": "What is true now, in a sentence or two.",
        },
        "checked_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "holds": {"type": "string", "enum": ["yes", "no", "unclear"]},
                    "note": {"type": "string"},
                },
                "required": ["claim", "holds", "note"],
                "additionalProperties": False,
            },
            "description": "One entry per claim handed to you.",
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["title", "url"],
                "additionalProperties": False,
            },
            "description": "The pages the verdict rests on.",
        },
    },
    "required": [
        "verdict",
        "confidence",
        "what_changed",
        "superseded_by",
        "current_state",
        "checked_claims",
        "sources",
    ],
    "additionalProperties": False,
}


# --------------------------------------------------------------------------
# coercion
# --------------------------------------------------------------------------
#: Generous caps. Long enough never to truncate a genuine answer, short enough
#: that a runaway generation cannot bloat the database or the email.
MAX_TEXT = 20_000
MAX_LIST_ITEMS = 40
MAX_ITEM_LEN = 1_000

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HTTP_URL = re.compile(r"^https?://", re.IGNORECASE)


def _text(value: Any, *, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value[:MAX_LIST_ITEMS]:
        if isinstance(entry, str) and entry.strip():
            out.append(entry.strip()[:MAX_ITEM_LEN])
    return out


def _enum(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    return value if isinstance(value, str) and value in allowed else fallback


def coerce_expiry_date(value: Any) -> str | None:
    """Accept only a well-formed `YYYY-MM-DD`; anything else means "no expiry".

    A malformed date silently compared against `today` would drop live items into
    the "expired" bucket, so this is strict on purpose.
    """
    text = _text(value, limit=32)
    return text if _ISO_DATE.match(text) else None


def coerce_summary(raw: Any) -> dict[str, Any]:
    """Normalise a Pass A result into exactly the keys the renderer reads."""
    data = raw if isinstance(raw, dict) else {}

    staleness = _enum(
        data.get("staleness_class"),
        STALENESS_VALUES,
        # Unknown class fails safe towards being checked rather than trusted.
        Staleness.TIME_SENSITIVE.value,
    )
    claims = _string_list(data.get("claims_to_verify"))

    return {
        "tldr": _text(data.get("tldr"), limit=MAX_ITEM_LEN),
        "detailed_summary": _text(data.get("detailed_summary")),
        "key_points": _string_list(data.get("key_points")),
        "actionable_steps": _string_list(data.get("actionable_steps")),
        "tools_mentioned": _string_list(data.get("tools_mentioned")),
        "prerequisites": _string_list(data.get("prerequisites")),
        "topics": _string_list(data.get("topics")),
        "staleness_class": staleness,
        "staleness_reason": _text(data.get("staleness_reason"), limit=MAX_ITEM_LEN),
        # Evergreen content has nothing to check; drop stray claims so Pass B's
        # queue matches the classification.
        "claims_to_verify": [] if staleness == Staleness.EVERGREEN.value else claims,
        "expiry_date": coerce_expiry_date(data.get("expiry_date")),
        "content_quality": _enum(data.get("content_quality"), QUALITY_VALUES, "unclear"),
    }


def coerce_verdict(raw: Any) -> dict[str, Any]:
    """Normalise a Pass B result. Anything unreadable becomes `unverified`."""
    data = raw if isinstance(raw, dict) else {}

    verdict = _enum(data.get("verdict"), VERDICT_VALUES, Verdict.UNVERIFIED.value)

    superseded_by = _text(data.get("superseded_by"), limit=2_000)
    # Only keep a real URL: prose here would render as a broken link.
    if not _HTTP_URL.match(superseded_by):
        superseded_by = ""

    checked: list[dict[str, str]] = []
    raw_claims = data.get("checked_claims")
    if isinstance(raw_claims, list):
        for entry in raw_claims[:MAX_LIST_ITEMS]:
            if not isinstance(entry, dict):
                continue
            claim = _text(entry.get("claim"), limit=MAX_ITEM_LEN)
            if not claim:
                continue
            checked.append(
                {
                    "claim": claim,
                    "holds": _enum(entry.get("holds"), ("yes", "no", "unclear"), "unclear"),
                    "note": _text(entry.get("note"), limit=MAX_ITEM_LEN),
                }
            )

    return {
        "verdict": verdict,
        "confidence": _enum(data.get("confidence"), ("high", "medium", "low"), "low"),
        "what_changed": _text(data.get("what_changed"), limit=MAX_TEXT),
        "superseded_by": superseded_by,
        "current_state": _text(data.get("current_state"), limit=MAX_TEXT),
        "checked_claims": checked,
        "sources": coerce_sources(data.get("sources")),
    }


def coerce_sources(raw: Any) -> list[dict[str, str]]:
    """Keep only entries with a usable http(s) URL, de-duplicated by URL."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in raw[:MAX_LIST_ITEMS]:
        if not isinstance(entry, dict):
            continue
        url = _text(entry.get("url"), limit=2_000)
        if not _HTTP_URL.match(url) or url in seen:
            continue
        seen.add(url)
        title = _text(entry.get("title"), limit=MAX_ITEM_LEN) or url
        out.append({"title": title, "url": url})
    return out


def unverified_verdict(reason: str) -> dict[str, Any]:
    """A verdict for an item Pass B could not settle.

    Used for search errors, exhausted continuations and malformed output. Never
    conflated with `still_valid` — an unchecked item is reported as unchecked.
    """
    return {
        "verdict": Verdict.UNVERIFIED.value,
        "confidence": "low",
        "what_changed": "",
        "superseded_by": "",
        "current_state": "",
        "checked_claims": [],
        "sources": [],
        "unverified_reason": reason[:MAX_ITEM_LEN],
    }


def not_applicable_verdict() -> dict[str, Any]:
    """The verdict recorded for evergreen items, which skip Pass B entirely."""
    return {
        "verdict": Verdict.NOT_APPLICABLE.value,
        "confidence": "high",
        "what_changed": "",
        "superseded_by": "",
        "current_state": "",
        "checked_claims": [],
        "sources": [],
    }
