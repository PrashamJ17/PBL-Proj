"""Pass A — read everything, summarise it in detail, decide what needs checking.

Runs as one batch over every enriched item: no tools, no web access, structured
JSON out. Two jobs in one call because both need the same expensive input (the
full transcript), and splitting them would pay for it twice:

1. the detailed summary the digest is built from;
2. a `staleness_class` and a list of specific `claims_to_verify`, which decide
   whether the item goes on to Pass B at all.

That second job is where the cost control lives. Most saves are evergreen and
skip the web search entirely; you can only tell which after reading the content,
which is why this ordering exists.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from saveddigest.store import Item, Staleness, Status, Store
from saveddigest.triage.batch import BatchOutcome, is_refusal, text_of
from saveddigest.triage.schemas import SUMMARY_SCHEMA, coerce_summary

log = logging.getLogger(__name__)

CUSTOM_ID_PREFIX = "summarise-"

#: Transcripts are unbounded — a three-hour podcast is ~100k tokens. The model's
#: context would hold it, but at batch rates that is real money for one saved
#: video, so input is capped and the truncation is disclosed in the prompt rather
#: than hidden. Roughly 30k tokens.
DEFAULT_MAX_CONTENT_CHARS = 120_000

SYSTEM_PROMPT = """\
You are triaging things a person saved months ago and never went back to. For \
each one you produce two things: a summary detailed enough that they need not \
watch the original, and a judgement about whether the content could have gone \
out of date.

On the summary. `detailed_summary` is the part that matters most — write several \
paragraphs and keep the specifics: the actual argument, the numbers, the named \
tools and versions, the steps in the order given, the caveats the author raised. \
A reader should finish it knowing what the content said, not merely what it was \
about. Do not pad it with restatement or with commentary about the format. If the \
content is thin or is mostly an advert, say so in `content_quality` and keep the \
summary short — do not inflate it.

On staleness. This decides whether the item gets fact-checked against the web, \
so classify on whether the content's *usefulness* depends on facts that move:

- `evergreen`: techniques, mental models, mathematics, history, durable \
explanations. Most well-made educational content is this.
- `time_sensitive`: rests on current prices, rankings, "best X" lists, who runs \
what, what is currently recommended, or the state of a fast-moving field.
- `version_bound`: tied to a specific version of software, a product, or an API \
that will move on.
- `dated_event`: refers to a deadline, launch, sale or event.

`claims_to_verify` becomes the input to the web check, so write specific \
falsifiable statements ("Django 4.2 is the current LTS release", "the free tier \
includes 500 build minutes"), not topics ("check if Django changed"). Leave it \
empty for evergreen content.

