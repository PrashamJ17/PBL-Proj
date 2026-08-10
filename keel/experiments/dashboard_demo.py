"""Generate the retention dashboard end to end from a simulated tenant.

`make dashboard`. Runs the whole Phase 5 path in the order a real tenant would: simulate
a business, run a randomised multi-arm pilot on half of it, fit per-rung effects, choose
a rung per customer, explain every choice, and write the page.

It exists so the dashboard is reproducible rather than a screenshot, and so the numbers
on it are the numbers the gate experiment measured -- not a mock-up that quietly looks
better than the thing it depicts.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from keel.experiments.abstention import FEATURES
from keel.experiments.ladder import _multi_arm_frame
from keel.policy.economics import _expit, benefit_posterior
from keel.policy.ladder import LadderOptimiser
from keel.report.dashboard import render_dashboard
from keel.report.reasons import explain
from keel.sim import SimConfig, simulate
from keel.sim.counterfactual import LADDER

RELIABILITY = (
    "This engine chose better than a single well-chosen offer on <strong>58% of "
    "tests</strong> (95% confidence: 42%&ndash;72%). That is better than guessing, and "
    "it is <strong>not</strong> statistically distinguishable from a coin flip (D-058)."
)


def build(
    n_customers: int = 1500,
    seed: int = 5,
    risk_aversion: float = 0.0,
    budget: float | None = 0.30,
    out: Path | None = None,
) -> Path:
    sim = simulate(SimConfig(n_customers=n_customers, n_months=24, seed=seed))
    frame = _multi_arm_frame(sim, decision_month=6, horizon=6, seed=seed)

    rng = np.random.default_rng(seed + 4211)
    is_train = rng.random(len(frame)) < 0.5
    train, test = frame[is_train], frame[~is_train]

    K = len(LADDER)
    arm = rng.integers(0, K + 1, len(train))
    y = np.where(
        arm == 0,
        train["y0"].to_numpy(),
        np.choose(np.clip(arm - 1, 0, K - 1),
                  [train[f"y1_{k}"].to_numpy() for k in range(K)]),
    )

    opt = LadderOptimiser(risk_aversion=risk_aversion, budget=budget,
                          seed=seed).fit(train[FEATURES], arm, y, K)

    value = test["clv"].to_numpy()
    costs = np.column_stack([test[f"cost_{k}"].to_numpy() for k in range(K)])
    rec = opt.recommend(test[FEATURES], value, costs)

    # Baseline risk and the probability effect of the chosen rung, for the money line.
    eta0, _ = opt.models_[0].joint_samples(test[FEATURES], n_samples=300, seed=seed)
    p0 = _expit(eta0).mean(axis=1)
    delta_p = np.zeros(len(test))
    for k in range(K):
        m = rec.rung == k
        if m.any():
            delta_p[m] = benefit_posterior(
                opt.models_[k], test[FEATURES][m], value[m], costs[m, k],
                n_samples=300, seed=seed,
            ).mean_delta_p

    reasons = explain(
        rec, opt.models_[0], test[FEATURES], [o.name for o in LADDER],
        value, costs, baseline_risk=p0, delta_p=delta_p,
        reliability_note=(
            "Beat a single well-chosen offer on 58% of tests (D-058) -- "
            "better than guessing, not proven"
        ),
    )

    return render_dashboard(
        reasons,
        offer_names=[o.name for o in LADDER],
        business_name=f"Demo tenant ({n_customers:,} customers)",
        ids=test["customer_id"].tolist(),
        reliability=RELIABILITY,
        out=out or Path("retention_dashboard.html"),
    )


if __name__ == "__main__":
    p = build()
    print(f"wrote {p.resolve()}")
