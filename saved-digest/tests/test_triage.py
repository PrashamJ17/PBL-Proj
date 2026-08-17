"""Pass A and Pass B: prompt construction, output coercion, and the honesty guards.

The guards are the point of this file. An `unverified` item reported as
`still_valid` is the worst output this tool can produce, because the user acts on
it without re-checking, so every path that could produce one is pinned here.
"""

from __future__ import annotations

import json

import pytest

from saveddigest.store import Item, Platform, Staleness, Status, Store, Verdict
from saveddigest.triage import summarize, verify
from saveddigest.triage.batch import BatchOutcome
from saveddigest.triage.schemas import (
    coerce_expiry_date,
    coerce_sources,
    coerce_summary,
    coerce_verdict,
    not_applicable_verdict,
    unverified_verdict,
)


def make_item(**over) -> Item:
    base = dict(
        platform=Platform.YOUTUBE,
        external_id="abcdefghijk",
        url="https://www.youtube.com/watch?v=abcdefghijk",
        source="youtube_playlist",
        title="Deploying Django in 2023",
        author="Some Channel",
        published_at="2023-05-01T00:00:00Z",
        saved_at="2023-06-01T00:00:00Z",
        content_text="Use Django 4.2 which is the current LTS release.",
        content_kind="auto_captions",
        id=42,
    )
    base.update(over)
    return Item(**base)  # type: ignore[arg-type]


GOOD_SUMMARY = {
    "tldr": "How to deploy Django.",
    "detailed_summary": "A long walkthrough of deploying Django with gunicorn...",
    "key_points": ["Use gunicorn", "Django 4.2 is the current LTS"],
    "actionable_steps": ["Pin Django to 4.2"],
    "tools_mentioned": ["Django 4.2", "gunicorn"],
    "prerequisites": ["Python basics"],
    "topics": ["django", "deployment"],
    "staleness_class": "version_bound",
    "staleness_reason": "Pinned to a specific Django LTS.",
    "claims_to_verify": ["Django 4.2 is the current LTS release"],
    "expiry_date": "",
    "content_quality": "substantive",
}


# ==========================================================================
# Pass A
# ==========================================================================
def test_custom_id_round_trips():
    item = make_item()
    cid = summarize.custom_id_for(item)
    assert summarize.item_id_from_custom_id(cid) == 42


def test_item_id_from_foreign_custom_id():
    assert summarize.item_id_from_custom_id("verify-42") is None
    assert summarize.item_id_from_custom_id("summarise-not-a-number") is None


def test_prompt_includes_metadata_and_content():
    prompt = summarize.build_user_prompt(make_item())
    assert "Deploying Django in 2023" in prompt
    assert "Some Channel" in prompt
    assert "Django 4.2" in prompt
    assert "--- CONTENT ---" in prompt


def test_prompt_warns_that_captions_are_machine_generated():
    """Auto-captions mishear technical terms; the model should not treat them as exact."""
    prompt = summarize.build_user_prompt(make_item(content_kind="auto_captions"))
    assert "mis-transcribed" in prompt


def test_prompt_tells_the_model_a_caption_is_not_the_audio():
    """Guards against inventing what an Instagram reel showed."""
    prompt = summarize.build_user_prompt(
        make_item(platform=Platform.INSTAGRAM, content_kind="caption")
    )
    assert "not the spoken audio" in prompt
    assert "do not infer" in prompt


def test_prompt_flags_metadata_only_items():
    prompt = summarize.build_user_prompt(make_item(content_kind="metadata_only"))
    assert "no transcript or caption" in prompt


def test_prompt_omits_absent_metadata_without_placeholders():
    prompt = summarize.build_user_prompt(make_item(title=None, author=None))
    assert "Title:" not in prompt
    assert "Author/channel:" not in prompt
    assert "None" not in prompt


def test_long_transcripts_are_truncated_and_disclosed():
    item = make_item(content_text="word " * 60_000)
    prompt = summarize.build_user_prompt(item, max_content_chars=1_000)
    assert "content truncated" in prompt
    assert len(prompt) < 3_000


