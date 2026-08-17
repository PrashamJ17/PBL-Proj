"""SQLite persistence.

Design rules that the rest of the codebase relies on:

1. `(platform, external_id)` is the dedup key. Re-running `sync` every week must
   not create a second row for the same video, and must not *reset* an item that
   has already been summarised — re-billing the Claude API for work already paid
   for is the failure mode this guards.
2. `status` names the furthest stage completed, so every stage is a resumable
   `SELECT ... WHERE status = ?`.
3. `liveness` is orthogonal to `status`: a dead video still has a summary from
   before it was deleted, and we still want to tell the user it is gone.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class Platform(StrEnum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"


class Status(StrEnum):
    """Furthest pipeline stage completed for an item."""

    NEW = "new"
    ENRICHED = "enriched"
    SUMMARISED = "summarised"
    VERIFIED = "verified"
    DELIVERED = "delivered"
    FAILED = "failed"


# The pipeline is linear. Declared explicitly so an accidental backwards write
# (which would re-bill the API) raises instead of silently succeeding.
_STAGE_ORDER: dict[Status, int] = {
    Status.NEW: 0,
    Status.ENRICHED: 1,
    Status.SUMMARISED: 2,
    Status.VERIFIED: 3,
    Status.DELIVERED: 4,
}


class Liveness(StrEnum):
    UNKNOWN = "unknown"
    ALIVE = "alive"
    DEAD = "dead"
    # Instagram behind a login wall is indistinguishable from deleted. We never
    # claim `DEAD` on a guess — a wrongly-dropped save is invisible to the user.
    UNVERIFIABLE = "unverifiable"


class Staleness(StrEnum):
    """Pass A's judgement about whether an item needs a web check."""

    EVERGREEN = "evergreen"
    TIME_SENSITIVE = "time_sensitive"
    VERSION_BOUND = "version_bound"
    DATED_EVENT = "dated_event"


#: Classes that get sent to Pass B. `EVERGREEN` skips the web search entirely —
#: that skip is where most of the cost saving comes from.
NEEDS_VERIFICATION: frozenset[Staleness] = frozenset(
    {Staleness.TIME_SENSITIVE, Staleness.VERSION_BOUND, Staleness.DATED_EVENT}
)


class Verdict(StrEnum):
    """Pass B's conclusion, or why there isn't one."""

    STILL_VALID = "still_valid"
    PARTLY_OUTDATED = "partly_outdated"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    #: Search failed, was rate-limited, or the model could not reach a
    #: conclusion. Never conflate with STILL_VALID.
    UNVERIFIED = "unverified"
    #: Never sent to Pass B because Pass A called it evergreen.
    NOT_APPLICABLE = "not_applicable"


def utcnow_iso() -> str:
    """Timezone-aware UTC timestamp, second precision, stable for tests."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT,
    author          TEXT,
    published_at    TEXT,
    saved_at        TEXT,
    captured_at     TEXT NOT NULL,
    source          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'new',
    liveness        TEXT NOT NULL DEFAULT 'unknown',
    content_text    TEXT,
    content_kind    TEXT,
    summary_json    TEXT,
    staleness_class TEXT,
    expiry_date     TEXT,
    verdict_json    TEXT,
    relevance_score REAL,
    delivered_at    TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    UNIQUE (platform, external_id)
);

CREATE INDEX IF NOT EXISTS idx_items_status ON items (status);
CREATE INDEX IF NOT EXISTS idx_items_saved_at ON items (saved_at);
"""


@dataclass
class Item:
    """One saved thing, at whatever stage of the pipeline it has reached."""

    platform: Platform
    external_id: str
    url: str
    source: str
    title: str | None = None
    author: str | None = None
    published_at: str | None = None
    saved_at: str | None = None
    captured_at: str | None = None
    status: Status = Status.NEW
    liveness: Liveness = Liveness.UNKNOWN
    content_text: str | None = None
    content_kind: str | None = None
    summary_json: str | None = None
    staleness_class: str | None = None
    expiry_date: str | None = None
    verdict_json: str | None = None
    relevance_score: float | None = None
    delivered_at: str | None = None
    attempts: int = 0
    error: str | None = None
    id: int | None = None

    # -- convenience: parsed JSON columns -----------------------------------
    @property
    def summary(self) -> dict[str, Any] | None:
        return _loads_or_none(self.summary_json)

    @property
    def verdict(self) -> dict[str, Any] | None:
        return _loads_or_none(self.verdict_json)

    @property
    def staleness(self) -> Staleness | None:
        if self.staleness_class is None:
            return None
        try:
            return Staleness(self.staleness_class)
        except ValueError:
            # An unrecognised class from a future/older version: treat as needing
            # a check rather than silently trusting it.
            return Staleness.TIME_SENSITIVE

    def days_since_saved(self, now: datetime | None = None) -> int:
        """Whole days since the user saved this. 0 when the date is unknown."""
        ref = _parse_iso(self.saved_at) or _parse_iso(self.captured_at)
        if ref is None:
            return 0
        now = now or datetime.now(UTC)
        return max(0, (now - ref).days)


