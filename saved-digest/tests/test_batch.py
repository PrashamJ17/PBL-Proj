"""Batch plumbing: result mapping, web-search error shape, pause_turn, polling.

These are the three documented behaviours that quietly produce wrong output if
mishandled, so each gets an explicit test.
"""

from __future__ import annotations

import pytest

from saveddigest.triage.batch import (
    CANCELED,
    ERRORED,
    EXPIRED,
    SUCCEEDED,
    BatchRunner,
    citations_of,
    index_results_by_custom_id,
    is_paused,
    is_refusal,
    pending_tool_use_ids,
    search_request_count,
    stop_reason,
    text_of,
    tool_result_payload,
    web_search_failure,
)


def result(custom_id: str, kind: str = SUCCEEDED, **kw):
    inner: dict = {"type": kind}
    if kind == SUCCEEDED:
        inner["message"] = kw.get("message", {"content": [], "stop_reason": "end_turn"})
    else:
        inner["error"] = kw.get("error", {"type": kind, "message": "boom"})
    return {"custom_id": custom_id, "result": inner}


# --------------------------------------------------------------------------
# result ordering — the mis-attribution bug
# --------------------------------------------------------------------------
def test_results_are_keyed_by_custom_id_not_position():
    """Batch results arrive in arbitrary order; position would mis-assign summaries."""
    submitted = ["item-1", "item-2", "item-3"]
    returned_out_of_order = [result("item-3"), result("item-1"), result("item-2")]

    indexed = index_results_by_custom_id(returned_out_of_order)

    assert set(indexed) == set(submitted)
    for custom_id in submitted:
        assert indexed[custom_id].custom_id == custom_id


def test_out_of_order_results_keep_their_own_payloads():
    a = result("item-a", message={"content": [{"type": "text", "text": "A body"}]})
    b = result("item-b", message={"content": [{"type": "text", "text": "B body"}]})
    indexed = index_results_by_custom_id([b, a])
    assert text_of(indexed["item-a"].message) == "A body"
    assert text_of(indexed["item-b"].message) == "B body"


def test_partial_batch_leaves_missing_ids_absent():
    """A missing id must be detectable, not silently mapped to someone else's result."""
    indexed = index_results_by_custom_id([result("item-1")])
    assert "item-2" not in indexed


def test_results_with_no_custom_id_are_dropped():
    indexed = index_results_by_custom_id([{"result": {"type": SUCCEEDED}}, result("ok")])
    assert set(indexed) == {"ok"}


def test_empty_results():
    assert index_results_by_custom_id([]) == {}


def test_duplicate_custom_ids_keep_the_last():
    first = result("dupe", message={"content": [{"type": "text", "text": "first"}]})
    second = result("dupe", message={"content": [{"type": "text", "text": "second"}]})
    indexed = index_results_by_custom_id([first, second])
    assert text_of(indexed["dupe"].message) == "second"


# --------------------------------------------------------------------------
# outcome classification
# --------------------------------------------------------------------------
def test_succeeded_outcome_is_ok():
    outcome = index_results_by_custom_id([result("a")])["a"]
    assert outcome.ok and not outcome.retryable


@pytest.mark.parametrize("kind", [CANCELED, EXPIRED])
def test_canceled_and_expired_are_retryable(kind):
    outcome = index_results_by_custom_id([result("a", kind)])["a"]
    assert not outcome.ok
    assert outcome.retryable


def test_server_error_is_retryable():
    outcome = index_results_by_custom_id(
        [result("a", ERRORED, error={"type": "api_error", "message": "overloaded"})]
    )["a"]
    assert outcome.retryable
    assert "api_error" in outcome.error


def test_invalid_request_is_not_retryable():
    """A malformed request will fail identically forever; stop paying for it."""
    outcome = index_results_by_custom_id(
        [result("a", ERRORED, error={"type": "invalid_request", "message": "bad schema"})]
    )["a"]
    assert not outcome.retryable


def test_succeeded_with_no_message_is_not_ok():
    indexed = index_results_by_custom_id([{"custom_id": "a", "result": {"type": SUCCEEDED}}])
    assert not indexed["a"].ok


