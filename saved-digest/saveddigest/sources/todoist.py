"""Instagram capture, by way of Todoist.

Instagram exposes saved posts through no API at all — the Graph API's "saves" is a
metric on *your own* posts, never a reader's collection. So capture inverts: you
share a reel to a Todoist project from Instagram's share sheet, and this module
reads that project.

The network client and the parsing are separate on purpose. `items_from_tasks` is
pure, so it can be tested against a recorded real API payload rather than a
hand-imagined one — the field-naming differences between Todoist's API versions
(`created_at` vs `added_at` vs `addedAt`) are exactly the kind of thing that only
shows up against the real thing.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import requests

from saveddigest.sources.urls import parse_urls_in_text
from saveddigest.store import Item, utcnow_iso

log = logging.getLogger(__name__)

_API_ROOT = "https://api.todoist.com/rest/v2"
_TIMEOUT = 30

#: Todoist has renamed this field across API versions; accept every spelling
#: rather than silently losing the save date (which is the digest's sort key).
_CREATED_KEYS = ("created_at", "added_at", "addedAt", "createdAt")

#: Label applied once an item has been ingested, so re-running `sync` does not
#: re-report the same task. Completing the task would also work but destroys the
#: user's own record of what they saved.
INGESTED_LABEL = "digested"


@dataclass(frozen=True)
class TodoistTask:
    """Only the fields capture needs, normalised across API versions."""

    id: str
    content: str
    description: str
    created_at: str | None
    labels: tuple[str, ...] = ()

    @property
    def searchable_text(self) -> str:
        """Content and description together — the link may be in either."""
        return f"{self.content}\n{self.description}"


def normalise_task(raw: dict[str, Any]) -> TodoistTask | None:
    """Coerce one API task object into `TodoistTask`, or None if unusable."""
    task_id = raw.get("id")
    if task_id is None:
        return None

    created = next(
        (raw[key] for key in _CREATED_KEYS if isinstance(raw.get(key), str)),
        None,
    )
    labels = raw.get("labels") or []
    return TodoistTask(
        id=str(task_id),
        content=str(raw.get("content") or ""),
        description=str(raw.get("description") or ""),
        created_at=created,
        labels=tuple(str(label) for label in labels if isinstance(label, str)),
    )


def items_from_tasks(
    raw_tasks: Iterable[dict[str, Any]],
    *,
    source: str = "todoist",
    skip_label: str | None = INGESTED_LABEL,
) -> tuple[list[Item], list[str]]:
    """Turn Todoist tasks into `Item`s.

    Returns `(items, consumed_task_ids)`. `consumed_task_ids` are the tasks that
    yielded at least one item and can therefore be marked ingested; a task with
    no recognisable link is left untouched so a typo'd URL can be fixed rather
    than silently swallowed.

    De-duplicates within the batch too: sharing the same reel from two surfaces
    (`/reel/` and `/reels/`) produces two tasks but must produce one item.
    """
    items: list[Item] = []
    consumed: list[str] = []
    # key -> index into `items`, so a later duplicate can enrich the first copy
    # rather than being dropped outright.
    seen: dict[tuple[str, str], int] = {}

    for raw in raw_tasks:
        task = normalise_task(raw)
        if task is None:
            log.debug("skipping task with no id: %r", raw)
            continue
        if skip_label and skip_label in task.labels:
            continue

        parsed_links = parse_urls_in_text(task.searchable_text)
        if not parsed_links:
            # Not an error: the project can hold ordinary notes.
            log.debug("no recognised link in task %s", task.id)
            continue

        title = _human_title(task.content)
        produced = False

        for link in parsed_links:
            key = (str(link.platform), link.external_id)

            if key in seen:
                # The same reel shared twice, e.g. once as /reel/ and once as
                # /reels/. Keep one item, but don't throw away information the
                # duplicate carried: a human-written title beats a bare URL, and
                # the earlier save date is the one that matters for ageing.
                existing = items[seen[key]]
                if existing.title is None and title is not None:
                    existing.title = title
                existing.saved_at = _earlier_iso(existing.saved_at, task.created_at)
                produced = True
                continue

            seen[key] = len(items)
            items.append(
                Item(
                    platform=link.platform,
                    external_id=link.external_id,
                    url=link.canonical_url,
                    source=source,
                    title=title,
                    saved_at=task.created_at,
                    captured_at=utcnow_iso(),
                )
            )
            produced = True

        if produced:
            consumed.append(task.id)

    return items, consumed


def _human_title(content: str) -> str | None:
    """A task's content as a title, or None when it is just a pasted URL.

    "https://www.instagram.com/reel/AbC/" is a useless digest heading; enrich will
    replace it with the real caption. Anything the user actually typed is kept.
    """
    title = content.strip()
    if not title or title.startswith(("http://", "https://")):
        return None
    return title


def _earlier_iso(a: str | None, b: str | None) -> str | None:
    """Lexicographically earlier of two ISO-8601 strings, ignoring missing ones.

    Todoist stamps are always UTC with the same format, so a string compare is
    correct here and avoids a parse on the hot path.
    """
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


class TodoistClient:
    """Minimal Todoist REST client. Network-facing; kept free of parsing logic."""

    def __init__(self, token: str, *, session: requests.Session | None = None):
        if not token:
            raise ValueError("a Todoist API token is required")
        self._token = token
        self._session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def find_project_id(self, name: str) -> str | None:
        """Resolve a project by exact name, case-insensitively."""
        response = self._session.get(
            f"{_API_ROOT}/projects", headers=self._headers(), timeout=_TIMEOUT
        )
        response.raise_for_status()
        target = name.casefold()
        for project in response.json():
            if str(project.get("name", "")).casefold() == target:
                return str(project["id"])
        return None

    def tasks_in_project(self, project_id: str) -> list[dict[str, Any]]:
        response = self._session.get(
            f"{_API_ROOT}/tasks",
            headers=self._headers(),
            params={"project_id": project_id},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def add_label(self, task_id: str, label: str) -> None:
        """Append a label, preserving the ones already there.

        Todoist's update endpoint replaces the whole label array, so this reads
        first. Without the read, marking an item ingested would wipe any labels
        the user had applied themselves.
        """
        current = self._session.get(
            f"{_API_ROOT}/tasks/{task_id}", headers=self._headers(), timeout=_TIMEOUT
        )
        current.raise_for_status()
        labels = list(current.json().get("labels") or [])
        if label in labels:
            return
        labels.append(label)
        response = self._session.post(
            f"{_API_ROOT}/tasks/{task_id}",
            headers=self._headers(),
            json={"labels": labels},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()

    def mark_ingested(self, task_ids: Sequence[str], label: str = INGESTED_LABEL) -> int:
        """Label each task, tolerating individual failures.

        A failure here is benign — the item is already stored, and the worst case
        is that next week's sync sees the task again and de-duplicates it. So one
        broken task must not abort the whole run.
        """
        marked = 0
        for task_id in task_ids:
            try:
                self.add_label(task_id, label)
                marked += 1
            except requests.RequestException as exc:
                log.warning("could not label task %s as ingested: %s", task_id, exc)
        return marked
