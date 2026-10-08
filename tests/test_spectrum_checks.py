"""Tests for the checks on the risk-lift correlation (D-074).

The checks exist because a single correlation from a single split can be produced by the
coefficient, the scale, the definition of risk, or the split. Two of those are artefacts
that can be shown with arithmetic and no model, and they are shown here, so that the
reason for each check is something the suite demonstrates and not something a docstring
asserts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from test_benchmarks import make_rct

from retainiq.benchmarks import spectrum_checks
from retainiq.benchmarks.datasets import RCT
from retainiq.benchmarks.spectrum import measure
from retainiq.benchmarks.spectrum_checks import (
    ALL_RISKS,
    CLIP,
    COEFFICIENTS,
    FOLLOW_UP,
    RISKS,
    SCALES,
    SIM,
    SIM_CUSTOMERS,
    SPLITS,
    STEPS,
    STOPPING,
    STOPPING_SETTINGS,
    Setting,
    all_correlations,
    benefits,
    boosting_rounds,
    correlation,
    figure,
    fitting,
    has_follow_up,
    incremental,
    interval,
    logit,
    one_split,
    report,
    report_stopping,
    run,
    stopping_diagnostic,
    subsim_trial,
    summarise,
    true_correlations,
    with_steps,
)

CORRELATION_COLUMNS = [f"{r}_{c}_{s}" for r in RISKS for c in COEFFICIENTS for s in SCALES]
FOLLOW_UP_COLUMNS = [f"{r}_{c}_{s}" for r in FOLLOW_UP for c in COEFFICIENTS for s in SCALES]


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def churn_trial(slope: float, shift: float, n: int = 6000, seed: int = 0) -> RCT:
    """A retention trial. Untreated churn rises with `x`; the offer changes churn by
    `shift + slope * x`, so a negative slope helps the customers at highest risk most
    and a positive one harms them."""
    rng = np.random.default_rng(seed)
    x = rng.random(n)
    t = rng.integers(0, 2, n)
    p = np.clip(0.15 + 0.5 * x + t * (shift + slope * x), 0.01, 0.99)
    return RCT(name="churn", X=pd.DataFrame({"x": x, "noise": rng.normal(size=n)}),
               treatment=t, outcome=(rng.random(n) < p).astype(float), outcome_name="churned")


@pytest.fixture(scope="module")
def response_split():
    return one_split(make_rct(n=4000, seed=3), seed=0)


@pytest.fixture(scope="module")
def helps_the_risky():
    return one_split(churn_trial(slope=-0.30, shift=0.0), seed=0, benefit_sign=-1)


@pytest.fixture(scope="module")
def harms_the_risky():
    return one_split(churn_trial(slope=+0.35, shift=-0.12), seed=0, benefit_sign=-1)


# --- what was fixed in advance ------------------------------------------------


def test_the_number_of_splits_is_the_one_pre_registered():
    assert SPLITS == 30


def test_the_simulated_trial_is_the_one_pre_registered():
    import inspect

    defaults = inspect.signature(subsim_trial).parameters
    assert SIM_CUSTOMERS == 60_000
    assert defaults["n_customers"].default == 60_000 and defaults["seed"].default == 7
    assert SIM.benefit_sign == -1


def test_every_check_is_measured_on_every_split(response_split):
    assert set(CORRELATION_COLUMNS) <= set(response_split)
    assert len(CORRELATION_COLUMNS) == 12


# --- the pieces ----------------------------------------------------------------


def test_a_probability_of_zero_or_one_has_a_finite_log_odds():
    assert np.isfinite(logit(np.array([0.0, 1.0]))).all()
    assert logit(np.array([0.0]))[0] == pytest.approx(np.log(CLIP / (1 - CLIP)))
    assert logit(np.array([1.0]))[0] == pytest.approx(-logit(np.array([0.0]))[0])
    assert logit(np.array([0.5]))[0] == pytest.approx(0.0)


@pytest.mark.parametrize("coefficient", COEFFICIENTS)
def test_a_constant_input_has_no_correlation_to_report(coefficient):
    """Zero would say "unrelated", which is a finding. There is nothing to find."""
    varying, flat = np.arange(10.0), np.full(10, 3.0)
    assert np.isnan(correlation(flat, varying, coefficient))
    assert np.isnan(correlation(varying, flat, coefficient))


@pytest.mark.parametrize("coefficient", COEFFICIENTS)
def test_two_customers_are_not_enough_to_correlate(coefficient):
    assert np.isnan(correlation(np.array([1.0, 2.0]), np.array([2.0, 1.0]), coefficient))


def test_an_unknown_coefficient_is_refused():
    with pytest.raises(ValueError, match="unknown coefficient"):
        correlation(np.arange(5.0), np.arange(5.0), "kendall")


def test_spearman_sees_an_ordering_that_pearson_understates():
    """Targeting uses the order. A relation that is perfectly ordered but curved is a
    perfect one for targeting, and Pearson does not report it as such."""
    x = np.linspace(0.0, 6.0, 200)
    y = np.exp(x)
    assert correlation(x, y, "spearman") == pytest.approx(1.0)
    assert correlation(x, y, "pearson") < 0.85


def test_one_extreme_customer_moves_pearson_and_not_spearman():
    rng = np.random.default_rng(0)
    a, b = rng.normal(size=300), rng.normal(size=300)
    a[0], b[0] = 60.0, 60.0
    assert correlation(a, b, "pearson") > 0.8
    assert abs(correlation(a, b, "spearman")) < 0.2


def test_a_benefit_is_positive_when_the_treatment_helps():
    """More visits is a benefit; so is less churn. The sign is carried by the setting."""
    more, fewer = np.array([0.30]), np.array([0.20])
    assert benefits(more, fewer, sign=+1)["prob"][0] > 0      # a visit campaign that works
    assert benefits(fewer, more, sign=-1)["prob"][0] > 0      # a retention offer that works
    assert benefits(more, fewer, sign=-1)["prob"][0] < 0      # an offer that causes churn
    assert benefits(fewer, more, sign=-1)["logodds"][0] > 0


def test_extra_good_outcomes_are_counted_with_the_settings_sign():
    """Four customers targeted; the treated two stayed and the control two left. The
    offer prevented churn at a rate of one per customer: four over the set."""
    rct = RCT(name="t", X=pd.DataFrame({"x": np.arange(6.0)}),
              treatment=np.array([1, 1, 0, 0, 1, 0]),
              outcome=np.array([0.0, 0.0, 1.0, 1.0, 1.0, 0.0]), outcome_name="churned")
    scores = np.array([9.0, 8.0, 7.0, 6.0, 1.0, 0.0])
    assert incremental(scores, rct, 4 / 6, sign=-1) == pytest.approx(4.0)
    assert incremental(scores, rct, 4 / 6, sign=+1) == pytest.approx(-4.0)


# --- the two artefacts, shown without a model ------------------------------------


def test_the_scale_alone_can_produce_a_positive_correlation():
    """Check 2. Give every customer the *same* effect on the log-odds scale. On the
    probability scale the effect is then largest where the baseline is highest, for
    baselines below a half, and a strong correlation appears that says nothing about
    who the offer suits. On the log-odds scale there is no variation to correlate."""
    base = np.linspace(0.02, 0.30, 400)
    treated = sigmoid(logit(base) + 0.4)
    found = all_correlations(benefits(treated, base, sign=+1), base)
    assert found["pearson_prob"] > 0.95
    assert found["spearman_prob"] == pytest.approx(1.0)
    assert np.isnan(found["pearson_logodds"])
    assert np.isnan(found["spearman_logodds"])


def test_the_scale_artefact_reverses_above_a_half():
    """The same uniform shift, with baselines above a half: now the probability-scale
    effect is smallest where the baseline is highest. The sign of the artefact depends
    on how common the outcome is, which is a property of the dataset, not the offer."""
    base = np.linspace(0.70, 0.98, 400)
    treated = sigmoid(logit(base) + 0.4)
    assert all_correlations(benefits(treated, base, sign=+1), base)["pearson_prob"] < -0.95


@pytest.mark.parametrize("sign, direction", [(+1, -1), (-1, +1)])
def test_risk_from_the_subtracted_model_shares_its_noise(sign, direction):
    """Check 3. True effect and true risk are unrelated here. The estimated effect is
    one noisy estimate minus another, so correlating it with the one that is subtracted
    finds the noise: negative when the outcome is good, positive when it is churn. A
    risk estimated on other customers has different noise and finds nothing."""
    rng = np.random.default_rng(1)
    n = 20_000
    p0 = 0.30 + rng.normal(0, 0.01, n)
    p1 = p0 + sign * 0.05                     # the same true effect for everyone
    p0_hat = p0 + rng.normal(0, 0.05, n)
    p1_hat = p1 + rng.normal(0, 0.05, n)
    other_hat = p0 + rng.normal(0, 0.05, n)

    benefit = benefits(p1_hat, p0_hat, sign)["prob"]
    same = correlation(benefit, p0_hat, "pearson")
    independent = correlation(benefit, other_hat, "pearson")
    assert direction * same > 0.5
    assert abs(independent) < 0.1


# --- one split of a trial ----------------------------------------------------------


def test_the_pooled_pearson_figure_is_the_one_the_spectrum_command_reports():
    """The checks are checks *of* that number, so they must start from it."""
    rct = make_rct(n=3000, seed=5)
    corr, advantage, negative = measure(rct, seed=0)
    row = one_split(rct, seed=0)
    assert row["pooled_pearson_prob"] == pytest.approx(corr)
    assert row["advantage_pct"] == pytest.approx(advantage)
    assert row["predicted_negative"] == pytest.approx(negative)


def test_a_split_is_reproducible():
    rct = make_rct(n=1500, seed=2)
    a, b = one_split(rct, seed=4), one_split(rct, seed=4)
    assert a.keys() == b.keys()
    assert all(a[k] == pytest.approx(b[k], nan_ok=True) for k in a)


def test_half_the_customers_are_held_out(response_split):
    assert response_split["n_test"] == 2000


def test_every_correlation_lies_between_minus_one_and_one(response_split):
    values = np.array([response_split[c] for c in CORRELATION_COLUMNS])
    assert np.isfinite(values).all() and (np.abs(values) <= 1.0).all()


SIGN_COLUMNS = ("pooled_pearson_prob", "pooled_spearman_prob", "control_indep_pearson_prob")


def test_an_offer_that_helps_the_riskiest_most_gives_a_positive_correlation(helps_the_risky):
    """The independent figure is fitted on half as many customers and is weaker for it,
    so what is pinned is the sign with room to spare, not a size."""
    for column in SIGN_COLUMNS:
        assert helps_the_risky[column] > 0.15, column


def test_an_offer_that_harms_the_riskiest_gives_a_negative_correlation(harms_the_risky):
    """The retention case: the customers likeliest to leave are the ones the offer
    drives away. Benefit falls as risk rises, on every definition of risk."""
    for column in SIGN_COLUMNS:
        assert harms_the_risky[column] < -0.15, column


def test_when_the_offer_harms_the_riskiest_the_uplift_model_beats_the_churn_score(
        harms_the_risky):
    assert harms_the_risky["best_uplift"] > harms_the_risky["best_outcome"]
    assert harms_the_risky["gain_per_1000"] > 0
    assert harms_the_risky["predicted_negative"] > 0.2


def test_the_gain_per_thousand_is_the_gap_scaled_to_a_thousand_customers(harms_the_risky):
    r = harms_the_risky
    assert r["gain_per_1000"] == pytest.approx(
        1000.0 * (r["best_uplift"] - r["best_outcome"]) / r["n_test"])


def test_a_run_labels_every_split_with_its_setting():
    frame = run(make_rct(n=1200, seed=1), Setting("Synthetic", "test"), splits=2)
    assert list(frame["seed"]) == [0, 1]
    assert set(frame["setting"]) == {"Synthetic"} and set(frame["domain"]) == {"test"}


# --- the simulator, measured like an experiment -------------------------------------


@pytest.fixture(scope="module")
def trial():
    return subsim_trial(n_customers=3000, seed=11)


def test_the_simulated_trial_gives_models_no_oracle_column(trial):
    from retainiq.experiments.abstention import FEATURES

    rct, truth = trial
    assert list(rct.X.columns) == list(FEATURES)
    forbidden = {"y0", "y1", "tau_true", "p_churn_control", "p_churn_treated",
                 "value_of_treating", "segment", "hidden_state"}
    assert not forbidden & set(rct.X.columns)
    assert not set(truth.columns) & set(rct.X.columns)


def test_the_simulated_trial_shows_one_outcome_per_customer_from_their_own_arm(trial):
    """Rebuild the potential outcomes and check the trial reveals only the assigned one."""
    from retainiq.sim import SimConfig, simulate
    from retainiq.sim.counterfactual import potential_outcomes

    rct, _ = trial
    sim = simulate(SimConfig(n_customers=3000, n_months=24, seed=11))
    po = potential_outcomes(sim, decision_month=6, horizon=6)
    snap = sim.snapshot(6)[["customer_id"]]
    po = po.merge(snap, on="customer_id", how="inner").reset_index(drop=True)
    assert len(po) == len(rct)
    expected = np.where(rct.treatment == 1, po["y1"], po["y0"])
    assert np.array_equal(rct.outcome, expected)


def test_the_simulated_trial_is_randomised_and_reproducible(trial):
    rct, truth = trial
    assert 0.45 < rct.treatment.mean() < 0.55
    assert set(np.unique(rct.outcome)) <= {0.0, 1.0}
    again, truth_again = subsim_trial(n_customers=3000, seed=11)
    assert np.array_equal(rct.treatment, again.treatment)
    assert np.array_equal(rct.outcome, again.outcome)
    pd.testing.assert_frame_equal(truth, truth_again)


def test_assignment_in_the_simulated_trial_ignores_the_customer(trial):
    """A coin toss: assignment must not track the true effect or the true risk."""
    rct, truth = trial
    for column in ("tau_true", "p_churn_control"):
        assert abs(np.corrcoef(rct.treatment, truth[column])[0, 1]) < 0.06, column


def test_the_true_correlation_is_between_benefit_and_untreated_risk():
    """An offer that cuts churn by a fifth of its untreated level helps the riskiest
    most: benefit rises with risk on the probability scale."""
    p0 = np.linspace(0.05, 0.60, 50)
    truth = pd.DataFrame({"p_churn_control": p0, "p_churn_treated": 0.8 * p0})
    found = true_correlations(truth)
    assert set(found) == {f"{c}_{s}" for c in COEFFICIENTS for s in SCALES}
    assert found["pearson_prob"] == pytest.approx(1.0)
    assert found["spearman_prob"] == pytest.approx(1.0)


def test_the_true_correlation_is_negative_when_the_offer_harms_the_riskiest():
    p0 = np.linspace(0.05, 0.60, 50)
    truth = pd.DataFrame({"p_churn_control": p0, "p_churn_treated": p0 + 0.3 * (p0 - 0.2)})
    assert true_correlations(truth)["pearson_prob"] == pytest.approx(-1.0)


# --- summarising ---------------------------------------------------------------------


def test_the_interval_is_the_mean_and_the_spread_across_splits():
    mean, low, high = interval(pd.Series(np.arange(101.0)))
    assert (mean, low, high) == pytest.approx((50.0, 2.5, 97.5))


def test_splits_with_no_measurement_are_left_out_of_the_interval():
    mean, low, high = interval(pd.Series([1.0, np.nan, 3.0]))
    assert mean == pytest.approx(2.0)
    assert all(np.isnan(v) for v in interval(pd.Series([np.nan, np.nan])))


def frame_of(values: dict[str, list[float]], setting: str = "A") -> pd.DataFrame:
    n = len(next(iter(values.values())))
    base = {c: [0.1] * n for c in [*CORRELATION_COLUMNS, *FOLLOW_UP_COLUMNS, "advantage_pct",
                                   "gain_per_1000"]}
    return pd.DataFrame({"seed": range(n), "n_test": 100, **base, **values,
                         "setting": setting, "domain": "test"})


def test_the_summary_says_how_many_splits_each_figure_rests_on():
    s = summarise(frame_of({"control_indep_pearson_prob": [0.2, np.nan, 0.4]}))
    row = s[s["measure"] == "control_indep_pearson_prob"].iloc[0]
    assert row["splits"] == 2 and row["mean"] == pytest.approx(0.3)
    assert s[s["measure"] == "pooled_pearson_prob"].iloc[0]["splits"] == 3


def test_the_report_has_a_section_for_each_check():
    text = report(frame_of({"pooled_pearson_prob": [0.5, 0.7]}))
    for heading in ("1. THE COEFFICIENT", "2. THE SCALE", "3. THE DEFINITION OF RISK",
                    "4. WHAT THE UPLIFT MODEL GAINS"):
        assert heading in text
    assert "mean over 2 splits" in text
    assert "+0.60 [+0.51, +0.69]" in text


def test_a_figure_that_was_never_measured_is_shown_as_not_available():
    text = report(frame_of({"control_indep_pearson_prob": [np.nan, np.nan]}))
    assert "n/a" in text


def test_the_simulators_truth_is_printed_only_when_supplied():
    frame = frame_of({"pooled_pearson_prob": [0.5, 0.7]})
    assert "THE SIMULATOR'S TRUTH" not in report(frame)
    text = report(frame, {"pearson_prob": -0.10, "spearman_logodds": -0.27}, "a note")
    assert "THE SIMULATOR'S TRUTH" in text and "pearson, prob: -0.10" in text
    assert text.count("a note") == 1


def test_settings_are_reported_in_the_order_they_were_run():
    frame = pd.concat([frame_of({"pooled_pearson_prob": [0.1, 0.2]}, "Zeta"),
                       frame_of({"pooled_pearson_prob": [0.3, 0.4]}, "Alpha")],
                      ignore_index=True)
    text = report(frame)
    assert text.index("Zeta") < text.index("Alpha")


# --- the figure and the command -------------------------------------------------------


def five_settings() -> pd.DataFrame:
    names = [("Hillstrom (mens)", "promotional email"), ("Criteo", "advertising"),
             ("Hillstrom (womens)", "promotional email"), ("Lenta", "retail promotion"),
             (SIM.name, SIM.domain)]
    parts = []
    for i, (name, domain) in enumerate(names):
        part = frame_of({"pooled_pearson_prob": [0.1 * i, 0.1 * i + 0.2],
                         "pooled_pearson_logodds": [-0.1 * i, 0.05],
                         "gain_per_1000": [float(i), i + 1.5]}, name)
        parts.append(part.assign(domain=domain))
    return pd.concat(parts, ignore_index=True)


def test_the_figure_is_written_from_the_splits_it_is_given(tmp_path):
    out = figure(five_settings(), tmp_path / "fig.png")
    assert out.exists() and out.stat().st_size > 20_000


def test_the_figure_does_not_overwrite_the_single_split_figure():
    """`spectrum.py` still draws its one-split figure. This one has its own file, so
    running either command leaves the other's picture as that command drew it."""
    import inspect

    assert "fig07_correlation_checked.png" in inspect.getsource(figure)
    assert "fig03" not in inspect.getsource(figure)


