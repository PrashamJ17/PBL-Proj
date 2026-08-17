"""Pure decision logic in the enrich stage.

The network calls need a residential IP and cannot run in CI, but every choice
they depend on — which subtitle track to use, whether captions are machine-made,
what to fall back to — is pure and exercised here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saveddigest.enrich.media import (
    ContentKind,
    FetchedContent,
    _as_int,
    _timestamp_to_iso,
    _upload_date_to_iso,
    build_youtube_fallback_text,
    classify_subtitle_kind,
    language_from_subtitle_path,
    pick_subtitle_file,
    rank_subtitle_language,
)


# --------------------------------------------------------------------------
# subtitle track selection
# --------------------------------------------------------------------------
def test_preference_order_is_exact_then_orig_then_regional():
    tags = ["en-GB", "en-orig", "en", "de", "en-US"]
    assert sorted(tags, key=rank_subtitle_language)[:3] == ["en", "en-orig", "en-GB"]


def test_non_preferred_languages_sort_last_and_deterministically():
    tags = ["fr", "de", "es"]
    assert sorted(tags, key=rank_subtitle_language) == ["de", "es", "fr"]


def test_ranking_is_case_insensitive():
    assert rank_subtitle_language("EN")[0] == rank_subtitle_language("en")[0]
    assert rank_subtitle_language("EN-ORIG")[0] == rank_subtitle_language("en-orig")[0]


def test_a_different_preferred_language_reorders():
    tags = ["en", "de-orig", "de"]
    assert sorted(tags, key=lambda t: rank_subtitle_language(t, preferred="de"))[0] == "de"


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("dQw4w9WgXcQ.en.vtt", "en"),
        ("dQw4w9WgXcQ.en-orig.vtt", "en-orig"),
        ("dQw4w9WgXcQ.en-GB.vtt", "en-GB"),
        # An id containing dots must not confuse the split.
        ("some.video.id.en.vtt", "en"),
    ],
)
def test_language_recovered_from_filename(filename, expected):
    assert language_from_subtitle_path(Path(filename)) == expected


def test_language_from_filename_without_a_tag():
    assert language_from_subtitle_path(Path("novtt.vtt")) == ""


def test_pick_subtitle_file_prefers_exact_language(tmp_path):
    for name in ["v.en-GB.vtt", "v.de.vtt", "v.en.vtt", "v.en-orig.vtt"]:
        (tmp_path / name).write_text("WEBVTT\n")
    assert pick_subtitle_file(tmp_path.iterdir()).name == "v.en.vtt"


def test_pick_subtitle_file_falls_back_to_orig(tmp_path):
    for name in ["v.en-GB.vtt", "v.en-orig.vtt"]:
        (tmp_path / name).write_text("WEBVTT\n")
    assert pick_subtitle_file(tmp_path.iterdir()).name == "v.en-orig.vtt"


def test_pick_subtitle_file_ignores_non_vtt_files(tmp_path):
    (tmp_path / "v.en.srt").write_text("1\n")
    (tmp_path / "v.info.json").write_text("{}")
    (tmp_path / "v.de.vtt").write_text("WEBVTT\n")
    assert pick_subtitle_file(tmp_path.iterdir()).name == "v.de.vtt"


def test_pick_subtitle_file_returns_none_when_nothing_matches(tmp_path):
    (tmp_path / "v.mp4").write_text("")
    assert pick_subtitle_file(tmp_path.iterdir()) is None


def test_pick_subtitle_file_on_empty_directory(tmp_path):
    assert pick_subtitle_file(tmp_path.iterdir()) is None


def test_pick_subtitle_file_is_stable_across_directory_orderings(tmp_path):
    """Same inputs must always give the same transcript, hence the same summary."""
    names = ["v.en-GB.vtt", "v.en.vtt", "v.de.vtt"]
    for name in names:
        (tmp_path / name).write_text("WEBVTT\n")
    picks = {pick_subtitle_file(reversed(list(tmp_path.iterdir()))).name for _ in range(3)}
    assert picks == {"v.en.vtt"}


# --------------------------------------------------------------------------
# manual vs machine captions
# --------------------------------------------------------------------------
def test_manual_subtitles_are_detected():
    info = {"subtitles": {"en": [{}]}, "automatic_captions": {"en": [{}]}}
    assert classify_subtitle_kind(info, "en") == ContentKind.MANUAL_SUBS


def test_auto_captions_when_no_manual_track():
    info = {"subtitles": {}, "automatic_captions": {"en": [{}]}}
    assert classify_subtitle_kind(info, "en") == ContentKind.AUTO_SUBS


def test_regional_variant_matches_its_base_language():
    info = {"subtitles": {"en-GB": [{}]}, "automatic_captions": {}}
    assert classify_subtitle_kind(info, "en") == ContentKind.MANUAL_SUBS


def test_orig_tag_matches_the_base_language():
    info = {"subtitles": {"en": [{}]}, "automatic_captions": {}}
    assert classify_subtitle_kind(info, "en-orig") == ContentKind.MANUAL_SUBS


def test_unknown_track_is_assumed_machine_made():
    """The cautious default: label it auto so the digest under-claims, not over-claims."""
    assert classify_subtitle_kind({}, "en") == ContentKind.AUTO_SUBS


# --------------------------------------------------------------------------
# fallback text when a video has no captions
# --------------------------------------------------------------------------
def test_fallback_joins_title_and_description():
    assert build_youtube_fallback_text("A title", "A description") == (
        "A title\n\nA description"
    )


def test_fallback_with_only_a_title():
    assert build_youtube_fallback_text("A title", None) == "A title"


def test_fallback_with_only_a_description():
    assert build_youtube_fallback_text(None, "Body text") == "Body text"


def test_fallback_ignores_whitespace_only_parts():
    assert build_youtube_fallback_text("   ", "\n\n") == ""


def test_fallback_with_nothing_available():
    assert build_youtube_fallback_text(None, None) == ""


# --------------------------------------------------------------------------
# usability gate
# --------------------------------------------------------------------------
def test_content_with_text_is_usable():
    assert FetchedContent(text="real words", kind=ContentKind.AUTO_SUBS).is_usable


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_empty_content_is_not_usable(text):
    """Guards against asking the model to summarise nothing 'in detail'."""
    assert not FetchedContent(text=text, kind=ContentKind.METADATA_ONLY).is_usable


# --------------------------------------------------------------------------
# coercions
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("20240401", "2024-04-01T00:00:00+00:00"), ("20260817", "2026-08-17T00:00:00+00:00")],
)
def test_upload_date_to_iso(raw, expected):
    assert _upload_date_to_iso(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "2024-04-01", "abcdefgh", 20240401, "202404"])
def test_bad_upload_dates_yield_none(raw):
    assert _upload_date_to_iso(raw) is None


def test_timestamp_to_iso():
    assert _timestamp_to_iso(1700000000) == "2023-11-14T22:13:20+00:00"


@pytest.mark.parametrize("raw", [None, "not a number", [], {}])
def test_bad_timestamps_yield_none(raw):
    assert _timestamp_to_iso(raw) is None


def test_absurd_timestamp_does_not_raise():
    assert _timestamp_to_iso(10**20) is None


@pytest.mark.parametrize(("raw", "expected"), [(5, 5), ("7", 7), (5.9, 5), (None, None)])
def test_as_int(raw, expected):
    assert _as_int(raw) == expected


def test_as_int_rejects_bools():
    """`True` is an int in Python; a duration of `True` seconds is a bug, not 1."""
    assert _as_int(True) is None
    assert _as_int(False) is None
