"""Tests for the small-sample reliability experiment (D-023, D-072, D-073).

None of these needs a dataset download. The win rate and its interval are tested on
hand-made results where the answer is known, and the experiment itself on a synthetic
randomised trial.

The reason this file exists: the project's headline small-sample figure, "the best method
beats random on 75% of draws at n = 500", was quoted for two months from twenty draws,
with no interval beside it and no command that printed it. Fifteen wins in twenty is
compatible with anything from 51% to 91%.
"""

from __future__ import annotations

import inspect
import re

import numpy as np
import pandas as pd
import pytest
from test_benchmarks import make_rct

from retainiq.benchmarks import small_n
from retainiq.benchmarks.small_n import (
    DRAWS,
    METHODS,
    SmallNResult,
    exact_interval,
    rate,
    report,
    run,
    win_rates,
)


def result_from(wins_by_method: dict[str, list[float]], random: list[float],
                train_size: int = 500) -> SmallNResult:
    """A result with chosen outcomes: one value per draw for each method and for random."""
    rows = [{"train_size": np.nan, "method": "random", "seed": s, "incremental": v,
             "uplift_per_contact": np.nan} for s, v in enumerate(random)]
    for method, values in wins_by_method.items():
        rows += [{"train_size": train_size, "method": method, "seed": s, "incremental": v,
                  "uplift_per_contact": np.nan} for s, v in enumerate(values)]
    return SmallNResult(dataset="hand-made", frame=pd.DataFrame(rows))


# --- the interval -----------------------------------------------------------


@pytest.mark.parametrize(
    ("wins", "draws", "low", "high"),
    [
        (15, 20, 0.509, 0.913),      # the figure the documents quoted for two months
        (14, 20, 0.457, 0.881),      # what twenty draws give today
        (145, 200, 0.658, 0.786),    # the figure the documents quote now
        (10, 20, 0.272, 0.728),
    ],
)
def test_exact_interval_matches_known_values(wins, draws, low, high):
    got = exact_interval(wins, draws)
    assert got == pytest.approx((low, high), abs=0.0015)


def test_twenty_draws_cannot_separate_three_in_four_from_a_coin_toss():
    """The arithmetic behind D-072. An interval this wide was never printed."""
    low, high = exact_interval(15, 20)
    assert high - low > 0.40
    assert exact_interval(14, 20)[0] < 0.5


def test_two_hundred_draws_can():
    low, high = exact_interval(145, 200)
    assert low > 0.5 and high - low < 0.14


def test_no_wins_and_all_wins_have_closed_ends():
    assert exact_interval(0, 20)[0] == 0.0
    assert exact_interval(20, 20)[1] == 1.0
    assert 0 < exact_interval(0, 20)[1] < 0.2
    assert 0.8 < exact_interval(20, 20)[0] < 1


def test_one_draw_gives_an_interval_that_says_nothing():
    assert exact_interval(1, 1) == pytest.approx((0.025, 1.0), abs=0.001)


@pytest.mark.parametrize(("wins", "draws"), [(1, 0), (0, 0), (5, 4), (-1, 10)])
def test_an_impossible_count_is_refused(wins, draws):
    with pytest.raises(ValueError):
        exact_interval(wins, draws)


def test_the_interval_narrows_as_draws_increase():
    widths = [np.subtract(*exact_interval(int(0.7 * n), n)[::-1]) for n in (20, 50, 200, 1000)]
    assert widths == sorted(widths, reverse=True)


# --- the win rate -----------------------------------------------------------


def test_win_rate_is_paired_on_the_draw_not_compared_with_randoms_average():
    """Random scores 0, 10, 0, 10. A method scoring 5 every time beats its *average* on
    no draw and beats it *on the same draw* twice."""
    w = win_rates(result_from({"s_learner": [5, 5, 5, 5]}, random=[0, 10, 0, 10]))
    row = w.iloc[0]
    assert (row["wins"], row["draws"]) == (2, 4)
    assert row["win_rate"] == pytest.approx(0.5)


def test_a_tie_with_random_is_not_a_win():
    w = win_rates(result_from({"s_learner": [3, 3]}, random=[3, 3]))
    assert w.iloc[0]["wins"] == 0


def test_a_fit_that_failed_is_a_draw_that_did_not_beat_random():
    """`run` records a failed fit as NaN. A business whose model failed has gained
    nothing, so it stays in the denominator."""
    w = win_rates(result_from({"t_learner": [9, np.nan, 9, np.nan]}, random=[1, 1, 1, 1]))
    row = w.iloc[0]
    assert (row["wins"], row["draws"]) == (2, 4)


def test_every_win_rate_carries_its_interval():
    w = win_rates(result_from({"s_learner": [9] * 15 + [0] * 5}, random=[1] * 20))
    row = w.iloc[0]
    assert (row["low"], row["high"]) == pytest.approx(exact_interval(15, 20))
    assert row["low"] < row["win_rate"] < row["high"]


def test_a_method_with_no_draws_at_a_size_has_no_row():
    w = win_rates(result_from({"s_learner": [9, 9]}, random=[1, 1]))
    assert list(w["method"]) == ["s_learner"]


def test_win_rates_of_an_empty_result_is_empty():
    empty = SmallNResult("none", pd.DataFrame(
        columns=["train_size", "method", "seed", "incremental", "uplift_per_contact"]))
    assert win_rates(empty).empty
    assert "No draws to compare" in report(empty)


# --- what is printed --------------------------------------------------------


def test_a_rate_is_always_printed_with_its_interval():
    assert rate(145, 200) == "72.5% [66%, 79%]"
    assert rate(15, 20) == "75.0% [51%, 91%]"


