"""Tests for the public-benchmark harness.

Dataset-dependent tests skip when the data has not been downloaded, so the suite
still runs offline and in CI. The estimator and model logic is tested on synthetic
RCTs with known ground truth, which does not need the download at all -- that is
where the correctness risk actually lives.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from keel.benchmarks.datasets import (
    CRITEO_BYTES,
    CRITEO_REFERENCE,
    DATA_DIR,
    LENTA_BYTES,
    RCT,
    check_representative,
    load_criteo,
    load_hillstrom,
    load_lenta,
)
from keel.benchmarks.evaluate import (
    abstention_sweep,
    evaluate_policy,
    qini_coefficient,
    qini_curve,
    random_baseline,
    top_k_mask,
    uplift_of_set,
)
from keel.benchmarks.models import ALL_TARGETERS, ClassTransform, SLearner, TLearner
from keel.benchmarks.run import split


def _complete(name: str, expect_bytes: int | None = None) -> bool:
    """Is this dataset present AND fully downloaded?

    Existence is not completeness. A download in progress leaves a file that exists,
    passes `.exists()`, and then fails to parse -- which is exactly how these tests
    started erroring mid-download. For the compressed sets the expected byte count is
    known, so check it rather than trusting the path.
    """
    path = DATA_DIR / name
    if not path.exists():
        return False
    return expect_bytes is None or path.stat().st_size == expect_bytes


HAS_DATA = _complete("hillstrom.csv")
HAS_CRITEO = _complete("criteo-uplift-v2.1.csv.gz", CRITEO_BYTES)
HAS_LENTA = _complete("lenta_dataset.csv.gz", LENTA_BYTES)

needs_data = pytest.mark.skipif(not HAS_DATA, reason="hillstrom.csv not downloaded")
needs_criteo = pytest.mark.skipif(not HAS_CRITEO, reason="criteo not fully downloaded")
needs_lenta = pytest.mark.skipif(not HAS_LENTA, reason="lenta not fully downloaded")


# --- synthetic RCT with known truth -----------------------------------------


def make_rct(n=4000, seed=0, effect=0.15, harm_fraction=0.0) -> RCT:
    """A randomised trial where we control the treatment effect exactly.

    `harm_fraction` creates a sleeping-dog segment -- customers whose outcome the
    treatment makes *worse* -- so the estimator can be tested on data that actually
    contains the phenomenon Hillstrom lacks.
    """
    rng = np.random.default_rng(seed)
    x = rng.random(n)
    t = rng.integers(0, 2, n)

    base = 0.2 + 0.3 * x
    harmed = x < harm_fraction
    tau = np.where(harmed, -effect, effect)

    p = np.clip(base + t * tau, 0.01, 0.99)
    y = (rng.random(n) < p).astype(float)

    return RCT(
        name="synthetic",
        X=pd.DataFrame({"x": x, "noise": rng.normal(size=n)}),
        treatment=t,
        outcome=y,
        outcome_name="response",
    )


# --- the estimator ----------------------------------------------------------


def test_uplift_of_set_recovers_a_known_effect():
    rct = make_rct(n=20000, effect=0.15)
    everyone = np.ones(len(rct), dtype=bool)
    assert uplift_of_set(rct.treatment, rct.outcome, everyone) == pytest.approx(0.15, abs=0.02)


def test_uplift_of_set_detects_harm():
    """The estimator must be able to report a negative effect at all."""
    rct = make_rct(n=20000, effect=0.15, harm_fraction=1.0)
    everyone = np.ones(len(rct), dtype=bool)
    assert uplift_of_set(rct.treatment, rct.outcome, everyone) < -0.10


def test_uplift_is_nan_when_an_arm_is_missing():
    """No control counterpart means no comparison. Returning 0 would understate
    rather than flag the gap."""
    rct = make_rct(n=500)
    only_treated = rct.treatment == 1
    assert np.isnan(uplift_of_set(rct.treatment, rct.outcome, only_treated))


def test_top_k_mask_selects_exactly_k():
    scores = np.array([0.5, 0.1, 0.9, 0.3])
    assert top_k_mask(scores, 2).sum() == 2
    assert top_k_mask(scores, 2)[2]  # highest score selected
    assert top_k_mask(scores, 0).sum() == 0


def test_random_baseline_matches_the_overall_effect():
    """Random selection should recover the average treatment effect, since a random
    subset is representative by construction."""
    rct = make_rct(n=20000, effect=0.15)
    r = random_baseline(rct, budget_fraction=0.3, n_repeats=100)
    assert r.uplift_per_contact == pytest.approx(0.15, abs=0.03)


def test_qini_is_positive_for_a_ranking_that_works():
    rct = make_rct(n=8000, effect=0.15, harm_fraction=0.3)
    # Oracle-ish score: the harmed segment is exactly x < 0.3.
    scores = rct.X["x"].to_numpy()
    assert qini_coefficient(qini_curve(scores, rct)) > 0


def test_qini_is_negative_for_a_ranking_that_is_backwards():
    """The metric must be able to say 'worse than random', or it cannot express the
    outcome this project is about."""
    rct = make_rct(n=8000, effect=0.15, harm_fraction=0.3)
    backwards = -rct.X["x"].to_numpy()  # targets the harmed segment first
    assert qini_coefficient(qini_curve(backwards, rct)) < 0


def test_evaluate_policy_returns_a_usable_interval():
    rct = make_rct(n=6000)
    r = evaluate_policy("test", rct.X["x"].to_numpy(), rct, 0.3, n_boot=100)
    assert r.ci_low < r.incremental_outcome < r.ci_high
    assert r.n_targeted == pytest.approx(0.3 * len(rct), rel=0.02)


def test_abstention_sweep_is_monotone_in_selection():
    rct = make_rct(n=4000)
    sweep = abstention_sweep(rct.X["x"].to_numpy(), rct)
    assert sweep["n_targeted"].is_monotonic_decreasing


# --- models -----------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_TARGETERS, ids=[c.name for c in ALL_TARGETERS])
def test_every_targeter_fits_and_scores(cls):
    rct = make_rct(n=2000)
    model = cls(seed=0).fit(rct.X, rct.treatment, rct.outcome)
    scores = model.score(rct.X)
    assert len(scores) == len(rct)
    assert np.isfinite(scores).all()


@pytest.mark.parametrize("cls", [TLearner, SLearner, ClassTransform])
def test_uplift_models_rank_a_harmed_segment_last(cls):
    """With a large, clearly separated harmed segment, an uplift model must put it
    at the bottom. If it cannot do this, it is not measuring a treatment effect."""
    rct = make_rct(n=12000, effect=0.25, harm_fraction=0.35, seed=1)
    model = cls(seed=0).fit(rct.X, rct.treatment, rct.outcome)
    scores = model.score(rct.X)

    harmed = rct.X["x"].to_numpy() < 0.35
    assert scores[harmed].mean() < scores[~harmed].mean()


def test_uplift_models_beat_outcome_models_when_harm_exists():
    """The core claim, on synthetic data where the mechanism is present by
    construction. Hillstrom cannot test this because it has no harmed segment."""
    from keel.benchmarks.models import OutcomePropensity

    rct = make_rct(n=12000, effect=0.25, harm_fraction=0.35, seed=2)
    k_frac = 0.3

    up = SLearner(seed=0).fit(rct.X, rct.treatment, rct.outcome).score(rct.X)
    out = OutcomePropensity(seed=0).fit(rct.X, rct.treatment, rct.outcome).score(rct.X)

    u_up = evaluate_policy("up", up, rct, k_frac, n_boot=50).incremental_outcome
    u_out = evaluate_policy("out", out, rct, k_frac, n_boot=50).incremental_outcome
    assert u_up > u_out


# --- the real dataset -------------------------------------------------------


@needs_data
def test_hillstrom_loads_with_expected_shape():
    rct = load_hillstrom()
    assert len(rct) > 40_000
    assert set(np.unique(rct.treatment)) == {0, 1}
    assert 0.45 < rct.treatment.mean() < 0.55, "arms should be balanced"


@needs_data
def test_hillstrom_has_no_post_treatment_covariates():
    """`visit`, `conversion` and `spend` are measured after assignment. If any
    leaked into X, the randomisation argument collapses."""
    rct = load_hillstrom()
    forbidden = {"visit", "conversion", "spend", "segment"}
    assert forbidden.isdisjoint(set(rct.X.columns))


@needs_data
def test_hillstrom_treatment_effect_is_positive():
    """Documented result: the campaign raises visits substantially."""
    rct = load_hillstrom()
    ate = rct.outcome[rct.treatment == 1].mean() - rct.outcome[rct.treatment == 0].mean()
    assert 0.03 < ate < 0.06


@needs_data
def test_hillstrom_has_no_sleeping_dogs():
    """Regression test on the key scoping finding.

    Every decile of predicted uplift has POSITIVE true uplift. This is why
    Hillstrom cannot test the worse-than-random claim: the precondition -- a
    negative-uplift segment -- does not exist in this dataset."""
    from keel.benchmarks.run import split

    rct = load_hillstrom()
    train, test = split(rct, seed=0)
    scores = TLearner(seed=0).fit(train.X, train.treatment, train.outcome).score(test.X)

    q = np.quantile(scores, [0.0, 0.1])
    bottom = (scores >= q[0]) & (scores < q[1])
    assert uplift_of_set(test.treatment, test.outcome, bottom) > 0


@needs_data
def test_subsample_preserves_balance():
    rct = load_hillstrom()
    small = rct.subsample(1000, seed=0)
    assert 900 < len(small) < 1100
    assert abs(small.treatment.mean() - rct.treatment.mean()) < 0.05


# --- Criteo -----------------------------------------------------------------


def test_representativeness_check_rejects_single_arm():
    """The guard that saved us. Criteo's file is sorted by treatment, so a prefix
    read yields 100% treated rows and uplift becomes undefined -- not noisy,
    undefined. This must be caught, not averaged over."""
    all_treated = pd.DataFrame({
        "treatment": np.ones(1000, dtype=int),
        "visit": np.zeros(1000),
        "conversion": np.zeros(1000),
    })
    checks = check_representative(all_treated, CRITEO_REFERENCE)
    assert checks["treatment_rate"][0] == 1.0
    assert not checks["treatment_rate"][2], "a single-arm sample must fail the check"


def test_representativeness_check_accepts_a_valid_sample():
    """Complement: the check must not reject good data, or it is useless."""
    rng = np.random.default_rng(0)
    n = 200_000
    good = pd.DataFrame({
        "treatment": (rng.random(n) < 0.85).astype(int),
        "visit": (rng.random(n) < 0.047).astype(float),
        "conversion": (rng.random(n) < 0.0029).astype(float),
    })
    assert all(ok for _, _, ok in check_representative(good, CRITEO_REFERENCE).values())


@needs_criteo
def test_criteo_loads_with_expected_shape():
    rct = load_criteo(sample_rows=200_000, seed=0)
    assert len(rct) == 200_000
    assert set(np.unique(rct.treatment)) == {0, 1}
    assert 0.80 < rct.treatment.mean() < 0.90, "Criteo is 85/15, not balanced"


@needs_criteo
def test_criteo_excludes_exposure_from_covariates():
    """`exposure` records whether the ad was actually served -- decided AFTER
    randomisation and correlated with behaviour. Using it as a feature silently
    converts a clean RCT into observational data."""
    rct = load_criteo(sample_rows=50_000, seed=0)
    assert "exposure" not in rct.X.columns
    assert {"visit", "conversion", "treatment"}.isdisjoint(set(rct.X.columns))
    assert list(rct.X.columns) == [f"f{i}" for i in range(12)]


@needs_criteo
def test_criteo_sampling_is_random_not_prefix():
    """Two different seeds must give different rows. If sampling were a prefix,
    every seed would return the same (all-treated) block."""
    a = load_criteo(sample_rows=100_000, seed=0)
    b = load_criteo(sample_rows=100_000, seed=1)
    assert not np.array_equal(a.X.to_numpy(), b.X.to_numpy())
    for r in (a, b):
        assert 0.80 < r.treatment.mean() < 0.90


@needs_criteo
def test_criteo_treatment_effect_is_positive():
    rct = load_criteo(sample_rows=1_000_000, seed=0)
    ate = rct.outcome[rct.treatment == 1].mean() - rct.outcome[rct.treatment == 0].mean()
    assert 0.005 < ate < 0.020


@needs_criteo
def test_criteo_uplift_is_coupled_to_propensity():
    """Regression test on the organising finding.

    On Criteo, estimated treatment effect correlates strongly with outcome
    propensity, so both rank the same customers and uplift modelling adds little.
    This is the opposite of the churn setting and it is why the claim needed
    scoping."""
    rct = load_criteo(sample_rows=400_000, seed=0)
    train, test = split(rct, seed=0)
    from keel.benchmarks.models import OutcomePropensity

    tau = TLearner(seed=0).fit(train.X, train.treatment, train.outcome).score(test.X)
    prop = OutcomePropensity(seed=0).fit(train.X, train.treatment, train.outcome).score(test.X)
    assert np.corrcoef(tau, prop)[0, 1] > 0.3


# --- Lenta ------------------------------------------------------------------


@needs_lenta
def test_lenta_loads_with_expected_shape():
    rct = load_lenta(sample_rows=50_000, seed=0)
    assert len(rct) == 50_000
    assert set(np.unique(rct.treatment)) == {0, 1}
    assert 0.70 < rct.treatment.mean() < 0.80, "Lenta is ~75/25"


@needs_lenta
def test_lenta_excludes_the_outcome_and_group_columns():
    """`group` is the treatment assignment and `response_att` the outcome. Either
    one leaking into X would make the whole thing circular."""
    rct = load_lenta(sample_rows=20_000, seed=0)
    forbidden = {"group", "response_att", "client_id", "CardHolder"}
    assert forbidden.isdisjoint(set(rct.X.columns))


@needs_lenta
def test_lenta_features_are_finite():
    """Lenta has many sparse purchase statistics; NaNs must not reach the learners."""
    rct = load_lenta(sample_rows=20_000, seed=0)
    assert np.isfinite(rct.X.to_numpy(dtype=float)).all()


@needs_lenta
def test_lenta_response_rate_matches_published():
    rct = load_lenta(sample_rows=100_000, seed=0)
    assert 0.05 < rct.outcome.mean() < 0.15, "published response rate is ~10%"


@needs_lenta
def test_lenta_feature_count_is_capped():
    """Capped for cross-dataset comparability: Lenta has ~190 columns against
    Criteo's 12, and letting it use all of them would confound 'more features'
    with 'different domain' in the correlation comparison."""
    rct = load_lenta(sample_rows=20_000, seed=0, max_features=30)
    assert len(rct.X.columns) <= 30