def test_the_figure_plots_no_oracle_point():
    """Every point is a fitted model on a trial. The oracle's figure is in other units
    and stays in the text."""
    import inspect

    source = inspect.getsource(figure)
    assert "tau_true" not in source and "oracle" not in source.lower().replace(
        "no point is an oracle", "")


def test_the_figure_shows_both_scales():
    assert [m for m, _ in spectrum_checks.PANELS] == ["pooled_pearson_prob",
                                                      "pooled_pearson_logodds"]


@pytest.fixture
def saved(tmp_path):
    path = tmp_path / "splits.csv"
    frame = five_settings()
    frame[frame["setting"] != SIM.name].to_csv(path, index=False)
    return path


def test_splits_read_back_from_a_file_say_they_were_not_re_run(saved, capsys):
    assert spectrum_checks.main(["--from-splits", str(saved), "--no-figure"]) == 0
    out = capsys.readouterr().out
    assert f"RE-READ from {saved.name}, not re-run" in out
    assert "1. THE COEFFICIENT" in out


def test_a_run_does_not_claim_to_be_re_read(monkeypatch, capsys):
    monkeypatch.setattr(spectrum_checks, "collect",
                        lambda splits, include: (five_settings(), {"pearson_prob": -0.1}))
    assert spectrum_checks.main(["--no-figure"]) == 0
    out = capsys.readouterr().out
    assert "RE-READ" not in out and "THE SIMULATOR'S TRUTH" in out


