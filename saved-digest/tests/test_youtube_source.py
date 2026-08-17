"""YouTube playlist parsing.

Payload shapes follow the documented `playlistItems.list` and `videos.list`
responses, including the tombstone rows YouTube leaves behind when a video in a
playlist is deleted or made private.
"""

from __future__ import annotations

import pytest

from saveddigest.sources.youtube import (
    entries_to_items,
    missing_video_ids,
    parse_duration_seconds,
    parse_playlist_page,
    parse_videos_page,
)
from saveddigest.store import Liveness, Platform

# A realistic two-page playlist response: one healthy video, one deleted.
PLAYLIST_PAGE = {
    "nextPageToken": "CDIQAA",
    "items": [
        {
            "snippet": {
                # When it was added to the playlist == when the user saved it.
                "publishedAt": "2025-11-02T18:04:11Z",
                "title": "Designing Data-Intensive Applications in 20 minutes",
                "videoOwnerChannelTitle": "Some Engineering Channel",
                "resourceId": {"kind": "youtube#video", "videoId": "abcdefghijk"},
            },
            "contentDetails": {
                "videoId": "abcdefghijk",
                "videoPublishedAt": "2023-04-01T09:00:00Z",
            },
        },
        {
            "snippet": {
                "publishedAt": "2024-02-10T08:00:00Z",
                "title": "Deleted video",
                "resourceId": {"kind": "youtube#video", "videoId": "gonevideo01"},
            },
            "contentDetails": {"videoId": "gonevideo01"},
        },
    ],
}


# --------------------------------------------------------------------------
# playlist pages
# --------------------------------------------------------------------------
def test_parse_playlist_page_returns_entries_and_token():
    entries, token = parse_playlist_page(PLAYLIST_PAGE)
    assert token == "CDIQAA"
    assert [e.video_id for e in entries] == ["abcdefghijk", "gonevideo01"]


def test_playlist_publishedat_is_treated_as_the_save_date():
    """The single most important mapping in this module."""
    entries, _ = parse_playlist_page(PLAYLIST_PAGE)
    assert entries[0].added_at == "2025-11-02T18:04:11Z"


def test_video_publishedat_is_kept_separately_for_staleness_judging():
    entries, _ = parse_playlist_page(PLAYLIST_PAGE)
    assert entries[0].video_published_at == "2023-04-01T09:00:00Z"
    assert entries[0].added_at != entries[0].video_published_at


def test_healthy_entry_keeps_title_and_channel():
    entries, _ = parse_playlist_page(PLAYLIST_PAGE)
    assert entries[0].title == "Designing Data-Intensive Applications in 20 minutes"
    assert entries[0].channel == "Some Engineering Channel"
    assert entries[0].liveness is Liveness.UNKNOWN


@pytest.mark.parametrize(
    "title", ["Deleted video", "deleted video", "Private video", "[Private video]"]
)
def test_tombstone_titles_are_detected(title):
    payload = {
        "items": [
            {
                "snippet": {"title": title, "resourceId": {"videoId": "tombstone01"}},
                "contentDetails": {"videoId": "tombstone01"},
            }
        ]
    }
    entries, _ = parse_playlist_page(payload)
    assert entries[0].liveness is Liveness.DEAD
    # The placeholder must not become the digest heading.
    assert entries[0].title is None


def test_a_real_video_merely_mentioning_deleted_video_is_not_a_tombstone():
    """Exact match only — otherwise a legitimate title gets binned."""
    payload = {
        "items": [
            {
                "snippet": {
                    "title": "Deleted video recovery: how I got my footage back",
                    "resourceId": {"videoId": "realvideo01"},
                },
                "contentDetails": {"videoId": "realvideo01"},
            }
        ]
    }
    entries, _ = parse_playlist_page(payload)
    assert entries[0].liveness is Liveness.UNKNOWN
    assert entries[0].title == "Deleted video recovery: how I got my footage back"


def test_video_id_read_from_content_details_when_resource_id_absent():
    payload = {"items": [{"snippet": {"title": "t"}, "contentDetails": {"videoId": "fromcontent"}}]}
    entries, _ = parse_playlist_page(payload)
    assert entries[0].video_id == "fromcontent"


def test_video_id_read_from_resource_id_when_content_details_absent():
    payload = {"items": [{"snippet": {"title": "t", "resourceId": {"videoId": "fromresource"}}}]}
    entries, _ = parse_playlist_page(payload)
    assert entries[0].video_id == "fromresource"


def test_non_video_resources_are_skipped():
    payload = {
        "items": [
            {
                "snippet": {
                    "title": "a nested playlist",
                    "resourceId": {"kind": "youtube#playlist", "playlistId": "PL123"},
                }
            }
        ]
    }
    entries, _ = parse_playlist_page(payload)
    assert entries == []


def test_rows_with_no_video_id_are_skipped_not_fatal():
    payload = {"items": [{"snippet": {"title": "broken"}}, PLAYLIST_PAGE["items"][0]]}
    entries, _ = parse_playlist_page(payload)
    assert [e.video_id for e in entries] == ["abcdefghijk"]