def test_truncate_content_reports_whether_it_cut():
    short, cut = summarize.truncate_content("hello", limit=100)
    assert (short, cut) == ("hello", False)
    long, cut = summarize.truncate_content("a" * 200, limit=100)
    assert cut is True and len(long) == 100


def test_truncate_prefers_a_word_boundary():
    text = ("word " * 100).strip()
    cut, _ = summarize.truncate_content(text, limit=52)
    assert not cut.endswith("wor")
    assert cut.endswith("word")


def test_build_request_shape():
    request = summarize.build_request(make_item(), model="claude-opus-5", effort="medium")
    assert request["custom_id"] == "summarise-42"
    params = request["params"]
    assert params["model"] == "claude-opus-5"
    assert params["output_config"]["effort"] == "medium"
    assert params["output_config"]["format"]["type"] == "json_schema"
    # Pass A must not carry tools: that is what makes structured output safe here.
    assert "tools" not in params


def test_parse_summary_message_reads_json():
    message = {"content": [{"type": "text", "text": json.dumps(GOOD_SUMMARY)}]}
    parsed = summarize.parse_summary_message(message)
    assert parsed["staleness_class"] == "version_bound"
    assert parsed["claims_to_verify"] == ["Django 4.2 is the current LTS release"]


def test_parse_summary_message_on_refusal():
    assert summarize.parse_summary_message({"stop_reason": "refusal", "content": []}) is None


def test_parse_summary_message_on_truncated_json():
    message = {"content": [{"type": "text", "text": '{"tldr": "cut off'}]}
    assert summarize.parse_summary_message(message) is None


def test_parse_summary_message_on_empty_body():
    assert summarize.parse_summary_message({"content": []}) is None


def test_needs_web_check_only_for_non_evergreen():
    assert not summarize.needs_web_check({"staleness_class": "evergreen"})
    for cls in ("time_sensitive", "version_bound", "dated_event"):
        assert summarize.needs_web_check({"staleness_class": cls})


def test_apply_outcome_advances_and_stores(tmp_path):
    with Store(tmp_path / "a.db") as store:
        stored, _ = store.upsert(make_item(id=None))
        store.advance(stored.id, Status.ENRICHED)
        outcome = BatchOutcome(
            custom_id="summarise-1",
            kind="succeeded",
            message={"content": [{"type": "text", "text": json.dumps(GOOD_SUMMARY)}]},
        )
        assert summarize.apply_outcome(store, stored, outcome) is True

        after = store.get(stored.id)
        assert after.status is Status.SUMMARISED
        assert after.staleness is Staleness.VERSION_BOUND
        assert after.summary["tldr"] == "How to deploy Django."


def test_apply_outcome_on_transport_failure_records_attempt(tmp_path):
    with Store(tmp_path / "b.db") as store:
        stored, _ = store.upsert(make_item(id=None))
        store.advance(stored.id, Status.ENRICHED)
        outcome = BatchOutcome(
            custom_id="summarise-1", kind="errored", error="api_error: overloaded"
        )
        assert summarize.apply_outcome(store, stored, outcome) is False

        after = store.get(stored.id)
        assert after.status is Status.ENRICHED, "must stay put so it retries"
        assert after.attempts == 1
        assert "overloaded" in after.error


def test_apply_outcome_on_unparseable_output_does_not_advance(tmp_path):
    with Store(tmp_path / "c.db") as store:
        stored, _ = store.upsert(make_item(id=None))
        store.advance(stored.id, Status.ENRICHED)
        outcome = BatchOutcome(
            custom_id="summarise-1",
            kind="succeeded",
            message={"content": [{"type": "text", "text": "not json"}]},
        )
        assert summarize.apply_outcome(store, stored, outcome) is False
        assert store.get(stored.id).status is Status.ENRICHED


# ==========================================================================
# Pass A output coercion
# ==========================================================================
def test_coerce_summary_fills_every_key_from_nothing():
    coerced = coerce_summary(None)
    assert set(coerced) == set(GOOD_SUMMARY) | set()
    assert coerced["tldr"] == ""
    assert coerced["key_points"] == []


