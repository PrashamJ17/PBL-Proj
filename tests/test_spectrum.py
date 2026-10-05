"""Tests for the risk-lift correlation measurement and its figure (D-026, D-068).

Nothing here needs a dataset download. The measurement is tested on synthetic
randomised experiments whose correlation is built in, and the figure is tested on
hand-made points, so the suite runs offline and in CI.

The second half exists because of D-068. The figure once drew a simulator point,
measured against true effects with an oracle policy, exactly like four points measured
from fitted models, and its footnote called the gap between them "the signal". These
tests pin the distinction so that it cannot be dropped again without a failure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from retainiq.benchmarks.datasets import RCT

pytest.importorskip("matplotlib")

from retainiq.benchmarks import spectrum  # noqa: E402
from retainiq.benchmarks.spectrum import ESTIMATED, ORACLE, Point  # noqa: E402

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def make_rct(benefit_rises_with_propensity: bool, n: int = 6000, seed: int = 0) -> RCT:
    """A randomised experiment where the sign of corr(benefit, propensity) is chosen.

    Propensity to respond rises with ``x``. The treatment effect either rises with it
    too, or falls and turns negative for the customers most likely to respond, which is
    the structure a churn score walks into.
    """
    rng = np.random.default_rng(seed)
    x = rng.random(n)
    t = rng.integers(0, 2, n)
    base = 0.25 + 0.40 * x
    slope = 0.30 if benefit_rises_with_propensity else -0.30
    tau = slope * (x - 0.5)
    y = (rng.random(n) < np.clip(base + t * tau, 0.01, 0.99)).astype(float)
    return RCT(
        name="synthetic",
        X=pd.DataFrame({"x": x, "noise": rng.normal(size=n)}),
        treatment=t,
        outcome=y,
        outcome_name="response",
    )


@pytest.fixture(scope="module")
def measured():
    return {
        "agree": spectrum.measure(make_rct(benefit_rises_with_propensity=True)),
        "conflict": spectrum.measure(make_rct(benefit_rises_with_propensity=False)),
    }


# --- the measurement --------------------------------------------------------


def test_correlation_is_positive_when_benefit_rises_with_propensity(measured):
    corr, _, _ = measured["agree"]
    assert corr > 0.1  # measured +0.50 to +0.60 over five seeds


def test_correlation_is_negative_when_the_likeliest_responders_benefit_least(measured):
    corr, _, _ = measured["conflict"]
    assert corr < -0.1  # measured -0.28 to -0.52 over five seeds


def test_uplift_gains_more_when_the_two_orderings_conflict(measured):
    """The direction of D-026 on data where the truth is known.

    When the customers an outcome model ranks highest are the ones treatment harms, the
    outcome model's selection has a negative effect and an uplift model must beat it.
    When the orderings agree there is little or nothing to gain.
    """
    _, advantage_agree, _ = measured["agree"]
    _, advantage_conflict, _ = measured["conflict"]
    assert advantage_conflict > 0
    assert advantage_conflict > advantage_agree


def test_harmed_customers_are_predicted_in_both_designs(measured):
    """Both designs harm the same share of customers, and both are seen to.

    Harm existing is therefore not what separates them (the refinement in D-026): what
    differs is whether the harmed customers sit where the outcome model ranks highest.
    """
    for _, _, negative_share in measured.values():
        assert 0.2 < negative_share < 0.8


# --- how a point records the way it was measured ------------------------------


def test_a_point_is_estimated_unless_stated_otherwise():
    assert Point("x", "advertising", 0.1, 1.0, 0.1, 10).basis == ESTIMATED


def test_the_simulator_point_is_an_oracle_point():
    """SubSim uses true effects and the oracle policy, and must say so.

    Signs only: the values depend on a fitted model and are not pinned across
    platforms (D-063).
    """
    point = spectrum.subsim_point()
    assert point.basis == ORACLE
    assert point.correlation < 0
    assert point.uplift_advantage > 0
    assert 0 < point.negative_share < 1


# --- the figure and the report -------------------------------------------------

EST = Point("Criteo", "advertising", 0.58, 0.6, 0.159, 1_500_000)
ORA = Point("SubSim (churn)", "subscription retention", -0.19, 106.9, 0.257, 3589, ORACLE)


def test_an_oracle_point_is_drawn_hollow_and_an_estimated_one_filled():
    estimated, oracle = spectrum.marker_style(EST), spectrum.marker_style(ORA)
    assert oracle["facecolor"] == "white"
    assert estimated["facecolor"] != "white"
    assert oracle["marker"] != estimated["marker"]


def test_only_an_oracle_label_is_called_an_upper_bound():
    assert "upper bound" in spectrum.point_label(ORA)
    assert "upper bound" not in spectrum.point_label(EST)


def test_only_an_estimated_share_is_called_predicted():
    """SubSim's share is the true share harmed. The old figure labelled it "predicted"."""
    assert "predicted" in spectrum.point_label(EST)
    assert "predicted" not in spectrum.point_label(ORA)
    assert "known" in spectrum.point_label(ORA)