Set `expiry_date` only when the content names an actual date. Report what the \
content says, not whether you agree with it.\
"""


def custom_id_for(item: Item) -> str:
    """Stable per-item batch id. Reversed by `item_id_from_custom_id`."""
    return f"{CUSTOM_ID_PREFIX}{item.id}"


def item_id_from_custom_id(custom_id: str) -> int | None:
    if not custom_id.startswith(CUSTOM_ID_PREFIX):
        return None
    try:
        return int(custom_id[len(CUSTOM_ID_PREFIX) :])
    except ValueError:
        return None


def truncate_content(text: str, limit: int = DEFAULT_MAX_CONTENT_CHARS) -> tuple[str, bool]:
    """Cap the input, cutting on a word boundary. Returns `(text, was_truncated)`."""
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    boundary = cut.rfind(" ")
    if boundary > limit * 0.9:
        cut = cut[:boundary]
    return cut, True


def build_user_prompt(item: Item, *, max_content_chars: int = DEFAULT_MAX_CONTENT_CHARS) -> str:
    """Assemble the per-item prompt.

    Metadata goes in as labelled fields rather than prose so the model can tell a
    transcript from a caption — a summary built from a 40-word Instagram caption
    should not claim the confidence of one built from an hour-long transcript.
    """
    content, truncated = truncate_content(item.content_text or "", max_content_chars)

    lines = [
        f"Platform: {item.platform}",
        f"URL: {item.url}",
    ]
    if item.title:
        lines.append(f"Title: {item.title}")
    if item.author:
        lines.append(f"Author/channel: {item.author}")
    if item.published_at:
        lines.append(f"Published: {item.published_at}")
    if item.saved_at:
        lines.append(f"Saved by the user: {item.saved_at}")
    lines.append(f"Content type: {item.content_kind or 'unknown'}")

    if item.content_kind == "auto_captions":
        lines.append(
            "Note: machine-generated captions. Technical terms and names may be "
            "mis-transcribed; do not treat an odd spelling as the author's."
        )
    elif item.content_kind == "caption":
        lines.append(
            "Note: this is the post's written caption only, not the spoken audio. "
            "Summarise what is actually here and do not infer what the video showed."
        )
    elif item.content_kind == "metadata_only":
        lines.append(
            "Note: no transcript or caption was available — only the title and "
            "description below. Keep the summary proportionate and set "
            "content_quality to 'unclear'."
        )

    if truncated:
        lines.append(
            f"Note: content truncated to the first {max_content_chars} characters."
        )

    header = "\n".join(lines)
    return f"{header}\n\n--- CONTENT ---\n{content}\n--- END CONTENT ---"


def build_request(
    item: Item,
    *,
    model: str,
    effort: str = "medium",
    max_tokens: int = 16_000,
    max_content_chars: int = DEFAULT_MAX_CONTENT_CHARS,
) -> dict[str, Any]:
    """One batch request. Plain dicts so it can be asserted on without the SDK.

    `output_config` carries both `effort` and `format`; structured output is safe
    in this pass because there are no tools and therefore no citations.
    """
    return {
        "custom_id": custom_id_for(item),
        "params": {
            "model": model,
            "max_tokens": max_tokens,
            "system": SYSTEM_PROMPT,
            "output_config": {
                "effort": effort,
                "format": {"type": "json_schema", "schema": SUMMARY_SCHEMA},
            },
            "messages": [
                {
                    "role": "user",
                    "content": build_user_prompt(
                        item, max_content_chars=max_content_chars
                    ),
                }
            ],
        },
    }


def parse_summary_message(message: Any) -> dict[str, Any] | None:
    """Read the JSON body out of a Pass A message.

    `output_config.format` guarantees the first text block is valid JSON, but a
    refusal or a `max_tokens` cut-off still has to be handled — hence None rather
    than an exception.
    """
    if is_refusal(message):
        log.warning("Pass A refused for one item")
        return None
    body = text_of(message).strip()
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        log.warning("Pass A returned non-JSON output (%d chars)", len(body))
        return None
    return coerce_summary(parsed)


def apply_outcome(store: Store, item: Item, outcome: BatchOutcome) -> bool:
    """Persist one Pass A result. Returns True when the item advanced.

    A failure records an attempt and leaves the item at its current stage, so the
    next run retries it — until `max_attempts`, after which the queue skips it and
    the digest reports it as unprocessed rather than dropping it.
    """
    assert item.id is not None

    if not outcome.ok:
        store.record_failure(item.id, outcome.error or f"batch result: {outcome.kind}")
        return False

    summary = parse_summary_message(outcome.message)
    if summary is None:
        store.record_failure(item.id, "could not parse Pass A output")
        return False

    store.advance(
        item.id,
        Status.SUMMARISED,
        summary_json=json.dumps(summary, ensure_ascii=False),
        staleness_class=summary["staleness_class"],
        expiry_date=summary["expiry_date"],
        error=None,
    )
    return True


def needs_web_check(summary: dict[str, Any]) -> bool:
    """Whether Pass B should look at this item.

    Evergreen content skips the search — that skip is most of the cost saving.
    An item classed as needing a check but offering no specific claims still goes
    through: "is this still the current recommendation" is checkable from the
    summary alone.
    """
    return summary.get("staleness_class") != Staleness.EVERGREEN.value
