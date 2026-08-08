"""Tests for the Churn Autopsy report.

This is the first artifact a real business receives, and the only one they will judge
us on before paying anything. The tests that matter here are about **honesty**: that
estimated figures are labelled as estimates, that caveats reach the page instead of
being quietly dropped, and that the report refuses to make causal claims billing data
cannot support.
"""

from __future__ import annotations

import pandas as pd
import pytest

from keel.core.schema import EVENTS, TICKETS, Dataset, empty
from keel.ingest.subsim_adapter import to_canonical
from keel.report.autopsy import Autopsy, analyse
from keel.report.render import generate, render
from keel.sim import SimConfig, simulate

CFG = SimConfig(n_customers=600, n_months=18, seed=7)


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return to_canonical(simulate(CFG))


@pytest.fixture(scope="module")
def autopsy(dataset) -> Autopsy:
    return analyse(dataset)


# --- the analysis -----------------------------------------------------------


def test_analysis_runs_on_billing_data_alone(dataset):
    """Customers + subscriptions + invoices must be enough. Anything more is a
    barrier most small businesses will not clear."""
    billing_only = Dataset(
        customers=dataset.customers,
        subscriptions=dataset.subscriptions,
        invoices=dataset.invoices,
        events=empty(EVENTS),
        tickets=empty(TICKETS),
    )
    a = analyse(billing_only)
    assert a.n_customers > 0
    assert a.n_failures > 0


def test_headline_numbers_are_plausible(autopsy):
    assert autopsy.n_active <= autopsy.n_customers
    assert autopsy.mrr_active > 0
    assert 0 <= autopsy.monthly_logo_churn <= 1
    assert 0 <= autopsy.monthly_revenue_churn <= 1
    assert 0 <= autopsy.recovery_rate <= 1


def test_retention_curve_starts_at_one_and_declines(autopsy):
    curve = autopsy.retention_curve
    assert curve["retention"].iloc[0] == pytest.approx(1.0)
    assert curve["retention"].is_monotonic_decreasing
    assert (curve["retention"] >= 0).all()


def test_recovery_is_detected(autopsy):
    """If this reads 0%, the adapter is not emitting the retry that succeeded and
    every dunning finding in the report is wrong."""
    assert autopsy.recovery_rate > 0.15


def test_involuntary_churn_is_identified(autopsy):
    """Departures following an unrecovered failure. Distinguishing these matters
    because a retention offer does nothing for an expired card."""
    assert autopsy.n_involuntary > 0
    assert autopsy.n_involuntary <= autopsy.n_churned
    assert 0.10 < autopsy.involuntary_share < 0.60


def test_decline_mix_is_ranked_by_money(autopsy):
    mix = autopsy.decline_mix
    assert not mix.empty
    assert mix["amount"].is_monotonic_decreasing


# --- honesty ----------------------------------------------------------------


def test_findings_are_ranked_by_money(autopsy):
    values = [f.annual_value for f in autopsy.findings()]
    assert values == sorted(values, reverse=True)


def test_benchmark_based_findings_are_labelled_as_estimates(autopsy):
    """The distinction between 'computed from your invoices' and 'extrapolated from
    an industry benchmark' is what separates a diagnostic from a sales document."""
    findings = autopsy.findings()
    benchmark_findings = [f for f in findings if "leaving money on the table" in f.title]
    for f in benchmark_findings:
        assert not f.measured
        assert f.confidence == "estimated from industry benchmarks"


def test_measured_findings_are_labelled_as_measured(autopsy):
    churn_cost = next(f for f in autopsy.findings() if "costs you annually" in f.title)
    assert churn_cost.measured


def test_every_finding_has_an_action(autopsy):
    """A finding without an action is trivia."""
    for f in autopsy.findings():
        assert f.action.strip()
        assert f.detail.strip()


def test_missing_decline_codes_produce_a_visible_caveat(dataset):
    """When we cannot compute something, the report must say so rather than
    silently omitting the section."""
    inv = dataset.invoices.copy()
    inv["failure_code"] = pd.Series([None] * len(inv), dtype="string")
    stripped = Dataset(
        customers=dataset.customers, subscriptions=dataset.subscriptions, invoices=inv,
    )
    a = analyse(stripped)
    assert a.decline_mix.empty
    assert any("decline code" in n.lower() for n in a.notes)


def test_missing_invoices_produce_a_visible_caveat(dataset):
    from keel.core.schema import INVOICES

    a = analyse(Dataset(
        customers=dataset.customers,
        subscriptions=dataset.subscriptions,
        invoices=empty(INVOICES),
    ))
    assert a.n_failures == 0
    assert any("invoice" in n.lower() for n in a.notes)


