"""Sending the digest through the Gmail API.

Uses the same Google OAuth credential as the YouTube read, with the `gmail.send`
scope — so there is one consent screen, one token file, and no SMTP app password
to manage separately.

Sent as `multipart/alternative` with both a plain-text and an HTML part. The text
part is not a courtesy: it is what shows up in notification previews, in clients
with images and styling disabled, and in the `--dry-run` output.
"""

from __future__ import annotations

import base64
import logging
from email.message import EmailMessage
from typing import Any

from saveddigest.config import Config
from saveddigest.deliver.html import render_html, render_text
from saveddigest.deliver.rank import Digest, subject_line
from saveddigest.google_auth import AuthError, build_service

log = logging.getLogger(__name__)


def build_message(
    digest: Digest, *, to: str, subject: str | None = None, sender: str | None = None
) -> EmailMessage:
    """Assemble the multipart message. Pure — no network, no auth."""
    message = EmailMessage()
    message["To"] = to
    if sender:
        message["From"] = sender
    message["Subject"] = subject or subject_line(digest)

    message.set_content(render_text(digest), subtype="plain", charset="utf-8")
    message.add_alternative(render_html(digest), subtype="html", charset="utf-8")
    return message


def encode_for_gmail(message: EmailMessage) -> str:
    """Gmail's `messages.send` takes the raw RFC 822 message, base64url encoded."""
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def send_digest(
    digest: Digest,
    config: Config,
    *,
    to: str | None = None,
    service: Any | None = None,
) -> str:
    """Send the digest and return the Gmail message id.

    Raises `AuthError` with an actionable message when no recipient is
    configured, rather than sending nowhere and reporting success.
    """
    recipient = to or config.digest_to
    if not recipient:
        raise AuthError(
            "No digest recipient. Set SAVED_DIGEST_TO=you@example.com, or pass "
            "--to on the command line."
        )

    message = build_message(digest, to=recipient)
    gmail = service or build_service("gmail", "v1", config)
    sent = (
        gmail.users()
        .messages()
        .send(userId="me", body={"raw": encode_for_gmail(message)})
        .execute()
    )
    message_id = str(sent.get("id", ""))
    log.info("sent digest to %s (message %s)", recipient, message_id)
    return message_id
