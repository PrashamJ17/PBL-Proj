"""Message Batches plumbing shared by Pass A and Pass B.

Batching is the right shape here twice over: nothing in a weekly digest is
latency-sensitive, and batch requests are billed at half price. Web search is
supported inside a batch too — though the Batches API throttles searches
per-organisation, so a large first run can take a while. That is latency, not
failure, and the poller is patient accordingly.

Response handling is separated from transport so the fiddly parts can be tested
without an API key. Three of them matter:

1. **Results come back in arbitrary order.** They must be keyed by `custom_id`;
   zipping them against the request list silently attaches each summary to the
   wrong saved item.
2. **A failed web search returns HTTP 200.** The error arrives as
   `web_search_tool_result.content` being a single error *object* where success is
   a *list*. Branching on that shape is the difference between "we could not
   check this" and a confident wrong "still valid".
3. **`pause_turn`** ends a long search turn early; the paused assistant message
   must be sent back unchanged to continue.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

#: Terminal batch state.
_ENDED = "ended"

#: Batch result kinds, per the Batches API.
SUCCEEDED = "succeeded"
ERRORED = "errored"
CANCELED = "canceled"
EXPIRED = "expired"


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read `key` from either an SDK model or a plain dict.

    The SDK returns pydantic models; tests and recorded fixtures use dicts. One
    accessor keeps the parsing code identical for both.
    """
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _blocks(message: Any) -> list[Any]:
    content = _get(message, "content") or []
    return list(content) if isinstance(content, (list, tuple)) else []


# --------------------------------------------------------------------------
# outcomes
# --------------------------------------------------------------------------
@dataclass
class BatchOutcome:
    """One request's result, normalised."""

    custom_id: str
    kind: str
    message: Any | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.kind == SUCCEEDED and self.message is not None

    @property
    def retryable(self) -> bool:
        """Whether re-submitting could plausibly succeed.

        `errored` covers both permanent validation failures and transient server
        errors; the API distinguishes them by `error.type`, and only
        `invalid_request` is worth giving up on.
        """
        if self.kind in (CANCELED, EXPIRED):
            return True
        if self.kind == ERRORED:
            return "invalid_request" not in (self.error or "")
        return False


def index_results_by_custom_id(results: Iterable[Any]) -> dict[str, BatchOutcome]:
    """Key batch results by `custom_id`.

    The Batches API makes no ordering promise, so this mapping — not list
    position — is the only correct way to reunite a result with its item.
    """
    out: dict[str, BatchOutcome] = {}
    for raw in results:
        custom_id = _get(raw, "custom_id")
        if not isinstance(custom_id, str) or not custom_id:
            log.warning("batch result with no custom_id; dropping it")
            continue

        result = _get(raw, "result")
        kind = _get(result, "type") or ERRORED

        message = _get(result, "message") if kind == SUCCEEDED else None
        error: str | None = None
        if kind != SUCCEEDED:
            err = _get(result, "error")
            error = f"{_get(err, 'type') or kind}: {_get(err, 'message') or ''}".strip(": ")

        out[custom_id] = BatchOutcome(
            custom_id=custom_id, kind=kind, message=message, error=error
        )
    return out


# --------------------------------------------------------------------------
# message inspection
# --------------------------------------------------------------------------
def stop_reason(message: Any) -> str | None:
    value = _get(message, "stop_reason")
    return value if isinstance(value, str) else None


def is_paused(message: Any) -> bool:
    """True when a long server-tool turn stopped early and can be resumed."""
    return stop_reason(message) == "pause_turn"


def is_refusal(message: Any) -> bool:
    """True when safety classifiers declined the request.

    Checked before reading `content`, which is empty or partial on a refusal.
    """
    return stop_reason(message) == "refusal"


