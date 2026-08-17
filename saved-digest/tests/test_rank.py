"""Filtering and ranking — the half of the job that keeps the digest readable."""

from __future__ import annotations

import json
from datetime import date

import pytest

from saveddigest.deliver.rank import (
    Placement,
    build_digest,
    classify,
    has_expired,
    is_unchecked,
    relevance_score,
    subject_line,
    summarise_counts,
)
from saveddigest.store import Item, Liveness, Platform, Verdict

TODAY = date(2026, 8, 17)


def make_item(
    *,
    item_id: int = 1,
    saved_days_ago: int = 30,
    verdict: str | None = Verdict.STILL_VALID.value,
    quality: str = "substantive",
    liveness: Liveness = Liveness.ALIVE,
    expiry: str | None = None,
    tldr: str = "A summary",
    actionable: bool = False,
    unverified_reason: str = "",
) -> Item:
    saved = date(2026, 8, 17).toordinal() - saved_days_ago
    saved_at = date.fromordinal(saved).isoformat() + "T00:00:00+00:00"

    summary = {
        "tldr": tldr,
        "detailed_summary": "Body" if tldr else "",
        "content_quality": quality,
        "actionable_steps": ["do a thing"] if actionable else [],
    }
    verdict_json = None
    if verdict is not None:
        payload = {"verdict": verdict, "sources": []}
        if unverified_reason:
            payload["unverified_reason"] = unverified_reason
        verdict_json = json.dumps(payload)

    return Item(
        id=item_id,
        platform=Platform.YOUTUBE,
        external_id=f"vid{item_id:08d}",
        url=f"https://www.youtube.com/watch?v=vid{item_id:08d}",
        source="youtube_playlist",
        title=f"Item {item_id}",
        saved_at=saved_at,
        liveness=liveness,
        expiry_date=expiry,
        summary_json=json.dumps(summary),
        verdict_json=verdict_json,
    )


# --------------------------------------------------------------------------
# placement
# --------------------------------------------------------------------------
def test_healthy_item_goes_in_the_body():
    placement, reason = classify(make_item(), today=TODAY)
    assert placement is Placement.BODY
    assert reason == ""


def test_dead_item_goes_to_the_footer_not_the_bin():
    """Reported, never silently dropped."""
    placement, reason = classify(make_item(liveness=Liveness.DEAD), today=TODAY)
    assert placement is Placement.GONE
    assert reason == "no longer available"


def test_expired_verdict_goes_to_the_footer():
    placement, _ = classify(make_item(verdict=Verdict.EXPIRED.value), today=TODAY)
    assert placement is Placement.EXPIRED


def test_past_expiry_date_expires_the_item_without_a_verdict():
    placement, reason = classify(
        make_item(verdict=None, expiry="2025-01-01"), today=TODAY
    )
    assert placement is Placement.EXPIRED
    assert "2025-01-01" in reason


def test_future_expiry_date_stays_in_the_body():
    placement, _ = classify(make_item(expiry="2027-01-01"), today=TODAY)
    assert placement is Placement.BODY


def test_expiry_today_is_not_yet_expired():
    """A deadline today is still actionable today."""
    placement, _ = classify(make_item(expiry=TODAY.isoformat()), today=TODAY)
    assert placement is Placement.BODY


def test_item_with_no_readable_summary_is_held_back():
    placement, reason = classify(make_item(tldr=""), today=TODAY)
    assert placement is Placement.NO_CONTENT
    assert "nothing could be read" in reason


def test_dead_beats_expired_in_priority():
    """A deleted video's deadline no longer matters."""
    item = make_item(liveness=Liveness.DEAD, expiry="2020-01-01")
    assert classify(item, today=TODAY)[0] is Placement.GONE


@pytest.mark.parametrize("raw", [None, "", "not a date", "2026-13-45"])
def test_malformed_expiry_never_expires_an_item(raw):
    """A bad date must not push a live item into the expired bucket."""
    assert has_expired(make_item(expiry=raw), today=TODAY) is False


# --------------------------------------------------------------------------
# unchecked labelling
# --------------------------------------------------------------------------
def test_unverified_verdict_is_flagged_unchecked():
    assert is_unchecked(make_item(verdict=Verdict.UNVERIFIED.value))


def test_not_applicable_is_not_unchecked():
    """Evergreen content was correctly judged not to need a check."""
    assert not is_unchecked(make_item(verdict=Verdict.NOT_APPLICABLE.value))


def test_still_valid_is_not_unchecked():
    assert not is_unchecked(make_item(verdict=Verdict.STILL_VALID.value))


def test_unverifiable_liveness_with_no_verdict_is_unchecked():
    item = make_item(verdict=None, liveness=Liveness.UNVERIFIABLE)
    assert is_unchecked(item)


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------
def test_older_saves_outrank_newer_ones():
    old = relevance_score(make_item(saved_days_ago=300), today=TODAY)
    new = relevance_score(make_item(saved_days_ago=3), today=TODAY)
    assert old > new


def test_age_contribution_saturates():
    """A five-year-old save must not permanently monopolise the digest."""
    one_year = relevance_score(make_item(saved_days_ago=365), today=TODAY)
    five_years = relevance_score(make_item(saved_days_ago=365 * 5), today=TODAY)
    assert five_years == pytest.approx(one_year)


def test_a_brand_new_save_still_scores_above_zero():
    assert relevance_score(make_item(saved_days_ago=0), today=TODAY) > 0


