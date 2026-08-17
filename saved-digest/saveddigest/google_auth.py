"""One Google OAuth credential, shared by YouTube reads and Gmail sends.

Two scopes, one consent screen. Keeping this in a single module means the token
file has a single owner, and adding a scope later forces a deliberate re-consent
rather than a confusing partial-permission failure at run time.

The installed-app flow needs a browser once. After that the refresh token in
`config.google_token_path` is enough, which is what makes an unattended weekly
cron job possible.
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any

from saveddigest.config import GOOGLE_SCOPES, Config

log = logging.getLogger(__name__)


class AuthError(RuntimeError):
    """Raised with an actionable message rather than a library traceback."""


def _require_google_libs() -> tuple[Any, Any, Any]:
    """Import the Google libraries lazily, with a useful error if absent."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise AuthError(
            "Google client libraries are missing. Install them with:\n"
            "    pip install google-api-python-client google-auth-oauthlib"
        ) from exc
    return Credentials, InstalledAppFlow, Request


def load_credentials(config: Config, *, allow_interactive: bool = False) -> Any:
    """Return usable credentials, refreshing or re-consenting as needed.

    `allow_interactive=False` (the default, and what cron uses) means a missing or
    unrefreshable token is an error telling the user to run `init-auth`, rather
    than a process that blocks forever waiting on a browser that nobody will open.
    """
    Credentials, InstalledAppFlow, Request = _require_google_libs()

    token_path = config.google_token_path
    creds = None

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(token_path), list(GOOGLE_SCOPES)
            )
        except (ValueError, json.JSONDecodeError) as exc:
            raise AuthError(
                f"{token_path} is not a valid credentials file ({exc}). "
                "Delete it and re-run `saved-digest init-auth`."
            ) from exc

    if creds and creds.valid:
        return creds

    # An expired access token with a refresh token is the normal steady state.
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            if not allow_interactive:
                raise AuthError(
                    f"Could not refresh the Google token ({exc}). Google expires "
                    "refresh tokens for apps in 'testing' publishing status after "
                    "7 days. Re-run `saved-digest init-auth`."
                ) from exc
            log.warning("refresh failed (%s); falling back to a new consent", exc)
            creds = None
        else:
            _write_token(token_path, creds)
            return creds

    if not allow_interactive:
        raise AuthError(
            "No usable Google credentials. Run `saved-digest init-auth` once to "
            "grant access (it opens a browser)."
        )

    if not config.google_client_secret_path.exists():
        raise AuthError(
            f"Missing OAuth client secrets at {config.google_client_secret_path}.\n"
            "Create a Desktop-app OAuth client in the Google Cloud console, enable "
            "the YouTube Data API v3 and the Gmail API, download the JSON, and save "
            "it to that path. See README.md -> Google setup."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(config.google_client_secret_path), list(GOOGLE_SCOPES)
    )
    # port=0 lets the OS pick a free loopback port for the redirect.
    creds = flow.run_local_server(port=0, prompt="consent")
    _write_token(token_path, creds)
    return creds


def _write_token(path: Path, creds: Any) -> None:
    """Persist the token 0600 — it contains a long-lived refresh token."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename so an interrupted write cannot leave a truncated token.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(creds.to_json(), encoding="utf-8")
    with contextlib.suppress(OSError):  # pragma: no cover - unusual filesystems
        tmp.chmod(0o600)
    tmp.replace(path)
    log.info("wrote Google token to %s", path)


def build_service(name: str, version: str, config: Config) -> Any:
    """Construct a discovery-based Google API client."""
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover
        raise AuthError(
            "google-api-python-client is missing. Install it with:\n"
            "    pip install google-api-python-client"
        ) from exc
    creds = load_credentials(config)
    # cache_discovery=False avoids a noisy warning and a stale on-disk cache.
    return build(name, version, credentials=creds, cache_discovery=False)
