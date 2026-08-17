"""One-time Watch Later backlog import.

Watch Later cannot be read through the YouTube Data API — the playlist is
system-managed, and `relatedPlaylists` returns the literal constant `WL` even for
your own authorised channel. The only way in is a logged-in browser session, so
this reads it via yt-dlp using cookies lifted from a local browser.

**This path is deliberately quarantined.** It is unofficial, it breaks whenever
YouTube changes its internals, and it needs a browser profile on the same machine.
So it exists to move an existing backlog across *once*; the ongoing capture path
is an ordinary playlist read through the official API, which never breaks.

A flat playlist listing carries no "added to playlist" date, so imported items
have no `saved_at`. The store falls back to `captured_at` for ordering, which
means the whole backlog sorts together — correct, since we genuinely do not know
which was saved first.
"""

from __future__ import annotations

import logging
from typing import Any

from saveddigest.store import Item, Platform, utcnow_iso

log = logging.getLogger(__name__)

SOURCE_WATCH_LATER = "youtube_wl"

WATCH_LATER_URL = "https://www.youtube.com/playlist?list=WL"

#: Titles yt-dlp reports for entries whose video is gone.
_TOMBSTONES = frozenset({"[deleted video]", "[private video]", "deleted video", "private video"})


class WatchLaterError(RuntimeError):
    """Raised with a message that says what to do instead."""


def parse_flat_entries(info: dict[str, Any]) -> list[Item]:
    """Convert a yt-dlp flat-playlist info dict into items.

    Pure, so the awkward shape of yt-dlp's output can be tested without a browser
    profile or network access.
    """
    entries = info.get("entries") or []
    items: list[Item] = []
    seen: set[str] = set()

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        video_id = entry.get("id")
        if not isinstance(video_id, str) or not video_id or video_id in seen:
            continue
        seen.add(video_id)

        title = entry.get("title")
        if isinstance(title, str) and title.strip().casefold() in _TOMBSTONES:
            title = None

        items.append(
            Item(
                platform=Platform.YOUTUBE,
                external_id=video_id,
                url=f"https://www.youtube.com/watch?v={video_id}",
                source=SOURCE_WATCH_LATER,
                title=title or None,
                author=entry.get("uploader") or entry.get("channel") or None,
                # A flat listing has no add-date; the store orders these by
                # captured_at instead.
                saved_at=None,
                captured_at=utcnow_iso(),
            )
        )
    return items


def import_watch_later(browser: str, *, max_items: int | None = None) -> list[Item]:
    """Read Watch Later using cookies from `browser`.

    `browser` is a yt-dlp browser name: chrome, firefox, edge, brave, safari,
    chromium, opera, vivaldi.
    """
    try:
        import yt_dlp
    except ImportError as exc:
        raise WatchLaterError(
            "yt-dlp is required for the Watch Later import:\n    pip install yt-dlp"
        ) from exc

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        # Flat: we only need ids here. Metadata comes from the official API later.
        "extract_flat": True,
        "cookiesfrombrowser": (browser,),
    }
    if max_items:
        opts["playlistend"] = max_items

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(WATCH_LATER_URL, download=False)
    except Exception as exc:  # noqa: BLE001 - yt-dlp raises many types
        raise WatchLaterError(
            f"could not read Watch Later via {browser} cookies: {exc}\n"
            "Common causes: the browser is not logged into YouTube, the profile is "
            "locked by a running browser (close it and retry), or YouTube changed "
            "its internals. Move the backlog into your playlist by hand instead — "
            "ongoing capture does not depend on this."
        ) from exc

    if not isinstance(info, dict):
        raise WatchLaterError("unexpected response shape from yt-dlp")

    items = parse_flat_entries(info)
    if not items:
        raise WatchLaterError(
            "Watch Later returned no entries. Either it is empty, or the cookies "
            "did not authenticate. Check youtube.com/playlist?list=WL in that browser."
        )
    return items