def test_coerce_summary_unknown_staleness_fails_safe_to_checking():
    coerced = coerce_summary({**GOOD_SUMMARY, "staleness_class": "brand_new_class"})
    assert coerced["staleness_class"] == Staleness.TIME_SENSITIVE.value


def test_coerce_summary_drops_claims_on_evergreen():
    """Keeps Pass B's queue consistent with the classification."""
    coerced = coerce_summary(
        {**GOOD_SUMMARY, "staleness_class": "evergreen", "claims_to_verify": ["x"]}
    )
    assert coerced["claims_to_verify"] == []


def test_coerce_summary_filters_non_string_list_entries():
    coerced = coerce_summary({**GOOD_SUMMARY, "key_points": ["ok", 42, None, "  ", "fine"]})
    assert coerced["key_points"] == ["ok", "fine"]


def test_coerce_summary_caps_runaway_output():
    coerced = coerce_summary(
        {**GOOD_SUMMARY, "detailed_summary": "x" * 100_000, "key_points": ["y"] * 500}
    )
    assert len(coerced["detailed_summary"]) == 20_000
    assert len(coerced["key_points"]) == 40


def test_coerce_summary_unknown_quality_becomes_unclear():
    assert coerce_summary({**GOOD_SUMMARY, "content_quality": "amazing"})[
        "content_quality"
    ] == "unclear"


@pytest.mark.parametrize("raw", ["2026-08-17", "2024-01-01"])
def test_valid_expiry_dates_kept(raw):
    assert coerce_expiry_date(raw) == raw


@pytest.mark.parametrize(
    "raw", ["", "next tuesday", "17/08/2026", "2026-8-7", None, 20260817, "2026-08-17T00:00:00Z"]
)
def test_invalid_expiry_dates_become_none(raw):
    """A malformed date compared against today would wrongly expire a live item."""
    assert coerce_expiry_date(raw) is None


# ==========================================================================
# Pass B
# ==========================================================================
GOOD_VERDICT = {
    "verdict": "superseded",
    "confidence": "high",
    "what_changed": "Django 4.2 is no longer the newest LTS.",
    "superseded_by": "https://docs.djangoproject.com/en/5.2/",
    "current_state": "Django 5.2 is current; 4.2 LTS support ends April 2026.",
    "checked_claims": [
        {"claim": "Django 4.2 is the current LTS", "holds": "no", "note": "5.2 is current"}
    ],
    "sources": [{"title": "Django docs", "url": "https://docs.djangoproject.com/"}],
}


def searched_message(payload: dict, *, searches: int = 2, citations=None) -> dict:
    block: dict = {"type": "text", "text": json.dumps(payload)}
    if citations:
        block["citations"] = citations
    return {
        "content": [block],
        "stop_reason": "end_turn",
        "usage": {"server_tool_use": {"web_search_requests": searches}},
    }


def test_verify_custom_id_round_trips():
    assert verify.item_id_from_custom_id(verify.custom_id_for(make_item())) == 42


def test_verify_prompt_sends_the_summary_not_the_transcript():
    """Re-sending the transcript would double the input cost for no gain."""
    prompt = verify.build_user_prompt(make_item(), GOOD_SUMMARY, today="2026-08-17")
    assert "A long walkthrough" in prompt
    assert "Use Django 4.2 which is the current LTS release." not in prompt


def test_verify_prompt_lists_claims_and_todays_date():
    prompt = verify.build_user_prompt(make_item(), GOOD_SUMMARY, today="2026-08-17")
    assert "Today's date: 2026-08-17" in prompt
    assert "1. Django 4.2 is the current LTS release" in prompt


def test_verify_prompt_handles_no_extracted_claims():
    summary = {**GOOD_SUMMARY, "claims_to_verify": []}
    prompt = verify.build_user_prompt(make_item(), summary, today="2026-08-17")
    assert "No specific claims were extracted" in prompt