def test_the_command_draws_the_figure_from_the_splits_it_printed(monkeypatch, capsys, tmp_path):
    drawn = {}

    def fake_figure(frame):
        drawn["frame"] = frame
        return tmp_path / "fig.png"

    frame = five_settings()
    monkeypatch.setattr(spectrum_checks, "collect", lambda splits, include: (frame, {}))
    monkeypatch.setattr(spectrum_checks, "figure", fake_figure)
    assert spectrum_checks.main([]) == 0
    assert drawn["frame"] is frame
    assert "fig.png" in capsys.readouterr().out


def test_a_partial_run_does_not_redraw_the_figure(monkeypatch, capsys):
    """Running one setting must not replace a five-setting figure with a one-setting one."""
    def refuse(frame):
        raise AssertionError("the figure was drawn from a subset of settings")

    part = five_settings()
    part = part[part["setting"] == "Criteo"]
    monkeypatch.setattr(spectrum_checks, "collect", lambda splits, include: (part, {}))
    monkeypatch.setattr(spectrum_checks, "figure", refuse)
    assert spectrum_checks.main(["--only", "Criteo"]) == 0
    assert "Figure not drawn" in capsys.readouterr().out


def test_the_oracle_figure_is_never_printed_as_comparable(monkeypatch, capsys):
    monkeypatch.setattr(spectrum_checks, "collect",
                        lambda splits, include: (five_settings(), {"pearson_prob": -0.1}))
    spectrum_checks.main(["--no-figure"])
    assert "different units" in capsys.readouterr().out


