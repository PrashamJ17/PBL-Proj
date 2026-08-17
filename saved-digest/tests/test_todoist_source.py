"""Todoist capture, tested against a payload recorded from the live API.

REAL_PAYLOAD below is not invented: it is the verbatim response for the
"Saved from Instagram" project of a real account. That matters because Todoist
spells the creation timestamp `addedAt` here, while its documented REST v2 uses
`created_at` — a fixture written from the docs alone would have hidden that.
"""

from __future__ import annotations

from saveddigest.sources.todoist import (
    INGESTED_LABEL,
    TodoistTask,
    items_from_tasks,
    normalise_task,
)
from saveddigest.sources.urls import is_unresolved_share
from saveddigest.store import Platform

# Verbatim from the live Todoist API for project 6hHVcfJR5fC67938.
REAL_PAYLOAD: list[dict] = [
    {
        "id": "6hHVcgw3VcXxgrqg",
        "content": "https://www.instagram.com/reel/DAbCdEfGhIj/?igsh=MXY5cmpsaGdmMmR3bQ%3D%3D",
        "description": "Typical share-sheet output: reel link with igsh tracking parameter.",
        "recurring": False,
        "priority": "p4",
        "projectId": "6hHVcfJR5fC67938",
        "labels": [],
        "checked": False,
        "addedAt": "2026-08-17T08:24:50.988Z",
    },
    {
        "id": "6hHVcgw9r5VJqFX8",
        "content": "Great explainer on compound interest",
        "description": (
            "Shared via Instagram\n"
            "https://www.instagram.com/reels/DAbCdEfGhIj/\n"
            "Same reel as above, plural /reels/ form — must deduplicate."
        ),
        "recurring": False,
        "priority": "p4",
        "projectId": "6hHVcfJR5fC67938",
        "labels": [],
        "checked": False,
        "addedAt": "2026-08-17T08:24:51.535Z",
    },
    {
        "id": "6hHVcgxPM6PvhCc8",
        "content": "https://www.instagram.com/p/CxYz789Post/",
        "description": "A saved photo/carousel post rather than a reel.",
        "recurring": False,
        "priority": "p4",
        "projectId": "6hHVcfJR5fC67938",
        "labels": [],
        "checked": False,
        "addedAt": "2026-08-17T08:24:52.136Z",
    },
    {
        "id": "6hHVcgx48GpC2vcg",
        "content": "https://www.instagram.com/share/reel/_Xk92LmNq",
        "description": "Opaque share redirect — contains no shortcode, needs resolution.",
        "recurring": False,
        "priority": "p4",
        "projectId": "6hHVcfJR5fC67938",
        "labels": [],
        "checked": False,
        "addedAt": "2026-08-17T08:24:52.667Z",
    },
    {
        "id": "6hHVch4cq2WfvvJg",
        "content": "Reminder: buy oat milk",
        "description": "A task with no link at all — must be skipped without error.",
        "recurring": False,
        "priority": "p4",
        "projectId": "6hHVcfJR5fC67938",
        "labels": [],
        "checked": False,
        "addedAt": "2026-08-17T08:24:53.855Z",
    },
]


# --------------------------------------------------------------------------
# against the real payload
# --------------------------------------------------------------------------
def test_real_payload_yields_three_deduplicated_items():
    items, consumed = items_from_tasks(REAL_PAYLOAD)
    assert [i.external_id for i in items] == [
        "DAbCdEfGhIj",
        "CxYz789Post",
        "share:_Xk92LmNq",
    ]
    assert all(i.platform is Platform.INSTAGRAM for i in items)
    assert len(items) == 3


def test_real_payload_consumes_every_task_that_had_a_link():
    _, consumed = items_from_tasks(REAL_PAYLOAD)
    # All four link-bearing tasks, including the duplicate share.
    assert consumed == [
        "6hHVcgw3VcXxgrqg",
        "6hHVcgw9r5VJqFX8",
        "6hHVcgxPM6PvhCc8",
        "6hHVcgx48GpC2vcg",
    ]


def test_task_without_a_link_is_left_alone():
    """A note or a typo'd URL must stay unlabelled so it can be fixed."""
    _, consumed = items_from_tasks(REAL_PAYLOAD)
    assert "6hHVch4cq2WfvvJg" not in consumed


def test_duplicate_share_donates_its_human_title():
    """Task 1 is a bare URL; task 2 is the same reel with a real title.

    The duplicate is not stored, but its title is better than nothing, so it is
    backfilled onto the item that was kept.
    """
    items, _ = items_from_tasks(REAL_PAYLOAD)
    reel = next(i for i in items if i.external_id == "DAbCdEfGhIj")
    assert reel.title == "Great explainer on compound interest"


def test_bare_url_content_does_not_become_a_title():
    items, _ = items_from_tasks(REAL_PAYLOAD)
    post = next(i for i in items if i.external_id == "CxYz789Post")
    assert post.title is None


def test_camelcase_added_at_is_read_as_the_save_date():
    """The field-name difference this fixture exists to pin down."""
    items, _ = items_from_tasks(REAL_PAYLOAD)
    assert items[0].saved_at == "2026-08-17T08:24:50.988Z"
    assert all(i.saved_at is not None for i in items)


def test_duplicate_keeps_the_earlier_save_date():
    items, _ = items_from_tasks(REAL_PAYLOAD)
    reel = next(i for i in items if i.external_id == "DAbCdEfGhIj")
    # Task 1 (…50.988Z) precedes task 2 (…51.535Z).
    assert reel.saved_at == "2026-08-17T08:24:50.988Z"


