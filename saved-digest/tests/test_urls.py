"""URL canonicalisation — the dedup key. Errors here mean weekly repeats."""

from __future__ import annotations

import pytest

from saveddigest.sources.urls import extract_urls, parse_url, parse_urls_in_text
from saveddigest.store import Platform

VIDEO = "dQw4w9WgXcQ"


# --------------------------------------------------------------------------
# YouTube
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VIDEO}",
        f"http://www.youtube.com/watch?v={VIDEO}",
        f"https://youtube.com/watch?v={VIDEO}",
        f"https://m.youtube.com/watch?v={VIDEO}",
        f"https://music.youtube.com/watch?v={VIDEO}",
        f"https://youtu.be/{VIDEO}",
        f"https://www.youtube.com/shorts/{VIDEO}",
        f"https://www.youtube.com/live/{VIDEO}",
        f"https://www.youtube.com/embed/{VIDEO}",
        f"https://www.youtube.com/v/{VIDEO}",
        # share-sheet noise
        f"https://youtu.be/{VIDEO}?t=42",
        f"https://www.youtube.com/watch?v={VIDEO}&t=90s",
        f"https://www.youtube.com/watch?v={VIDEO}&list=PLabc&index=3",
        f"https://www.youtube.com/watch?v={VIDEO}&feature=share&si=xYz",
        # scheme-less paste
        f"youtube.com/watch?v={VIDEO}",
        f"www.youtube.com/watch?v={VIDEO}",
    ],
)
def test_every_youtube_form_yields_the_same_id_and_canonical_url(url):
    parsed = parse_url(url)
    assert parsed is not None, url
    assert parsed.platform is Platform.YOUTUBE
    assert parsed.external_id == VIDEO
    assert parsed.canonical_url == f"https://www.youtube.com/watch?v={VIDEO}"
    assert parsed.needs_resolution is False


def test_youtube_variants_all_collapse_to_one_id():
    """The point of canonicalisation: five surfaces, one database row."""
    urls = [
        f"https://www.youtube.com/watch?v={VIDEO}",
        f"https://youtu.be/{VIDEO}?t=42",
        f"https://m.youtube.com/watch?v={VIDEO}",
        f"https://www.youtube.com/shorts/{VIDEO}",
        f"youtube.com/watch?v={VIDEO}",
    ]
    assert len({parse_url(u).external_id for u in urls}) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=tooshort",
        "https://www.youtube.com/watch?v=waaaaaaaaaaaytoolong",
        "https://www.youtube.com/watch",  # no v=
        "https://www.youtube.com/watch?list=PLabc",  # playlist, not a video
        "https://www.youtube.com/",
        "https://www.youtube.com/@somechannel",
        "https://www.youtube.com/results?search_query=cats",
        "https://www.youtube.com/watch?v=has spaces!!",
    ],
)
def test_non_video_youtube_urls_are_rejected(url):
    assert parse_url(url) is None


def test_youtube_id_with_leading_hyphen_and_underscore():
    """Base64url ids legitimately start with `-` or `_`."""
    for vid in ["-abcdefghij", "_abcdefghij", "a-b_c-d_e-fg"[:11]]:
        parsed = parse_url(f"https://youtu.be/{vid}")
        assert parsed is not None and parsed.external_id == vid


# --------------------------------------------------------------------------
# Instagram
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("url", "expected_canonical"),
    [
        ("https://www.instagram.com/p/CxYz123abc/", "https://www.instagram.com/p/CxYz123abc/"),
        ("https://instagram.com/p/CxYz123abc", "https://www.instagram.com/p/CxYz123abc/"),
        (
            "https://www.instagram.com/reel/CxYz123abc/",
            "https://www.instagram.com/reel/CxYz123abc/",
        ),
        # `reels` and `reel` are the same object and must not double up.
        (
            "https://www.instagram.com/reels/CxYz123abc/",
            "https://www.instagram.com/reel/CxYz123abc/",
        ),
        (
            "https://www.instagram.com/tv/CxYz123abc/",
            "https://www.instagram.com/tv/CxYz123abc/",
        ),
        # Nested under a username, as the web UI sometimes renders.
        (
            "https://www.instagram.com/someuser/p/CxYz123abc/",
            "https://www.instagram.com/p/CxYz123abc/",
        ),
        # Share-sheet tracking parameter.
        (
            "https://www.instagram.com/reel/CxYz123abc/?igsh=MzRlODBiNWFlZA==",
            "https://www.instagram.com/reel/CxYz123abc/",
        ),
        ("https://m.instagram.com/p/CxYz123abc/", "https://www.instagram.com/p/CxYz123abc/"),
    ],
)
def test_instagram_post_forms(url, expected_canonical):
    parsed = parse_url(url)
    assert parsed is not None, url
    assert parsed.platform is Platform.INSTAGRAM
    assert parsed.external_id == "CxYz123abc"
    assert parsed.canonical_url == expected_canonical
    assert parsed.needs_resolution is False


