"""Tests for the delivery path a real engagement uses (D-062).

Phase 2's gate is a paying client, and the way that gate fails is not a crash. It is a
confident report built on a misread export, discovered by the prospect. So most of these
pin refusals: that minor units are caught rather than converted, that an assumption is
recorded rather than made quietly, and that the report command cannot skip the check.

The ingest tests use column names copied from actual Stripe dashboard exports, because
every one of them broke the loader the first time it was run against them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from keel.cli import main
from keel.core.schema import CUSTOMERS, SUBSCRIPTIONS
from keel.ingest.csv_ingest import load, normalise_columns
from keel.ingest.preflight import preflight, render_preflight


def _stripe(n=400, seed=0, cents=True, churn=0.35, months=700):
    rng = np.random.default_rng(seed)
    created = pd.to_datetime("2023-06-01") + pd.to_timedelta(rng.integers(0, months, n), "D")
    cust = pd.DataFrame({
        "id": [f"cus_{i:05d}" for i in range(n)],
        "Email": [f"u{i}@example.com" for i in range(n)],
        "Created (UTC)": created,
    })
    ch = rng.random(n) < churn
    amount = rng.integers(900, 29900, n)
    subs = pd.DataFrame({
        "id": [f"sub_{i:05d}" for i in range(n)],
        "Customer ID": cust["id"],
        "Status": np.where(ch, "canceled", "active"),
        "Created (UTC)": created,
        "Canceled At (UTC)": [
            (c + pd.Timedelta(days=int(rng.integers(30, 500)))) if k else ""
            for c, k in zip(created, ch, strict=True)
        ],
        "Plan Amount": amount if cents else amount / 100.0,
        "Plan Currency": "usd",
    })
    return cust, subs


# --- the loader survives a real export ---------------------------------------


def test_parenthetical_timezone_suffixes_are_stripped():
    """Every Stripe export ships "Created (UTC)". It matched nothing and failed the
    load on the first file a prospect would ever send."""
    f = pd.DataFrame({"id": ["a"], "Created (UTC)": ["2024-01-01"]})
    assert "created_at" in normalise_columns(f, CUSTOMERS).columns


def test_bare_id_binds_to_the_tables_own_key():
    """`id` on a subscriptions export is the subscription, not the customer. Treating
    it as a global alias for customer_id loaded sub ids into the customer column."""
    f = pd.DataFrame({"id": ["sub_1"], "Customer ID": ["cus_1"]})
    out = normalise_columns(f, SUBSCRIPTIONS)
    assert out["subscription_id"].iloc[0] == "sub_1"
    assert out["customer_id"].iloc[0] == "cus_1"


def test_a_real_id_column_beats_email_as_the_customer_key():
    """`email` is a plausible identifier and sits earlier in the alias list, so it won
    over the actual id column and every subscription then referenced a customer that
    did not exist."""
    f = pd.DataFrame({"id": ["cus_1"], "Email": ["a@b.com"]})
    assert normalise_columns(f, CUSTOMERS)["customer_id"].iloc[0] == "cus_1"


def test_a_full_stripe_shaped_export_loads():
    cust, subs = _stripe()
    ds = load(customers=cust, subscriptions=subs)
    assert len(ds.subscriptions) == len(subs)
    assert ds.subscriptions["customer_id"].isin(set(ds.customers["customer_id"])).all()


def test_absent_required_columns_are_recorded_not_silently_filled():
    cust, subs = _stripe()
    got: list[str] = []
    load(customers=cust, subscriptions=subs, assumptions=got)
    assert any("interval" in a for a in got)
    assert any("plan" in a for a in got)
    # The interval note has to be alarming: it scales every revenue figure.
    assert any("12x" in a for a in got)


def test_supplied_defaults_override_and_are_attributed():
    cust, subs = _stripe()
    got: list[str] = []
    ds = load(customers=cust, subscriptions=subs,
              defaults={"interval": "year"}, assumptions=got)
    assert (ds.subscriptions["interval"] == "year").all()
    assert any("you told us" in a for a in got)


# --- preflight refuses the dangerous cases -----------------------------------


def test_minor_units_are_blocked_never_converted():
    """The check that motivates the module. It must not guess -- a silent divide would
    be the same class of error as the one it exists to catch (D-057)."""
    ds = load(*_stripe(cents=True))
    p = preflight(ds)
    assert p.blocked
    unit = next(c for c in p.checks if c.name == "currency units")
    assert unit.level == "block"
    assert "minor units" in unit.detail
    # And it says what the number would become, so the operator can sanity-check it.
    assert "158" in unit.detail or "per month" in unit.detail


def test_plausible_major_units_pass():
    ds = load(*_stripe(cents=False))
    p = preflight(ds)
    assert not p.blocked
    assert p.verdict.startswith("READY") or p.verdict.startswith("CHECK")


def test_end_before_start_is_blocked():
    cust, subs = _stripe(cents=False)
    subs.loc[:5, "Canceled At (UTC)"] = pd.Timestamp("2000-01-01")
    p = preflight(load(cust, subs))
    assert p.blocked
    assert any(c.name == "date order" for c in p.checks)


def test_no_cancellations_at_all_is_blocked():
    cust, subs = _stripe(cents=False, churn=0.0)
    p = preflight(load(cust, subs))
    assert p.blocked
    assert any(c.name == "churn signal" and c.level == "block" for c in p.checks)


def test_too_little_history_is_blocked():
    cust, subs = _stripe(cents=False, months=60)
    p = preflight(load(cust, subs))
    assert any(c.name == "history" and c.level == "block" for c in p.checks)


def test_small_samples_warn_about_modelling_not_about_the_report():
    """Below ~250 a report is still honest; a model is not. The distinction has to
    reach the operator before they promise the wrong thing."""
    cust, subs = _stripe(n=120, cents=False)
    p = preflight(load(cust, subs))
    c = next(c for c in p.checks if c.name == "sample size")
    assert c.level == "warn"
    assert "still honest" in c.fix or "Do not promise" in c.fix


def test_duplicate_subscription_ids_are_rejected_by_the_loader():
    """Caught by `Dataset.validate` during load, before preflight ever sees the frame.
    Pinned here so the guard is not quietly relaxed, and so preflight is not credited
    with a check it does not perform."""
    from keel.core.schema import SchemaError

    cust, subs = _stripe(cents=False)
    subs = pd.concat([subs, subs.iloc[:3]], ignore_index=True)
    with pytest.raises(SchemaError, match="duplicate"):
        load(cust, subs)


def test_render_puts_blockers_first_and_shows_assumptions():
    got: list[str] = []
    ds = load(*_stripe(cents=True), assumptions=got)
    txt = render_preflight(preflight(ds, got))
    assert "BLOCKED" in txt
    assert txt.index("BLOCK") < txt.index("  ok  ")
    assert "ASSUMPTIONS MADE FOR YOU" in txt


# --- the CLI -----------------------------------------------------------------


def _files(tmp_path, **kw):
    cust, subs = _stripe(**kw)
    c, s = tmp_path / "c.csv", tmp_path / "s.csv"
    cust.to_csv(c, index=False)
    subs.to_csv(s, index=False)
    return str(c), str(s)


def test_preflight_command_exits_nonzero_when_blocked(tmp_path, capsys):
    c, s = _files(tmp_path, cents=True)
    assert main(["preflight", "--customers", c, "--subscriptions", s]) == 1
    assert "BLOCKED" in capsys.readouterr().out


def test_autopsy_refuses_to_run_on_a_blocked_export(tmp_path):
    c, s = _files(tmp_path, cents=True)
    out = tmp_path / "r.html"
    assert main(["autopsy", "--customers", c, "--subscriptions", s,
                 "--out", str(out)]) == 1
    assert not out.exists(), "a blocked export must not produce a report"


def test_force_overrides_but_the_conversion_flag_is_the_real_fix(tmp_path):
    c, s = _files(tmp_path, cents=True)
    out = tmp_path / "r.html"
    assert main(["autopsy", "--customers", c, "--subscriptions", s,
                 "--out", str(out), "--force"]) == 0
    assert out.exists()


def test_full_run_with_units_corrected(tmp_path, capsys):
    c, s = _files(tmp_path, cents=True)
    out = tmp_path / "r.html"
    code = main(["autopsy", "--customers", c, "--subscriptions", s,
                 "--divide-amounts-by", "100", "--interval", "month",
                 "--name", "Acme", "--out", str(out)])
    assert code == 0 and out.exists()
    text = capsys.readouterr().out
    assert "READY" in text
    assert "divided by 100" in text
    assert "Acme" in out.read_text(encoding="utf-8")


def test_unreadable_input_fails_cleanly(tmp_path, capsys):
    assert main(["preflight", "--customers", str(tmp_path / "nope.csv"),
                 "--subscriptions", str(tmp_path / "nope.csv")]) == 2
    assert "could not read" in capsys.readouterr().err


def test_bad_interval_is_rejected_by_the_parser(tmp_path):
    c, s = _files(tmp_path, cents=False)
    with pytest.raises(SystemExit):
        main(["preflight", "--customers", c, "--subscriptions", s,
              "--interval", "fortnight"])


# --- Razorpay: epoch timestamps and paise ------------------------------------


def _epoch_seconds(index):
    """Epoch seconds, independent of the index's datetime resolution.

    `index.astype("int64") // 10**9` is the obvious form and is **version-fragile**:
    pandas 2 may give the index microsecond rather than nanosecond resolution, in which
    case that expression is off by a thousand. It produced a fixture full of values
    outside the epoch window, `_to_datetime` correctly declined to treat them as
    timestamps, and the test failed in CI while passing locally.
    """
    return index.astype("datetime64[s]").astype("int64")


def _end_value(e, epoch):
    if e is None:
        return ""
    return int(e.timestamp()) if epoch else e


def _razorpay(n=400, seed=1, epoch=True, paise=True):
    """Razorpay's export shape: epoch seconds, amounts in paise, `start_at`/`plan_id`."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2023-05-01") + pd.to_timedelta(rng.integers(0, 600, n), "D")
    ch = rng.random(n) < 0.45
    cust = pd.DataFrame({
        "id": [f"cust_{i:06d}" for i in range(n)],
        "name": [f"C{i}" for i in range(n)],
        "created_at": _epoch_seconds(start) if epoch else start,
    })
    ends = [
        (s + pd.Timedelta(days=int(rng.integers(30, 400)))) if k else None
        for s, k in zip(start, ch, strict=True)
    ]
    subs = pd.DataFrame({
        "id": [f"sub_{i:06d}" for i in range(n)],
        "customer_id": cust["id"],
        "plan_id": rng.choice(["plan_499", "plan_999"], n),
        "status": np.where(ch, "cancelled", "active"),
        "start_at": _epoch_seconds(start) if epoch else start,
        "ended_at": [_end_value(e, epoch) for e in ends],
        "amount": rng.choice([49900, 99900], n) if paise else rng.choice([499.0, 999.0], n),
    })
    return cust, subs


