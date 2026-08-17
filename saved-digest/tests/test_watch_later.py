"""Watch Later flat-playlist parsing.

The network call needs a logged-in browser profile and cannot run in CI, but the
shape of yt-dlp's flat output is awkward enough to be worth pinning.
"""

from __future__ import annotations

import pytest

from saveddigest.sources.youtube_wl import (
    SOURCE_WATCH_LATER,
    WATCH_LATER_URL,
    parse_flat_entries,
)
from saveddigest.store import Platform

# Shape of `extract_flat` output for a Watch Later listing.
FLAT_INFO = {
    "_type": "playlist",
    "id": "WL",
    "title": "Watch later",
    "entries": [
        {
            "_type": "url",
            "id": "abcdefghijk",
            "title": "Designing Data-Intensive Applications in 20 minutes",
            "uploader": "Some Engineering Channel",
            "duration": 1269,
        },
        {
            "_type": "url",
            "id": "gonevideo01",
            "title": "[Deleted video]",
            "uploader": None,
            "duration": None,
        },
        {
            "_type": "url",
            "id": "privatevid1",
            "title": "[Private video]",
        },
    ],
}


def test_parses_every_entry():
    items = parse_flat_entries(FLAT_INFO)
    assert [i.external_id for i in items] == ["abcdefghijk", "gonevideo01", "privatevid1"]
    assert all(i.platform is Platform.YOUTUBE for i in items)


def test_source_is_recorded_so_imports_are_distinguishable():
    items = parse_flat_entries(FLAT_INFO)
    assert all(i.source == SOURCE_WATCH_LATER for i in items)


def test_canonical_urls_are_built():
    items = parse_flat_entries(FLAT_INFO)
    assert items[0].url == "https://www.youtube.com/watch?v=abcdefghijk"


def test_metadata_is_carried_when_present():
    items = parse_flat_entries(FLAT_INFO)
    assert items[0].title == "Designing Data-Intensive Applications in 20 minutes"
    assert items[0].author == "Some Engineering Channel"


@pytest.mark.parametrize("title", ["[Deleted video]", "[Private video]", "Deleted video"])
def test_tombstone_titles_are_not_used_as_headings(title):
    items = parse_flat_entries({"entries": [{"id": "tombstone01", "title": title}]})
    assert items[0].title is None


def test_flat_listing_has_no_save_date():
    """A flat playlist carries no add-date, so ordering falls back to capture time."""
    items = parse_flat_entries(FLAT_INFO)
    assert all(i.saved_at is None for i in items)
    assert all(i.captured_at for i in items)


def test_duplicate_ids_collapse():
    info = {"entries": [{"id": "same0000001"}, {"id": "same0000001"}]}
    assert len(parse_flat_entries(info)) == 1


def test_entries_without_an_id_are_skipped():
    info = {"entries": [{"title": "no id"}, {"id": "good0000001"}]}
    assert [i.external_id for i in parse_flat_entries(info)] == ["good0000001"]


def test_non_dict_entries_are_skipped():
    info = {"entries": ["not a dict", None, {"id": "good0000001"}]}
    assert [i.external_id for i in parse_flat_entries(info)] == ["good0000001"]


def test_empty_and_missing_entries():
    assert parse_flat_entries({"entries": []}) == []
    assert parse_flat_entries({}) == []


def test_channel_used_when_uploader_absent():
    info = {"entries": [{"id": "abcdefghijk", "channel": "Chan"}]}
    assert parse_flat_entries(info)[0].author == "Chan"


def test_watch_later_url_targets_the_system_playlist():
    assert WATCH_LATER_URL.endswith("list=WL")
