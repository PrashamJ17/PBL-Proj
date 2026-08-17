"""Fetching the actual content behind a saved link.

Split deliberately into pure decision logic (testable offline, and tested) and
thin network wrappers around yt-dlp (not testable without egress).

**This stage must run from a residential IP.** YouTube rate-limits and blocks
known cloud-provider ranges, so a caption fetch that works on a laptop returns
`RequestBlocked`/`IpBlocked` from AWS, GCP, Azure or a CI runner. That single fact
is why the whole tool is a local cron job rather than a hosted service.

Instagram has a second, unrelated limit: the default tier reads the *caption*,
not the spoken audio. Transcribing a Reel means downloading the video and running
a local Whisper model, so it is opt-in (`--deep`, `pip install
'saved-digest[audio]'`) rather than standard. See docs/INSTAGRAM.md.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from saveddigest.enrich.vtt import vtt_to_text

log = logging.getLogger(__name__)


class ContentKind:
    """Provenance of `Item.content_text`, so the digest can caveat honestly."""

    MANUAL_SUBS = "manual_subtitles"
    AUTO_SUBS = "auto_captions"
    CAPTION = "caption"
    METADATA_ONLY = "metadata_only"
    AUDIO_TRANSCRIPT = "audio_transcript"


@dataclass
class FetchedContent:
    """What enrich managed to obtain for one item."""

    text: str
    kind: str
    title: str | None = None
    author: str | None = None
    published_at: str | None = None
    duration_seconds: int | None = None

    @property
    def is_usable(self) -> bool:
        """Whether there is enough here for Pass A to say something real.

        A bare title is not enough to summarise "in detail", so items below this
        bar are marked metadata-only and the digest says so rather than inventing
        substance.
        """
        return bool(self.text and self.text.strip())


# --------------------------------------------------------------------------
# pure: choosing a subtitle track
# --------------------------------------------------------------------------
def rank_subtitle_language(tag: str, *, preferred: str = "en") -> tuple[int, int, str]:
    """Sort key for a subtitle language tag; lower is better.

    yt-dlp writes one file per language and there are usually several. Preference
    order, from a real `en.*` request:

    1. exact `en`
    2. `en-orig` — YouTube's label for the creator's original track
    3. any other `en-*` regional variant (`en-GB`, `en-US`)
    4. anything else, alphabetically for determinism

    A stable order matters: picking a different track between runs would change
    the transcript, and therefore the summary, for no reason.
    """
    normalised = tag.strip().casefold()
    base = normalised.split("-", 1)[0]
    want = preferred.strip().casefold()

    if normalised == want:
        return (0, 0, normalised)
    if normalised == f"{want}-orig":
        return (1, 0, normalised)
    if base == want:
        return (2, 0, normalised)
    return (3, 0, normalised)


def language_from_subtitle_path(path: Path, *, stem: str | None = None) -> str:
    """Recover the language tag yt-dlp encoded in a subtitle filename.

    yt-dlp writes `<outtmpl>.<lang>.vtt`, e.g. `dQw4w9WgXcQ.en-orig.vtt`, so the
    tag is the second-to-last dot-separated component.
    """
    parts = path.name.split(".")
    if len(parts) >= 3:
        return parts[-2]
    return stem or ""


def pick_subtitle_file(paths: Iterable[Path], *, preferred: str = "en") -> Path | None:
    """Choose the best subtitle file from those yt-dlp wrote."""
    candidates = [p for p in paths if p.suffix.lower() == ".vtt"]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda p: rank_subtitle_language(
            language_from_subtitle_path(p), preferred=preferred
        ),
    )


def classify_subtitle_kind(info: dict[str, Any], language: str) -> str:
    """Manual subtitles or machine captions, read from yt-dlp's info dict.

    Worth distinguishing: auto-captions mis-hear technical terms, so the digest
    labels a summary built from them differently.
    """
    base = language.split("-", 1)[0].casefold()

    def _has(section: str) -> bool:
        tracks = info.get(section) or {}
        return any(
            key.casefold() == language.casefold() or key.split("-", 1)[0].casefold() == base
            for key in tracks
        )

    if _has("subtitles"):
        return ContentKind.MANUAL_SUBS
    if _has("automatic_captions"):
        return ContentKind.AUTO_SUBS
    return ContentKind.AUTO_SUBS


def build_youtube_fallback_text(title: str | None, description: str | None) -> str:
    """Text to summarise when a video simply has no captions.

    Better than nothing and clearly weaker than a transcript, which is why the
    caller records `METADATA_ONLY` alongside it.
    """
    parts = [p.strip() for p in (title, description) if p and p.strip()]
    return "\n\n".join(parts)


# --------------------------------------------------------------------------
# network: yt-dlp wrappers
# --------------------------------------------------------------------------
def _ydl(opts: dict[str, Any]) -> Any:
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "yt-dlp is required for the enrich stage. Install it with:\n"
            "    pip install yt-dlp"
        ) from exc
    base = {"quiet": True, "no_warnings": True, "noprogress": True}
    return yt_dlp.YoutubeDL({**base, **opts})


def fetch_youtube_content(
    video_id: str,
    *,
    languages: Sequence[str] = ("en.*",),
    preferred: str = "en",
    workdir: Path | None = None,
) -> FetchedContent:
    """Download captions for one video and flatten them to prose.

    Falls back to title + description when the video has no caption track at all,
    which is common for small channels and for music.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        out = Path(tmp)
        opts = {
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": list(languages),
            "subtitlesformat": "vtt",
            "skip_download": True,
            "outtmpl": str(out / "%(id)s"),
        }
        with _ydl(opts) as ydl:
            info = ydl.extract_info(url, download=True) or {}

        subtitle_path = pick_subtitle_file(out.iterdir(), preferred=preferred)
        text = ""
        kind = ContentKind.METADATA_ONLY
        if subtitle_path is not None:
            raw = subtitle_path.read_text(encoding="utf-8", errors="replace")
            text = vtt_to_text(raw)
            if text:
                language = language_from_subtitle_path(subtitle_path)
                kind = classify_subtitle_kind(info, language)

    if not text:
        text = build_youtube_fallback_text(info.get("title"), info.get("description"))
        kind = ContentKind.METADATA_ONLY

    return FetchedContent(
        text=text,
        kind=kind,
        title=info.get("title") or None,
        author=info.get("uploader") or info.get("channel") or None,
        published_at=_upload_date_to_iso(info.get("upload_date")),
        duration_seconds=_as_int(info.get("duration")),
    )


