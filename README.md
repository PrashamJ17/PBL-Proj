# Keel

**Causal retention decisioning for small subscription businesses.**

> Churn prediction is solved. Retention *decisioning under small-sample causal
> uncertainty* is not.

A business with 800 customers cannot reliably estimate individual treatment effects.
Existing uplift methods either overfit catastrophically at that scale or collapse to
blanket targeting. Keel is a Bayesian, margin-aware retention decision engine that is
explicitly uncertainty-aware at small *n* — and that **abstains** when the evidence is
too thin.

We don't predict churn. We decide who to save, what to spend, and prove what it earned.

---

## The result this project is built on

A retention campaign targeted by churn score **loses money** — and loses *more than
targeting at random*. Verified 6/6 seeds, against a real gradient-boosted churn model
(holdout AUC ≈ 0.70) trained on observables with a strictly temporal split.

![Kill test](papers/figures/fig01_kill_test.png)

At a 20% budget on a 3,589-customer base:

| policy | treated | expected value | harmed |
|---|---:|---:|---:|
| do nothing | 0 | 0 | 0 |
| treat everyone | 3,589 | **−89,869** | 44 |
| random 20% | 718 | −17,035 | 9 |
| **churn-score top 20%** | 718 | **−22,123** | 19 |
| oracle uplift top 20% | 718 | +5,877 | 0 |
| **oracle uplift w/ abstention** | **209** | **+8,610** | **0** |

Three findings:

1. **A churn score is anti-informative for targeting.** Random targeting is merely
   uninformed. A churn score actively sorts *toward* the customers an offer harms —
   sleeping dogs are 48% of the top risk decile vs 2% of the bottom.
2. **Abstention beats ranking.** Treating 209 customers earns more than treating 718.
3. **Improving churn-model AUC can worsen business outcomes** under top-*k* targeting.
   The better the model gets at its own job, the more precisely it finds sleeping dogs.

The setup is deliberately adverse to the thesis: the offer's *average* treatment effect
is **beneficial** (mean τ = −0.010, enforced by a calibration gate). Every rupee lost is
attributable to targeting, not to a bad offer.

---

## Quickstart

```bash
pip install -e .
```

```python
from keel.sim import simulate, SimConfig
from keel.experiments.kill_test import run

sim = simulate(SimConfig(n_customers=6000, n_months=24, seed=7))
results, per_customer, auc = run(sim, decision_month=6, budget_fraction=0.20)

for r in results:
    print(f"{r.name:<32} {r.expected_value:>12,.0f}")
```

Reproduce the figure:

```bash
python -m keel.experiments.figures
```

Run the calibration gates and tests:

```bash
python -m pytest tests/ -q
```

---

## What's here

```
keel/
├── sim/                    SubSim — the simulator (paper 1)
│   ├── config.py           every generative parameter, documented
│   ├── latents.py          8 latent traits; attention ~ engagement via copula
│   ├── hazard.py           the monthly churn hazard (one definition, two regimes)
│   ├── subsim.py           lifecycle → person-period panel of OBSERVABLES only
│   ├── counterfactual.py   exact ground-truth τ + paired Y(0), Y(1)
│   └── calibration.py      targets, checks, and the intercept solver
├── experiments/
│   ├── kill_test.py        the go/no-go gate
│   └── figures.py          figure 1
docs/
├── BUILDLOG.md             what was built, what was tested, what happened
└── DECISIONS.md            why each modelling choice was made (D-001 … D-013)
```

**Status: Phase 0 complete.** 58 tests passing. Next: canonical schema, point-in-time
feature store, Stripe ingest, leakage suite (plan §12 Phase 1).

---

## Why SubSim exists

Real data never contains the counterfactual. You observe what happened to the customer
you treated, never what would have happened had you left them alone. So an uplift model
evaluated on real data can only be scored on group-level proxies (Qini, AUUC) that
assume you rank-and-treat-top-*k*.

SubSim knows both potential outcomes exactly, so models can be scored against **true
individual treatment effects**, and policies evaluated on **realised net revenue under
a budget constraint** — which is the question a business actually pays to have answered.

Two guards keep it a fair test bench rather than an answer key, both enforced in CI:

- no latent trait may appear in the observable panel;
- no single observable may correlate with `attention` above r = 0.95 — otherwise
  spotting sleeping dogs would be trivial and the simulator would have assumed away
  the problem it exists to pose.

Calibrated against published 2026 SMB-SaaS benchmarks (4.5% monthly voluntary churn,
30% involuntary share, flattening retention curve), verified stable across seeds. The
hazard intercept is **solved for by bisection**, never hand-tuned.