def _loads_or_none(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_iso(raw: str | None) -> datetime | None:
    """Parse an ISO-8601 string, tolerating a trailing `Z` and naive values."""
    if not raw:
        return None
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


_ITEM_COLUMNS = (
    "id",
    "platform",
    "external_id",
    "url",
    "title",
    "author",
    "published_at",
    "saved_at",
    "captured_at",
    "source",
    "status",
    "liveness",
    "content_text",
    "content_kind",
    "summary_json",
    "staleness_class",
    "expiry_date",
    "verdict_json",
    "relevance_score",
    "delivered_at",
    "attempts",
    "error",
)

#: Columns a caller may write through `update`. Anything else is a bug, and an
#: unknown key would otherwise be silently dropped by the SQL builder.
_UPDATABLE = frozenset(_ITEM_COLUMNS) - {"id", "platform", "external_id"}


def _row_to_item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"],
        platform=Platform(row["platform"]),
        external_id=row["external_id"],
        url=row["url"],
        title=row["title"],
        author=row["author"],
        published_at=row["published_at"],
        saved_at=row["saved_at"],
        captured_at=row["captured_at"],
        source=row["source"],
        status=Status(row["status"]),
        liveness=Liveness(row["liveness"]),
        content_text=row["content_text"],
        content_kind=row["content_kind"],
        summary_json=row["summary_json"],
        staleness_class=row["staleness_class"],
        expiry_date=row["expiry_date"],
        verdict_json=row["verdict_json"],
        relevance_score=row["relevance_score"],
        delivered_at=row["delivered_at"],
        attempts=row["attempts"],
        error=row["error"],
    )


