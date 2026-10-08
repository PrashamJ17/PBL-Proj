"""A quantity that was not measured is reported as not measured, never as zero (D-071).

Given customers and subscriptions but no invoices, the Churn Autopsy once printed "0%
failed payments recovered" and "0% churn that is involuntary", and then advised "fix the
involuntary share first". None of the three was a finding. The zeros meant "we did not
look", and the advice followed from nothing.

The rule these tests pin: a share that cannot be computed is None. A caller that formats
it as a percentage fails; the page says "not measured"; and the advice is given only
when the data supports it.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest
from test_preflight_cli import _stripe
from test_report_currency import page_text

from retainiq.core.schema import INVOICES, Dataset, empty
from retainiq.ingest.csv_ingest import load
from retainiq.ingest.preflight import preflight
from retainiq.ingest.subsim_adapter import to_canonical
from retainiq.report.autopsy import MATERIAL_INVOLUNTARY_SHARE, analyse
from retainiq.report.render import generate
from retainiq.sim import SimConfig, simulate

CFG = SimConfig(n_customers=600, n_months=18, seed=7)

FIX_FIRST = "Fix the involuntary share first"


@pytest.fixture(scope="module")
def with_invoices() -> Dataset:
    return to_canonical(simulate(CFG))


@pytest.fixture(scope="module")
def without_invoices(with_invoices) -> Dataset:
    return Dataset(customers=with_invoices.customers,
                   subscriptions=with_invoices.subscriptions, invoices=empty(INVOICES))


@pytest.fixture(scope="module")
def no_failed_payments() -> Dataset:
    """Invoices supplied, customers leave, and no payment ever fails."""
    cfg = replace(CFG, payments=replace(CFG.payments, monthly_failure_rate=0.0))
    return to_canonical(simulate(cfg))


@pytest.fixture(scope="module")
def no_departures() -> Dataset:
    cfg = replace(CFG, hazard=replace(CFG.hazard, intercept=-20.0),
                  payments=replace(CFG.payments, monthly_failure_rate=0.0))
    return to_canonical(simulate(cfg))


def actions(autopsy) -> str:
    return " ".join(f.action for f in autopsy.findings())


# --- the analysis -----------------------------------------------------------


def test_without_invoices_nothing_about_payments_is_measured(without_invoices):
    a = analyse(without_invoices)
    assert not a.invoices_supplied
    assert a.n_involuntary is None
    assert a.involuntary_share is None
    assert a.recovery_rate is None


def test_not_measured_cannot_be_printed_as_a_percentage(without_invoices):
    """The point of None over 0.0: forgetting the case is an error, not a wrong number."""
    a = analyse(without_invoices)
    with pytest.raises(TypeError):
        f"{a.involuntary_share:.0%}"
    with pytest.raises(TypeError):
        f"{a.recovery_rate:.0%}"


def test_with_invoices_the_same_business_is_measured(with_invoices):
    a = analyse(with_invoices)
    assert a.invoices_supplied
    assert a.n_involuntary > 0
    assert 0 < a.involuntary_share < 1
    assert 0 < a.recovery_rate < 1


def test_a_measured_zero_stays_a_zero(no_failed_payments):
    """Invoices were supplied and nothing failed: 0% involuntary is then a finding."""
    a = analyse(no_failed_payments)
    assert a.n_churned > 0 and a.invoices_supplied
    assert a.n_involuntary == 0
    assert a.involuntary_share == 0.0


def test_recovery_has_no_rate_when_nothing_failed(no_failed_payments):
    """ "You recover 0% of failed payments" is false of a business that had none."""
    a = analyse(no_failed_payments)
    assert a.n_failures == 0
    assert a.recovery_rate is None


def test_no_departures_means_no_share_of_them(no_departures):
    a = analyse(no_departures)
    assert a.n_churned == 0 and a.invoices_supplied
    assert a.involuntary_share is None


def test_failed_invoices_of_zero_value_do_not_divide_by_zero(with_invoices):
    inv = with_invoices.invoices.copy()
    inv.loc[inv["status"] == "failed", "amount"] = 0.0
    a = analyse(Dataset(customers=with_invoices.customers,
                        subscriptions=with_invoices.subscriptions, invoices=inv))
    assert a.n_failures > 0
    assert a.recovery_rate is None
    assert a.findings(), "the report must still be producible"


# --- the advice -------------------------------------------------------------


def test_without_invoices_the_report_does_not_advise_fixing_involuntary_churn(
    without_invoices,
):
    """The defect: advice that followed from a zero meaning "not measured"."""
    said = actions(analyse(without_invoices))
    assert FIX_FIRST not in said
    assert "Send your invoices" in said
    assert "not measured" in said


def test_the_advice_is_given_when_involuntary_churn_is_measured_and_material(with_invoices):
    a = analyse(with_invoices)
    assert a.involuntary_share > MATERIAL_INVOLUNTARY_SHARE
    assert FIX_FIRST in actions(a)


def test_a_small_measured_share_is_not_called_the_place_to_start(no_failed_payments):
    said = actions(analyse(no_failed_payments))
    assert FIX_FIRST not in said
    assert "mostly customers deciding to leave" in said


def test_no_departures_gets_no_advice_about_splitting_them(no_departures):
    said = actions(analyse(no_departures))
    assert FIX_FIRST not in said
    assert "No departures" in said


def test_a_benchmark_quoted_in_the_advice_is_labelled_as_one(without_invoices):
    """Every number is from their data or labelled as an estimate (the Autopsy's rule)."""
    said = actions(analyse(without_invoices))
    assert "20-40%" in said and "industry benchmarks" in said


# --- the page ---------------------------------------------------------------


def test_the_page_says_not_measured_and_never_zero(without_invoices, tmp_path):
    text = page_text(generate(without_invoices, "No Invoices Co", tmp_path / "r.html"))
    assert text.count("not measured failed payments recovered") == 1
    assert text.count("not measured churn that is involuntary") == 1
    assert "0% failed payments recovered" not in text
    assert "0% churn that is involuntary" not in text
    assert "which is not the same as zero" in text


def test_the_page_shows_percentages_when_they_were_measured(with_invoices, tmp_path):
    text = page_text(generate(with_invoices, "Invoices Co", tmp_path / "r.html"))
    assert re.search(r"\d+% failed payments recovered", text)
    assert re.search(r"\d+% churn that is involuntary", text)
    assert "not measured failed" not in text


def test_the_page_distinguishes_none_failed_from_not_measured(no_failed_payments, tmp_path):
    text = page_text(generate(no_failed_payments, "Clean Co", tmp_path / "r.html"))
    assert "none failed payments in the invoices you sent" in text
    assert "0% churn that is involuntary" in text, "measured, so the zero is real"
    assert "not measured" not in text.split("What we found")[0]


def test_the_page_says_no_departures_instead_of_zero_percent(no_departures, tmp_path):
    text = page_text(generate(no_departures, "Perfect Co", tmp_path / "r.html"))
    assert "no departures churn that is involuntary" in text
    assert "0% churn that is involuntary" not in text


# --- preflight --------------------------------------------------------------


def test_preflight_says_what_will_not_be_measured_without_changing_the_verdict():
    """Two files is the normal engagement. It must be told, and must not be alarmed."""
    report = preflight(load(*_stripe(cents=False)))
    check = next(c for c in report.checks if c.name == "invoices")
    assert check.level == "ok"
    assert "not measured, not as zero" in check.detail
    assert report.verdict == "READY"


def test_preflight_has_nothing_to_say_about_invoices_that_were_supplied(with_invoices):
    assert not [c for c in preflight(with_invoices).checks if c.name == "invoices"]
