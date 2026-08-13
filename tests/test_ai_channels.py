"""Tests for the AI-outreach channel analysis (D-064).

The commercial argument for automated retention is cost per contact. These tests pin the
finding that cost per contact is not the binding constraint — salience is — and that the
relationship runs the opposite way to the intuition automation encourages.
"""

from __future__ import annotations

import pytest

from keel.experiments.ai_channels import (
    AI_CALL_COST,
    AI_CALL_SAVEABILITY,
    break_even_salience,
    sweep,
)
from keel.sim import SimConfig, simulate
from keel.sim.counterfactual import Offer, potential_outcomes


@pytest.fixture(scope="module")
def frame():
    return sweep(n_customers=2500, seed=7)


def _voice(sim, salience):
    return potential_outcomes(sim, 6, 6, offer=Offer(
        "probe", 2, 0.0, 0, AI_CALL_COST,
        saveability_multiplier=AI_CALL_SAVEABILITY, salience_multiplier=salience))


def test_cheaper_wins_only_when_salience_is_unchanged(frame):
    """The automation argument is valid on its own terms: at matched intrusiveness, a
    twelve-times-cheaper channel does beat the human one. The case fails on salience,
    not on arithmetic, and the test says so rather than dismissing the premise."""
    human = frame[frame.channel == "human_checkin_call"].iloc[0]
    ai_matched = frame[frame.channel == "ai_voice_call(sal=0.55)"].iloc[0]
    assert ai_matched.cost < human.cost / 10
    assert ai_matched.treat_all_per_customer > human.treat_all_per_customer


def test_raising_salience_reverses_the_sign(frame):
    """Same price, same effectiveness, only intrusiveness changes — and the channel goes
    from earning money to destroying it."""
    cheap = frame[frame.channel == "ai_voice_call(sal=0.55)"].iloc[0]
    loud = frame[frame.channel == "ai_voice_call(sal=2.0)"].iloc[0]
    assert cheap.cost == loud.cost
    assert cheap.treat_all_per_customer > 0
    assert loud.treat_all_per_customer < 0


def test_harm_and_value_are_monotone_in_salience():
    sim = simulate(SimConfig(n_customers=2000, n_months=24, seed=7))
    harmed, value = [], []
    for s in (0.5, 1.0, 1.5, 2.0, 2.5):
        po = _voice(sim, s)
        harmed.append(float((po["tau_true"] > 0).mean()))
        value.append(float(po["value_of_treating"].mean()))
    assert harmed == sorted(harmed), "more intrusion must not harm fewer people"
    assert value == sorted(value, reverse=True)


def test_break_even_salience_is_below_neutral():
    """The headline. Break-even sits *below* 1.0, so a channel merely as intrusive as a
    standard retention offer already loses money when used on everyone. An unsolicited
    synthetic voice call is not plausibly less intrusive than that."""
    t = break_even_salience(n_customers=2500, seed=7)
    assert 0.0 < t < 1.0


def test_selection_matters_more_as_the_actuator_gets_louder(frame):
    """The perverse dynamic. A nearly-free channel removes the felt need to choose
    whom to contact, and choosing correctly becomes *more* important, not less."""
    quiet = frame[frame.channel == "ai_voice_call(sal=0.55)"].iloc[0]
    loud = frame[frame.channel == "ai_voice_call(sal=3.0)"].iloc[0]
    assert loud.oracle_share < quiet.oracle_share / 2


def test_low_salience_ai_email_is_not_the_problem(frame):
    """The finding is about intrusiveness, not about AI. A written, low-salience channel
    remains positive and is worth automating."""
    email = frame[frame.channel == "ai_email"].iloc[0]
    assert email.treat_all_per_customer > 0
    assert email.oracle_share > 0.5


def test_the_sweep_covers_both_signs(frame):
    """A sweep that never crosses zero would not have located anything."""
    v = frame[frame.channel.str.startswith("ai_voice")].treat_all_per_customer
    assert (v > 0).any() and (v < 0).any()