def test_razorpay_epoch_seconds_are_parsed_not_read_as_nanoseconds():
    """pandas reads a bare integer as nanoseconds and lands every row on 1970-01-01."""
    ds = load(*_razorpay())
    started = pd.to_datetime(ds.subscriptions["started_at"])
    assert started.min() > pd.Timestamp("2020-01-01")
    assert started.max() < pd.Timestamp("2030-01-01")


def test_sparse_epoch_columns_are_converted_too():
    """`ended_at` is legitimately sparse -- only churned customers have one. Testing
    what *fraction* of the column was numeric rejected exactly the column that most
    needed converting, and every cancellation date came back as 1970."""
    ds = load(*_razorpay())
    ended = pd.to_datetime(ds.subscriptions["ended_at"]).dropna()
    assert len(ended) > 0
    assert ended.min() > pd.Timestamp("2020-01-01")


def test_ordinary_date_strings_are_not_mistaken_for_epochs():
    ds = load(*_razorpay(epoch=False, paise=False))
    started = pd.to_datetime(ds.subscriptions["started_at"])
    assert started.min() > pd.Timestamp("2020-01-01")


def test_razorpay_column_names_resolve():
    ds = load(*_razorpay())
    assert ds.subscriptions["plan"].str.startswith("plan_").all()
    assert ds.subscriptions["customer_id"].isin(set(ds.customers["customer_id"])).all()