# --- the follow-up: why the definition of risk moves the figure (D-076) -----------------


def test_the_first_three_definitions_of_risk_are_as_first_pre_registered():
    """The follow-up adds two. It must not quietly change what the first three were."""
    assert RISKS == ("pooled", "control_same", "control_indep")
    assert FOLLOW_UP == ("pooled_half", "pooled_indep")
    assert ALL_RISKS == (*RISKS, *FOLLOW_UP)


def test_the_follow_up_figures_are_measured_on_every_split(response_split):
    values = np.array([response_split[c] for c in FOLLOW_UP_COLUMNS])
    assert len(FOLLOW_UP_COLUMNS) == 8
    assert np.isfinite(values).all() and (np.abs(values) <= 1.0).all()


def test_each_step_changes_one_thing_as_pre_registered():
    """Half the data with customers shared; then the sharing removed; then control only."""
    assert STEPS == {
        "step_data": ("pooled_half", "pooled"),
        "step_sharing": ("pooled_indep", "pooled_half"),
        "step_definition": ("control_indep", "pooled_indep"),
    }


def test_the_three_steps_add_up_to_the_movement_they_explain(response_split):
    """D-074 reported how far the figure moves between pooled risk and independent
    control-only risk. The steps are a decomposition of exactly that and nothing more."""
    w = with_steps(pd.DataFrame([response_split]))
    moved = w["control_indep_pearson_prob"] - w["pooled_pearson_prob"]
    assert w[list(STEPS)].sum(axis=1).iloc[0] == pytest.approx(moved.iloc[0])


