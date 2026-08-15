"""Tests for the Phase 4 sensitivity (D-055, D-056).

The point of a sensitivity is that it does not disturb the thing it is measuring. Most
of what is pinned here is therefore *absence* of change: that parameterising `run_once`
left the default path identical, and that sweeping a setting does not mutate the shared
config. A sensitivity that silently moved the baseline would be indistinguishable from
the recalibration it exists to avoid.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from retainiq.experiments.abstention import run_once, summarise
from retainiq.experiments.sensitivity import (
    TAU_BAND,
    economics,
    regret_matrix,
)
from retainiq.sim import SimConfig
from retainiq.sim.counterfactual import LADDER, REFERENCE_OFFER

# --- the sensitivity must not perturb the baseline --------------------------


def test_default_path_is_unchanged_by_parameterisation():
    """The Phase 4 headline must be reproducible by calling `run_once` with neither
    new argument. If this drifts, every number in D-054 and paper section 8 is stale."""
    bare = run_once(400, seed=1001)
    explicit = run_once(400, seed=1001, config=SimConfig(), offer=REFERENCE_OFFER)
    assert bare.keys() == explicit.keys()
    for name in bare:
        assert bare[name].realised_value == pytest.approx(explicit[name].realised_value)
        assert bare[name].n_treated == explicit[name].n_treated


def test_sweeping_a_config_does_not_mutate_the_default():
    """`SimConfig` is frozen, but `replace` on a nested field is easy to get wrong in a
    way that shares state. The default must be pristine after a sweep."""
    before = SimConfig().intervention.saveability_scale
    cfg = SimConfig()
    cfg = replace(cfg, intervention=replace(cfg.intervention, saveability_scale=-8.0))
    economics(n_customers=300, config=cfg)
    assert SimConfig().intervention.saveability_scale == before
    assert cfg.intervention.saveability_scale == -8.0


def test_offer_choice_actually_reaches_the_potential_outcomes():
    """A parameter that is accepted and then ignored is the worst kind of bug: every
    row of the ladder sensitivity would look identical and be reported as a finding."""
    cheap = economics(n_customers=1200, offer=LADDER[0])       # feature_nudge
    dear = economics(n_customers=1200, offer=LADDER[-1])       # discount_40_6mo
    assert cheap["median_cost"] < dear["median_cost"] / 100
    assert cheap["break_even"] < dear["break_even"]


# --- the economics are the economics ----------------------------------------


def test_break_even_is_below_the_oracle_treat_share():
    """Sanity on the quantity the whole diagnosis rests on: if the median break-even
    effect exceeds what the offer delivers, an oracle treats few people."""
    e = economics(n_customers=2000, offer=REFERENCE_OFFER)
    assert e["break_even"] > abs(e["mean_tau"]), "reference offer should be under water"
    assert e["pays_for"] < 0.20


def test_cheap_offer_inverts_the_break_even_relation():
    """The complement, and the reason axis 2 exists. A near-free offer clears its own
    break-even for most customers even though its effect is smaller."""
    e = economics(n_customers=2000, offer=LADDER[0])
    assert e["break_even"] < abs(e["mean_tau"])
    assert e["pays_for"] > 0.40


def test_larger_effect_raises_the_oracle_share_and_kills_sleeping_dogs():
    """The trade that axis 1 exists to expose. Both halves are asserted, because
    reporting only the first is how a sensitivity becomes a sales pitch."""
    cfg = SimConfig()
    weak = economics(n_customers=2000, config=cfg)
    strong_cfg = replace(cfg, intervention=replace(cfg.intervention, saveability_scale=-8.0))
    strong = economics(n_customers=2000, config=strong_cfg)
    assert strong["pays_for"] > weak["pays_for"]
    assert strong["sleeping_dog"] < weak["sleeping_dog"] / 2


def test_in_band_flag_tracks_the_calibration_gate():
    cfg = SimConfig()
    assert economics(n_customers=1500, config=cfg)["in_band"]
    out = replace(cfg, intervention=replace(cfg.intervention, saveability_scale=-12.0))
    e = economics(n_customers=1500, config=out)
    assert not e["in_band"]
    assert e["mean_tau"] < TAU_BAND[0]


# --- reporting ---------------------------------------------------------------


def test_ties_and_wins_are_counted_separately():
    """A rule that treats nobody scores exactly 0. Conflating that with a loss would
    hide the safety property; conflating it with a win would invent one."""
    frame = pd.DataFrame([
        {"n_customers": 500, "seed": s, "policy": p, "value": v,
         "n_treated": 0, "n_harmed": 0, "n_eligible": 100}
        for s, vals in enumerate([{"abstention": 0.0, "top_k_expected_value": -5.0,
                                   "treat_all": 3.0, "random_30pct": -1.0},
                                  {"abstention": 4.0, "top_k_expected_value": -5.0,
                                   "treat_all": -2.0, "random_30pct": -1.0}])
        for p, v in vals.items()
    ])
    s = summarise(frame)
    assert s["abstain_positive"].iloc[0] == pytest.approx(0.5)
    assert s["abstain_ties"].iloc[0] == pytest.approx(0.5)
    assert s["abstain_not_worse"].iloc[0] == pytest.approx(1.0)
    assert s["treat_all_positive"].iloc[0] == pytest.approx(0.5)


def test_regret_is_normalised_and_the_best_policy_scores_zero():
    rm = regret_matrix([("default", {})], sizes=(300,), seeds=2)
    cols = [c for c in rm.columns if c.startswith("regret_")]
    vals = rm[cols].to_numpy()
    assert np.nanmin(vals) == pytest.approx(0.0), "the best policy has zero regret"
    assert np.nanmax(vals) == pytest.approx(1.0), "the worst policy has regret 1"
    assert ((vals >= -1e-9) & (vals <= 1 + 1e-9)).all()


def test_tied_alphas_are_reported_as_undetermined():
    """At a sample size where no alpha can act, every arm scores exactly zero. Taking
    `max` would name the first one and invent a preference the data does not contain."""
    from retainiq.experiments.sensitivity import alpha_by_offer

    d = alpha_by_offer(alphas=(0.05, 0.49), sizes=(200,), seeds=1)
    tied = d[~d["determinate"]]
    assert d["determinate"].isin([True, False]).all()
    assert tied["best_alpha"].isna().all(), "a tie must not be reported as a winner"