def test_reel_and_reels_deduplicate_to_one_item():
    a = parse_url("https://www.instagram.com/reel/CxYz123abc/")
    b = parse_url("https://www.instagram.com/reels/CxYz123abc/?igsh=abc")
    assert a.external_id == b.external_id
    assert a.canonical_url == b.canonical_url


def test_opaque_share_link_is_flagged_not_guessed():
    """Instagram's share sheet emits redirects with no shortcode in them.

    Inventing a shortcode here would silently attach the wrong summary to the
    wrong reel, so these are flagged for an explicit resolution step instead.
    """
    parsed = parse_url("https://www.instagram.com/share/reel/_AbC123xyz")
    assert parsed is not None
    assert parsed.needs_resolution is True
    assert parsed.external_id == "share:_AbC123xyz"
    assert parsed.external_id.startswith("share:")


def test_share_provisional_id_cannot_collide_with_a_real_shortcode():
    share = parse_url("https://www.instagram.com/share/CxYz123abc")
    real = parse_url("https://www.instagram.com/p/CxYz123abc/")
    assert share.external_id != real.external_id


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/",
        "https://www.instagram.com/someuser/",  # profile, not a post
        "https://www.instagram.com/p/",  # no shortcode
        "https://www.instagram.com/explore/tags/cats/",
        "https://www.instagram.com/p/way-too-long-to-be-a-real-shortcode-by-far/",
        "https://www.instagram.com/p/ab/",  # below the minimum length
    ],
)
def test_non_post_instagram_urls_are_rejected(url):
    assert parse_url(url) is None


# --------------------------------------------------------------------------
# rejection of everything else
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url",
        "https://vimeo.com/123456",
        "https://twitter.com/someone/status/1",
        "https://www.tiktok.com/@a/video/123",
        "https://example.com/p/CxYz123abc/",  # right shape, wrong host
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_unrelated_urls_are_rejected(url):
    assert parse_url(url) is None


def test_lookalike_host_is_rejected():
    """`youtube.com.evil.test` must not be treated as YouTube."""
    assert parse_url("https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ") is None


# --------------------------------------------------------------------------
# extraction from free text (Todoist task content is markdown)
# --------------------------------------------------------------------------
def test_extract_urls_from_plain_text():
    text = f"watch this https://youtu.be/{VIDEO} later"
    assert extract_urls(text) == [f"https://youtu.be/{VIDEO}"]


def test_extract_urls_strips_trailing_sentence_punctuation():
    text = f"see https://youtu.be/{VIDEO}."
    assert extract_urls(text) == [f"https://youtu.be/{VIDEO}"]


def test_extract_urls_from_markdown_link():
    text = f"[great talk](https://youtu.be/{VIDEO})"
    assert extract_urls(text) == [f"https://youtu.be/{VIDEO}"]


def test_extract_urls_deduplicates_identical_strings():
    text = f"https://youtu.be/{VIDEO} and again https://youtu.be/{VIDEO}"
    assert extract_urls(text) == [f"https://youtu.be/{VIDEO}"]


def test_extract_urls_on_empty_text():
    assert extract_urls("") == []
    assert extract_urls(None) == []  # type: ignore[arg-type]


def test_parse_urls_in_text_finds_multiple_platforms_in_order():
    text = (
        "Two things: https://www.instagram.com/reel/CxYz123abc/ "
        f"and https://youtu.be/{VIDEO} — plus https://example.com/ignored"
    )
    found = parse_urls_in_text(text)
    assert [p.platform for p in found] == [Platform.INSTAGRAM, Platform.YOUTUBE]
    assert [p.external_id for p in found] == ["CxYz123abc", VIDEO]


def test_parse_urls_in_text_deduplicates_by_id_not_by_string():
    """Two spellings of one video are one item."""
    text = (
        f"https://www.youtube.com/watch?v={VIDEO} "
        f"https://youtu.be/{VIDEO}?t=10 "
        f"https://m.youtube.com/watch?v={VIDEO}"
    )
    assert len(parse_urls_in_text(text)) == 1


def test_parse_urls_in_text_ignores_unrecognised_links():
    assert parse_urls_in_text("https://example.com/ https://vimeo.com/1") == []


def test_parse_urls_in_text_on_a_realistic_todoist_task_body():
    body = (
        "Saved from Instagram\n"
        "https://www.instagram.com/reel/DAbCdEfGhIj/?igsh=MXY5cmpsaGdmMmR3bQ%3D%3D\n"
        "(shared via share sheet)"
    )
    found = parse_urls_in_text(body)
    assert len(found) == 1
    assert found[0].external_id == "DAbCdEfGhIj"
    assert found[0].canonical_url == "https://www.instagram.com/reel/DAbCdEfGhIj/"