def test_a_step_is_a_difference_on_the_same_split_not_a_difference_of_averages():
    frame = frame_of({"pooled_half_pearson_prob": [0.50, 0.10],
                      "pooled_indep_pearson_prob": [0.20, 0.30]})
    assert list(with_steps(frame)["step_sharing"]) == pytest.approx([-0.30, 0.20])


def test_the_steps_can_be_taken_on_another_coefficient_or_scale():
    frame = frame_of({"pooled_half_spearman_logodds": [0.40],
                      "pooled_indep_spearman_logodds": [0.15]})
    w = with_steps(frame, suffix="spearman_logodds")
    assert w["step_sharing"].iloc[0] == pytest.approx(-0.25)


def test_splits_saved_before_the_follow_up_are_left_as_they_are():
    old = frame_of({"pooled_pearson_prob": [0.5, 0.7]}).drop(columns=FOLLOW_UP_COLUMNS)
    assert not has_follow_up(old)
    assert with_steps(old) is old


def test_the_report_shows_the_follow_up_when_it_was_measured():
    text = report(frame_of({"pooled_half_pearson_prob": [0.5, 0.7],
                            "pooled_indep_pearson_prob": [0.2, 0.2]}))
    for heading in ("3b. WHY IT MOVES", "THE THREE STEPS", "SPREAD ACROSS SPLITS"):
        assert heading in text
    # The sharing step is taken split by split: 0.2 - 0.5 and 0.2 - 0.7.
    mean, low, high = interval(pd.Series([-0.3, -0.5]))
    assert f"{mean:+.2f} [{low:+.2f}, {high:+.2f}]" in text and mean == pytest.approx(-0.4)
    assert "add up to (control, independent) minus (pooled)" in text


