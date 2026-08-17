"""WebVTT -> plain prose.

YouTube's *auto-generated* captions are the hard case, and the reason this is a
module rather than a regex. They are emitted as a rolling two-line window, so
naive concatenation roughly doubles the transcript:

    00:00:00.000 --> 00:00:02.000 align:start position:0%
    the first thing<00:00:00.500><c> I want</c>

    00:00:02.000 --> 00:00:04.000 align:start position:0%
    the first thing I want
    to talk about<00:00:02.900><c> is</c>

Line 1 of the second cue repeats the first cue entirely. Feeding that to the API
pays twice for the same words and measurably degrades the summary, so cues are
flattened to lines, inline timing tags stripped, and consecutive repeats dropped.

Pure and offline by design: the network-facing download lives in
`enrich.transcript`, so the fiddly parsing can be tested exhaustively without a
network round trip.
"""

from __future__ import annotations

import html
import re

#: A cue's timing line. VTT allows `MM:SS.mmm` as well as `HH:MM:SS.mmm`, and
#: trailing cue settings (`align:start position:0%`) are optional.
_TIMING = re.compile(
    r"^\s*(?:\d{1,3}:)?\d{1,2}:\d{2}[.,]\d{1,3}\s*-->\s*"
    r"(?:\d{1,3}:)?\d{1,2}:\d{2}[.,]\d{1,3}"
)

#: Inline timing (`<00:00:00.500>`) and styling (`<c.colorE5E5E5>`, `</c>`) tags.
_INLINE_TAG = re.compile(r"<[^>]*>")

#: Blocks that carry no spoken text.
_METADATA_PREFIXES = ("WEBVTT", "NOTE", "STYLE", "REGION", "Kind:", "Language:")

_WHITESPACE = re.compile(r"[^\S\n]+")


def vtt_to_text(raw: str, *, join: str = " ") -> str:
    """Flatten a VTT document to prose.

    Cue order is preserved; consecutive duplicate lines (the rolling-window
    artefact) are collapsed. Returns `""` for empty or caption-free input rather
    than raising — a video with a malformed caption track should degrade to
    "no transcript", not crash the run.
    """
    if not raw or not raw.strip():
        return ""

    lines: list[str] = []
    for block in _blocks(raw):
        lines.extend(_cue_lines(block))

    deduped = _drop_consecutive_repeats(lines)
    return join.join(deduped).strip()


def _blocks(raw: str) -> list[list[str]]:
    """Split into cue blocks on blank lines, normalising line endings."""
    normalised = raw.replace("\r\n", "\n").replace("\r", "\n")
    return [
        [line for line in chunk.split("\n") if line.strip()]
        for chunk in re.split(r"\n\s*\n", normalised)
        if chunk.strip()
    ]


def _cue_lines(block: list[str]) -> list[str]:
    """Extract spoken lines from one block, or nothing if it isn't a cue."""
    # A cue may open with an optional identifier line before the timing line, so
    # scan for the timing rather than assuming it is first.
    timing_at: int | None = None
    for index, line in enumerate(block):
        if _TIMING.match(line):
            timing_at = index
            break

    if timing_at is None:
        return []  # WEBVTT header, NOTE, STYLE, or a stray identifier block.

    # Guard against a metadata block that happens to contain a `-->` in prose.
    head = block[0].strip()
    if timing_at != 0 and any(head.startswith(p) for p in _METADATA_PREFIXES):
        return []

    out: list[str] = []
    for line in block[timing_at + 1 :]:
        cleaned = _clean(line)
        if cleaned:
            out.append(cleaned)
    return out


def _clean(line: str) -> str:
    """Strip inline tags, unescape entities, collapse runs of spaces."""
    without_tags = _INLINE_TAG.sub("", line)
    # Unescape *after* tag removal: a literal `&lt;c&gt;` in the caption text is
    # real content and must survive, whereas a `<c>` tag must not.
    unescaped = html.unescape(without_tags)
    return _WHITESPACE.sub(" ", unescaped).strip()


def _drop_consecutive_repeats(lines: list[str]) -> list[str]:
    """Remove each line that repeats the one before it, case-insensitively.

    Only *consecutive* repeats go: a phrase legitimately repeated later in the
    video is content, not an artefact.
    """
    out: list[str] = []
    for line in lines:
        if out and line.casefold() == out[-1].casefold():
            continue
        out.append(line)
    return out