def text_of(message: Any) -> str:
    """Concatenate the message's text blocks."""
    parts: list[str] = []
    for block in _blocks(message):
        if _get(block, "type") == "text":
            text = _get(block, "text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def web_search_failure(message: Any) -> str | None:
    """The error code if any web search failed, else None.

    On success `web_search_tool_result.content` is a *list* of results; on failure
    it is a single error *object*. Both arrive with HTTP 200 and no exception, so
    this shape check is the only signal that a check did not actually happen.
    """
    for block in _blocks(message):
        if _get(block, "type") != "web_search_tool_result":
            continue
        content = _get(block, "content")
        if isinstance(content, Mapping):
            code = content.get("error_code") or content.get("type")
            if code:
                return str(code)
        elif not isinstance(content, (list, tuple)) and content is not None:
            code = _get(content, "error_code") or _get(content, "type")
            if code:
                return str(code)
    return None


def search_request_count(message: Any) -> int:
    """How many billed searches this message used (`$10` per 1,000)."""
    usage = _get(message, "usage")
    server = _get(usage, "server_tool_use")
    count = _get(server, "web_search_requests")
    return count if isinstance(count, int) and count >= 0 else 0


def citations_of(message: Any) -> list[dict[str, str]]:
    """Every web citation attached to the message's text blocks.

    Web search always emits citations, and the digest shows them so a verdict can
    be checked rather than trusted.
    """
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for block in _blocks(message):
        for citation in _get(block, "citations") or []:
            url = _get(citation, "url")
            if not isinstance(url, str) or not url or url in seen:
                continue
            seen.add(url)
            found.append(
                {
                    "url": url,
                    "title": _get(citation, "title") or url,
                    "cited_text": (_get(citation, "cited_text") or "")[:300],
                }
            )
    return found


def tool_result_payload(message: Any, tool_name: str) -> dict[str, Any] | None:
    """Input of the first `tool_use` block named `tool_name`.

    This is the fallback path for structured output: when `output_config.format`
    cannot be combined with web search, the model reports its verdict by calling
    a strict client tool instead, and the payload is that tool's input.
    """
    for block in _blocks(message):
        if _get(block, "type") == "tool_use" and _get(block, "name") == tool_name:
            payload = _get(block, "input")
            if isinstance(payload, Mapping):
                return dict(payload)
    return None


def pending_tool_use_ids(message: Any, tool_name: str) -> list[str]:
    """Ids of `tool_use` blocks for `tool_name`, needed to answer them."""
    ids: list[str] = []
    for block in _blocks(message):
        if _get(block, "type") == "tool_use" and _get(block, "name") == tool_name:
            block_id = _get(block, "id")
            if isinstance(block_id, str):
                ids.append(block_id)
    return ids


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------
@dataclass
class BatchRunner:
    """Submit a batch, wait for it, hand back outcomes keyed by `custom_id`."""

    client: Any
    poll_interval: float = 20.0
    #: Batch web search is throttled per organisation, so the first large run can
    #: legitimately take hours. The API's own ceiling is 24h.
    timeout: float = 24 * 60 * 60
    sleep: Any = field(default=time.sleep, repr=False)
    monotonic: Any = field(default=time.monotonic, repr=False)

    def run(self, requests: Sequence[Any]) -> dict[str, BatchOutcome]:
        if not requests:
            return {}
        batch_id = self.submit(requests)
        self.wait(batch_id)
        return self.collect(batch_id)

    def submit(self, requests: Sequence[Any]) -> str:
        batch = self.client.messages.batches.create(requests=list(requests))
        batch_id = _get(batch, "id")
        log.info("submitted batch %s with %d request(s)", batch_id, len(requests))
        return str(batch_id)

    def wait(self, batch_id: str) -> Any:
        """Poll until the batch ends, or raise `TimeoutError`."""
        started = self.monotonic()
        while True:
            batch = self.client.messages.batches.retrieve(batch_id)
            status = _get(batch, "processing_status")
            if status == _ENDED:
                return batch

            elapsed = self.monotonic() - started
            if elapsed > self.timeout:
                raise TimeoutError(
                    f"batch {batch_id} still {status} after {elapsed:.0f}s; "
                    "it is not lost — re-run the stage later to collect it"
                )
            counts = _get(batch, "request_counts")
            log.info(
                "batch %s: %s (processing=%s, succeeded=%s)",
                batch_id,
                status,
                _get(counts, "processing"),
                _get(counts, "succeeded"),
            )
            self.sleep(self.poll_interval)

    def collect(self, batch_id: str) -> dict[str, BatchOutcome]:
        return index_results_by_custom_id(self.client.messages.batches.results(batch_id))