def test_the_report_of_splits_saved_earlier_does_not_invent_a_follow_up():
    old = frame_of({"pooled_pearson_prob": [0.5, 0.7]}).drop(columns=FOLLOW_UP_COLUMNS)
    text = report(old)
    assert "3b." not in text and "THE THREE STEPS" not in text
    assert "3. THE DEFINITION OF RISK" in text


def test_the_summary_gives_the_spread_across_splits():
    s = summarise(frame_of({"pooled_pearson_prob": [0.2, 0.4, 0.6]}))
    row = s[s["measure"] == "pooled_pearson_prob"].iloc[0]
    assert row["sd"] == pytest.approx(0.2)


def test_one_split_has_no_spread_to_report():
    frame = frame_of({"pooled_pearson_prob": [0.3]})
    assert np.isnan(summarise(frame)["sd"]).all()
    spread_section = report(frame).split("SPREAD ACROSS SPLITS")[1].split("4. WHAT")[0]
    assert "n/a" in spread_section


@pytest.mark.parametrize("sign, treated_sd, control_sd, direction", [
    (+1, 0.06, 0.03, +1),     # a response the offer raises: treated arm is the noisier
    (+1, 0.03, 0.06, -1),
    (-1, 0.03, 0.06, +1),     # churn the offer lowers: control arm is the noisier
    (-1, 0.06, 0.03, -1),
])
def test_a_both_arm_risk_model_on_the_same_customers_inherits_the_noisier_arm(
        sign, treated_sd, control_sd, direction):
    """The follow-up's mechanism, with no model. True effect and true risk are unrelated.
    A risk model fitted on both arms of the same customers carries the errors of both arm
    models. They do not cancel: what is left has the sign of (noise in the arm the benefit
    adds) minus (noise in the arm it subtracts). A risk model fitted on other customers
    carries neither."""
    rng = np.random.default_rng(3)
    n = 20_000
    p0 = 0.30 + rng.normal(0, 0.01, n)
    p1 = p0 + sign * 0.05
    p1_hat = p1 + rng.normal(0, treated_sd, n)
    p0_hat = p0 + rng.normal(0, control_sd, n)
    same_customers = 0.5 * (p1_hat + p0_hat)
    other_customers = 0.5 * (p1 + p0) + rng.normal(0, 0.03, n)

    benefit = benefits(p1_hat, p0_hat, sign)["prob"]
    assert direction * correlation(benefit, same_customers, "pearson") > 0.4
    assert abs(correlation(benefit, other_customers, "pearson")) < 0.05