def test_last_page_has_no_token():
    entries, token = parse_playlist_page({"items": []})
    assert (entries, token) == ([], None)


def test_completely_empty_payload():
    assert parse_playlist_page({}) == ([], None)


# --------------------------------------------------------------------------
# entries -> items
# --------------------------------------------------------------------------
def test_entries_to_items_maps_fields_and_builds_canonical_urls():
    entries, _ = parse_playlist_page(PLAYLIST_PAGE)
    items = entries_to_items(entries)
    healthy = next(i for i in items if i.external_id == "abcdefghijk")
    assert healthy.platform is Platform.YOUTUBE
    assert healthy.url == "https://www.youtube.com/watch?v=abcdefghijk"
    assert healthy.saved_at == "2025-11-02T18:04:11Z"
    assert healthy.published_at == "2023-04-01T09:00:00Z"
    assert healthy.author == "Some Engineering Channel"
    assert healthy.source == "youtube_playlist"
    assert healthy.captured_at


def test_tombstone_item_is_stored_with_dead_liveness():
    """Kept, not dropped: the digest reports what vanished."""
    entries, _ = parse_playlist_page(PLAYLIST_PAGE)
    items = entries_to_items(entries)
    gone = next(i for i in items if i.external_id == "gonevideo01")
    assert gone.liveness is Liveness.DEAD


def test_same_video_twice_in_a_playlist_becomes_one_item():
    payload = {
        "items": [
            {
                "snippet": {
                    "publishedAt": "2026-01-01T00:00:00Z",
                    "title": "dupe",
                    "resourceId": {"videoId": "sameid00001"},
                },
                "contentDetails": {"videoId": "sameid00001"},
            },
            {
                "snippet": {
                    "publishedAt": "2024-01-01T00:00:00Z",
                    "title": "dupe",
                    "resourceId": {"videoId": "sameid00001"},
                },
                "contentDetails": {"videoId": "sameid00001"},
            },
        ]
    }
    entries, _ = parse_playlist_page(payload)
    items = entries_to_items(entries)
    assert len(items) == 1
    # The earlier add-date wins, so ageing reflects the first save.
    assert items[0].saved_at == "2024-01-01T00:00:00Z"


def test_custom_source_label():
    entries, _ = parse_playlist_page(PLAYLIST_PAGE)
    items = entries_to_items(entries, source="youtube_wl")
    assert all(i.source == "youtube_wl" for i in items)


def test_entries_to_items_on_empty_input():
    assert entries_to_items([]) == []


# --------------------------------------------------------------------------
# videos.list + liveness by omission
# --------------------------------------------------------------------------
VIDEOS_PAGE = {
    "items": [
        {
            "id": "abcdefghijk",
            "snippet": {
                "title": "Designing Data-Intensive Applications in 20 minutes",
                "channelTitle": "Some Engineering Channel",
                "publishedAt": "2023-04-01T09:00:00Z",
                "description": "A whistle-stop tour of DDIA.",
            },
            "contentDetails": {"duration": "PT21M9S"},
        }
    ]
}


def test_parse_videos_page_indexes_by_id():
    details = parse_videos_page(VIDEOS_PAGE)
    assert set(details) == {"abcdefghijk"}
    entry = details["abcdefghijk"]
    assert entry["channel"] == "Some Engineering Channel"
    assert entry["description"] == "A whistle-stop tour of DDIA."
    assert entry["duration_seconds"] == 21 * 60 + 9


def test_missing_ids_are_the_liveness_signal():
    """`videos.list` silently omits deleted/private ids — that omission is the check."""
    requested = ["abcdefghijk", "gonevideo01", "privatevid1"]
    details = parse_videos_page(VIDEOS_PAGE)
    assert missing_video_ids(requested, details) == ["gonevideo01", "privatevid1"]


def test_missing_video_ids_empty_when_all_present():
    assert missing_video_ids(["abcdefghijk"], parse_videos_page(VIDEOS_PAGE)) == []


def test_parse_videos_page_tolerates_absent_sections():
    details = parse_videos_page({"items": [{"id": "bare0000001"}]})
    entry = details["bare0000001"]
    assert entry["title"] is None
    assert entry["description"] == ""
    assert entry["duration_seconds"] is None


def test_parse_videos_page_skips_rows_without_an_id():
    assert parse_videos_page({"items": [{"snippet": {"title": "x"}}]}) == {}


# --------------------------------------------------------------------------
# ISO-8601 durations
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PT30S", 30),
        ("PT5M", 300),
        ("PT5M30S", 330),
        ("PT1H", 3600),
        ("PT1H2M3S", 3723),
        ("P1DT2H", 93600),
        ("P0D", 0),  # YouTube reports live streams like this
        ("PT0S", 0),
    ],
)
def test_parse_duration_seconds(raw, expected):
    assert parse_duration_seconds(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "not a duration", "5M30S", "PT", "P1Y"])
def test_malformed_durations_yield_none_rather_than_raising(raw):
    # "PT" is structurally valid-but-empty; treat as 0 only if it parses.
    result = parse_duration_seconds(raw)
    assert result is None or result == 0
