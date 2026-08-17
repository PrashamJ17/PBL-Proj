"""URL recognition and canonicalisation.

Everything a capture source finds arrives as a URL pasted by a share sheet, so it
carries tracking parameters, mobile hostnames, and short forms. These functions
reduce each to a stable `external_id` — the database's dedup key. Getting this
wrong shows up as the same reel appearing in the digest every single week.

Pure and offline, with one documented exception: Instagram's share sheet can emit
an opaque `/share/` redirect that contains no shortcode. Those cannot be resolved
without a network round trip, so they are reported as `needs_resolution` rather
than guessed at — see `ParsedUrl.needs_resolution`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from saveddigest.store import Platform

#: YouTube video ids are exactly 11 characters of base64url.
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

#: Instagram shortcodes are base64url and have varied in length over the years,
#: so this is deliberately looser than YouTube's fixed 11.
_INSTAGRAM_SHORTCODE = re.compile(r"^[A-Za-z0-9_-]{5,30}$")

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

_INSTAGRAM_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
    "ddinstagram.com",  # common privacy front-end that preserves the path shape
}

#: Instagram path segments that precede a shortcode.
_INSTAGRAM_POST_SEGMENTS = {"p", "reel", "reels", "tv"}

#: Matches any URL-ish token in free text. Todoist task content is markdown, so
#: links arrive as bare URLs or as `[label](url)`.
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\)\]\"']+")

#: Namespace for provisional ids minted from an opaque Instagram `/share/`
#: redirect. Kept as an id prefix rather than a separate column so the store
#: schema stays unchanged, and `is_unresolved_share` makes the check explicit
#: instead of scattering `startswith("share:")` through the pipeline.
SHARE_ID_PREFIX = "share:"


def is_unresolved_share(external_id: str) -> bool:
    """True when this id came from a `/share/` redirect and has no real shortcode yet."""
    return external_id.startswith(SHARE_ID_PREFIX)


@dataclass(frozen=True)
class ParsedUrl:
    """A recognised link, reduced to its stable identity."""

    platform: Platform
    external_id: str
    canonical_url: str
    #: True when the link is an opaque redirect whose real id needs an HTTP
    #: round trip. `external_id` is then a provisional id derived from the
    #: redirect token, so the item is still de-duplicated correctly.
    needs_resolution: bool = False


def parse_url(raw: str) -> ParsedUrl | None:
    """Recognise a YouTube or Instagram link. Returns None for anything else."""
    if not raw or not raw.strip():
        return None

    candidate = raw.strip()
    # Tolerate scheme-less pastes ("youtube.com/watch?v=...").
    if not candidate.lower().startswith(("http://", "https://")):
        candidate = "https://" + candidate

    try:
        parts = urlparse(candidate)
    except ValueError:
        return None

    host = (parts.hostname or "").lower()
    if host in _YOUTUBE_HOSTS:
        return _parse_youtube(parts)
    if host in _INSTAGRAM_HOSTS:
        return _parse_instagram(parts)
    return None


def extract_urls(text: str) -> list[str]:
    """All URL-ish tokens in free text, in order, de-duplicated.

    Trailing punctuation is trimmed because a URL at the end of a sentence
    ("...see https://youtu.be/abc.") would otherwise carry the full stop into the
    id and defeat de-duplication.
    """
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in _URL_IN_TEXT.finditer(text):
        url = match.group(0).rstrip(".,;:!?'\"")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def parse_urls_in_text(text: str) -> list[ParsedUrl]:
    """Every recognised YouTube/Instagram link in free text, de-duplicated by id."""
    seen: set[tuple[str, str]] = set()
    out: list[ParsedUrl] = []
    for url in extract_urls(text):
        parsed = parse_url(url)
        if parsed is None:
            continue
        key = (str(parsed.platform), parsed.external_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(parsed)
    return out


# --------------------------------------------------------------------------
# per-platform
# --------------------------------------------------------------------------
def _parse_youtube(parts) -> ParsedUrl | None:
    segments = [s for s in parts.path.split("/") if s]
    host = (parts.hostname or "").lower()
    video_id: str | None = None

    if host in {"youtu.be", "www.youtu.be"}:
        # https://youtu.be/<id>?t=30
        if segments:
            video_id = segments[0]
    elif segments and segments[0] == "watch":
        # https://www.youtube.com/watch?v=<id>&list=...&t=30s
        values = parse_qs(parts.query).get("v")
        if values:
            video_id = values[0]
    elif len(segments) >= 2 and segments[0] in {"shorts", "live", "embed", "v"}:
        video_id = segments[1]

    if video_id is None or not _YOUTUBE_ID.match(video_id):
        return None

    return ParsedUrl(
        platform=Platform.YOUTUBE,
        external_id=video_id,
        canonical_url=f"https://www.youtube.com/watch?v={video_id}",
    )


def _parse_instagram(parts) -> ParsedUrl | None:
    segments = [s for s in parts.path.split("/") if s]
    if not segments:
        return None

    # Opaque share redirect: https://www.instagram.com/share/reel/_AbC123
    # The shortcode is only discoverable by following the redirect.
    if segments[0] == "share":
        token = segments[-1]
        if not token or not _INSTAGRAM_SHORTCODE.match(token):
            return None
        return ParsedUrl(
            platform=Platform.INSTAGRAM,
            # Namespaced so a provisional id can never collide with a real
            # shortcode, and so `resolve` can find these rows later.
            external_id=f"{SHARE_ID_PREFIX}{token}",
            canonical_url=f"https://www.instagram.com/share/{token}/",
            needs_resolution=True,
        )

    # Post/reel, optionally nested under a username:
    #   /p/<code>/  /reel/<code>/  /reels/<code>/  /tv/<code>/
    #   /<username>/p/<code>/
    kind: str | None = None
    shortcode: str | None = None
    for index, segment in enumerate(segments):
        if segment in _INSTAGRAM_POST_SEGMENTS and index + 1 < len(segments):
            kind = segment
            shortcode = segments[index + 1]
            break

    if shortcode is None or not _INSTAGRAM_SHORTCODE.match(shortcode):
        return None

    # `reels` and `reel` address the same object; normalise so the same video
    # shared from two surfaces de-duplicates.
    path_kind = "reel" if kind in {"reel", "reels"} else kind
    return ParsedUrl(
        platform=Platform.INSTAGRAM,
        external_id=shortcode,
        canonical_url=f"https://www.instagram.com/{path_kind}/{shortcode}/",
    )