@pytest.mark.parametrize(
    ("share", "expected"),
    [
        (0.0047, "<1% predicted"),
        (0.0, "0% predicted"),
        (0.0051, "1% predicted"),
        (0.257, "26% predicted"),
    ],
)
def test_a_share_that_rounds_to_zero_is_not_printed_as_zero(share, expected):
    """Hillstrom (mens) has 0.47% predicted negative; "0%" said there were none."""
    label = spectrum.point_label(Point("h", "promotional email", 0.69, 1.0, share, 10))
    assert expected in label


def test_a_negative_advantage_is_printed_with_a_minus_sign_not_a_hyphen():
    label = spectrum.point_label(Point("h", "promotional email", 0.69, -5.6, 0.1, 10))
    assert "−5.6%" in label
    assert "-5.6%" not in label


def test_legend_separates_oracle_from_estimated_and_merges_arms_of_one_experiment():
    points = [
        Point("Hillstrom (mens)", "promotional email", 0.69, -5.6, 0.005, 10),
        Point("Hillstrom (womens)", "promotional email", 0.19, 12.7, 0.1, 10),
        EST,
        ORA,
    ]
    labels = [label for label, _ in spectrum.legend_entries(points)]
    assert labels == [
        "promotional email",
        "advertising",
        "subscription retention (simulator, oracle)",
    ]


def test_an_oracle_and_an_estimated_point_in_one_domain_get_separate_legend_entries():
    """The like-for-like simulator point D-068 asks for must not hide behind the oracle."""
    fitted = Point("SubSim (fitted)", "subscription retention", -0.1, 30.0, 0.2, 3589)
    labels = [label for label, _ in spectrum.legend_entries([ORA, fitted])]
    assert labels == ["subscription retention (simulator, oracle)", "subscription retention"]


def test_report_stars_oracle_rows_and_only_those():
    text = spectrum.report([EST, ORA])
    assert "SubSim (churn) *" in text
    assert "Criteo *" not in text
    assert "upper bound" in text.lower()


def test_report_has_no_footnote_when_every_row_is_estimated():
    assert "*" not in spectrum.report([EST])


def test_figure_renders_from_points_alone(tmp_path):
    out = spectrum.figure_3([EST, ORA], out=tmp_path / "fig.png")
    assert out.read_bytes()[:8] == PNG_SIGNATURE
    assert out.stat().st_size > 20_000


def test_figure_renders_a_point_with_an_unknown_name_and_domain(tmp_path):
    """A new dataset must not need a code change to be drawn; the old code raised KeyError."""
    new = Point("a new experiment", "a domain never seen", 0.3, 5.0, 0.1, 10)
    out = spectrum.figure_3([EST, new], out=tmp_path / "fig.png")
    assert out.read_bytes()[:8] == PNG_SIGNATURE