def test_structured_request_uses_output_config_format():
    request = verify.build_request(
        make_item(), GOOD_SUMMARY, model="claude-opus-5", today="2026-08-17",
        structured_output=True,
    )
    params = request["params"]
    assert request["custom_id"] == "verify-42"
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert [t["type"] for t in params["tools"]] == [verify.WEB_SEARCH_TOOL_TYPE]
    assert params["tools"][0]["response_inclusion"] == "excluded"
    assert params["tools"][0]["max_uses"] == 4


def test_tool_channel_request_adds_a_strict_tool_and_no_format():
    request = verify.build_request(
        make_item(), GOOD_SUMMARY, model="claude-opus-5", today="2026-08-17",
        structured_output=False,
    )
    params = request["params"]
    assert "format" not in params["output_config"]
    names = [t.get("name") for t in params["tools"]]
    assert verify.VERDICT_TOOL_NAME in names
    tool = next(t for t in params["tools"] if t.get("name") == verify.VERDICT_TOOL_NAME)
    assert tool["strict"] is True
    # `auto`, not forced: forcing would make it answer before searching.
    assert params["tool_choice"] == {"type": "auto"}


def test_max_searches_is_configurable():
    request = verify.build_request(
        make_item(), GOOD_SUMMARY, model="claude-opus-5", today="2026-08-17",
        structured_output=True, max_searches=1,
    )
    assert request["params"]["tools"][0]["max_uses"] == 1


# --- the honesty guards ---------------------------------------------------
def test_verdict_read_from_structured_output():
    verdict = verify.extract_verdict(
        searched_message(GOOD_VERDICT), structured_output=True
    )
    assert verdict["verdict"] == "superseded"
    assert verdict["superseded_by"] == "https://docs.djangoproject.com/en/5.2/"
    assert verdict["searches_used"] == 2


def test_verdict_read_from_the_tool_channel():
    message = {
        "content": [
            {"type": "text", "text": "Checked the docs."},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": verify.VERDICT_TOOL_NAME,
                "input": GOOD_VERDICT,
            },
        ],
        "stop_reason": "tool_use",
        "usage": {"server_tool_use": {"web_search_requests": 2}},
    }
    verdict = verify.extract_verdict(message, structured_output=False)
    assert verdict["verdict"] == "superseded"


def test_a_verdict_produced_without_searching_is_downgraded():
    """The central guard: no search means nothing was checked."""
    message = searched_message(GOOD_VERDICT, searches=0)
    verdict = verify.extract_verdict(message, structured_output=True)
    assert verdict["verdict"] == Verdict.UNVERIFIED.value
    assert "no web search" in verdict["unverified_reason"]


def test_search_failure_downgrades_even_with_a_well_formed_payload():
    message = {
        "content": [
            {"type": "text", "text": json.dumps(GOOD_VERDICT)},
            {
                "type": "web_search_tool_result",
                "content": {
                    "type": "web_search_tool_result_error",
                    "error_code": "too_many_requests",
                },
            },
        ],
        "usage": {"server_tool_use": {"web_search_requests": 1}},
    }
    verdict = verify.extract_verdict(message, structured_output=True)
    assert verdict["verdict"] == Verdict.UNVERIFIED.value
    assert "too_many_requests" in verdict["unverified_reason"]


def test_paused_turn_becomes_unverified_and_says_it_will_retry():
    message = {
        "content": [{"type": "text", "text": json.dumps(GOOD_VERDICT)}],
        "stop_reason": "pause_turn",
        "usage": {"server_tool_use": {"web_search_requests": 4}},
    }
    verdict = verify.extract_verdict(message, structured_output=True)
    assert verdict["verdict"] == Verdict.UNVERIFIED.value
    assert "retry" in verdict["unverified_reason"]


def test_refusal_becomes_unverified():
    verdict = verify.extract_verdict(
        {"stop_reason": "refusal", "content": []}, structured_output=True
    )
    assert verdict["verdict"] == Verdict.UNVERIFIED.value
    assert "declined" in verdict["unverified_reason"]