def test_paise_are_blocked_like_cents():
    p = preflight(load(*_razorpay(paise=True)))
    assert p.blocked
    unit = next(c for c in p.checks if c.name == "currency units")
    assert "paise" in unit.fix or "minor units" in unit.detail


def test_misparsed_dates_are_caught_as_a_backstop():
    """If a timestamp shape ever slips past `_to_datetime`, preflight must still stop
    it: no real billing history predates 1990."""
    cust, subs = _razorpay(epoch=False, paise=False)
    subs.loc[:9, "start_at"] = pd.Timestamp("1970-01-01")
    p = preflight(load(cust, subs))
    assert any(c.name == "date parsing" and c.level == "block" for c in p.checks)


def test_out_of_range_integers_are_not_treated_as_timestamps():
    """The guard that made the CI failure a *test* bug rather than a data-corruption
    bug. An integer outside the 1990-2050 epoch window is not a timestamp, so
    `_to_datetime` must decline to convert it -- and the preflight backstop must then
    catch the resulting nonsense date rather than letting it reach a report."""
    cust, subs = _razorpay(epoch=True, paise=False)
    subs["start_at"] = subs["start_at"] // 1000        # a thousand times too small
    ds = load(cust, subs)
    started = pd.to_datetime(ds.subscriptions["started_at"])
    assert started.max() < pd.Timestamp("1990-01-01"), "must not be silently rescaled"
    p = preflight(ds)
    assert p.blocked
    assert any(c.name == "date parsing" and c.level == "block" for c in p.checks)
