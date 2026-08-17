"""Capture -> store, end to end, on the real recorded Todoist payload.

The unit tests prove the transform is right. This proves the transform composes
with the store correctly — specifically that a weekly re-sync of the *same*
project does not duplicate rows or reset work already paid for.
"""

from __future__ import annotations

import json

from saveddigest.sources.todoist import items_from_tasks
from saveddigest.store import Platform, Staleness, Status, Store
from tests.test_todoist_source import REAL_PAYLOAD


def sync(store: Store, payload: list[dict]) -> tuple[int, int]:
    """Mimic what the `sync` command does: parse, then upsert each item."""
    items, _ = items_from_tasks(payload, skip_label=None)
    created = 0
    for item in items:
        _, was_created = store.upsert(item)
        created += int(was_created)
    return created, len(items)


def test_first_sync_creates_one_row_per_distinct_save(tmp_path):
    with Store(tmp_path / "a.db") as store:
        created, seen = sync(store, REAL_PAYLOAD)
        assert (created, seen) == (3, 3)
        assert len(store.all_items()) == 3


def test_second_sync_of_the_same_project_creates_nothing(tmp_path):
    """The weekly-repeat bug, checked at the integration level."""
    with Store(tmp_path / "b.db") as store:
        sync(store, REAL_PAYLOAD)
        created, seen = sync(store, REAL_PAYLOAD)
        assert created == 0
        assert seen == 3
        assert len(store.all_items()) == 3


def test_resync_preserves_summaries_already_paid_for(tmp_path):
    with Store(tmp_path / "c.db") as store:
        sync(store, REAL_PAYLOAD)

        reel = store.get_by_external_id(Platform.INSTAGRAM, "DAbCdEfGhIj")
        store.advance(
            reel.id,
            Status.SUMMARISED,
            content_text="caption text about compound interest",
            summary_json=json.dumps({"tldr": "compound interest compounds"}),
            staleness_class=str(Staleness.EVERGREEN),
        )

        sync(store, REAL_PAYLOAD)  # next week

        after = store.get_by_external_id(Platform.INSTAGRAM, "DAbCdEfGhIj")
        assert after.status is Status.SUMMARISED
        assert after.summary == {"tldr": "compound interest compounds"}
        assert after.staleness is Staleness.EVERGREEN


def test_new_save_appearing_later_is_picked_up_without_disturbing_the_rest(tmp_path):
    with Store(tmp_path / "d.db") as store:
        sync(store, REAL_PAYLOAD)
        later = REAL_PAYLOAD + [
            {
                "id": "brand-new",
                "content": "https://www.instagram.com/reel/NEWshortcode/",
                "description": "",
                "addedAt": "2026-08-18T09:00:00.000Z",
                "labels": [],
            }
        ]
        created, _ = sync(store, later)
        assert created == 1
        assert len(store.all_items()) == 4


def test_queue_order_is_oldest_save_first(tmp_path):
    """The digest surfaces things that have been rotting longest."""
    with Store(tmp_path / "e.db") as store:
        sync(store, REAL_PAYLOAD)
        queued = store.by_status(Status.NEW)
        dates = [i.saved_at for i in queued]
        assert dates == sorted(dates)


def test_stage_limit_partitions_the_backlog(tmp_path):
    """`--limit` must hand back a prefix of the queue, not a random subset."""
    with Store(tmp_path / "f.db") as store:
        sync(store, REAL_PAYLOAD)
        first_two = store.by_status(Status.NEW, limit=2)
        assert len(first_two) == 2
        assert [i.external_id for i in first_two] == [
            i.external_id for i in store.by_status(Status.NEW)[:2]
        ]


def test_title_backfilled_from_the_duplicate_reaches_the_database(tmp_path):
    with Store(tmp_path / "g.db") as store:
        sync(store, REAL_PAYLOAD)
        reel = store.get_by_external_id(Platform.INSTAGRAM, "DAbCdEfGhIj")
        assert reel.title == "Great explainer on compound interest"
