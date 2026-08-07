"""The kill test: does churn-score targeting actually destroy value?

This is the go/no-go gate on the whole project (plan §14.3). If a churn-score-ranked
retention campaign does NOT lose money here, the thesis is wrong and the honest move
is to find that out in week 3 rather than month 6.

Design choices that make this an honest test
--------------------------------------------
1. The churn model is a **real model trained on observable features only**, using a
   **strictly temporal split** (train on months < T, predict at T). Using the true
   churn probability would be a strawman -- the claim is not "churn models are
   inaccurate", it is "even an ACCURATE churn model is the wrong targeting rule".

2. The average treatment effect of the offer is **beneficial** (mean tau < 0, enforced
   by a calibration target). A blanket campaign helps on average. So any money the
   churn-score policy loses is attributable purely to *targeting*, not to a bad offer.

3. Value is measured against **doing nothing**, which is the real alternative and the
   baseline every vendor quietly omits from their case studies.

Policies compared
-----------------
``do_nothing``      treat nobody. The honest baseline.
``treat_all``       blanket campaign.
``random_k``        random k% -- isolates the value of the ranking itself.
``churn_score_k``   rank by predicted churn risk, treat top k%. What everyone does.
``oracle_uplift_k`` rank by TRUE value_of_treating. The upper bound nobody can reach.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from keel.sim.counterfactual import REFERENCE_OFFER, Offer, potential_outcomes
from keel.sim.subsim import SimResult

FEATURES = [
    "tenure_months", "mrr", "sessions_30d", "engagement_trend", "features_used",
    "support_tickets_90d", "unresolved_pain", "payment_failures_ltd",
    "seats_active_ratio", "champion_departed", "price_to_median",
]


@dataclass
class PolicyResult:
    name: str
    n_treated: int
    expected_value: float
    """Sum of -tau*clv - cost over treated. Exact expected incremental value."""
    realised_value: float
    """Sum of (y0-y1)*clv - cost over treated. What an experiment would observe."""
    offer_spend: float
    customers_saved: int
    customers_harmed: int

    @property
    def roi(self) -> float:
        return self.expected_value / self.offer_spend if self.offer_spend > 0 else 0.0


def train_churn_model(
    sim: SimResult, decision_month: int, seed: int = 0
) -> tuple[np.ndarray, float]:
    """Train a discrete-time hazard model and score customers at `decision_month`.

    Temporal split: trained only on person-period rows strictly BEFORE the decision
    month. Random splitting here would leak the future and inflate every metric --
    the single most common error in published churn work.

    Returns (risk_scores, holdout_auc).
    """
    panel = sim.panel
    train = panel[panel["month"] < decision_month]
    score = panel[panel["month"] == decision_month]

    if train.empty or score.empty or train["churn_voluntary"].nunique() < 2:
        return np.zeros(len(score)), float("nan")

    model = HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.08, max_depth=4, random_state=seed
    )
    model.fit(train[FEATURES], train["churn_voluntary"])

    # Honest generalisation estimate: score on the month AFTER training, which the
    # model has never seen.
    holdout = panel[panel["month"] == decision_month]
    auc = float("nan")
    if holdout["churn_voluntary"].nunique() > 1:
        auc = roc_auc_score(
            holdout["churn_voluntary"], model.predict_proba(holdout[FEATURES])[:, 1]
        )

    return model.predict_proba(score[FEATURES])[:, 1], auc


def _evaluate(name: str, po: pd.DataFrame, treat_mask: np.ndarray) -> PolicyResult:
    """Score a treatment assignment against the do-nothing counterfactual."""
    t = po[treat_mask]
    if t.empty:
        return PolicyResult(name, 0, 0.0, 0.0, 0.0, 0, 0)

    expected = float((-t["tau_true"] * t["clv"] - t["offer_cost"]).sum())
    realised = float(((t["y0"] - t["y1"]) * t["clv"] - t["offer_cost"]).sum())
    return PolicyResult(
        name=name,
        n_treated=int(len(t)),
        expected_value=expected,
        realised_value=realised,
        offer_spend=float(t["offer_cost"].sum()),
        customers_saved=int(((t["y0"] == 1) & (t["y1"] == 0)).sum()),
        customers_harmed=int(((t["y0"] == 0) & (t["y1"] == 1)).sum()),
    )


def run(
    sim: SimResult,
    decision_month: int = 6,
    horizon: int = 6,
    offer: Offer = REFERENCE_OFFER,
    budget_fraction: float = 0.20,
    seed: int = 0,
) -> tuple[list[PolicyResult], pd.DataFrame, float]:
    """Run the kill test. Returns (policy results, per-customer frame, model AUC)."""
    po = potential_outcomes(sim, decision_month=decision_month, horizon=horizon, offer=offer)
    risk, auc = train_churn_model(sim, decision_month, seed=seed)
    po = po.assign(predicted_risk=risk)

    n = len(po)
    k = max(int(round(budget_fraction * n)), 1)
    rng = np.random.default_rng(seed)

    def top_k(scores: np.ndarray) -> np.ndarray:
        mask = np.zeros(n, dtype=bool)
        mask[np.argsort(-scores)[:k]] = True
        return mask

    results = [
        _evaluate("do_nothing", po, np.zeros(n, dtype=bool)),
        _evaluate("treat_all", po, np.ones(n, dtype=bool)),
        _evaluate(f"random_{int(budget_fraction*100)}pct", po, top_k(rng.random(n))),
        _evaluate(
            f"churn_score_top{int(budget_fraction*100)}pct",
            po, top_k(po["predicted_risk"].to_numpy()),
        ),
        _evaluate(
            f"oracle_uplift_top{int(budget_fraction*100)}pct",
            po,
            top_k(po["value_of_treating"].to_numpy()),
        ),
        # The oracle's real advantage is not ranking but ABSTENTION: it declines to
        # treat anyone whose expected value is negative, at any budget.
        _evaluate("oracle_uplift_abstain", po, (po["value_of_treating"] > 0).to_numpy()),
    ]
    return results, po, auc


def budget_curve(
    sim: SimResult, decision_month: int = 6, horizon: int = 6, seed: int = 0
) -> pd.DataFrame:
    """Expected value vs budget for each ranking rule.

    The money analogue of a Qini curve. Qini asks "how much incremental outcome does
    my ranking capture"; this asks "how much money do I actually make", which is the
    question the business is paying to have answered.
    """
    po = potential_outcomes(sim, decision_month=decision_month, horizon=horizon)
    risk, _ = train_churn_model(sim, decision_month, seed=seed)
    po = po.assign(predicted_risk=risk)
    rng = np.random.default_rng(seed)
    rand = rng.random(len(po))

    rankings = {
        "churn_score": po["predicted_risk"].to_numpy(),
        "oracle_uplift": po["value_of_treating"].to_numpy(),
        "random": rand,
    }

    rows = []
    n = len(po)
    for frac in np.arange(0.0, 1.001, 0.05):
        k = int(round(frac * n))
        row = {"budget_fraction": frac, "n_treated": k}
        for label, scores in rankings.items():
            mask = np.zeros(n, dtype=bool)
            if k > 0:
                mask[np.argsort(-scores)[:k]] = True
            row[label] = _evaluate(label, po, mask).expected_value
        rows.append(row)
    return pd.DataFrame(rows)