def test_the_report_never_prints_a_win_rate_without_an_interval():
    """The rule D-072 ends on. Every percentage in the win-rate table is followed by a
    bracket; a bare "75%" cannot be printed by this module."""
    values = {m: [9] * 14 + [0] * 6 for m in METHODS}
    text = report(result_from(values, random=[1] * 20))
    table = text.split("Win rate against random targeting")[1]
    rates = re.findall(r"\d+\.\d%", table)
    with_interval = re.findall(r"\d+\.\d% \[\d+%, \d+%\]", table)
    assert rates and len(rates) == len(with_interval)


def test_the_report_says_how_many_draws_it_rests_on():
    values = {m: [9] * 14 + [0] * 6 for m in METHODS}
    text = report(result_from(values, random=[1] * 20))
    assert "(20 draws)" in text
    assert "14 of 20" in text


def test_the_report_names_the_best_and_the_weakest_method_at_each_size():
    values = {m: [9] * 10 + [0] * 10 for m in METHODS}
    values["s_learner"] = [9] * 18 + [0] * 2
    values["class_transform"] = [9] * 4 + [0] * 16
    text = report(result_from(values, random=[1] * 20))
    assert "best s_learner 18 of 20" in text
    assert "weakest class_transform" in text


def test_the_means_table_is_labelled_as_being_about_the_mean():
    """ "Uplift beats outcome models at every size" is true of the mean and is not true
    of the win rate at n = 500, where the intervals overlap."""
    values = {m: [9.0] * 6 for m in METHODS}
    text = report(result_from(values, random=[1.0] * 6))
    assert "On the MEAN" in text


# --- the experiment ---------------------------------------------------------


def test_the_named_command_runs_enough_draws_by_default():
    """The documents quote this command's default run. Twelve was the default while the
    documents quoted twenty."""
    assert inspect.signature(run).parameters["n_seeds"].default == DRAWS
    assert DRAWS >= 100


@pytest.fixture(scope="module")
def tiny() -> SmallNResult:
    return run(rct=make_rct(n=3000, seed=1), train_sizes=(300,), n_seeds=3)


def test_the_experiment_records_random_once_per_draw(tiny):
    random = tiny.frame[tiny.frame["method"] == "random"]
    assert sorted(random["seed"]) == [0, 1, 2]


def test_the_experiment_scores_every_method_on_every_draw(tiny):
    scored = tiny.frame[tiny.frame["train_size"] == 300]
    assert set(scored["method"]) == set(METHODS)
    assert (scored.groupby("method")["seed"].nunique() == 3).all()


def test_the_experiment_feeds_the_win_rates(tiny):
    w = win_rates(tiny)
    assert set(w["method"]) == set(METHODS)
    assert (w["draws"] == 3).all()
    assert ((w["wins"] >= 0) & (w["wins"] <= 3)).all()


def test_a_training_size_larger_than_the_data_is_skipped_not_fabricated():
    r = run(rct=make_rct(n=600, seed=2), train_sizes=(200, 50_000), n_seeds=2)
    assert set(r.frame["train_size"].dropna()) == {200}


# --- the figure -------------------------------------------------------------


def test_the_figure_is_drawn_from_a_result_without_any_dataset(tmp_path):
    pytest.importorskip("matplotlib")
    from retainiq.benchmarks.figures import figure_2

    values = {m: [9] * 14 + [0] * 6 for m in METHODS}
    frames = [result_from(values, random=[1] * 20, train_size=n).frame for n in (500, 1000)]
    frame = pd.concat([frames[0], frames[1][frames[1]["method"] != "random"]])
    out = figure_2(SmallNResult("hand-made", frame), out=tmp_path / "fig.png")
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert out.stat().st_size > 20_000


def test_the_command_draws_its_figure_from_the_run_it_printed(monkeypatch, capsys, tmp_path):
    """One run, two outputs. If the figure were drawn from a second run, the table and
    the picture could quote different numbers."""
    pytest.importorskip("matplotlib")
    from retainiq.benchmarks import figures

    calls = []
    values = {m: [9] * 3 for m in METHODS}

    def fake_run(n_seeds=DRAWS, **_):
        calls.append(n_seeds)
        return result_from(values, random=[1] * 3)

    seen = {}
    monkeypatch.setattr(small_n, "run", fake_run)
    monkeypatch.setattr(figures, "figure_2",
                        lambda result, **_: seen.setdefault("result", result) and tmp_path)
    assert small_n.main(["--draws", "3"]) == 0
    assert calls == [3], "exactly one run"
    assert isinstance(seen["result"], SmallNResult)
    assert "(3 draws)" in capsys.readouterr().out


def test_saved_draws_reproduce_the_table_and_say_they_were_re_read(monkeypatch, capsys, tmp_path):
    """A figure can be redrawn from saved draws without twenty minutes of fitting. The
    output must then say so: a table re-read from a file is not the experiment re-run."""
    values = {m: [9] * 14 + [0] * 6 for m in METHODS}
    monkeypatch.setattr(small_n, "run", lambda n_seeds=DRAWS, **_: result_from(values, [1] * 20))
    saved = tmp_path / "out" / "draws.csv"

    assert small_n.main(["--draws", "20", "--no-figure", "--save-draws", str(saved)]) == 0
    first = capsys.readouterr().out
    assert saved.exists()

    monkeypatch.setattr(small_n, "run", lambda **_: pytest.fail("must not run again"))
    assert small_n.main(["--no-figure", "--from-draws", str(saved)]) == 0
    second = capsys.readouterr().out

    marker = "Win rate against random targeting"
    assert first.split(marker)[1] == second.split(marker)[1]
    assert "RE-READ from draws.csv, not re-run" in second
    assert "RE-READ" not in first

