"""Pass B — check against the live web whether a save is still applicable.

Only items Pass A flagged as `time_sensitive`, `version_bound` or `dated_event`
reach here; evergreen content skips it, which is where the cost saving lives.

Batching matters and constrains the design. Web search *is* supported inside the
Batches API and is priced identically, so the 50% batch discount still applies.
But a batch request is **single-shot**: there is no second turn, so neither of the
two ways a turn can stop early can be continued in-batch.

* `pause_turn` — a long search turn stopped at the server-side iteration limit.
  Resuming needs another request, so in-batch this becomes `unverified` and the
  item is retried next run. `verify_one_sync` exists for that retry and *does*
  handle the continuation properly.
* a client-tool call — the fallback structured-output path. This one is fine
  single-shot: the verdict travels as the tool call's *input*, so we read it and
  never need to answer the call.

The guard that matters most: a verdict is only trusted if a search actually ran.
`usage.server_tool_use.web_search_requests` is the authority for that, because
`response_inclusion: "excluded"` can legitimately remove the result blocks from
the response. A confident "still_valid" produced without searching is the exact
failure this module exists to prevent, so it is downgraded to `unverified`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from saveddigest.config import Config
from saveddigest.store import Item, Status, Store, Verdict
from saveddigest.triage.batch import (
    BatchOutcome,
    citations_of,
    is_paused,
    is_refusal,
    search_request_count,
    text_of,
    tool_result_payload,
    web_search_failure,
)
from saveddigest.triage.schemas import (
    VERDICT_SCHEMA,
    coerce_sources,
    coerce_verdict,
    unverified_verdict,
)

log = logging.getLogger(__name__)

CUSTOM_ID_PREFIX = "verify-"
VERDICT_TOOL_NAME = "record_verdict"

#: Meta key caching the one-off capability probe, so it costs one tiny request
#: ever rather than one per run.
CAPABILITY_KEY = "verify_structured_output"
CAPABILITY_SUPPORTED = "supported"
CAPABILITY_UNSUPPORTED = "unsupported"

#: `web_search_20260318` adds `response_inclusion`, which keeps the raw search
#: dumps out of the response. We want the verdict, not the corpus.
WEB_SEARCH_TOOL_TYPE = "web_search_20260318"

#: The fallback structured-output channel: the model reports its verdict by
#: calling this tool, and we read the call's input. `strict` guarantees the input
#: validates against the schema.
VERDICT_TOOL: dict[str, Any] = {
    "name": VERDICT_TOOL_NAME,
    "description": (
        "Record your final verdict on whether the saved content is still "
        "applicable. Call this exactly once, after searching."
    ),
    "strict": True,
    "input_schema": VERDICT_SCHEMA,
}

SYSTEM_PROMPT = """\
You are checking whether something a person saved a while ago is still worth their \
time, or has been overtaken by events. Search the web before answering: you are \
being asked precisely because the answer depends on what is true today.

Check the specific claims you are given. For each, decide whether it still holds \
and say so in `checked_claims`. Then give one overall `verdict`:

- `still_valid` — the substance holds. Minor cosmetic drift does not disqualify it.
- `partly_outdated` — the core idea holds but specific details have moved. Say \
which in `what_changed`.
- `superseded` — a newer version or a direct replacement exists. Put its URL in \
`superseded_by`.
- `expired` — the deadline, event or window has passed.
- `unverified` — you searched and still cannot tell.

