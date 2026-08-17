"""Store correctness — the dedup and no-regression rules the pipeline depends on."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from saveddigest.store import (
    NEEDS_VERIFICATION,
    Item,
    Liveness,
    Platform,
    Staleness,
    Status,
    Store,
    Verdict,
    utcnow_iso,
)


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as s:
        yield s


def make_item(**over) -> Item:
    base = dict(
        platform=Platform.YOUTUBE,
        external_id="dQw4w9WgXcQ",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        source="youtube_playlist",
        title="A video",
        saved_at="2026-01-01T00:00:00+00:00",
    )
    base.update(over)
    return Item(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# dedup
# --------------------------------------------------------------------------
def test_upsert_creates_then_dedupes(store):
    _, created = store.upsert(make_item())
    assert created is True
    _, created_again = store.upsert(make_item())
    assert created_again is False
    assert len(store.all_items()) == 1


def test_same_external_id_different_platform_is_a_different_item(store):
    store.upsert(make_item(platform=Platform.YOUTUBE, external_id="abc123"))
    store.upsert(
        make_item(
            platform=Platform.INSTAGRAM,
            external_id="abc123",
            url="https://www.instagram.com/reel/abc123/",
            source="todoist",
        )
    )
    assert len(store.all_items()) == 2


def test_resync_does_not_regress_pipeline_progress(store):
    """The money bug: a weekly re-sync must not re-summarise the whole library."""
    stored, _ = store.upsert(make_item())
    store.advance(
        stored.id,
        Status.SUMMARISED,
        content_text="transcript body",
        summary_json=json.dumps({"tldr": "already done"}),
        staleness_class=str(Staleness.EVERGREEN),
    )

    # Same video comes back on the next sync, as it always will.
    store.upsert(make_item(title="A video (renamed)"))

    after = store.get_by_external_id(Platform.YOUTUBE, "dQw4w9WgXcQ")
    assert after.status is Status.SUMMARISED, "re-sync reset the stage"
    assert after.summary == {"tldr": "already done"}, "re-sync dropped the summary"
    assert after.content_text == "transcript body"
    assert after.title == "A video (renamed)", "metadata should still refresh"


def test_resync_keeps_earliest_saved_at(store):
    """Age drives the digest sort order; a re-sync must not make an old save look new."""
    store.upsert(make_item(saved_at="2025-03-01T00:00:00+00:00"))
    store.upsert(make_item(saved_at="2026-08-01T00:00:00+00:00"))
    item = store.get_by_external_id(Platform.YOUTUBE, "dQw4w9WgXcQ")
    assert item.saved_at == "2025-03-01T00:00:00+00:00"


def test_resync_fills_in_a_previously_unknown_saved_at(store):
    store.upsert(make_item(saved_at=None))
    store.upsert(make_item(saved_at="2026-02-02T00:00:00+00:00"))
    item = store.get_by_external_id(Platform.YOUTUBE, "dQw4w9WgXcQ")
    assert item.saved_at == "2026-02-02T00:00:00+00:00"


def test_upsert_sets_captured_at_when_absent(store):
    stored, _ = store.upsert(make_item(captured_at=None))
    assert stored.captured_at
    assert store.get(stored.id).captured_at == stored.captured_at


# --------------------------------------------------------------------------
# status transitions
# --------------------------------------------------------------------------
def test_advance_forward(store):
    stored, _ = store.upsert(make_item())
    store.advance(stored.id, Status.ENRICHED)
    assert store.get(stored.id).status is Status.ENRICHED


def test_advance_backwards_raises(store):
    stored, _ = store.upsert(make_item())
    store.advance(stored.id, Status.VERIFIED)
    with pytest.raises(ValueError, match="backwards"):
        store.advance(stored.id, Status.ENRICHED)


def test_advance_to_same_status_is_idempotent(store):
    """A retried stage rewrites its own status; that must not raise."""
    stored, _ = store.upsert(make_item())
    store.advance(stored.id, Status.ENRICHED)
    store.advance(stored.id, Status.ENRICHED, content_text="second attempt")
    assert store.get(stored.id).content_text == "second attempt"


def test_can_always_fail_and_recover(store):
    stored, _ = store.upsert(make_item())
    store.advance(stored.id, Status.VERIFIED)
    store.advance(stored.id, Status.FAILED, error="boom")
    assert store.get(stored.id).status is Status.FAILED
    # And a later successful run can move it on again.
    store.advance(stored.id, Status.DELIVERED)
    assert store.get(stored.id).status is Status.DELIVERED


def test_advance_unknown_item_raises(store):
    with pytest.raises(KeyError):
        store.advance(9999, Status.ENRICHED)


def test_update_rejects_unknown_column(store):
    stored, _ = store.upsert(make_item())
    with pytest.raises(ValueError, match="not updatable"):
        store.update(stored.id, definitely_not_a_column="x")


def test_update_rejects_identity_columns(store):
    """Rewriting the dedup key would orphan the row from its source."""
    stored, _ = store.upsert(make_item())
    with pytest.raises(ValueError, match="not updatable"):
        store.update(stored.id, external_id="something-else")


def test_update_with_no_fields_is_a_noop(store):
    stored, _ = store.upsert(make_item())
    store.update(stored.id)
    assert store.get(stored.id).title == "A video"


def test_update_accepts_enum_values(store):
    stored, _ = store.upsert(make_item())
    store.update(stored.id, liveness=Liveness.DEAD)
    assert store.get(stored.id).liveness is Liveness.DEAD


# --------------------------------------------------------------------------
# queue semantics
# --------------------------------------------------------------------------
def test_by_status_orders_oldest_save_first(store):
    store.upsert(make_item(external_id="new", saved_at="2026-08-01T00:00:00+00:00"))
    store.upsert(make_item(external_id="old", saved_at="2024-01-01T00:00:00+00:00"))
    store.upsert(make_item(external_id="mid", saved_at="2025-06-01T00:00:00+00:00"))
    assert [i.external_id for i in store.by_status(Status.NEW)] == ["old", "mid", "new"]


def test_by_status_falls_back_to_captured_at_for_ordering(store):
    """Watch-Later imports have no save date; they must still sort deterministically."""
    store.upsert(
        make_item(external_id="a", saved_at=None, captured_at="2026-01-02T00:00:00+00:00")
    )
    store.upsert(
        make_item(external_id="b", saved_at=None, captured_at="2026-01-01T00:00:00+00:00")
    )
    assert [i.external_id for i in store.by_status(Status.NEW)] == ["b", "a"]


def test_by_status_honours_limit(store):
    for n in range(5):
        store.upsert(make_item(external_id=f"v{n}"))
    assert len(store.by_status(Status.NEW, limit=2)) == 2


def test_by_status_skips_repeatedly_failing_items(store):
    stored, _ = store.upsert(make_item())
    for _ in range(3):
        store.record_failure(stored.id, "no captions available")
    assert store.by_status(Status.NEW) == []
    assert store.get(stored.id).attempts == 3
    assert "no captions" in store.get(stored.id).error


def test_by_status_accepts_multiple_statuses(store):
    a, _ = store.upsert(make_item(external_id="a"))
    b, _ = store.upsert(make_item(external_id="b"))
    store.advance(b.id, Status.ENRICHED)
    found = {i.external_id for i in store.by_status([Status.NEW, Status.ENRICHED])}
    assert found == {"a", "b"}


def test_record_failure_truncates_giant_messages(store):
    stored, _ = store.upsert(make_item())
    store.record_failure(stored.id, "x" * 10_000)
    assert len(store.get(stored.id).error) == 2000


def test_counts_by_status(store):
    a, _ = store.upsert(make_item(external_id="a"))
    store.upsert(make_item(external_id="b"))
    store.advance(a.id, Status.ENRICHED)
    assert store.counts_by_status() == {"new": 1, "enriched": 1}


# --------------------------------------------------------------------------
# parsing helpers on Item
# --------------------------------------------------------------------------
def test_summary_and_verdict_json_round_trip():
    item = make_item(
        summary_json=json.dumps({"tldr": "hi"}),
        verdict_json=json.dumps({"verdict": str(Verdict.SUPERSEDED)}),
    )
    assert item.summary["tldr"] == "hi"
    assert item.verdict["verdict"] == "superseded"


def test_malformed_json_columns_degrade_to_none():
    """A truncated write must not crash the digest renderer."""
    item = make_item(summary_json="{not json", verdict_json="[]")
    assert item.summary is None
    assert item.verdict is None  # a JSON list is not a summary object


def test_unknown_staleness_class_fails_safe_to_needing_a_check():
    item = make_item(staleness_class="something_from_the_future")
    assert item.staleness is Staleness.TIME_SENSITIVE
    assert item.staleness in NEEDS_VERIFICATION


def test_evergreen_is_the_only_class_that_skips_verification():
    assert Staleness.EVERGREEN not in NEEDS_VERIFICATION
    assert set(Staleness) - {Staleness.EVERGREEN} == set(NEEDS_VERIFICATION)


@pytest.mark.parametrize(
    "saved_at",
    [
        "2026-08-07T00:00:00+00:00",
        "2026-08-07T00:00:00Z",  # trailing Z
        "2026-08-07T00:00:00",  # naive, assumed UTC
    ],
)
def test_days_since_saved_handles_timestamp_variants(saved_at):
    now = datetime(2026, 8, 17, tzinfo=UTC)
    assert make_item(saved_at=saved_at).days_since_saved(now) == 10


def test_days_since_saved_falls_back_to_captured_at():
    now = datetime(2026, 8, 17, tzinfo=UTC)
    item = make_item(saved_at=None, captured_at="2026-08-10T00:00:00+00:00")
    assert item.days_since_saved(now) == 7


def test_days_since_saved_is_zero_when_unknown():
    assert make_item(saved_at=None, captured_at=None).days_since_saved() == 0


def test_days_since_saved_never_negative_for_future_dates():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    future = (now + timedelta(days=5)).isoformat()
    assert make_item(saved_at=future).days_since_saved(now) == 0


def test_days_since_saved_ignores_unparseable_dates():
    assert make_item(saved_at="last tuesday", captured_at=None).days_since_saved() == 0


# --------------------------------------------------------------------------
# meta / persistence
# --------------------------------------------------------------------------
def test_meta_round_trip(store):
    assert store.get_meta("nope") is None
    store.set_meta("verify_structured_output", "supported")
    assert store.get_meta("verify_structured_output") == "supported"
    store.set_meta("verify_structured_output", "unsupported")
    assert store.get_meta("verify_structured_output") == "unsupported"


def test_schema_version_recorded(store):
    assert store.get_meta("schema_version") == "1"


def test_reopening_an_existing_db_preserves_rows(tmp_path):
    path = tmp_path / "persist.db"
    with Store(path) as s:
        s.upsert(make_item())
    with Store(path) as s:
        assert len(s.all_items()) == 1


def test_utcnow_iso_is_timezone_aware_and_second_precision():
    stamp = utcnow_iso()
    assert stamp.endswith("+00:00")
    assert "." not in stamp