def test_unknown_result_kind_defaults_to_errored():
    indexed = index_results_by_custom_id([{"custom_id": "a", "result": {}}])
    assert indexed["a"].kind == ERRORED


# --------------------------------------------------------------------------
# web search failure detection — HTTP 200 with an error inside
# --------------------------------------------------------------------------
def test_successful_search_has_no_failure():
    message = {
        "content": [
            {
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_1",
                "content": [
                    {
                        "type": "web_search_result",
                        "url": "https://example.com/",
                        "title": "Example",
                    }
                ],
            }
        ]
    }
    assert web_search_failure(message) is None


@pytest.mark.parametrize(
    "code",
    ["max_uses_exceeded", "too_many_requests", "query_too_long", "unavailable"],
)
def test_search_error_object_is_detected(code):
    """`content` is an object on failure and a list on success — that's the tell."""
    message = {
        "content": [
            {
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_1",
                "content": {"type": "web_search_tool_result_error", "error_code": code},
            }
        ]
    }
    assert web_search_failure(message) == code


def test_empty_result_list_is_not_a_failure():
    """A search that matched nothing returns an empty list, which is not an error."""
    message = {
        "content": [
            {"type": "web_search_tool_result", "tool_use_id": "s1", "content": []}
        ]
    }
    assert web_search_failure(message) is None


def test_failure_found_among_several_searches():
    message = {
        "content": [
            {"type": "web_search_tool_result", "content": [{"url": "https://a.test/"}]},
            {
                "type": "web_search_tool_result",
                "content": {"type": "web_search_tool_result_error", "error_code": "unavailable"},
            },
        ]
    }
    assert web_search_failure(message) == "unavailable"


def test_message_with_no_search_blocks():
    assert web_search_failure({"content": [{"type": "text", "text": "hi"}]}) is None


def test_web_search_failure_on_empty_message():
    assert web_search_failure({}) is None
    assert web_search_failure(None) is None


# --------------------------------------------------------------------------
# stop reasons
# --------------------------------------------------------------------------
def test_pause_turn_detected():
    assert is_paused({"stop_reason": "pause_turn"})
    assert not is_paused({"stop_reason": "end_turn"})


def test_refusal_detected():
    assert is_refusal({"stop_reason": "refusal"})
    assert not is_refusal({"stop_reason": "end_turn"})


def test_stop_reason_missing_or_wrong_type():
    assert stop_reason({}) is None
    assert stop_reason({"stop_reason": 42}) is None


# --------------------------------------------------------------------------
# usage and citations
# --------------------------------------------------------------------------
def test_search_request_count_read_from_usage():
    message = {"usage": {"server_tool_use": {"web_search_requests": 3}}}
    assert search_request_count(message) == 3


@pytest.mark.parametrize(
    "message",
    [{}, {"usage": {}}, {"usage": {"server_tool_use": {}}},
     {"usage": {"server_tool_use": {"web_search_requests": "three"}}},
     {"usage": {"server_tool_use": {"web_search_requests": -1}}}],
)
def test_search_request_count_defaults_to_zero(message):
    assert search_request_count(message) == 0


def test_citations_collected_and_deduplicated():
    message = {
        "content": [
            {
                "type": "text",
                "text": "Django 5.2 is current",
                "citations": [
                    {
                        "type": "web_search_result_location",
                        "url": "https://docs.djangoproject.com/",
                        "title": "Django docs",
                        "cited_text": "Django 5.2 is the current release",
                    }
                ],
            },
            {
                "type": "text",
                "text": "and 4.2 is LTS",
                "citations": [
                    {"url": "https://docs.djangoproject.com/", "title": "Django docs"},
                    {"url": "https://endoflife.date/django", "title": "endoflife"},
                ],
            },
        ]
    }
    citations = citations_of(message)
    assert [c["url"] for c in citations] == [
        "https://docs.djangoproject.com/",
        "https://endoflife.date/django",
    ]
    assert citations[0]["cited_text"].startswith("Django 5.2")


def test_citation_title_defaults_to_the_url():
    message = {"content": [{"type": "text", "citations": [{"url": "https://a.test/"}]}]}
    assert citations_of(message)[0]["title"] == "https://a.test/"


