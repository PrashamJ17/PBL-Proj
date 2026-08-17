"""YouTube capture through the official Data API v3.

Watch Later is not readable here, and no scope changes that: `channels.list`
returns the literal constants `HL` and `WL` for the history and watch-later
playlist ids even for your own authorised channel, and those playlists are
system-managed and reject reads. This module therefore reads an *ordinary*
playlist ("To Watch"), which the API supports fully and indefinitely. The
one-time Watch Later backlog import lives in `sources.youtube_wl`.

Two useful facts the API gives us for free, both load-bearing for the digest:

* `playlistItems.snippet.publishedAt` is when the video was added to the
  playlist — i.e. when *you saved it*. That is the digest's ageing key.
* `contentDetails.videoPublishedAt` is when the video itself was published,
  which is what Pass A needs to judge whether the content is likely stale.

Deleted and private videos are not removed from playlists; they remain as entries
titled "Deleted video" / "Private video". Detecting them here is why the digest
can say "3 saved items no longer exist" instead of silently summarising nothing.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from saveddigest.store import Item, Liveness, Platform, utcnow_iso

log = logging.getLogger(__name__)

#: Titles YouTube substitutes for entries whose video is gone. Matched
#: case-insensitively and exactly, so a real video called "Deleted video (my
#: short film)" is not misclassified.
_TOMBSTONE_TITLES = frozenset(
    {
        "deleted video",
        "private video",
        "[deleted video]",
        "[private video]",
    }
)

_ISO_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)

SOURCE_PLAYLIST = "youtube_playlist"


@dataclass(frozen=True)
class PlaylistEntry:
    """One playlist row, normalised. Kept separate from `Item` because a
    tombstone still needs recording but carries no usable metadata."""

    video_id: str
    title: str | None
    channel: str | None
    added_at: str | None
    video_published_at: str | None
    liveness: Liveness


def parse_duration_seconds(raw: str | None) -> int | None:
    """ISO-8601 duration (`PT5M30S`) to seconds. None when absent or malformed.

    YouTube reports live streams as `P0D`, which correctly yields 0 rather than
    an exception.
    """
    if not raw:
        return None
    match = _ISO_DURATION.match(raw.strip())
    if not match:
        return None
    parts = {k: int(v) for k, v in match.groupdict(default="0").items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def _is_tombstone(title: str | None) -> bool:
    return title is not None and title.strip().casefold() in _TOMBSTONE_TITLES


def parse_playlist_page(payload: dict[str, Any]) -> tuple[list[PlaylistEntry], str | None]:
    """Turn one `playlistItems.list` response into entries plus a page token."""
    entries: list[PlaylistEntry] = []

    for raw in payload.get("items") or []:
        snippet = raw.get("snippet") or {}
        content = raw.get("contentDetails") or {}

        resource = snippet.get("resourceId") or {}
        # A playlist can in principle contain non-video resources; skip them
        # rather than minting an item with an unusable id.
        if resource.get("kind") not in (None, "youtube#video"):
            continue

        video_id = content.get("videoId") or resource.get("videoId")
        if not isinstance(video_id, str) or not video_id:
            log.debug("playlist row with no video id: %r", raw)
            continue

        title = snippet.get("title")
        tombstone = _is_tombstone(title)

        entries.append(
            PlaylistEntry(
                video_id=video_id,
                title=None if tombstone else (title or None),
                channel=snippet.get("videoOwnerChannelTitle") or None,
                added_at=snippet.get("publishedAt") or None,
                video_published_at=content.get("videoPublishedAt") or None,
                liveness=Liveness.DEAD if tombstone else Liveness.UNKNOWN,
            )
        )

    return entries, payload.get("nextPageToken")


def entries_to_items(
    entries: Iterable[PlaylistEntry], *, source: str = SOURCE_PLAYLIST
) -> list[Item]:
    """Map normalised playlist entries to storable items, de-duplicated.

    A playlist can legitimately contain the same video twice; the store would
    reject the second insert, so collapse them here and keep the earlier
    add-date.
    """
    by_id: dict[str, Item] = {}
    for entry in entries:
        existing = by_id.get(entry.video_id)
        if existing is not None:
            if entry.added_at and (
                existing.saved_at is None or entry.added_at < existing.saved_at
            ):
                existing.saved_at = entry.added_at
            continue
        by_id[entry.video_id] = Item(
            platform=Platform.YOUTUBE,
            external_id=entry.video_id,
            url=f"https://www.youtube.com/watch?v={entry.video_id}",
            source=source,
            title=entry.title,
            author=entry.channel,
            published_at=entry.video_published_at,
            saved_at=entry.added_at,
            captured_at=utcnow_iso(),
            liveness=entry.liveness,
        )
    return list(by_id.values())


def parse_videos_page(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index a `videos.list` response by video id.

    Values carry `title`, `channel`, `published_at`, `description` and
    `duration_seconds`. Ids *absent* from the response are the caller's signal
    that a video is deleted or private — see `missing_video_ids`.
    """
    out: dict[str, dict[str, Any]] = {}
    for raw in payload.get("items") or []:
        video_id = raw.get("id")
        if not isinstance(video_id, str):
            continue
        snippet = raw.get("snippet") or {}
        content = raw.get("contentDetails") or {}
        out[video_id] = {
            "title": snippet.get("title") or None,
            "channel": snippet.get("channelTitle") or None,
            "published_at": snippet.get("publishedAt") or None,
            "description": snippet.get("description") or "",
            "duration_seconds": parse_duration_seconds(content.get("duration")),
        }
    return out


def missing_video_ids(requested: Iterable[str], found: dict[str, Any]) -> list[str]:
    """Requested ids the API declined to return — deleted or private.

    This is the liveness check for YouTube, and it is free: `videos.list` simply
    omits ids it will not serve.
    """
    return [vid for vid in requested if vid not in found]


class YouTubeReader:
    """Reads a playlist through a discovery client. Network-facing only."""

    #: The API's hard maximum for both endpoints.
    PAGE_SIZE = 50

    def __init__(self, service: Any):
        self._service = service

    def resolve_playlist_id(self, title: str) -> str | None:
        """Find one of the authorised user's own playlists by exact title."""
        target = title.casefold()
        request = self._service.playlists().list(
            part="snippet", mine=True, maxResults=self.PAGE_SIZE
        )
        while request is not None:
            response = request.execute()
            for raw in response.get("items") or []:
                name = ((raw.get("snippet") or {}).get("title") or "").casefold()
                if name == target:
                    return raw.get("id")
            request = self._service.playlists().list_next(request, response)
        return None

    def read_playlist(
        self, playlist_id: str, *, max_items: int | None = None
    ) -> list[PlaylistEntry]:
        """Page through a playlist, newest-added last."""
        entries: list[PlaylistEntry] = []
        page_token: str | None = None

        while True:
            response = (
                self._service.playlistItems()
                .list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=self.PAGE_SIZE,
                    pageToken=page_token,
                )
                .execute()
            )
            page, page_token = parse_playlist_page(response)
            entries.extend(page)
            if max_items is not None and len(entries) >= max_items:
                return entries[:max_items]
            if not page_token:
                return entries

    def fetch_video_details(self, video_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Batch-fetch metadata, 50 ids per call (the API's limit)."""
        details: dict[str, dict[str, Any]] = {}
        for start in range(0, len(video_ids), self.PAGE_SIZE):
            chunk = video_ids[start : start + self.PAGE_SIZE]
            response = (
                self._service.videos()
                .list(part="snippet,contentDetails", id=",".join(chunk))
                .execute()
            )
            details.update(parse_videos_page(response))
        return details