def test_missing_payload_becomes_unverified():
    message = {"content": [], "usage": {"server_tool_use": {"web_search_requests": 2}}}
    verdict = verify.extract_verdict(message, structured_output=True)
    assert verdict["verdict"] == Verdict.UNVERIFIED.value


def test_wrong_channel_yields_unverified_rather_than_a_wrong_verdict():
    """Reading a tool-channel response as structured output must fail closed."""
    message = {
        "content": [
            {"type": "tool_use", "name": verify.VERDICT_TOOL_NAME, "input": GOOD_VERDICT}
        ],
        "usage": {"server_tool_use": {"web_search_requests": 2}},
    }
    verdict = verify.extract_verdict(message, structured_output=True)
    assert verdict["verdict"] == Verdict.UNVERIFIED.value


def test_require_search_can_be_relaxed_for_expiry_only_checks():
    message = searched_message(GOOD_VERDICT, searches=0)
    verdict = verify.extract_verdict(
        message, structured_output=True, require_search=False
    )
    assert verdict["verdict"] == "superseded"


# --- citations ------------------------------------------------------------
def test_api_citations_are_preferred_and_merged_with_model_sources():
    """API citations come from the search tool and cannot be invented."""
    message = searched_message(
        GOOD_VERDICT,
        citations=[
            {
                "url": "https://endoflife.date/django",
                "title": "Django EOL",
                "cited_text": "4.2 LTS ends April 2026",
            }
        ],
    )
    verdict = verify.extract_verdict(message, structured_output=True)
    urls = [s["url"] for s in verdict["sources"]]
    assert urls[0] == "https://endoflife.date/django"
    assert "https://docs.djangoproject.com/" in urls


def test_sources_without_citations_fall_back_to_the_model_list():
    verdict = verify.extract_verdict(
        searched_message(GOOD_VERDICT), structured_output=True
    )
    assert [s["url"] for s in verdict["sources"]] == ["https://docs.djangoproject.com/"]


# --- verdict coercion ----------------------------------------------------
def test_coerce_verdict_defaults_everything_to_unverified():
    coerced = coerce_verdict(None)
    assert coerced["verdict"] == Verdict.UNVERIFIED.value
    assert coerced["confidence"] == "low"
    assert coerced["sources"] == []


def test_coerce_verdict_rejects_a_non_url_superseded_by():
    """Prose here would render as a broken link in the digest."""
    coerced = coerce_verdict({**GOOD_VERDICT, "superseded_by": "the newer version"})
    assert coerced["superseded_by"] == ""


def test_coerce_verdict_keeps_a_real_url():
    coerced = coerce_verdict({**GOOD_VERDICT, "superseded_by": "http://example.com/x"})
    assert coerced["superseded_by"] == "http://example.com/x"


def test_coerce_verdict_normalises_checked_claims():
    coerced = coerce_verdict(
        {
            **GOOD_VERDICT,
            "checked_claims": [
                {"claim": "a", "holds": "definitely", "note": "n"},
                {"claim": "", "holds": "yes", "note": ""},
                "not a dict",
            ],
        }
    )
    assert coerced["checked_claims"] == [{"claim": "a", "holds": "unclear", "note": "n"}]


def test_coerce_verdict_unknown_verdict_becomes_unverified():
    assert coerce_verdict({**GOOD_VERDICT, "verdict": "probably_fine"})["verdict"] == (
        Verdict.UNVERIFIED.value
    )


def test_coerce_sources_drops_non_urls_and_deduplicates():
    sources = coerce_sources(
        [
            {"title": "A", "url": "https://a.test/"},
            {"title": "A again", "url": "https://a.test/"},
            {"title": "Bad", "url": "not a url"},
            {"title": "No url"},
            "not a dict",
        ]
    )
    assert sources == [{"title": "A", "url": "https://a.test/"}]


def test_coerce_sources_defaults_title_to_url():
    assert coerce_sources([{"url": "https://a.test/"}]) == [
        {"title": "https://a.test/", "url": "https://a.test/"}
    ]


