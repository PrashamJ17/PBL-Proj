"""Configuration: paths and credentials, all overridable by environment variable.

Nothing here reads the network or touches disk at import time, so tests can build
a Config pointing at a tmpdir without side effects.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "saved-digest"

# Google OAuth scopes. One consent covers both: reading the playlist and sending
# the digest. `youtube.readonly` cannot read Watch Later (that playlist is
# system-managed and closed to the API) — see docs/WHY-NOT-WATCH-LATER.md.
GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/gmail.send",
)


def _xdg_config_home() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".config"


def _xdg_data_home() -> Path:
    raw = os.environ.get("XDG_DATA_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".local" / "share"


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration.

    `config_dir` holds secrets (OAuth client + token), `data_dir` holds the
    database. They are separate so a user can back up one without the other.
    """

    config_dir: Path
    data_dir: Path

    # --- Capture -----------------------------------------------------------
    youtube_playlist_title: str = "To Watch"
    # Resolved playlist id; when unset the playlist is looked up by title.
    youtube_playlist_id: str | None = None
    todoist_token: str | None = None
    todoist_project_name: str = "Saved from Instagram"
    # Browser to lift cookies from for the one-time Watch Later import.
    cookies_from_browser: str | None = None

    # --- Claude ------------------------------------------------------------
    anthropic_api_key: str | None = None
    model: str = "claude-opus-5"
    effort: str = "medium"
    # Bounds cost per verified item. Simple factual checks use 1-3 searches.
    max_searches_per_item: int = 4

    # --- Delivery ----------------------------------------------------------
    digest_to: str | None = None
    digest_item_limit: int = 12
    # Per-run batch sizes. The first run finds hundreds of items; without these
    # the initial batch is large and the first email is unreadable.
    stage_limit: int = 50

    extra: dict[str, str] = field(default_factory=dict)

    # -- derived paths ------------------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.data_dir / "saved-digest.db"

    @property
    def google_client_secret_path(self) -> Path:
        return self.config_dir / "google_client_secret.json"

    @property
    def google_token_path(self) -> Path:
        return self.config_dir / "google_token.json"

    def ensure_dirs(self) -> None:
        """Create both directories. Config dir is 0700 — it holds a refresh token."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # Best effort: not all filesystems honour chmod (e.g. some mounts on WSL).
        with contextlib.suppress(OSError):
            self.config_dir.chmod(0o700)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        e = os.environ if env is None else env

        def _int(key: str, default: int) -> int:
            raw = e.get(key)
            if raw is None or not raw.strip():
                return default
            try:
                value = int(raw)
            except ValueError as exc:
                raise ValueError(f"{key} must be an integer, got {raw!r}") from exc
            if value <= 0:
                raise ValueError(f"{key} must be positive, got {value}")
            return value

        config_dir = Path(e["SAVED_DIGEST_CONFIG_DIR"]).expanduser() if e.get(
            "SAVED_DIGEST_CONFIG_DIR"
        ) else _xdg_config_home() / APP_NAME
        data_dir = Path(e["SAVED_DIGEST_DATA_DIR"]).expanduser() if e.get(
            "SAVED_DIGEST_DATA_DIR"
        ) else _xdg_data_home() / APP_NAME

        return cls(
            config_dir=config_dir,
            data_dir=data_dir,
            youtube_playlist_title=e.get("SAVED_DIGEST_PLAYLIST_TITLE") or "To Watch",
            youtube_playlist_id=e.get("SAVED_DIGEST_PLAYLIST_ID") or None,
            todoist_token=e.get("TODOIST_API_TOKEN") or None,
            todoist_project_name=e.get("SAVED_DIGEST_TODOIST_PROJECT")
            or "Saved from Instagram",
            cookies_from_browser=e.get("SAVED_DIGEST_COOKIES_BROWSER") or None,
            anthropic_api_key=e.get("ANTHROPIC_API_KEY") or None,
            model=e.get("SAVED_DIGEST_MODEL") or "claude-opus-5",
            effort=e.get("SAVED_DIGEST_EFFORT") or "medium",
            max_searches_per_item=_int("SAVED_DIGEST_MAX_SEARCHES", 4),
            digest_to=e.get("SAVED_DIGEST_TO") or None,
            digest_item_limit=_int("SAVED_DIGEST_ITEM_LIMIT", 12),
            stage_limit=_int("SAVED_DIGEST_STAGE_LIMIT", 50),
        )
