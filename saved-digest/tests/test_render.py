"""Digest rendering: content fidelity, honest labelling, and escaping.

Escaping matters more than usual here. Titles come from YouTube and every summary
field comes from a language model, so all of it is untrusted markup being pasted
into an HTML email.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from saveddigest.deliver.html import _age_phrase, render_html, render_text
from saveddigest.deliver.rank import build_digest
from saveddigest.store import Item, Liveness, Platform, Verdict

TODAY = date(2026, 8, 17)


def make_item(
    *,
    item_id: int = 1,
    title: str = "Deploying Django in 2023",
    saved_days_ago: int = 400,
    verdict: dict | None = None,
    summary: dict | None = None,
    liveness: Liveness = Liveness.ALIVE,
    expiry: str | None = None,
) -> Item:
    saved_at = (
        date.fromordinal(TODAY.toordinal() - saved_days_ago).isoformat() + "T00:00:00+00:00"
    )
    base_summary = {
        "tldr": "A walkthrough of deploying Django with gunicorn and nginx.",
        "detailed_summary": (
            "The video starts by arguing that most deployment guides skip the boring "
            "parts.\n\nIt then walks through gunicorn worker counts, suggesting "
            "2*cores+1, and shows an nginx config for static files."
        ),
        "key_points": ["Use gunicorn", "Django 4.2 was the LTS at the time"],
        "actionable_steps": ["Pin Django to the current LTS"],
        "tools_mentioned": ["Django 4.2", "gunicorn", "nginx"],
        "content_quality": "substantive",
    }
    if summary is not None:
        base_summary.update(summary)

    return Item(
        id=item_id,
        platform=Platform.YOUTUBE,
        external_id=f"vid{item_id:08d}",
        url=f"https://www.youtube.com/watch?v=vid{item_id:08d}",
        source="youtube_playlist",
        title=title,
        author="Some Channel",
        saved_at=saved_at,
        liveness=liveness,
        expiry_date=expiry,
        summary_json=json.dumps(base_summary),
        verdict_json=json.dumps(verdict) if verdict else None,
    )


SUPERSEDED = {
    "verdict": Verdict.SUPERSEDED.value,
    "confidence": "high",
    "what_changed": "Django 4.2 is no longer the newest LTS release.",
    "superseded_by": "https://docs.djangoproject.com/en/5.2/",
    "current_state": "Django 5.2 is current.",
    "checked_claims": [
        {
            "claim": "Django 4.2 is the current LTS",
            "holds": "no",
            "note": "5.2 shipped since",
        }
    ],
    "sources": [
        {"title": "Django documentation", "url": "https://docs.djangoproject.com/"}
    ],
}

UNVERIFIED = {
    "verdict": Verdict.UNVERIFIED.value,
    "confidence": "low",
    "what_changed": "",
    "superseded_by": "",
    "current_state": "",
    "checked_claims": [],
    "sources": [],
    "unverified_reason": "web search failed: too_many_requests",
}


def digest_of(items, **kw):
    return build_digest(items, today=TODAY, generated_at="2026-08-17 09:00 UTC", **kw)


# --------------------------------------------------------------------------
# the detail the user asked for
# --------------------------------------------------------------------------
def test_html_includes_the_detailed_summary_paragraphs():
    html = render_html(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "most deployment guides skip the boring" in html
    assert "2*cores+1" in html
    # Two source paragraphs become two <p> blocks.
    assert html.count("nginx config for static files") == 1


def test_html_includes_key_points_and_actions():
    html = render_html(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "Key points" in html
    assert "Use gunicorn" in html
    assert "What you could do" in html
    assert "Pin Django to the current LTS" in html


def test_html_includes_the_verdict_and_what_changed():
    html = render_html(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "Superseded" in html
    assert "no longer the newest LTS" in html


def test_html_links_to_the_current_version():
    html = render_html(digest_of([make_item(verdict=SUPERSEDED)]))
    assert 'href="https://docs.djangoproject.com/en/5.2/"' in html


def test_html_shows_citations_so_the_verdict_can_be_checked():
    html = render_html(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "Sources" in html
    assert 'href="https://docs.djangoproject.com/"' in html


def test_html_shows_the_claims_that_were_checked():
    html = render_html(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "Claims checked" in html
    assert "Django 4.2 is the current LTS" in html
    assert "5.2 shipped since" in html


def test_html_shows_how_long_it_has_been_waiting():
    html = render_html(digest_of([make_item(saved_days_ago=400, verdict=SUPERSEDED)]))
    assert "over a year ago" in html


# --------------------------------------------------------------------------
# honest labelling of unchecked items
# --------------------------------------------------------------------------
def test_unverified_item_is_labelled_not_checked():
    """The central honesty requirement in the render layer."""
    html = render_html(digest_of([make_item(verdict=UNVERIFIED)]))
    assert "Not checked" in html
    assert "Not fact-checked" in html
    assert "too_many_requests" in html
    assert "unverified" in html.lower()


def test_unverified_item_does_not_claim_a_verdict():
    html = render_html(digest_of([make_item(verdict=UNVERIFIED)]))
    assert "Still valid" not in html
    assert "What changed" not in html


def test_evergreen_item_gets_no_change_section():
    evergreen = {
        "verdict": Verdict.NOT_APPLICABLE.value,
        "confidence": "high",
        "what_changed": "",
        "superseded_by": "",
        "current_state": "",
        "checked_claims": [],
        "sources": [],
    }
    html = render_html(digest_of([make_item(verdict=evergreen)]))
    assert "Evergreen" in html
    assert "What changed" not in html
    assert "Not fact-checked" not in html


def test_thin_and_promotional_items_are_flagged_inline():
    html = render_html(
        digest_of([make_item(summary={"content_quality": "promotional"}, verdict=SUPERSEDED)])
    )
    assert "flagged promotional" in html


# --------------------------------------------------------------------------
# footers
# --------------------------------------------------------------------------
def test_dead_items_appear_in_a_footer_not_as_cards():
    html = render_html(
        digest_of(
            [
                make_item(item_id=1, verdict=SUPERSEDED),
                make_item(item_id=2, title="Gone forever", liveness=Liveness.DEAD),
            ]
        )
    )
    assert "No longer available (1)" in html
    assert "Gone forever" in html
    # The dead item must not get a full summary block.
    assert html.count("Key points") == 1


def test_expired_items_get_a_footer_with_a_reason():
    html = render_html(
        digest_of([make_item(title="CFP closes soon", expiry="2024-01-01", verdict=None)])
    )
    assert "Expired (1)" in html
    assert "2024-01-01" in html


def test_unreadable_items_are_reported_not_hidden():
    html = render_html(
        digest_of([make_item(summary={"tldr": "", "detailed_summary": ""})])
    )
    assert "Nothing readable (1)" in html


def test_held_back_count_is_disclosed():
    items = [make_item(item_id=n, verdict=SUPERSEDED) for n in range(1, 8)]
    html = render_html(digest_of(items, limit=2))
    assert "waiting for next time" in html


def test_empty_digest_renders_a_friendly_page():
    html = render_html(digest_of([]))
    assert "Nothing to resurface" in html


def test_generation_note_carries_the_reliability_caveat():
    html = render_html(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "language model with web search" in html
    assert "check anything you plan to act on" in html


# --------------------------------------------------------------------------
# escaping — untrusted titles and model output
# --------------------------------------------------------------------------
def test_script_in_a_title_is_escaped():
    html = render_html(
        digest_of([make_item(title="<script>alert('xss')</script>", verdict=SUPERSEDED)])
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_html_in_model_output_is_escaped():
    html = render_html(
        digest_of(
            [
                make_item(
                    verdict=SUPERSEDED,
                    summary={
                        "tldr": "<img src=x onerror=alert(1)>",
                        "detailed_summary": "<b>not bold</b>",
                        "key_points": ["<i>italic?</i>"],
                    },
                )
            ]
        )
    )
    assert "<img src=x" not in html
    assert "<b>not bold</b>" not in html
    assert "&lt;b&gt;not bold&lt;/b&gt;" in html
    assert "&lt;i&gt;italic?&lt;/i&gt;" in html


def test_quotes_in_a_title_cannot_break_out_of_the_attribute():
    html = render_html(
        digest_of([make_item(title='" onmouseover="alert(1)', verdict=SUPERSEDED)])
    )
    assert 'onmouseover="alert(1)"' not in html
    assert "&quot;" in html


def test_ampersand_separator_is_not_double_escaped():
    """The metadata line uses a middot entity; it must not become &amp;middot;."""
    html = render_html(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "&amp;middot;" not in html
    assert "&middot;" in html


def test_no_external_resources_are_referenced():
    """A self-contained email: no tracking pixels, no CDN fonts."""
    html = render_html(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "<img" not in html
    assert "<link" not in html
    assert "<script" not in html.lower()
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    # Only real content links to YouTube/docs, no asset loads.
    assert all("youtube.com" in u or "djangoproject.com" in u for u in external)


# --------------------------------------------------------------------------
# plain text alternative
# --------------------------------------------------------------------------
def test_text_render_includes_summary_and_sources():
    text = render_text(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "[Superseded]" in text
    assert "most deployment guides skip the boring" in text
    assert "Current version: https://docs.djangoproject.com/en/5.2/" in text
    assert "src: https://docs.djangoproject.com/" in text


def test_text_render_flags_unverified():
    text = render_text(digest_of([make_item(verdict=UNVERIFIED)]))
    assert "! NOT fact-checked" in text
    assert "too_many_requests" in text


def test_text_render_lists_footers():
    text = render_text(
        digest_of([make_item(title="Gone", liveness=Liveness.DEAD)])
    )
    assert "NO LONGER AVAILABLE (1)" in text
    assert "Gone" in text


def test_text_render_of_empty_digest():
    assert "Nothing to resurface" in render_text(digest_of([]))


def test_text_render_contains_no_html_tags():
    text = render_text(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "<div" not in text
    assert "<p " not in text


# --------------------------------------------------------------------------
# age phrasing
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (0, "saved today"),
        (1, "saved yesterday"),
        (5, "saved 5 days ago"),
        (29, "saved 29 days ago"),
        (60, "saved 2 months ago"),
        (200, "saved 7 months ago"),
        (400, "saved over a year ago"),
        (900, "saved over 2 years ago"),
    ],
)
def test_age_phrase(days, expected):
    assert _age_phrase(days) == expected


def test_age_phrase_handles_negative_days():
    assert _age_phrase(-3) == "saved today"


# --------------------------------------------------------------------------
# the copy must describe the ordering that actually happens
# --------------------------------------------------------------------------
def test_digest_does_not_claim_to_be_ordered_purely_by_age():
    """Regression: the intro line once said "Oldest saves first", which was untrue.

    Ranking weights verdict and quality as well as age, so a newer still-valid
    item can outrank an older superseded one. The copy must not overclaim.
    """
    items = [
        make_item(item_id=1, saved_days_ago=430, verdict=SUPERSEDED),
        make_item(item_id=2, saved_days_ago=260, verdict={
            "verdict": Verdict.NOT_APPLICABLE.value, "confidence": "high",
            "what_changed": "", "superseded_by": "", "current_state": "",
            "checked_claims": [], "sources": [],
        }),
    ]
    digest = digest_of(items)
    html = render_html(digest)
    text = render_text(digest)

    # The newer evergreen item genuinely sorts first here.
    assert [e.item.id for e in digest.entries] == [2, 1]
    for rendered in (html, text):
        assert "Oldest saves first" not in rendered
        assert "Oldest first" not in rendered
        assert "Longest-waiting first" in rendered


def test_text_render_separates_paragraphs_with_blank_lines():
    text = render_text(digest_of([make_item(verdict=SUPERSEDED)]))
    assert "\n\n   It then walks" in text or "\n\n   " in text
