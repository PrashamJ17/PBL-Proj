"""Tests for SubSim.

The most important test in this file is `test_latents_do_not_leak_into_panel`.
Everything else checks that the simulator is realistic; that one checks that it is
*fair*. A simulator whose observable panel carries the latents is not a test bench,
it is an answer key, and every downstream causal result computed on it would be
worthless.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from retainiq.sim import SimConfig, simulate
from retainiq.sim.calibration import TARGETS, measure, sweep_seeds

CFG = SimConfig(n_customers=1500, n_months=24, seed=7)


@pytest.fixture(scope="module")
def result():
    return simulate(CFG)


# --- fairness ---------------------------------------------------------------


def test_latents_do_not_leak_into_panel(result):
    """No latent trait may appear as an observable column.

    Models see `panel`. If a latent leaked in, a model could read the generative
    process directly and every uplift comparison downstream would be meaningless.
    """
    latent_names = {
        "price_sensitivity",
        "habit_strength",
        "engagement_base",
        "engagement_decay",
        "attention",
        "feature_adoption_breadth",
        "champion_stability",
        "budget_fragility",
    }
    assert latent_names.isdisjoint(set(result.panel.columns))


def test_no_observable_is_a_perfect_proxy_for_attention(result):
    """`attention` must remain only partially inferable from observables.

    If any single observable recovered `attention` almost exactly, detecting
    sleeping dogs would be trivial and uplift modelling would be unnecessary --
    the simulator would have assumed away the problem it exists to pose.
    """
    snap = result.snapshot(month=6)
    attention = result.latents.attention[snap["customer_id"].to_numpy()]
    numeric = snap.select_dtypes(include=[np.number]).drop(columns=["customer_id"])

    for col in numeric.columns:
        v = numeric[col].to_numpy()
        if np.std(v) < 1e-9:
            continue
        r = abs(np.corrcoef(v, attention)[0, 1])
        assert r < 0.95, f"{col} is a near-perfect proxy for attention (r={r:.3f})"


# --- reproducibility --------------------------------------------------------


def test_simulation_is_deterministic_given_seed():
    a = simulate(CFG).panel
    b = simulate(CFG).panel
    assert a.equals(b)


def test_different_seeds_give_different_data():
    a = simulate(CFG).panel
    b = simulate(replace(CFG, seed=CFG.seed + 1)).panel
    assert not a.equals(b)


# --- realism ----------------------------------------------------------------


def test_meets_all_calibration_targets(result):
    stats = measure(result)
    failures = [
        f"{t.name}={stats[t.name]:.4f} outside [{t.low}, {t.high}]"
        for t in TARGETS
        if not (t.low <= stats[t.name] <= t.high)
    ]
    assert not failures, "; ".join(failures)


def test_calibration_is_stable_across_seeds():
    """A simulator calibrated on one lucky seed is not calibrated."""
    stats = sweep_seeds(replace(CFG, n_customers=1200), n_seeds=5)
    for t in TARGETS:
        mean, _ = stats[t.name]
        assert t.low <= mean <= t.high, f"{t.name} mean {mean:.4f} outside target"


def test_voluntary_and_involuntary_churn_are_disjoint(result):
    """A customer cannot churn both ways in the same month."""
    both = result.panel["churn_voluntary"] & result.panel["churn_involuntary"]
    assert both.sum() == 0


def test_censoring_exists(result):
    """Right-censored customers must exist and be flagged.

    Without censoring there is nothing for survival analysis to handle, and the
    project's core modelling argument would be untestable.
    """
    assert result.customers["censored"].sum() > 0
    assert (result.customers.loc[result.customers["censored"], "churn_month"] == -1).all()


def test_hazard_declines_with_tenure(result):
    """Fragile customers leave first, so the surviving pool gets hardier."""
    panel = result.panel
    early = panel[panel["month"] < 6]["churn_voluntary"].mean()
    late = panel[panel["month"] >= 12]["churn_voluntary"].mean()
    assert early > late


def test_low_engagement_predicts_churn(result):
    """Engagement must be the dominant observable churn signal.

    This is what makes a naive churn model rank low-engagement customers highest --
    the precondition for the sleeping-dog failure the project is built around.
    """
    panel = result.panel
    churned = panel[panel["churn_voluntary"] == 1]["sessions_30d"].mean()
    stayed = panel[panel["churn_voluntary"] == 0]["sessions_30d"].mean()
    assert churned < stayed


def test_panel_only_contains_at_risk_rows(result):
    """Once a customer churns they must stop appearing in the panel."""
    panel = result.panel.sort_values(["customer_id", "month"])
    last_month = panel.groupby("customer_id")["month"].max()
    churned = result.customers[~result.customers["censored"]].set_index("customer_id")
    common = churned.index.intersection(last_month.index)
    assert (last_month.loc[common] == churned.loc[common, "churn_month"]).all()
