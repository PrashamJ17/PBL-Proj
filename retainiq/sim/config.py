"""SubSim configuration.

Every generative parameter lives here, named and documented. Paper 1's contribution
is the *calibration* of these against public benchmark aggregates, so they must never
be buried as magic numbers inside the simulation loop.

Sign convention: all `beta_*` coefficients are on the monthly churn-hazard logit.
Positive => raises churn hazard. Negative => protective.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HazardParams:
    """Coefficients of the monthly voluntary-churn hazard (logit scale)."""

    intercept: float = -3.8125
    """Baseline monthly churn logit.

    NOT hand-picked: solved by `calibration.calibrate_intercept` to hit 4.5%
    monthly voluntary churn averaged over seeds. Re-run that solver after changing
    any other hazard coefficient or latent distribution, since they all shift the
    mean hazard."""

    beta_price: float = 1.5
    """Price sensitivity x price pressure. The classic 'too expensive' driver."""

    beta_habit: float = -1.9
    """Habit strength is protective. Spotify/Prime lesson: habit beats prediction."""

    beta_adoption: float = -1.6
    """Feature-adoption breadth is protective. The Amazon Prime 'benefit attach
    rate' effect: members using several benefits churn dramatically less."""

    beta_engagement_decay: float = 2.2
    """Accumulated engagement decay. The dominant observable churn signal --
    and, deliberately, also the signal most confounded with sleeping dogs."""

    beta_champion_lost: float = 2.4
    """B2B: the buyer left the company. Frequently the single strongest predictor,
    and almost never in anyone's model."""

    beta_budget_shock: float = 2.8
    """Exogenous budget shock. Largely unsaveable -> generates Lost Causes."""

    beta_tenure_early: float = 1.3
    """Early-tenure hazard spike (failure-to-activate), decays with tenure."""

    tenure_decay_months: float = 4.0
    """Months over which the early-tenure spike decays."""

    beta_support_pain: float = 0.9
    """Unresolved support friction."""


@dataclass(frozen=True)
class InterventionParams:
    """Counterfactual response to a retention offer (effect on churn-hazard logit).

    The four uplift quadrants emerge from the interaction of two opposing forces:

      saveability  -- the offer addresses a real, addressable reason for leaving
                      => LOWERS churn hazard  (Persuadables)
      salience     -- being contacted reminds a dormant payer that they are paying
                      => RAISES churn hazard  (Sleeping Dogs)

    The whole thesis rests on the fact that `salience` loads on LOW engagement,
    which is also the strongest *predictive* churn signal. So a churn-score-ranked
    campaign concentrates its budget precisely on the customers it harms.
    """

    saveability_scale: float = -2.0
    """Max protective effect of a well-matched offer, on the hazard logit."""

    salience_scale: float = 1.8
    """Max harmful effect of contacting a dormant, low-attention payer.

    Calibrated so Sleeping Dogs are ~17% of the base -- a minority segment, which
    is what the uplift literature actually reports. An earlier value of 2.6 put
    them at 30% and made the average treatment effect *negative*; that would have
    made the headline result trivially easy and, fairly, invited the charge that
    the simulator was tuned to flatter the method.

    At 1.8 the average treatment effect is BENEFICIAL (mean tau ~ -0.010): a
    blanket campaign helps on average. Any demonstration that churn-score
    targeting loses money must therefore come purely from bad *targeting*, not
    from the offer being bad. That is the harder claim and the one worth making."""

    price_match_weight: float = 0.65
    """How much of saveability comes from the offer matching a price objection."""

    risk_match_weight: float = 0.35
    """How much comes from the customer being genuinely at risk and reachable."""

    unsaveable_damping: float = 0.15
    """Residual saveability when the churn cause is exogenous (champion lost,
    budget shock). Near zero -> Lost Causes really are lost."""


@dataclass(frozen=True)
class EconomicsParams:
    """Unit economics. Currency-agnostic; interpret as your tenant's currency."""

    mrr_lognormal_mu: float = 4.0
    """log-scale mean of MRR. exp(4.0) ~ 55/mo median."""

    mrr_lognormal_sigma: float = 0.8
    """MRR dispersion. Real SMB customer bases are heavily right-skewed."""

    gross_margin: float = 0.80
    """Typical SaaS gross margin."""

    monthly_discount_rate: float = 0.01
    """For discounting future margin into CLV."""

    offer_discount_pct: float = 0.20
    """Depth of the modelled retention discount."""

    offer_discount_months: int = 3
    """Duration of the modelled retention discount."""

    contact_fixed_cost: float = 0.50
    """Per-contact cost (email/SMS/ops overhead), independent of the discount."""


@dataclass(frozen=True)
class PaymentParams:
    """Involuntary churn -- 20-40% of all churn, and the fastest ROI in the stack."""

    monthly_failure_rate: float = 0.035
    """Probability an invoice fails in a given month. B2B corporate cards run
    4-6% per invoice; B2C debit/prepaid runs 8-15%. Set toward the low end of the
    blended band so that involuntary churn lands mid-range (~30%) as a share of
    total churn rather than dominating it."""

    passive_recovery_rate: float = 0.42
    """Recovery with processor-native retries only. Median operators sit 30-45%."""

    smart_recovery_rate: float = 0.62
    """Recovery with decline-code-aware retry timing + multi-touch dunning.
    Top-quartile operators reach 55-70%."""


@dataclass(frozen=True)
class SimConfig:
    """Top-level SubSim configuration."""

    n_customers: int = 2_000
    """Deliberately small by ML standards. The entire thesis is about small n."""

    n_months: int = 24
    """Observation window."""

    seed: int = 7

    hazard: HazardParams = field(default_factory=HazardParams)
    intervention: InterventionParams = field(default_factory=InterventionParams)
    economics: EconomicsParams = field(default_factory=EconomicsParams)
    payments: PaymentParams = field(default_factory=PaymentParams)

    # --- Population composition -------------------------------------------------
    champion_turnover_monthly: float = 0.018
    """Monthly probability the B2B champion leaves."""

    budget_shock_monthly: float = 0.012
    """Monthly probability of an exogenous budget shock."""

    attention_engagement_corr: float = 0.6
    """Correlation between `attention` and baseline engagement.

    This is the most consequential single parameter in the simulator. It controls
    how much the sleeping-dog population overlaps with the high-churn-score
    population. At 0 the naive policy is merely wasteful; at high values it is
    actively value-destroying. Sensitivity analysis over this parameter is a
    required figure in paper 2."""
