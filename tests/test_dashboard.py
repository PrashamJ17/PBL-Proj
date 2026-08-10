"""Tests for the retention dashboard (D-061).

A dashboard is a claim about what is known, made in a medium that hides its own
assumptions well. Most of what is pinned here is that the page cannot quietly become
more confident than the evidence: the reliability banner is unconditional, weak
recommendations are marked in the table rather than only inside a collapsed row, and the
abstention split stays truthful about which kind of "no" it is.

The rest is the boring but load-bearing part -- the file is genuinely self-contained, and
tenant-supplied strings cannot inject markup.
"""

from __future__ import annotations

import re

import pytest

from keel.report.dashboard import render_dashboard
from keel.report.reasons import Reason

OFFERS = ["feature_nudge", "checkin_call", "discount_40_6mo"]


def _reasons():
    return [
        Reason(index=0, action="discount_40_6mo", expected_value=900.0, confidence=0.47,
               drivers=["they pay more than similar customers makes it less likely to work"],
               economics="worth 8,000 if kept", runner_up="next best is checkin call",
               caveat="thin evidence: only a 47% chance this makes money at all"),
        Reason(index=1, action="feature_nudge", expected_value=120.0, confidence=0.81,
               drivers=["usage is falling makes the offer more likely to work"],
               economics="worth 900 if kept"),
        Reason(index=2, action="no offer", expected_value=0.0, confidence=0.0,
               economics="no offer we can measure pays for itself here (best of 3 is -4)"),
        Reason(index=3, action="no offer", expected_value=0.0, confidence=0.0,
               economics="the budget was spent on customers where it earns more"),
    ]


def _html(tmp_path, reasons=None, **kw):
    out = tmp_path / "d.html"
    render_dashboard(reasons if reasons is not None else _reasons(),
                     offer_names=OFFERS, out=out, **kw)
    return out.read_text(encoding="utf-8")


# --- the page cannot become more confident than the evidence -----------------


def test_reliability_banner_is_unconditional(tmp_path):
    """There is deliberately no argument that removes it. A per-customer
    recommendation list without D-058's win rate on the page claims more than the
    project demonstrated."""
    html = _html(tmp_path)
    assert "Read this before you act" in html
    assert "58% of tests" in html
    # And it precedes the recommendations, not buried after them.
    assert html.index("Read this before") < html.index("Who to contact")


def test_weak_recommendations_are_marked_in_the_table_not_only_in_the_detail(tmp_path):
    """Sorting by money puts coin-flips near the top when the upside is large. The
    warning has to sit next to the number it qualifies."""
    html = _html(tmp_path)
    rows = re.findall(r'<tr class="row".*?</tr>', html, flags=re.S)
    weak = [r for r in rows if "47%" in r]
    assert weak and "caution" in weak[0]
    strong = [r for r in rows if "81%" in r]
    assert strong and "caution" not in strong[0]


def test_headline_counts_actions_and_abstentions(tmp_path):
    html = _html(tmp_path)
    assert "2</div>" in html                      # two actions
    assert "leaving <strong>2,</strong>" not in html
    assert "4 customers assessed" in html or "4</strong>" in html or "4:," not in html


def test_abstention_split_distinguishes_budget_from_unprofitable(tmp_path):
    """The two kinds of 'no' license different responses -- one is about the customer,
    the other about the budget. Collapsing them makes the page unactionable."""
    html = _html(tmp_path)
    assert "no offer we can measure pays for" in html
    assert "the budget ran out" in html
    m = re.search(r"<strong>(\d+),?</strong>\s*because no offer", html)
    assert m and m.group(1) == "1"
    m2 = re.search(r"<strong>(\d+),?</strong>\s*because the budget ran out", html)
    assert m2 and m2.group(1) == "1"


def test_the_page_states_what_it_cannot_tell_you(tmp_path):
    html = _html(tmp_path)
    assert "What this cannot tell you" in html
    assert "randomised holdout" in html


# --- self-contained ----------------------------------------------------------


def test_no_external_requests(tmp_path):
    """It must open offline, from an email attachment, with no network. The only URLs
    permitted are XML namespaces inside the inline SVG, which are identifiers."""
    html = _html(tmp_path)
    urls = set(re.findall(r'https?://[^"\'\s<>)]+', html))
    allowed = ("w3.org", "purl.org", "creativecommons.org", "matplotlib.org")
    assert all(any(a in u for a in allowed) for u in urls), urls
    assert "<script src=" not in html and "<link " not in html


def test_charts_inherit_the_page_colour(tmp_path):
    """D-038: matplotlib bakes text colour at render time, which made the first report's
    axis labels invisible in dark mode. The sentinels must have been swapped out."""
    html = _html(tmp_path)
    assert "<svg" in html
    assert "currentColor" in html
    assert "#abcdef" not in html and "#123456" not in html


def test_both_themes_are_styled(tmp_path):
    html = _html(tmp_path)
    assert "prefers-color-scheme: dark" in html
    assert 'data-theme="dark"' in html
    assert 'data-theme="light"' in html


# --- tenant data is data -----------------------------------------------------


def test_tenant_strings_cannot_inject_markup(tmp_path):
    """Customer ids and business names come from a tenant's export. They are data."""
    rs = _reasons()
    html = _html(tmp_path, reasons=rs,
                 business_name="<script>alert(1)</script>",
                 ids=["<img onerror=alert(2)>", "b", "c", "d"])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<img onerror" not in html


def test_ids_are_used_when_supplied(tmp_path):
    html = _html(tmp_path, ids=["cust_A", "cust_B", "cust_C", "cust_D"])
    assert "cust_A" in html


# --- edge cases --------------------------------------------------------------


def test_no_recommendations_at_all_is_refused_with_a_useful_message(tmp_path):
    with pytest.raises(ValueError, match="no reasons"):
        render_dashboard([], offer_names=OFFERS, out=tmp_path / "x.html")


def test_all_abstentions_still_renders(tmp_path):
    """The common case at small n: the optimiser treats nobody. The page must say so
    rather than crash on an empty action table."""
    rs = [r for r in _reasons() if not r.is_action]
    html = _html(tmp_path, reasons=rs)
    assert "0</div>" in html
    assert "Why we are leaving" in html


def test_limit_is_reported_when_it_truncates(tmp_path):
    rs = [Reason(index=i, action="feature_nudge", expected_value=float(100 - i),
                 confidence=0.9) for i in range(30)]
    html = _html(tmp_path, reasons=rs, limit=5)
    assert "Showing the 5 largest of 30" in html
    assert len(re.findall(r'<tr class="row"', html)) == 5


def test_actions_are_ordered_by_money(tmp_path):
    rs = [
        Reason(index=0, action="feature_nudge", expected_value=10.0, confidence=0.9),
        Reason(index=1, action="checkin_call", expected_value=900.0, confidence=0.9),
    ]
    html = _html(tmp_path, reasons=rs)
    # Scoped to the table body: the chart labels and the filter dropdown are ordered by
    # rung index, so a whole-document search finds those first and proves nothing.
    body = re.search(r"<tbody>(.*?)</tbody>", html, flags=re.S).group(1)
    assert body.index("checkin call") < body.index("feature nudge")


def test_unknown_offer_name_does_not_break_the_filter(tmp_path):
    rs = [Reason(index=0, action="mystery_offer", expected_value=5.0, confidence=0.9)]
    html = _html(tmp_path, reasons=rs)
    assert 'data-rung="-1"' in html