# --- rendering --------------------------------------------------------------


def test_report_renders_and_is_self_contained(autopsy, tmp_path):
    """No external requests: it must open offline, from an email attachment, on a
    plane. Charts are inline SVG, styles are inline CSS."""
    out = render(autopsy, "Test Co", tmp_path / "report.html")
    html = out.read_text()

    assert "<svg" in html, "charts should be inline SVG"
    assert "<style>" in html
    for tag in ("<script src=", 'href="http', 'src="http'):
        assert tag not in html, f"report reaches out to the network via {tag}"


def test_report_contains_the_headline_number(autopsy, tmp_path):
    out = render(autopsy, "Test Co", tmp_path / "report.html")
    html = out.read_text()
    assert "Churn Autopsy" in html
    assert "Test Co" in html
    assert "costs you per year" in html


def test_report_states_what_it_will_not_do(autopsy, tmp_path):
    """The report must decline to recommend individual targets. Billing data cannot
    support that, and pretending otherwise is exactly the failure this whole project
    exists to argue against."""
    html = render(autopsy, "Test Co", tmp_path / "report.html").read_text()
    assert "does not recommend which" in html
    assert "interventions" in html


def test_chart_text_follows_the_page_theme(autopsy, tmp_path):
    """Chart axis text must inherit the page colour, not be baked at render time.

    The first version wrote matplotlib's default dark text into the SVG, so in dark
    mode every axis label was dark-on-dark and invisible. Sentinel colours are
    swapped for `currentColor` so the charts follow whatever theme is active."""
    html = render(autopsy, "Test Co", tmp_path / "report.html").read_text()

    assert "currentColor" in html, "chart chrome should inherit the page colour"
    assert "#abcdef" not in html and "#123456" not in html, "sentinel colour leaked"


def test_light_is_the_default_theme(autopsy, tmp_path):
    """Follows the system preference, but falls back to light -- this report gets
    printed and forwarded, and an unexpectedly dark page wastes ink."""
    html = render(autopsy, "Test Co", tmp_path / "report.html").read_text()
    before_media_queries = html.split("@media")[0]

    assert "color-scheme: light;" in before_media_queries
    assert "prefers-color-scheme: dark" in html, "should still honour a dark system"
    assert '[data-theme="dark"]' in html, "explicit override must win both ways"
    assert "@media print" in html, "printing should force the light palette"


def test_theme_toggle_needs_no_network(autopsy, tmp_path):
    html = render(autopsy, "Test Co", tmp_path / "report.html").read_text()
    assert 'id="theme"' in html
    assert "<script>" in html and "<script src=" not in html


def test_report_prints_its_caveats(dataset, tmp_path):
    inv = dataset.invoices.copy()
    inv["failure_code"] = pd.Series([None] * len(inv), dtype="string")
    a = analyse(Dataset(
        customers=dataset.customers, subscriptions=dataset.subscriptions, invoices=inv,
    ))
    html = render(a, "Test Co", tmp_path / "report.html").read_text()
    assert "could not determine" in html


def test_generate_is_the_whole_pipeline(dataset, tmp_path):
    out = generate(dataset, "Acme", tmp_path / "r.html")
    assert out.exists() and out.stat().st_size > 10_000


# --- edge cases -------------------------------------------------------------


def test_tiny_business(tmp_path):
    """40 customers is a real prospect, not a degenerate case."""
    ds = to_canonical(simulate(SimConfig(n_customers=40, n_months=12, seed=3)))
    out = generate(ds, "Tiny Co", tmp_path / "tiny.html")
    assert out.exists()


def test_business_with_no_churn_at_all(tmp_path):
    from dataclasses import replace

    cfg = replace(
        CFG,
        hazard=replace(CFG.hazard, intercept=-20.0),
        payments=replace(CFG.payments, monthly_failure_rate=0.0),
    )
    ds = to_canonical(simulate(cfg))
    a = analyse(ds)
    assert a.monthly_logo_churn == 0.0
    assert generate(ds, "Perfect Co", tmp_path / "p.html").exists()


def test_empty_subscriptions_is_refused():
    from keel.core.schema import CUSTOMERS, INVOICES, SUBSCRIPTIONS

    with pytest.raises(ValueError, match="nothing to analyse"):
        analyse(Dataset(
            customers=empty(CUSTOMERS),
            subscriptions=empty(SUBSCRIPTIONS),
            invoices=empty(INVOICES),
        ))
