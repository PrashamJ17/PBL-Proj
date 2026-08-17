#!/usr/bin/env python3
"""Render a digest from fixture data, with no API calls or network access.

Purpose: look at the layout. Tests assert that strings appear; they cannot tell
you that a 47%-confidence item is sitting above a solid one, or that the footer
reads as an afterthought. Run this after touching `deliver/`.

    python3 scripts/sample_digest.py /tmp/digest.html

Every render path is represented: superseded with a replacement link, evergreen,
caption-only Instagram, partly outdated, unverified, expired, and deleted.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

# Allow running from a checkout without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saveddigest.deliver.html import render_html, render_text  # noqa: E402
from saveddigest.deliver.rank import build_digest, subject_line  # noqa: E402
from saveddigest.store import Item, Liveness, Platform, Verdict  # noqa: E402

TODAY = date(2026, 8, 17)


def days_ago(n: int) -> str:
    return date.fromordinal(TODAY.toordinal() - n).isoformat() + "T00:00:00+00:00"


def item(
    item_id: int,
    *,
    platform: Platform = Platform.YOUTUBE,
    title: str,
    author: str,
    saved_days_ago: int,
    summary: dict,
    verdict: dict | None,
    liveness: Liveness = Liveness.ALIVE,
    expiry: str | None = None,
) -> Item:
    # Distinct 11-character ids so the preview does not show the same link on
    # every card (which made an earlier version of this script misleading).
    slug = f"sample{item_id:05d}"
    url = (
        f"https://www.youtube.com/watch?v={slug}"
        if platform is Platform.YOUTUBE
        else f"https://www.instagram.com/reel/{slug}/"
    )
    return Item(
        id=item_id,
        platform=platform,
        external_id=slug,
        url=url,
        source="youtube_playlist" if platform is Platform.YOUTUBE else "todoist",
        title=title,
        author=author,
        saved_at=days_ago(saved_days_ago),
        liveness=liveness,
        expiry_date=expiry,
        summary_json=json.dumps(summary),
        verdict_json=json.dumps(verdict) if verdict else None,
    )


ITEMS = [
    # Superseded: the flagship case for "is this still applicable".
    item(
        1,
        title="Deploying Django to production the right way (2023)",
        author="Pretty Printed",
        saved_days_ago=430,
        summary={
            "tldr": "An end-to-end production Django deploy on a single VPS.",
            "detailed_summary": (
                "The video argues most tutorials stop at `runserver` and leave you to "
                "guess the rest, then walks the whole path: gunicorn behind nginx, a "
                "systemd unit so the app restarts on boot, Postgres on the same box, "
                "and certbot for TLS.\n\n"
                "The gunicorn section is the most concrete part. It recommends "
                "2*cores+1 workers as a starting point, warns that the default 30s "
                "timeout will kill long report requests, and shows how to move those "
                "to a Celery worker instead.\n\n"
                "It closes on the settings split: a base module plus per-environment "
                "overrides, with SECRET_KEY and DATABASE_URL read from the "
                "environment. Django 4.2 is pinned throughout as 'the current LTS'."
            ),
            "key_points": [
                "gunicorn workers: start at 2*cores+1",
                "The 30s default timeout kills long requests; offload to Celery",
                "Split settings per environment, secrets from env vars",
                "Django 4.2 is the current LTS release",
            ],
            "actionable_steps": [
                "Pin Django to the current LTS rather than 4.2",
                "Set an explicit gunicorn --timeout for report endpoints",
            ],
            "tools_mentioned": ["Django 4.2", "gunicorn", "nginx", "systemd", "certbot"],
            "prerequisites": ["Basic Django", "SSH comfort"],
            "topics": ["django", "deployment", "devops"],
            "content_quality": "substantive",
        },
        verdict={
            "verdict": Verdict.SUPERSEDED.value,
            "confidence": "high",
            "what_changed": (
                "Django 4.2 is no longer the current LTS. 5.2 LTS shipped in April "
                "2026, and 4.2's extended support ends April 2026."
            ),
            "superseded_by": "https://docs.djangoproject.com/en/5.2/howto/deployment/",
            "current_state": (
                "The deployment shape in the video is still correct; only the version "
                "pin and a couple of settings names have moved."
            ),
            "checked_claims": [
                {
                    "claim": "Django 4.2 is the current LTS release",
                    "holds": "no",
                    "note": "5.2 LTS is current as of April 2026",
                },
                {
                    "claim": "gunicorn's default timeout is 30 seconds",
                    "holds": "yes",
                    "note": "unchanged",
                },
            ],
            "sources": [
                {
                    "title": "Django download and supported versions",
                    "url": "https://www.djangoproject.com/download/",
                },
                {"title": "endoflife.date - Django", "url": "https://endoflife.date/django"},
            ],
            "searches_used": 3,
        },
    ),
    # Evergreen: skipped Pass B entirely, and says so rather than implying a check.
    item(
        2,
        title="But what is the Central Limit Theorem?",
        author="3Blue1Brown",
        saved_days_ago=260,
        summary={
            "tldr": "A geometric intuition for why averages tend towards a normal distribution.",
            "detailed_summary": (
                "The video builds up from repeatedly rolling dice and plotting the sum, "
                "showing the distribution converging on a bell curve regardless of the "
                "shape of the underlying die.\n\n"
                "It then makes the conditions precise: the samples must be independent, "
                "identically distributed, and have finite variance. The Cauchy "
                "distribution is used as the counterexample where the theorem fails, "
                "which is the part most explanations omit."
            ),
            "key_points": [
                "Convergence needs independence, identical distribution and finite variance",
                "The Cauchy distribution has no finite variance, so the theorem does not apply",
                "Convergence speed depends on the skew of the source distribution",
            ],
            "actionable_steps": [],
            "tools_mentioned": [],
            "prerequisites": ["Basic probability"],
            "topics": ["statistics", "probability", "mathematics"],
            "content_quality": "substantive",
        },
        verdict={
            "verdict": Verdict.NOT_APPLICABLE.value,
            "confidence": "high",
            "what_changed": "",
            "superseded_by": "",
            "current_state": "",
            "checked_claims": [],
            "sources": [],
        },
    ),
    # Instagram, caption-only: the honest weak tier.
    item(
        3,
        platform=Platform.INSTAGRAM,
        title="Great explainer on compound interest",
        author="@financewithsarah",
        saved_days_ago=95,
        summary={
            "tldr": "A worked example of compound interest over 30 years.",
            "detailed_summary": (
                "This is the post's written caption only, not the spoken audio. The "
                "caption gives one worked figure: investing 5,000 a year from age 25 at "
                "an assumed 7% annual return reaches roughly 500,000 by 55, against "
                "150,000 contributed.\n\n"
                "No methodology, fee assumptions or tax treatment appear in the "
                "caption, so the arithmetic cannot be checked from what is here."
            ),
            "key_points": [
                "5,000/year from age 25 at 7% reaches roughly 500,000 by 55",
                "Total contributed over that period is 150,000",
            ],
            "actionable_steps": ["Re-run the numbers with a real fee assumption"],
            "tools_mentioned": [],
            "prerequisites": [],
            "topics": ["personal-finance", "investing"],
            "content_quality": "thin",
        },
        verdict={
            "verdict": Verdict.STILL_VALID.value,
            "confidence": "medium",
            "what_changed": "",
            "superseded_by": "",
            "current_state": (
                "The arithmetic is time-independent. 7% remains a commonly cited "
                "long-run nominal equity assumption, though it is not a guarantee."
            ),
            "checked_claims": [
                {
                    "claim": "7% is a reasonable long-run annual return assumption",
                    "holds": "unclear",
                    "note": "commonly used for nominal equity returns; before fees and inflation",
                }
            ],
            "sources": [
                {"title": "S&P 500 historical returns", "url": "https://www.officialdata.org/us/stocks/s-p-500/"}
            ],
            "searches_used": 2,
        },
    ),
    # Partly outdated: the common real outcome for "best X" content.
    item(
        4,
        title="The 10 best AI coding tools (2024 edition)",
        author="Tech Roundup Weekly",
        saved_days_ago=510,
        summary={
            "tldr": "A ranked roundup of AI coding assistants as of early 2024.",
            "detailed_summary": (
                "A ten-item ranking with pricing for each. The top three are presented "
                "as clear leaders, with free tiers highlighted, and the video spends "
                "most of its time on autocomplete quality rather than agentic use.\n\n"
                "Pricing is quoted throughout in monthly per-seat terms, and several "
                "tools are described as being in a free beta."
            ),
            "key_points": [
                "Ranked on autocomplete quality, not agentic capability",
                "Several tools listed as free beta at time of recording",
                "Per-seat monthly pricing quoted for each entry",
            ],
            "actionable_steps": ["Re-check current pricing before choosing"],
            "tools_mentioned": ["GitHub Copilot", "Tabnine", "Codeium"],
            "prerequisites": [],
            "topics": ["ai", "developer-tools"],
            "content_quality": "promotional",
        },
        verdict={
            "verdict": Verdict.PARTLY_OUTDATED.value,
            "confidence": "medium",
            "what_changed": (
                "The category moved from autocomplete to agentic coding after this was "
                "recorded, several free betas became paid, and the ranking no longer "
                "reflects what is available."
            ),
            "superseded_by": "",
            "current_state": (
                "The evaluation criteria are the useful part and still apply; the "
                "specific ranking and every price should be treated as stale."
            ),
            "checked_claims": [
                {
                    "claim": "Several listed tools are free in beta",
                    "holds": "no",
                    "note": "the betas referenced have since moved to paid tiers",
                }
            ],
            "sources": [
                {"title": "GitHub Copilot plans", "url": "https://github.com/features/copilot/plans"}
            ],
            "searches_used": 4,
        },
    ),
    # Unverified: the search genuinely failed. Must not read as "fine".
    item(
        5,
        title="Is this obscure indie build tool still maintained?",
        author="Small Channel",
        saved_days_ago=300,
        summary={
            "tldr": "A walkthrough of a small build tool's config format.",
            "detailed_summary": (
                "A short screencast configuring a niche build tool: the manifest "
                "format, how tasks are declared, and how caching is keyed. The author "
                "notes the project is maintained by one person."
            ),
            "key_points": ["Single-maintainer project", "Cache keyed on manifest hash"],
            "actionable_steps": [],
            "tools_mentioned": ["obscure-build 0.4"],
            "prerequisites": [],
            "topics": ["build-tools"],
            "content_quality": "substantive",
        },
        verdict={
            "verdict": Verdict.UNVERIFIED.value,
            "confidence": "low",
            "what_changed": "",
            "superseded_by": "",
            "current_state": "",
            "checked_claims": [],
            "sources": [],
            "unverified_reason": "web search failed: too_many_requests",
        },
    ),
    # Expired: footer, one line.
    item(
        6,
        title="PyCon 2025 call for proposals - how to write a good one",
        author="PyCon",
        saved_days_ago=380,
        expiry="2024-12-15",
        summary={
            "tldr": "Advice for writing a conference proposal.",
            "detailed_summary": "Guidance on scoping a talk and writing an abstract.",
            "key_points": ["Scope narrowly"],
            "actionable_steps": [],
            "tools_mentioned": [],
            "prerequisites": [],
            "topics": ["conferences"],
            "content_quality": "substantive",
        },
        verdict=None,
    ),
    # Deleted: footer, one line.
    item(
        7,
        title="Advanced caching patterns explained",
        author="Unknown",
        saved_days_ago=600,
        liveness=Liveness.DEAD,
        summary={
            "tldr": "",
            "detailed_summary": "",
            "key_points": [],
            "actionable_steps": [],
            "tools_mentioned": [],
            "prerequisites": [],
            "topics": [],
            "content_quality": "unclear",
        },
        verdict=None,
    ),
]


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("digest-sample.html")
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    digest = build_digest(ITEMS, limit=12, today=TODAY, generated_at=generated)

    out.write_text(render_html(digest), encoding="utf-8")
    text_path = out.with_suffix(".txt")
    text_path.write_text(render_text(digest), encoding="utf-8")

    print(f"subject: {subject_line(digest)}")
    print(f"html:    {out}  ({out.stat().st_size:,} bytes)")
    print(f"text:    {text_path}")
    print(
        f"body={len(digest.entries)} gone={len(digest.gone)} "
        f"expired={len(digest.expired)} unreadable={len(digest.no_content)} "
        f"held_back={digest.held_back}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