def fetch_instagram_content(
    url: str, *, cookies_from_browser: str | None = None
) -> FetchedContent:
    """Read a public post's caption, author and title.

    Deliberately metadata-only. `cookies_from_browser` reaches private posts but
    ties the run to your logged-in session, so it stays opt-in and off by default.
    """
    opts: dict[str, Any] = {"skip_download": True}
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)

    with _ydl(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}

    # yt-dlp maps an Instagram caption onto `description`.
    caption = (info.get("description") or "").strip()
    return FetchedContent(
        text=caption,
        kind=ContentKind.CAPTION if caption else ContentKind.METADATA_ONLY,
        title=info.get("title") or None,
        author=info.get("uploader") or info.get("channel") or None,
        published_at=_timestamp_to_iso(info.get("timestamp")),
        duration_seconds=_as_int(info.get("duration")),
    )


def resolve_share_redirect(share_url: str) -> str | None:
    """Follow an Instagram `/share/` redirect to the real post URL.

    Returns None on any failure — a share link we cannot resolve stays flagged
    rather than being silently attached to the wrong post.
    """
    try:
        import requests
    except ImportError:  # pragma: no cover
        return None
    try:
        response = requests.head(
            share_url, allow_redirects=True, timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (compatible; saved-digest/0.1)"},
        )
    except Exception as exc:
        log.warning("could not resolve share link %s: %s", share_url, exc)
        return None
    final = response.url
    return final if final and final != share_url else None


# --------------------------------------------------------------------------
# small coercions
# --------------------------------------------------------------------------
def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _upload_date_to_iso(raw: Any) -> str | None:
    """yt-dlp's `upload_date` is `YYYYMMDD`."""
    if not isinstance(raw, str) or len(raw) != 8 or not raw.isdigit():
        return None
    return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}T00:00:00+00:00"


def _timestamp_to_iso(raw: Any) -> str | None:
    from datetime import UTC, datetime

    seconds = _as_int(raw)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, UTC).replace(microsecond=0).isoformat()
    except (OverflowError, OSError, ValueError):
        return None
