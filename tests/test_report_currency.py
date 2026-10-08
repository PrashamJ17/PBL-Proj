"""The report shows amounts in the currency the data is in, or in none (D-071).

The Churn Autopsy once printed every amount in rupees. The formatter hard-coded the
symbol, and the canonical subscriptions table has no currency column, so a dollar export
with a "Plan Currency" column of "usd" came back as "₹2.6 lakh". No test caught it,
because every report in the suite was built from the simulator, which is in rupees.

The rule these tests pin: the currency is read from the export or stated by the
operator. It is never assumed. When nobody states it, amounts are plain numbers.
"""

from __future__ import annotations

import html
import re

import pandas as pd
import pytest
from test_preflight_cli import _stripe

from retainiq.cli import main
from retainiq.core.schema import CUSTOMERS, INVOICES, Dataset, currency_code, empty
from retainiq.ingest.csv_ingest import load, stated_currencies
from retainiq.ingest.preflight import preflight
from retainiq.ingest.stripe import to_canonical as stripe_to_canonical
from retainiq.ingest.subsim_adapter import to_canonical
from retainiq.report.autopsy import analyse, format_money
from retainiq.report.render import generate
from retainiq.sim import SimConfig, simulate

RUPEE_WORDS = re.compile(r"₹|\blakh\b|\bcrore\b")


def page_text(path) -> str:
    """The words a reader sees: no styles, scripts or chart markup."""
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"<style.*?</style>|<script.*?</script>|<svg.*?</svg>", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def export(currency="usd", second_currency=None, **kw):
    """A Stripe-shaped export in major units, with its currency column under control."""
    cust, subs = _stripe(cents=False, **kw)
    if currency is None:
        subs = subs.drop(columns=["Plan Currency"])
    else:
        subs["Plan Currency"] = currency
    if second_currency:
        subs.loc[subs.index[::2], "Plan Currency"] = second_currency
    return cust, subs


def write(tmp_path, cust, subs):
    c, s = tmp_path / "c.csv", tmp_path / "s.csv"
    cust.to_csv(c, index=False)
    subs.to_csv(s, index=False)
    return str(c), str(s)


# --- formatting -------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(5_752, "₹5,752"), (260_000, "₹2.6 lakh"), (15_000_000, "₹1.50 crore")],
)
def test_rupees_are_grouped_in_lakh_and_crore(amount, expected):
    """Unchanged from before the fix: the sample report is in rupees by design."""
    assert format_money(amount, "INR") == expected


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        (183_738, "USD", "$183,738"),
        (1_840_000, "USD", "$1.84 million"),
        (1_234, "EUR", "€1,234"),
        (1_234, "GBP", "£1,234"),
        (1_234, "CHF", "CHF 1,234"),
    ],
)
def test_other_currencies_use_their_own_symbol_and_thousands(amount, currency, expected):
    text = format_money(amount, currency)
    assert text == expected
    assert not RUPEE_WORDS.search(text)


def test_an_unstated_currency_is_a_plain_number():
    """A wrong symbol is worse than a missing one."""
    assert format_money(1_234, None) == "1,234"
    assert format_money(1_840_000, None) == "1.84 million"


@pytest.mark.parametrize(
    ("currency", "expected"),
    [("USD", "-$1,234"), ("INR", "-₹1,234"), (None, "-1,234"), ("CHF", "-CHF 1,234")],
)
def test_a_negative_amount_keeps_its_sign_in_front(currency, expected):
    assert format_money(-1_234, currency) == expected


@pytest.mark.parametrize(
    ("stated", "expected"),
    [("usd", "USD"), (" inr ", "INR"), ("EUR", "EUR"),
     ("unknown", None), ("", None), (None, None), (float("nan"), None)],
)
def test_a_currency_code_is_normalised_and_placeholders_are_not_currencies(stated, expected):
    """"unknown" is what the loader writes into an invoices table with no currency
    column. Read back as a currency it would print "UNKNOWN 1,234"."""
    assert currency_code(stated) == expected


# --- where the currency comes from ------------------------------------------


def test_a_subscriptions_only_export_keeps_its_currency():
    """The defect at its source. The canonical table drops "Plan Currency"."""
    cust, subs = export("usd")
    assert stated_currencies(subs) == {"USD"}
    assert load(cust, subs).currency == "USD"


def test_an_export_that_states_no_currency_has_none():
    got: list[str] = []
    ds = load(*export(None), assumptions=got)
    assert ds.currency is None
    assert ds.currencies == ()
    assert any("currency" in a and "not stated" in a for a in got)


def test_the_operators_statement_is_used_and_attributed():
    got: list[str] = []
    ds = load(*export(None), assumptions=got, currency="inr")
    assert ds.currency == "INR"
    assert any("INR" in a and "you told us" in a for a in got)