def test_tracking_parameters_are_stripped_from_the_stored_url():
    items, _ = items_from_tasks(REAL_PAYLOAD)
    reel = next(i for i in items if i.external_id == "DAbCdEfGhIj")
    assert reel.url == "https://www.instagram.com/reel/DAbCdEfGhIj/"
    assert "igsh" not in reel.url


def test_share_redirect_is_marked_unresolved():
    items, _ = items_from_tasks(REAL_PAYLOAD)
    share = next(i for i in items if i.external_id.startswith("share:"))
    assert is_unresolved_share(share.external_id)
    assert not any(
        is_unresolved_share(i.external_id)
        for i in items
        if i.external_id != share.external_id
    )


def test_every_item_records_its_source_and_capture_time():
    items, _ = items_from_tasks(REAL_PAYLOAD)
    assert all(i.source == "todoist" for i in items)
    assert all(i.captured_at for i in items)


def test_rerunning_on_the_same_payload_is_deterministic():
    first, consumed_a = items_from_tasks(REAL_PAYLOAD)
    second, consumed_b = items_from_tasks(REAL_PAYLOAD)
    assert [i.external_id for i in first] == [i.external_id for i in second]
    assert consumed_a == consumed_b


# --------------------------------------------------------------------------
# label-based skipping (how re-sync avoids re-reporting)
# --------------------------------------------------------------------------
def test_already_ingested_tasks_are_skipped():
    payload = [dict(REAL_PAYLOAD[0], labels=[INGESTED_LABEL])]
    items, consumed = items_from_tasks(payload)
    assert items == []
    assert consumed == []


def test_other_labels_do_not_cause_a_skip():
    payload = [dict(REAL_PAYLOAD[0], labels=["finance", "watch-soon"])]
    items, _ = items_from_tasks(payload)
    assert len(items) == 1


def test_skip_label_can_be_disabled():
    payload = [dict(REAL_PAYLOAD[0], labels=[INGESTED_LABEL])]
    items, _ = items_from_tasks(payload, skip_label=None)
    assert len(items) == 1


# --------------------------------------------------------------------------
# normalisation across API versions and malformed rows
# --------------------------------------------------------------------------
def test_normalise_accepts_rest_v2_snake_case():
    task = normalise_task(
        {
            "id": "1",
            "content": "x",
            "description": "",
            "created_at": "2026-01-01T00:00:00Z",
            "labels": [],
        }
    )
    assert task == TodoistTask(
        id="1", content="x", description="", created_at="2026-01-01T00:00:00Z", labels=()
    )


def test_normalise_accepts_integer_ids():
    task = normalise_task({"id": 12345, "content": "x"})
    assert task is not None and task.id == "12345"


def test_normalise_rejects_a_task_with_no_id():
    assert normalise_task({"content": "orphan"}) is None


def test_normalise_tolerates_missing_content_and_description():
    task = normalise_task({"id": "1"})
    assert task is not None
    assert task.content == ""
    assert task.description == ""
    assert task.created_at is None


def test_normalise_ignores_non_string_labels():
    task = normalise_task({"id": "1", "labels": ["ok", 42, None]})
    assert task is not None and task.labels == ("ok",)


def test_normalise_ignores_a_non_string_timestamp():
    task = normalise_task({"id": "1", "addedAt": 1700000000})
    assert task is not None and task.created_at is None


def test_items_from_tasks_survives_a_malformed_row_mid_batch():
    payload = [REAL_PAYLOAD[0], {"no_id": True}, REAL_PAYLOAD[2]]
    items, consumed = items_from_tasks(payload)
    assert [i.external_id for i in items] == ["DAbCdEfGhIj", "CxYz789Post"]
    assert len(consumed) == 2


def test_empty_input():
    assert items_from_tasks([]) == ([], [])


# --------------------------------------------------------------------------
# mixed platforms: a YouTube link pasted into the Instagram project
# --------------------------------------------------------------------------
def test_a_youtube_link_in_the_instagram_project_is_still_captured():
    payload = [
        {
            "id": "yt1",
            "content": "https://youtu.be/dQw4w9WgXcQ",
            "description": "",
            "addedAt": "2026-08-01T00:00:00Z",
            "labels": [],
        }
    ]
    items, consumed = items_from_tasks(payload)
    assert len(items) == 1
    assert items[0].platform is Platform.YOUTUBE
    assert items[0].external_id == "dQw4w9WgXcQ"
    assert consumed == ["yt1"]


def test_one_task_containing_two_different_links_produces_two_items():
    payload = [
        {
            "id": "both",
            "content": "Two saves in one note",
            "description": (
                "https://www.instagram.com/reel/AbCdEfGhIjK/ and "
                "https://youtu.be/dQw4w9WgXcQ"
            ),
            "addedAt": "2026-08-01T00:00:00Z",
            "labels": [],
        }
    ]
    items, consumed = items_from_tasks(payload)
    assert {i.platform for i in items} == {Platform.INSTAGRAM, Platform.YOUTUBE}
    assert len(items) == 2
    # Consumed once, not once per link.
    assert consumed == ["both"]


def test_both_items_from_one_task_share_its_title_and_date():
    payload = [
        {
            "id": "both",
            "content": "Two saves in one note",
            "description": (
                "https://www.instagram.com/reel/AbCdEfGhIjK/ "
                "https://youtu.be/dQw4w9WgXcQ"
            ),
            "addedAt": "2026-08-01T00:00:00Z",
            "labels": [],
        }
    ]
    items, _ = items_from_tasks(payload)
    assert {i.title for i in items} == {"Two saves in one note"}
    assert {i.saved_at for i in items} == {"2026-08-01T00:00:00Z"}


def test_custom_source_label_is_recorded():
    items, _ = items_from_tasks([REAL_PAYLOAD[2]], source="todoist_backlog")
    assert items[0].source == "todoist_backlog"