def test_the_shared_noise_cancels_when_both_arms_are_equally_noisy():
    """Why this artefact can be absent in one experiment and large in another."""
    rng = np.random.default_rng(4)
    n = 20_000
    p0 = 0.30 + rng.normal(0, 0.01, n)
    p1_hat = p0 + 0.05 + rng.normal(0, 0.05, n)
    p0_hat = p0 + rng.normal(0, 0.05, n)
    benefit = benefits(p1_hat, p0_hat, +1)["prob"]
    assert abs(correlation(benefit, 0.5 * (p1_hat + p0_hat), "pearson")) < 0.05


# --- the diagnostic: the classifier's early stopping (D-076, exploratory) ---------------


def same(a: dict, b: dict) -> bool:
    """Exactly equal, entry by entry, with a missing figure equal to a missing figure."""
    return a.keys() == b.keys() and all(
        a[k] == b[k] or (np.isnan(a[k]) and np.isnan(b[k])) for k in a)


@pytest.fixture(scope="module")
def diagnostic():
    return stopping_diagnostic(make_rct(n=1500, seed=2), Setting("Synthetic", "test"), splits=2)


def test_the_two_ways_of_fitting_are_the_default_and_off():
    assert STOPPING == {"automatic": "auto", "off": False}


def test_the_diagnostic_covers_the_settings_where_a_model_crosses_the_line():
    """Hillstrom's arms hold about 10,650 customers each and the simulated trial about 9,000,
    either side of the 10,000 at which the library starts stopping early."""
    assert STOPPING_SETTINGS == ("Hillstrom (mens)", "Hillstrom (womens)", "SubSim (fitted)")


def test_fitting_reaches_every_benchmark_classifier():
    from retainiq.benchmarks import models

    with fitting(False):
        assert models._clf(3).early_stopping is False
        assert spectrum_checks._clf(3).early_stopping is False
    assert models._clf(3).early_stopping == "auto"
    assert spectrum_checks._clf(3).early_stopping == "auto"