def test_invoices_state_the_currency_through_their_own_column():
    sim = to_canonical(simulate(SimConfig(n_customers=120, n_months=8, seed=2)))
    assert sim.currency == "INR"
    blank = sim.invoices.assign(currency="unknown")
    silent = Dataset(customers=sim.customers, subscriptions=sim.subscriptions, invoices=blank)
    assert silent.currency is None


def test_a_dataset_with_no_invoices_and_no_statement_has_no_currency():
    sim = to_canonical(simulate(SimConfig(n_customers=120, n_months=8, seed=2)))
    bare = Dataset(customers=sim.customers, subscriptions=sim.subscriptions,
                   invoices=empty(INVOICES))
    assert bare.currency is None


def test_the_stripe_api_adapter_carries_the_price_currency():
    customer = {"id": "cus_1", "created": 1_700_000_000}
    subscription = {
        "id": "sub_1", "customer": "cus_1", "status": "active", "created": 1_700_000_000,
        "items": {"data": [{"quantity": 1, "price": {
            "id": "p", "unit_amount": 2900, "currency": "gbp",
            "recurring": {"interval": "month", "interval_count": 1}}}]},
    }
    ds = stripe_to_canonical([customer], [subscription], [])
    assert ds.currency == "GBP"


# --- the report -------------------------------------------------------------


def test_a_dollar_export_is_reported_in_dollars(tmp_path):
    """The defect, end to end."""
    out = generate(load(*export("usd")), "Dollar Co", tmp_path / "r.html")
    text = page_text(out)
    assert re.search(r"\$[\d,]+ is what churn costs you", text)
    assert not RUPEE_WORDS.search(text)


def test_an_export_with_no_currency_is_reported_without_any_symbol(tmp_path):
    out = generate(load(*export(None)), "Plain Co", tmp_path / "r.html")
    text = page_text(out)
    assert re.search(r"(?<![$₹€£])\b[\d,]+ is what churn costs you", text)
    assert not RUPEE_WORDS.search(text)
    assert "$" not in text
    assert "does not state a currency" in text


def test_simulated_data_is_still_reported_in_rupees(tmp_path):
    """The sample report is denominated in rupees on purpose; the fix must not move it."""
    ds = to_canonical(simulate(SimConfig(n_customers=200, n_months=12, seed=5)))
    assert analyse(ds).currency == "INR"
    assert "₹" in page_text(generate(ds, "Sim Co", tmp_path / "r.html"))


# --- preflight, and the command line ----------------------------------------


def test_preflight_says_where_the_currency_came_from():
    read = next(c for c in preflight(load(*export("usd"))).checks if c.name == "currency")
    told = next(c for c in preflight(load(*export(None), currency="inr")).checks
                if c.name == "currency")
    silent = next(c for c in preflight(load(*export(None))).checks if c.name == "currency")
    assert (read.level, read.detail) == ("ok", "USD (read from the export)")
    assert (told.level, told.detail) == ("ok", "INR (you told us)")
    assert silent.level == "ok" and "without a currency symbol" in silent.detail


def test_two_currencies_in_one_export_block_the_report(tmp_path):
    """Every headline figure is a sum, and dollars cannot be added to euros."""
    cust, subs = export("usd", second_currency="eur")
    report = preflight(load(cust, subs))
    check = next(c for c in report.checks if c.name == "currency")
    assert report.blocked and check.level == "block"
    assert "EUR" in check.detail and "USD" in check.detail

    c, s = write(tmp_path, cust, subs)
    out = tmp_path / "r.html"
    assert main(["autopsy", "--customers", c, "--subscriptions", s, "--out", str(out)]) == 1
    assert not out.exists()


def test_a_forced_mixed_currency_report_shows_no_symbol_and_says_why(tmp_path):
    c, s = write(tmp_path, *export("usd", second_currency="eur"))
    out = tmp_path / "r.html"
    assert main(["autopsy", "--customers", c, "--subscriptions", s, "--out", str(out),
                 "--force"]) == 0
    text = page_text(out)
    assert "more than one currency (EUR, USD)" in text
    assert "$" not in text and "€" not in text and not RUPEE_WORDS.search(text)


def test_a_statement_that_contradicts_the_export_is_flagged_not_hidden():
    ds = load(*export("usd"), currency="inr")
    check = next(c for c in preflight(ds).checks if c.name == "currency")
    assert check.level == "warn"
    assert "INR" in check.detail and "USD" in check.detail
    assert ds.currency == "INR", "what the operator said is what the report uses"


def test_the_currency_flag_reaches_the_report(tmp_path, capsys):
    c, s = write(tmp_path, *export(None))
    out = tmp_path / "r.html"
    assert main(["autopsy", "--customers", c, "--subscriptions", s, "--out", str(out),
                 "--currency", "inr"]) == 0
    assert "INR (you told us)" in capsys.readouterr().out
    assert "₹" in page_text(out)


def test_an_empty_dataset_has_no_currency_to_report():
    ds = Dataset(customers=empty(CUSTOMERS), subscriptions=pd.DataFrame(),
                 invoices=empty(INVOICES))
    assert ds.currencies == () and ds.currency is None