class Store:
    """Thin, explicit wrapper over SQLite. No ORM, no lazy loading."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        if self.path.parent != Path(""):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # -- lifecycle ----------------------------------------------------------
    def _migrate(self) -> None:
        # `executescript` issues an implicit COMMIT before it runs, so it cannot
        # be nested inside our own BEGIN/COMMIT. With isolation_level=None these
        # two statements are already autocommitted individually, and both are
        # idempotent (IF NOT EXISTS / DO NOTHING), so a crash between them is safe.
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT (key) DO NOTHING",
            (str(SCHEMA_VERSION),),
        )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Explicit transaction. `isolation_level=None` means we drive BEGIN."""
        self._conn.execute("BEGIN")
        try:
            yield self._conn
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # -- meta / capability flags -------------------------------------------
    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # -- writes -------------------------------------------------------------
    def upsert(self, item: Item) -> tuple[Item, bool]:
        """Insert `item`, or refresh metadata if we already have it.

        Returns `(stored_item, created)`.

        On conflict this deliberately does **not** touch `status`, `content_*`,
        `summary_json`, `verdict_json` or `delivered_at`. A weekly re-sync sees
        every playlist entry again; resetting progress here would re-summarise
        and re-email the entire library every single run.

        `saved_at` keeps the *earliest* known value, because "how long has this
        been rotting" is the digest's primary sort key and a re-sync must not
        make an old save look new.
        """
        existing = self.get_by_external_id(item.platform, item.external_id)
        captured = item.captured_at or utcnow_iso()

        if existing is None:
            cur = self._conn.execute(
                """
                INSERT INTO items (
                    platform, external_id, url, title, author, published_at,
                    saved_at, captured_at, source, status, liveness,
                    content_text, content_kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(item.platform),
                    item.external_id,
                    item.url,
                    item.title,
                    item.author,
                    item.published_at,
                    item.saved_at,
                    captured,
                    item.source,
                    str(item.status),
                    str(item.liveness),
                    item.content_text,
                    item.content_kind,
                ),
            )
            return replace(item, id=cur.lastrowid, captured_at=captured), True

        # Titles get edited and channels get renamed; refresh those. Keep the
        # earliest saved_at.
        merged_saved_at = _earliest(existing.saved_at, item.saved_at)
        self._conn.execute(
            """
            UPDATE items
               SET url          = ?,
                   title        = COALESCE(?, title),
                   author       = COALESCE(?, author),
                   published_at = COALESCE(?, published_at),
                   saved_at     = ?
             WHERE id = ?
            """,
            (
                item.url,
                item.title,
                item.author,
                item.published_at,
                merged_saved_at,
                existing.id,
            ),
        )
        refreshed = self.get(existing.id)  # type: ignore[arg-type]
        assert refreshed is not None
        return refreshed, False

    def update(self, item_id: int, **fields: Any) -> None:
        """Patch named columns. Rejects unknown columns rather than ignoring them."""
        if not fields:
            return
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"not updatable column(s): {sorted(unknown)}")
        # StrEnum values serialise as themselves, but be explicit for sqlite3.
        payload = {k: (str(v) if isinstance(v, StrEnum) else v) for k, v in fields.items()}
        assignments = ", ".join(f"{k} = :{k}" for k in payload)
        payload["_id"] = item_id
        self._conn.execute(f"UPDATE items SET {assignments} WHERE id = :_id", payload)

    def advance(self, item_id: int, to: Status, **fields: Any) -> None:
        """Move an item forward one-way, writing `fields` in the same statement.

        Raises on a backwards move. `FAILED` is reachable from anywhere, and
        re-writing the *same* status is allowed so a retried stage is idempotent.
        """
        current = self.get(item_id)
        if current is None:
            raise KeyError(f"no item with id {item_id}")
        if to is not Status.FAILED and current.status is not Status.FAILED:
            here, there = _STAGE_ORDER[current.status], _STAGE_ORDER[to]
            if there < here:
                raise ValueError(
                    f"refusing to move item {item_id} backwards: "
                    f"{current.status} -> {to}"
                )
        self.update(item_id, status=to, **fields)

    def record_failure(self, item_id: int, message: str) -> None:
        """Bump the attempt counter and store the message, keeping the stage."""
        self._conn.execute(
            "UPDATE items SET attempts = attempts + 1, error = ? WHERE id = ?",
            (message[:2000], item_id),
        )

    # -- reads --------------------------------------------------------------
    def get(self, item_id: int) -> Item | None:
        row = self._conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return _row_to_item(row) if row else None

    def get_by_external_id(self, platform: Platform, external_id: str) -> Item | None:
        row = self._conn.execute(
            "SELECT * FROM items WHERE platform = ? AND external_id = ?",
            (str(platform), external_id),
        ).fetchone()
        return _row_to_item(row) if row else None

    def by_status(
        self,
        status: Status | Sequence[Status],
        *,
        limit: int | None = None,
        max_attempts: int = 3,
    ) -> list[Item]:
        """Items at `status`, oldest save first, skipping ones that keep failing.

        `max_attempts` stops a permanently broken item (a video with no captions
        that also 500s) from consuming the whole per-run budget every week.
        """
        statuses = [status] if isinstance(status, Status) else list(status)
        placeholders = ", ".join("?" for _ in statuses)
        sql = (
            f"SELECT * FROM items WHERE status IN ({placeholders}) AND attempts < ? "
            "ORDER BY COALESCE(saved_at, captured_at) ASC, id ASC"
        )
        params: list[Any] = [str(s) for s in statuses] + [max_attempts]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [_row_to_item(r) for r in self._conn.execute(sql, params)]

    def all_items(self) -> list[Item]:
        return [_row_to_item(r) for r in self._conn.execute("SELECT * FROM items ORDER BY id")]

    def counts_by_status(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM items GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}


def _earliest(a: str | None, b: str | None) -> str | None:
    """Earliest of two ISO timestamps, ignoring unparseable/missing ones."""
    da, db = _parse_iso(a), _parse_iso(b)
    if da is None:
        return b if db is not None else a
    if db is None:
        return a
    return a if da <= db else b