def test_still_valid_outranks_superseded_at_equal_age():
    valid = relevance_score(make_item(verdict=Verdict.STILL_VALID.value), today=TODAY)
    superseded = relevance_score(make_item(verdict=Verdict.SUPERSEDED.value), today=TODAY)
    assert valid > superseded


def test_unverified_outranks_superseded():
    """"Not checked" is likelier to still be worth reading than "replaced"."""
    unverified = relevance_score(make_item(verdict=Verdict.UNVERIFIED.value), today=TODAY)
    superseded = relevance_score(make_item(verdict=Verdict.SUPERSEDED.value), today=TODAY)
    assert unverified > superseded


def test_promotional_content_sinks():
    substantive = relevance_score(make_item(quality="substantive"), today=TODAY)
    promo = relevance_score(make_item(quality="promotional"), today=TODAY)
    assert promo < substantive * 0.5


def test_actionable_items_get_a_bonus():
    plain = relevance_score(make_item(actionable=False), today=TODAY)
    actionable = relevance_score(make_item(actionable=True), today=TODAY)
    assert actionable > plain


def test_missing_summary_and_verdict_do_not_crash_scoring():
    bare = Item(
        id=9,
        platform=Platform.INSTAGRAM,
        external_id="x",
        url="https://www.instagram.com/p/x/",
        source="todoist",
    )
    assert relevance_score(bare, today=TODAY) >= 0


# --------------------------------------------------------------------------
# digest assembly
# --------------------------------------------------------------------------
def test_build_digest_partitions_into_body_and_footers():
    items = [
        make_item(item_id=1),
        make_item(item_id=2, liveness=Liveness.DEAD),
        make_item(item_id=3, verdict=Verdict.EXPIRED.value),
        make_item(item_id=4, tldr=""),
    ]
    digest = build_digest(items, today=TODAY)
    assert [e.item.id for e in digest.entries] == [1]
    assert [e.item.id for e in digest.gone] == [2]
    assert [e.item.id for e in digest.expired] == [3]
    assert [e.item.id for e in digest.no_content] == [4]


def test_body_is_sorted_by_score_descending():
    items = [
        make_item(item_id=1, saved_days_ago=5),
        make_item(item_id=2, saved_days_ago=400),
        make_item(item_id=3, saved_days_ago=100),
    ]
    digest = build_digest(items, today=TODAY)
    assert [e.item.id for e in digest.entries] == [2, 3, 1]


def test_limit_caps_the_body_and_reports_the_remainder():
    items = [make_item(item_id=n, saved_days_ago=n * 10) for n in range(1, 8)]
    digest = build_digest(items, limit=3, today=TODAY)
    assert len(digest.entries) == 3
    assert digest.held_back == 4
    assert digest.total_considered == 7


def test_footers_are_never_truncated_by_the_limit():
    """The count of what vanished must not depend on how many entries fitted."""
    items = [make_item(item_id=n) for n in range(1, 6)] + [
        make_item(item_id=n, liveness=Liveness.DEAD) for n in range(10, 14)
    ]
    digest = build_digest(items, limit=1, today=TODAY)
    assert len(digest.entries) == 1
    assert len(digest.gone) == 4


def test_ordering_is_stable_for_identical_scores():
    items = [make_item(item_id=n, saved_days_ago=50) for n in (3, 1, 2)]
    first = [e.item.id for e in build_digest(items, today=TODAY).entries]
    second = [e.item.id for e in build_digest(items, today=TODAY).entries]
    assert first == second == [1, 2, 3]


def test_empty_input_produces_an_empty_digest():
    digest = build_digest([], today=TODAY)
    assert digest.is_empty
    assert digest.total_considered == 0


def test_digest_with_only_footer_items_is_not_empty():
    digest = build_digest([make_item(liveness=Liveness.DEAD)], today=TODAY)
    assert not digest.is_empty
    assert not digest.entries


# --------------------------------------------------------------------------
# counts and subject line
# --------------------------------------------------------------------------
def test_summarise_counts():
    items = [
        make_item(item_id=1),
        make_item(item_id=2, verdict=Verdict.SUPERSEDED.value),
        make_item(item_id=3, verdict=Verdict.UNVERIFIED.value),
        make_item(item_id=4, liveness=Liveness.DEAD),
        make_item(item_id=5, verdict=Verdict.EXPIRED.value),
    ]
    counts = summarise_counts(build_digest(items, today=TODAY))
    assert counts == {
        "shown": 3,
        "held_back": 0,
        "gone": 1,
        "expired": 1,
        "no_content": 0,
        "unchecked": 1,
        "superseded": 1,
    }


def test_subject_line_names_the_contents():
    items = [
        make_item(item_id=1),
        make_item(item_id=2, verdict=Verdict.SUPERSEDED.value),
        make_item(item_id=3, liveness=Liveness.DEAD),
    ]
    subject = subject_line(build_digest(items, today=TODAY))
    assert "2 saved items" in subject
    assert "1 superseded" in subject
    assert "1 gone" in subject


def test_subject_line_singular():
    assert "1 saved item," not in subject_line(build_digest([make_item()], today=TODAY))
    assert "1 saved item" in subject_line(build_digest([make_item()], today=TODAY))


def test_subject_line_when_nothing_to_report():
    assert subject_line(build_digest([], today=TODAY)) == "Saved digest: nothing new"