def test_cited_text_is_truncated():
    message = {
        "content": [
            {"type": "text", "citations": [{"url": "https://a.test/", "cited_text": "x" * 900}]}
        ]
    }
    assert len(citations_of(message)[0]["cited_text"]) == 300


def test_citations_on_a_message_with_none():
    assert citations_of({"content": [{"type": "text", "text": "no sources"}]}) == []


# --------------------------------------------------------------------------
# tool-based structured output (the fallback path)
# --------------------------------------------------------------------------
def test_tool_result_payload_extracted():
    message = {
        "content": [
            {"type": "text", "text": "Let me record that."},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "record_verdict",
                "input": {"verdict": "superseded"},
            },
        ]
    }
    assert tool_result_payload(message, "record_verdict") == {"verdict": "superseded"}


def test_tool_result_payload_ignores_other_tools():
    message = {
        "content": [
            {"type": "tool_use", "id": "t1", "name": "something_else", "input": {"a": 1}}
        ]
    }
    assert tool_result_payload(message, "record_verdict") is None


def test_tool_result_payload_when_absent():
    assert tool_result_payload({"content": []}, "record_verdict") is None


def test_pending_tool_use_ids():
    message = {
        "content": [
            {"type": "tool_use", "id": "toolu_a", "name": "record_verdict", "input": {}},
            {"type": "tool_use", "id": "toolu_b", "name": "record_verdict", "input": {}},
            {"type": "tool_use", "id": "toolu_c", "name": "other", "input": {}},
        ]
    }
    assert pending_tool_use_ids(message, "record_verdict") == ["toolu_a", "toolu_b"]


# --------------------------------------------------------------------------
# text extraction
# --------------------------------------------------------------------------
def test_text_of_concatenates_only_text_blocks():
    message = {
        "content": [
            {"type": "text", "text": "part one "},
            {"type": "server_tool_use", "name": "web_search", "input": {}},
            {"type": "text", "text": "part two"},
        ]
    }
    assert text_of(message) == "part one part two"


def test_text_of_on_empty_or_odd_content():
    assert text_of({}) == ""
    assert text_of({"content": None}) == ""
    assert text_of({"content": "not a list"}) == ""


# --------------------------------------------------------------------------
# polling
# --------------------------------------------------------------------------
class FakeBatches:
    def __init__(self, statuses, results=None):
        self.statuses = list(statuses)
        self._results = results or []
        self.created = None
        self.retrieve_calls = 0

    def create(self, requests):
        self.created = requests
        return {"id": "batch_test"}

    def retrieve(self, batch_id):
        self.retrieve_calls += 1
        status = self.statuses.pop(0) if self.statuses else "ended"
        return {"processing_status": status, "request_counts": {"processing": 1}}

    def results(self, batch_id):
        return self._results


class FakeClient:
    def __init__(self, batches):
        self.messages = type("M", (), {"batches": batches})()


def test_runner_polls_until_ended_then_collects():
    batches = FakeBatches(["in_progress", "in_progress", "ended"], [result("item-1")])
    runner = BatchRunner(FakeClient(batches), poll_interval=0, sleep=lambda _: None)
    outcomes = runner.run(["req"])
    assert batches.retrieve_calls == 3
    assert set(outcomes) == {"item-1"}


def test_runner_short_circuits_on_no_requests():
    batches = FakeBatches(["ended"])
    runner = BatchRunner(FakeClient(batches), sleep=lambda _: None)
    assert runner.run([]) == {}
    assert batches.created is None, "must not submit an empty batch"


def test_runner_times_out_with_an_actionable_message():
    """A slow batch is not lost; the message must say so."""
    batches = FakeBatches(["in_progress"] * 100)
    clock = iter([0, 10, 10_000, 20_000])
    runner = BatchRunner(
        FakeClient(batches),
        poll_interval=0,
        timeout=100,
        sleep=lambda _: None,
        monotonic=lambda: next(clock),
    )
    with pytest.raises(TimeoutError, match="re-run the stage later"):
        runner.run(["req"])


def test_runner_passes_requests_through_unchanged():
    batches = FakeBatches(["ended"], [])
    runner = BatchRunner(FakeClient(batches), poll_interval=0, sleep=lambda _: None)
    runner.run(["a", "b"])
    assert batches.created == ["a", "b"]