Use `unverified` rather than guessing. A wrong confident answer is worse than an \
admitted gap here, because the person will act on it without re-checking. Set \
`confidence` to reflect what the sources actually support, and list the pages you \
relied on in `sources`.\
"""


def custom_id_for(item: Item) -> str:
    return f"{CUSTOM_ID_PREFIX}{item.id}"


def item_id_from_custom_id(custom_id: str) -> int | None:
    if not custom_id.startswith(CUSTOM_ID_PREFIX):
        return None
    try:
        return int(custom_id[len(CUSTOM_ID_PREFIX) :])
    except ValueError:
        return None


def build_user_prompt(item: Item, summary: dict[str, Any], *, today: str) -> str:
    """Give the checker the summary and the claims, not the whole transcript.

    Re-sending the transcript would double the input cost for no benefit: Pass A
    already distilled the checkable assertions.
    """
    lines = [
        f"Today's date: {today}",
        f"Saved content: {item.url}",
    ]
    if item.title:
        lines.append(f"Title: {item.title}")
    if item.author:
        lines.append(f"Author/channel: {item.author}")
    if item.published_at:
        lines.append(f"Published: {item.published_at}")
    lines.append(f"Staleness class from triage: {summary.get('staleness_class')}")
    if summary.get("staleness_reason"):
        lines.append(f"Why it might be stale: {summary['staleness_reason']}")
    if summary.get("expiry_date"):
        lines.append(f"Date named in the content: {summary['expiry_date']}")
    if summary.get("tools_mentioned"):
        lines.append("Tools/versions named: " + ", ".join(summary["tools_mentioned"]))

    lines.append("")
    lines.append("What the content says:")
    lines.append(summary.get("detailed_summary") or summary.get("tldr") or "(no summary)")

    claims = summary.get("claims_to_verify") or []
    lines.append("")
    if claims:
        lines.append("Claims to check:")
        lines.extend(f"{n}. {claim}" for n, claim in enumerate(claims, start=1))
    else:
        lines.append(
            "No specific claims were extracted. Judge whether this content's "
            "central recommendation is still what someone would be told today."
        )

    return "\n".join(lines)


def build_request(
    item: Item,
    summary: dict[str, Any],
    *,
    model: str,
    today: str,
    structured_output: bool,
    effort: str = "medium",
    max_tokens: int = 16_000,
    max_searches: int = 4,
    response_inclusion: str = "excluded",
) -> dict[str, Any]:
    """One Pass B batch request.

    `structured_output` picks the channel the verdict comes back on:
    `output_config.format` when the API accepts it alongside web search, otherwise
    a strict tool call. See `probe_structured_output_support`.
    """
    search_tool: dict[str, Any] = {
        "type": WEB_SEARCH_TOOL_TYPE,
        "name": "web_search",
        "max_uses": max_searches,
        "response_inclusion": response_inclusion,
    }

    params: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": SYSTEM_PROMPT,
        "tools": [search_tool],
        "messages": [
            {"role": "user", "content": build_user_prompt(item, summary, today=today)}
        ],
    }

    if structured_output:
        params["output_config"] = {
            "effort": effort,
            "format": {"type": "json_schema", "schema": VERDICT_SCHEMA},
        }
    else:
        # Tool-call channel. `auto` rather than a forced choice on purpose: forcing
        # the tool would make the model call it immediately, before searching.
        params["output_config"] = {"effort": effort}
        params["tools"].append(VERDICT_TOOL)
        params["tool_choice"] = {"type": "auto"}

    return {"custom_id": custom_id_for(item), "params": params}


# --------------------------------------------------------------------------
# reading the result
# --------------------------------------------------------------------------
def extract_verdict(
    message: Any, *, structured_output: bool, require_search: bool = True
) -> dict[str, Any]:
    """Turn a Pass B message into a verdict dict, or an honest `unverified`.

    Order matters: every way the check could have failed is tested *before* the
    payload is trusted, so a well-formed verdict built on no evidence cannot slip
    through.
    """
    if is_refusal(message):
        return unverified_verdict("the model declined to answer this request")

    if is_paused(message):
        # Single-shot in a batch; `verify_one_sync` resumes it on the retry.
        return unverified_verdict("search turn paused before finishing (will retry)")

    failure = web_search_failure(message)
    if failure is not None:
        return unverified_verdict(f"web search failed: {failure}")

    searches = search_request_count(message)
    if require_search and searches == 0:
        return unverified_verdict("no web search was performed, so nothing was checked")

    payload = (
        _json_payload(message)
        if structured_output
        else tool_result_payload(message, VERDICT_TOOL_NAME)
    )
    if payload is None:
        return unverified_verdict("could not read a verdict from the response")

    verdict = coerce_verdict(payload)

    # Prefer the API's own citations over the model's self-reported source list:
    # citations are attached by the search tool and cannot be hallucinated.
    api_citations = citations_of(message)
    if api_citations:
        merged = coerce_sources(
            [{"title": c["title"], "url": c["url"]} for c in api_citations]
        )
        existing = {s["url"] for s in merged}
        merged.extend(s for s in verdict["sources"] if s["url"] not in existing)
        verdict["sources"] = merged

    verdict["searches_used"] = searches
    return verdict


def _json_payload(message: Any) -> dict[str, Any] | None:
    body = text_of(message).strip()
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        log.warning("Pass B returned non-JSON output (%d chars)", len(body))
        return None
    return parsed if isinstance(parsed, dict) else None


def apply_outcome(
    store: Store, item: Item, outcome: BatchOutcome, *, structured_output: bool
) -> bool:
    """Persist one Pass B result.

    Note this advances the item even when the verdict is `unverified`: the digest
    can show an unchecked item with that caveat, which is more useful than holding
    it back forever. A *transport* failure is different and does not advance.
    """
    assert item.id is not None

    if not outcome.ok:
        store.record_failure(item.id, outcome.error or f"batch result: {outcome.kind}")
        return False

    verdict = extract_verdict(outcome.message, structured_output=structured_output)
    store.advance(
        item.id,
        Status.VERIFIED,
        verdict_json=json.dumps(verdict, ensure_ascii=False),
        error=None,
    )
    return True


def record_skipped(store: Store, item: Item, verdict: dict[str, Any]) -> None:
    """Advance an evergreen item past Pass B without spending anything."""
    assert item.id is not None
    store.advance(
        item.id,
        Status.VERIFIED,
        verdict_json=json.dumps(verdict, ensure_ascii=False),
        error=None,
    )


# --------------------------------------------------------------------------
# synchronous path (used for retrying paused turns)
# --------------------------------------------------------------------------
def verify_one_sync(
    client: Any,
    item: Item,
    summary: dict[str, Any],
    *,
    config: Config,
    today: str,
    structured_output: bool,
    max_continuations: int = 5,
) -> dict[str, Any]:
    """Verify one item outside a batch, resuming `pause_turn` properly.

    A paused turn is continued by sending the paused assistant message back
    **unchanged** — which is only possible outside a batch, and is why this exists
    alongside the batch path.
    """
    request = build_request(
        item,
        summary,
        model=config.model,
        today=today,
        structured_output=structured_output,
        effort=config.effort,
        max_searches=config.max_searches_per_item,
    )
    params = dict(request["params"])
    messages = list(params.pop("messages"))

    for _ in range(max_continuations + 1):
        message = client.messages.create(messages=messages, **params)
        if not is_paused(message):
            return extract_verdict(message, structured_output=structured_output)
        # Echo the paused turn back verbatim to resume it.
        messages = [*messages, {"role": "assistant", "content": message.content}]

    return unverified_verdict(
        f"search still paused after {max_continuations} continuations"
    )


# --------------------------------------------------------------------------
# capability probe
# --------------------------------------------------------------------------
def probe_structured_output_support(client: Any, model: str) -> bool:
    """Can `output_config.format` be combined with the web search tool?

    Web search always emits citations, and structured outputs are documented as
    incompatible with citations — but that documented conflict concerns
    `citations: {enabled: true}` on *document* blocks, and the combination used
    here is not addressed either way. So rather than designing around a guess,
    this asks the API once with a deliberately trivial request.

    Returns True if accepted. A `400` means fall back to the tool channel; any
    other error is re-raised, because treating an auth or network failure as
    "unsupported" would silently and permanently degrade every future verdict.
    """
    probe = {
        "model": model,
        "max_tokens": 1_024,
        "tools": [
            {
                "type": WEB_SEARCH_TOOL_TYPE,
                "name": "web_search",
                "max_uses": 1,
                "response_inclusion": "excluded",
            }
        ],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
            }
        },
        "messages": [{"role": "user", "content": "Reply with {\"ok\": true}."}],
    }

    try:
        client.messages.create(**probe)
    except Exception as exc:  # noqa: BLE001 - inspected below, then re-raised
        if _is_bad_request(exc):
            log.info(
                "structured output is not accepted with web search (%s); "
                "using the strict-tool channel instead",
                exc,
            )
            return False
        raise
    return True


def _is_bad_request(exc: BaseException) -> bool:
    """True for an HTTP 400, without importing the SDK's exception classes."""
    status = getattr(exc, "status_code", None)
    if status == 400:
        return True
    name = type(exc).__name__
    return name in {"BadRequestError", "InvalidRequestError"}


def resolve_structured_output(store: Store, client: Any, model: str) -> bool:
    """Cached form of the probe. One tiny request, once, ever."""
    cached = store.get_meta(CAPABILITY_KEY)
    if cached == CAPABILITY_SUPPORTED:
        return True
    if cached == CAPABILITY_UNSUPPORTED:
        return False

    supported = probe_structured_output_support(client, model)
    store.set_meta(
        CAPABILITY_KEY, CAPABILITY_SUPPORTED if supported else CAPABILITY_UNSUPPORTED
    )
    return supported


def verdict_is_trustworthy(verdict: dict[str, Any]) -> bool:
    """Whether the digest may present this verdict as a finding.

    False for `unverified` and for `not_applicable`, so the renderer can label
    them rather than implying they were checked.
    """
    return verdict.get("verdict") not in {
        Verdict.UNVERIFIED.value,
        Verdict.NOT_APPLICABLE.value,
    }
