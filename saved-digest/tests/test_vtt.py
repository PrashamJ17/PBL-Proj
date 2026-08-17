"""VTT flattening, including the rolling-window artefact that doubles transcripts."""

from __future__ import annotations

from saveddigest.enrich.vtt import vtt_to_text

# A faithful excerpt of what `yt-dlp --write-auto-sub --sub-format vtt` produces
# for a YouTube video: header metadata, cue settings, inline timing tags, and the
# two-line rolling window where each cue repeats the previous line.
YOUTUBE_AUTO_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.030 --> 00:00:02.909 align:start position:0%
the first thing<00:00:00.560><c> I</c><00:00:00.880><c> want</c>

00:00:02.909 --> 00:00:02.919 align:start position:0%
the first thing I want


00:00:02.919 --> 00:00:05.669 align:start position:0%
the first thing I want
to talk<00:00:03.400><c> about</c><00:00:04.120><c> is</c><00:00:04.560><c> caching</c>

00:00:05.669 --> 00:00:05.679 align:start position:0%
to talk about is caching


00:00:05.679 --> 00:00:08.500 align:start position:0%
to talk about is caching
because<00:00:06.000><c> it</c><00:00:06.400><c> matters</c>
"""


def test_youtube_rolling_window_is_collapsed():
    text = vtt_to_text(YOUTUBE_AUTO_VTT)
    assert text == (
        "the first thing I want to talk about is caching because it matters"
    )


def test_rolling_window_does_not_duplicate_words():
    """The failure this module exists to prevent: paying twice per word."""
    text = vtt_to_text(YOUTUBE_AUTO_VTT)
    assert text.count("the first thing I want") == 1
    assert text.count("to talk about is caching") == 1


def test_header_and_metadata_lines_are_dropped():
    text = vtt_to_text(YOUTUBE_AUTO_VTT)
    for junk in ("WEBVTT", "Kind:", "Language:", "align:start", "position:0%", "-->"):
        assert junk not in text


def test_inline_timing_and_styling_tags_are_stripped():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
<c.colorE5E5E5>hello</c><00:00:01.500><c> there</c>
"""
    assert vtt_to_text(vtt) == "hello there"


def test_html_entities_are_unescaped():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
Bell &amp; Co. said &quot;yes&quot; &mdash; profits &gt; costs
"""
    assert vtt_to_text(vtt) == 'Bell & Co. said "yes" — profits > costs'


def test_escaped_angle_brackets_survive_tag_stripping():
    """`&lt;c&gt;` is real spoken content about a tag; `<c>` is markup."""
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
<c>the</c> tag is written &lt;c&gt; in VTT
"""
    assert vtt_to_text(vtt) == "the tag is written <c> in VTT"


def test_note_and_style_blocks_are_ignored():
    vtt = """WEBVTT

NOTE this file was machine generated

STYLE
::cue { color: white }

00:00:01.000 --> 00:00:02.000
actual speech
"""
    assert vtt_to_text(vtt) == "actual speech"


def test_note_block_containing_an_arrow_is_still_ignored():
    """A NOTE mentioning `-->` must not be mistaken for a cue."""
    vtt = """WEBVTT

NOTE
conversion pipeline: srt --> vtt
this line is commentary

00:00:01.000 --> 00:00:02.000
real words
"""
    assert vtt_to_text(vtt) == "real words"


def test_cue_identifiers_before_the_timing_line_are_skipped():
    vtt = """WEBVTT

cue-42
00:00:01.000 --> 00:00:02.000
spoken words
"""
    assert vtt_to_text(vtt) == "spoken words"


def test_short_mm_ss_timestamps_are_accepted():
    """VTT permits MM:SS.mmm; some tracks in the wild use it."""
    vtt = """WEBVTT

00:01.000 --> 00:03.000
short form timestamps
"""
    assert vtt_to_text(vtt) == "short form timestamps"


def test_comma_decimal_separator_is_accepted():
    """SRT-style commas appear in converted tracks."""
    vtt = """WEBVTT

00:00:01,000 --> 00:00:02,000
comma separated
"""
    assert vtt_to_text(vtt) == "comma separated"


def test_long_videos_with_hour_timestamps():
    vtt = """WEBVTT

01:02:03.000 --> 01:02:05.000
deep into a long talk
"""
    assert vtt_to_text(vtt) == "deep into a long talk"


def test_windows_line_endings():
    vtt = "WEBVTT\r\n\r\n00:00:01.000 --> 00:00:02.000\r\ncrlf speech\r\n"
    assert vtt_to_text(vtt) == "crlf speech"


def test_non_consecutive_repeats_are_preserved_as_content():
    """A refrain repeated later in the video is real, not an artefact."""
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
never gonna give you up

00:00:02.000 --> 00:00:03.000
never gonna let you down

00:00:03.000 --> 00:00:04.000
never gonna give you up
"""
    assert vtt_to_text(vtt).count("never gonna give you up") == 2


def test_case_differing_consecutive_repeats_are_collapsed():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
Hello There

00:00:02.000 --> 00:00:03.000
hello there
"""
    assert vtt_to_text(vtt) == "Hello There"


def test_custom_join_separator():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
one

00:00:02.000 --> 00:00:03.000
two
"""
    assert vtt_to_text(vtt, join="\n") == "one\ntwo"


def test_whitespace_runs_are_collapsed_but_never_across_lines():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
spaced      out     words
"""
    assert vtt_to_text(vtt) == "spaced out words"


# --------------------------------------------------------------------------
# degenerate input: must return "" rather than raise
# --------------------------------------------------------------------------
def test_empty_string():
    assert vtt_to_text("") == ""


def test_whitespace_only():
    assert vtt_to_text("   \n\n  \t \n") == ""


def test_header_with_no_cues():
    assert vtt_to_text("WEBVTT\nKind: captions\nLanguage: en\n") == ""


def test_cue_with_empty_payload():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000

00:00:02.000 --> 00:00:03.000
only real line
"""
    assert vtt_to_text(vtt) == "only real line"


def test_cue_whose_payload_is_only_tags():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
<00:00:01.500><c></c>

00:00:02.000 --> 00:00:03.000
surviving line
"""
    assert vtt_to_text(vtt) == "surviving line"


def test_garbage_input_does_not_raise():
    assert vtt_to_text("this is not a vtt file at all") == ""


def test_missing_webvtt_header_still_parses_cues():
    """Some tools omit the header; the cues are still usable."""
    vtt = "00:00:01.000 --> 00:00:02.000\nheaderless but valid\n"
    assert vtt_to_text(vtt) == "headerless but valid"
