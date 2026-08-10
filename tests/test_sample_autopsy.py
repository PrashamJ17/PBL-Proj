"""Tests for the sample Churn Autopsy used in outreach.

This artefact goes to strangers, which changes what matters about it. The tests are
almost entirely about it not lying: that it says it is simulated, that rescaling the
currency moved only the currency, and that its caveats describe real limitations rather
than decorative ones.
"""

from __future__ import annotations

import pytest

from keel.experiments.sample_autopsy import (
    N_MONTHS,
    SAMPLE_NOTES,
    SEED,
    TARGET_MEDIAN_MRR,
    _rescale_money,
    build,
)
from keel.ingest.subsim_adapter import to_canonical
from keel.report.autopsy import analyse
from keel.report.render import render
from keel.sim import SimConfig, simulate


@pytest.fixture(scope="module")
def html(tmp_path_factory):
    return build(out=tmp_path_factory.mktemp("s") / "sample.html").read_text(encoding="utf-8")


# --- it must never pass for a real business ---------------------------------


def test_the_sample_says_it_is_simulated_before_anything_else(html):
    """A prospect who mistakes a demo for a real client's report has learned that we
    circulate client data, which is the fear the engagement exists to overcome."""
    assert "This is a sample, not a real business" in html
    assert html.index("not a real business") < html.index("What we found")
    assert "simulated" in html


def test_demo_marking_is_structural_not_a_naming_convention():
    """`demo` is a parameter so a sample cannot be produced without the banner. If it
    ever becomes possible to render one silently, this fails."""
    data = to_canonical(simulate(SimConfig(n_customers=300, n_months=12, seed=1)), seed=1)
    plain = render(analyse(data), business_name="X", out=None)
    assert "not a real business" not in plain.read_text(encoding="utf-8")
    plain.unlink(missing_ok=True)


def test_title_and_heading_both_carry_the_sample_marker(html):
    assert "Churn Autopsy (sample)" in html      # browser tab / forwarded link
    assert "Churn Autopsy &mdash; sample" in html or "Churn Autopsy — sample" in html


# --- rescaling moved money and nothing else ---------------------------------


def test_rescaling_leaves_every_rate_identical():
    """The justification for rescaling at all: the hazard uses price *relative to the
    median*, so a constant multiplier cannot move churn. If that ever stops being true,
    the sample is a distorted business and this must fail."""
    sim = simulate(SimConfig(n_customers=500, n_months=N_MONTHS, seed=SEED))
    raw = analyse(to_canonical(sim, seed=SEED))
    scaled = analyse(_rescale_money(to_canonical(sim, seed=SEED), TARGET_MEDIAN_MRR))

    assert scaled.monthly_logo_churn == pytest.approx(raw.monthly_logo_churn, abs=1e-12)
    assert scaled.monthly_revenue_churn == pytest.approx(raw.monthly_revenue_churn, abs=1e-12)
    assert scaled.involuntary_share == pytest.approx(raw.involuntary_share, abs=1e-12)
    assert scaled.recovery_rate == pytest.approx(raw.recovery_rate, abs=1e-12)
    assert scaled.n_churned == raw.n_churned
    assert scaled.n_failures == raw.n_failures


def test_rescaling_puts_the_price_where_it_was_asked_to():
    sim = simulate(SimConfig(n_customers=500, n_months=N_MONTHS, seed=SEED))
    data = _rescale_money(to_canonical(sim, seed=SEED), TARGET_MEDIAN_MRR)
    assert float(data.subscriptions["mrr"].median()) == pytest.approx(TARGET_MEDIAN_MRR)


def test_invoices_are_rescaled_with_subscriptions():
    """Scaling MRR without scaling invoices would make failed-payment amounts
    inconsistent with revenue — a demo that contradicts itself."""
    sim = simulate(SimConfig(n_customers=400, n_months=N_MONTHS, seed=SEED))
    raw = to_canonical(sim, seed=SEED)
    before = float(raw.invoices["amount"].median())
    after = float(_rescale_money(to_canonical(sim, seed=SEED),
                                 TARGET_MEDIAN_MRR).invoices["amount"].median())
    assert after > before * 10


def test_a_degenerate_price_column_is_left_alone():
    sim = simulate(SimConfig(n_customers=200, n_months=12, seed=2))
    data = to_canonical(sim, seed=2)
    data.subscriptions["mrr"] = 0.0
    assert float(_rescale_money(data, 2_400.0).subscriptions["mrr"].max()) == 0.0


# --- the money reads like a real business -----------------------------------


def test_the_sample_business_is_plausibly_priced():
    """The defect that prompted the rescale: unscaled, the sample described 900
    customers paying about Rs 15 a month and losing Rs 5,752 a year, which a founder
    dismisses on sight."""
    sim = simulate(SimConfig(n_customers=900, n_months=N_MONTHS, seed=SEED))
    a = analyse(_rescale_money(to_canonical(sim, seed=SEED), TARGET_MEDIAN_MRR))
    per_customer = a.mrr_active / max(a.n_active, 1)
    assert 500 < per_customer < 20_000
    assert a.annual_churn_cost > 50_000


# --- the caveats are real ---------------------------------------------------


def test_the_sample_states_what_it_cannot_show(html):
    """Simulated data is complete, so without explicit notes this section would be
    absent — and it is one of the reasons to trust the report."""
    assert "What we could not determine" in html
    assert "single cohort" in html


def test_the_caveats_describe_actual_limitations():
    """Both notes must be true of the data, not decorative — a false modesty claim is
    still a false claim, and this artefact goes to strangers.

    An earlier draft asserted the sample had no usage or ticket data. The adapter emits
    43,000 events and a full ticket table, so the note was simply untrue and this test
    caught it before it reached a prospect. What *is* true is that the Autopsy computes
    from billing alone and ignores those tables entirely.
    """
    sim = simulate(SimConfig(n_customers=300, n_months=12, seed=3))
    data = to_canonical(sim, seed=3)
    assert data.customers["created_at"].nunique() == 1, "cohort caveat must be true"

    # The billing-only caveat, asserted by construction: stripping usage and support
    # data must change nothing on the page.
    from keel.core.schema import EVENTS, TICKETS, empty

    with_usage = analyse(data)
    stripped = to_canonical(sim, seed=3)
    stripped.events, stripped.tickets = empty(EVENTS), empty(TICKETS)
    without = analyse(stripped)
    assert without.monthly_logo_churn == pytest.approx(with_usage.monthly_logo_churn)
    assert without.annual_churn_cost == pytest.approx(with_usage.annual_churn_cost)
    assert without.n_failures == with_usage.n_failures
    assert len(SAMPLE_NOTES) == 2


# --- self-contained, like the report it stands in for -----------------------


def test_the_sample_is_emailable(html):
    assert "<script src=" not in html and "<link " not in html
    assert "currentColor" in html          # charts follow the theme (D-038)
    assert "#abcdef" not in html