# --- trustworthiness ----------------------------------------------------
@pytest.mark.parametrize(
    ("verdict", "trustworthy"),
    [
        ("still_valid", True),
        ("partly_outdated", True),
        ("superseded", True),
        ("expired", True),
        ("unverified", False),
        ("not_applicable", False),
    ],
)
def test_verdict_is_trustworthy(verdict, trustworthy):
    assert verify.verdict_is_trustworthy({"verdict": verdict}) is trustworthy


def test_unverified_verdict_carries_its_reason():
    verdict = unverified_verdict("search was rate limited")
    assert verdict["verdict"] == Verdict.UNVERIFIED.value
    assert verdict["unverified_reason"] == "search was rate limited"


def test_not_applicable_verdict_shape():
    verdict = not_applicable_verdict()
    assert verdict["verdict"] == Verdict.NOT_APPLICABLE.value
    assert verdict["sources"] == []


# --- persistence --------------------------------------------------------
def test_apply_outcome_advances_even_when_unverified(tmp_path):
    """An unchecked item is still shown, labelled — better than vanishing."""
    with Store(tmp_path / "d.db") as store:
        stored, _ = store.upsert(make_item(id=None))
        store.advance(stored.id, Status.SUMMARISED)
        outcome = BatchOutcome(
            custom_id="verify-1",
            kind="succeeded",
            message=searched_message(GOOD_VERDICT, searches=0),
        )
        assert verify.apply_outcome(store, stored, outcome, structured_output=True)

        after = store.get(stored.id)
        assert after.status is Status.VERIFIED
        assert after.verdict["verdict"] == Verdict.UNVERIFIED.value


def test_apply_outcome_transport_failure_does_not_advance(tmp_path):
    with Store(tmp_path / "e.db") as store:
        stored, _ = store.upsert(make_item(id=None))
        store.advance(stored.id, Status.SUMMARISED)
        outcome = BatchOutcome(custom_id="verify-1", kind="expired", error="expired: ")
        assert not verify.apply_outcome(store, stored, outcome, structured_output=True)
        assert store.get(stored.id).status is Status.SUMMARISED


def test_record_skipped_marks_evergreen_items_not_applicable(tmp_path):
    with Store(tmp_path / "f.db") as store:
        stored, _ = store.upsert(make_item(id=None))
        store.advance(stored.id, Status.SUMMARISED)
        verify.record_skipped(store, stored, not_applicable_verdict())
        after = store.get(stored.id)
        assert after.status is Status.VERIFIED
        assert after.verdict["verdict"] == Verdict.NOT_APPLICABLE.value


# --- capability probe ---------------------------------------------------
class BadRequestError(Exception):
    status_code = 400


class AuthError(Exception):
    status_code = 401


class ProbeClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return {"content": [{"type": "text", "text": '{"ok": true}'}]}


def test_probe_returns_true_when_accepted():
    assert verify.probe_structured_output_support(ProbeClient(), "claude-opus-5") is True


def test_probe_returns_false_on_400():
    client = ProbeClient(BadRequestError("format not allowed with citations"))
    assert verify.probe_structured_output_support(client, "claude-opus-5") is False


def test_probe_reraises_non_400_errors():
    """An auth failure must not be silently recorded as 'unsupported' forever."""
    with pytest.raises(AuthError):
        verify.probe_structured_output_support(ProbeClient(AuthError("bad key")), "m")


def test_probe_result_is_cached_in_the_store(tmp_path):
    with Store(tmp_path / "g.db") as store:
        client = ProbeClient()
        assert verify.resolve_structured_output(store, client, "claude-opus-5") is True
        assert verify.resolve_structured_output(store, client, "claude-opus-5") is True
        assert client.calls == 1, "probe must not repeat once cached"
        assert store.get_meta(verify.CAPABILITY_KEY) == verify.CAPABILITY_SUPPORTED


def test_cached_unsupported_is_honoured(tmp_path):
    with Store(tmp_path / "h.db") as store:
        store.set_meta(verify.CAPABILITY_KEY, verify.CAPABILITY_UNSUPPORTED)
        client = ProbeClient()
        assert verify.resolve_structured_output(store, client, "m") is False
        assert client.calls == 0