def test_fitting_changes_nothing_about_the_classifier_but_its_stopping():
    from retainiq.benchmarks import models

    default = models._clf(5).get_params()
    with fitting(False):
        changed = models._clf(5).get_params()
    assert {k for k in default if default[k] != changed[k]} == {"early_stopping"}


def test_the_classifier_is_put_back_even_when_a_fit_fails():
    from retainiq.benchmarks import models

    original = models._clf
    with pytest.raises(RuntimeError, match="a fit failed"), fitting(False):
        raise RuntimeError("a fit failed")
    assert models._clf is original and spectrum_checks._clf is original


def test_automatic_stopping_is_exactly_the_default():
    """The diagnostic's "automatic" column has to be the main tables' figure, to the last
    digit, or the comparison beside it is with something else."""
    rct = make_rct(n=1500, seed=2)
    plain = one_split(rct, seed=1)
    with fitting("auto"):
        forced = one_split(rct, seed=1)
    assert same(plain, forced)


def test_below_ten_thousand_rows_stopping_makes_no_difference():
    """Nothing stops early on a small sample, so every result in this project that was
    fitted on fewer than 10,000 rows is untouched by what the diagnostic found."""
    rct = make_rct(n=4000, seed=3)
    with fitting("auto"):
        automatic = one_split(rct, seed=0)
    with fitting(False):
        off = one_split(rct, seed=0)
    assert same(automatic, off)


def test_above_ten_thousand_rows_the_default_stops_early_and_off_does_not():
    rct = make_rct(n=44_000, seed=6)
    with fitting("auto"):
        automatic = boosting_rounds(rct, seed=0)
    with fitting(False):
        off = boosting_rounds(rct, seed=0)
    assert automatic["train_treated"] > 10_000 and automatic["train_control"] > 10_000
    assert [off[k] for k in ("rounds_treated", "rounds_control", "rounds_pooled")] == [150] * 3
    assert min(automatic[k] for k in ("rounds_treated", "rounds_control", "rounds_pooled")) < 150


def test_the_diagnostic_measures_every_split_both_ways(diagnostic):
    assert len(diagnostic) == 4
    assert sorted(diagnostic["stopping"].unique()) == ["automatic", "off"]
    assert list(diagnostic[diagnostic["stopping"] == "off"]["seed"]) == [0, 1]
    assert {"rounds_treated", "rounds_control", "rounds_pooled", "train_treated",
            "train_control", "pooled_indep_pearson_prob", "gain_per_1000"} <= set(diagnostic)


def test_the_diagnostic_report_says_it_was_not_pre_registered(diagnostic):
    text = report_stopping(diagnostic)
    assert "EXPLORATORY: not pre-registered" in text.splitlines()[1]
    for heading in ("A. HOW LONG EACH MODEL WAS FITTED", "B. THE TABLE'S FIGURE",
                    "C. ONE CHANGE AT A TIME, stopping off", "D. WHAT THE UPLIFT MODEL GAINS"):
        assert heading in text


def test_the_diagnostic_report_shows_the_arm_sizes_that_decide_it(diagnostic):
    row = next(ln for ln in report_stopping(diagnostic).splitlines()
               if ln.startswith("Synthetic") and "/" in ln)
    treated = int(diagnostic["train_treated"].median())
    assert f"{treated:,}" in row and "150 / 150 / 150" in row


def test_the_diagnostic_runs_only_when_asked_for(monkeypatch, capsys, diagnostic):
    def refuse(*_):
        raise AssertionError("the thirty-split run was started")

    monkeypatch.setattr(spectrum_checks, "collect", refuse)
    monkeypatch.setattr(spectrum_checks, "collect_stopping", lambda splits, include: diagnostic)
    monkeypatch.setattr(spectrum_checks, "figure", refuse)
    assert spectrum_checks.main(["--stopping-diagnostic"]) == 0
    assert "EXPLORATORY" in capsys.readouterr().out


def test_the_main_command_does_not_run_the_diagnostic(monkeypatch, capsys):
    def refuse(*_):
        raise AssertionError("the diagnostic was run")

    monkeypatch.setattr(spectrum_checks, "collect", lambda splits, include: (five_settings(), {}))
    monkeypatch.setattr(spectrum_checks, "collect_stopping", refuse)
    assert spectrum_checks.main(["--no-figure"]) == 0
    assert "EXPLORATORY" not in capsys.readouterr().out
