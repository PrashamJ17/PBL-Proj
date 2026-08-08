# Keel

[![CI](https://github.com/PrashamJ17/PBL-Proj/actions/workflows/ci.yml/badge.svg)](https://github.com/PrashamJ17/PBL-Proj/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

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
git clone https://github.com/PrashamJ17/PBL-Proj.git
cd PBL-Proj
make install     # or: pip install -e ".[dev,viz]"
make check       # lint + 302 tests + calibration gates
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

## Repository layout

```
keel/
├── sim/            SubSim — the simulator. Latents (attention ~ engagement via a
│                   copula), one hazard definition, exact ground-truth τ with paired
│                   potential outcomes, dunning, and a solver for the calibration.
├── core/           Canonical schema (occurred_at + available_at on every fact),
│                   point-in-time feature store, leakage audit.
├── ingest/         Stripe (pure, fixture-tested) · CSV · SubSim adapter.
├── models/         survival/ (discrete-time hazard, competing risks, metrics,
│                   Cox/RSF/DeepSurv baselines) · clv/ (value, value at risk).
├── policy/         Retry policies for failed payments.
├── report/         Churn Autopsy — billing CSV in, self-contained HTML out.
├── benchmarks/     Public RCTs (Hillstrom, Criteo, Lenta) + Telco/GBSG2 survival data.
└── experiments/    kill_test · leakage_penalty · dunning · survival · clv · figures

tests/              302 tests — fairness, realism, edge cases, leakage gate
docs/
├── BUILDLOG.md     what was built, what was tested, what happened
└── DECISIONS.md    why each modelling choice was made (D-001 … D-049)
explainer/          10 documents for non-technical evaluators & investors
papers/paper1/      merged paper draft — README says what is evidence vs specification
CHANGELOG.md        checkpoint history, newest first
CLAUDE.md           project state + working protocol
```

### Commands

| | |
|---|---|
| `make check` | lint + tests + calibration gates — **run before every commit** |
| `make killtest` | re-run the founding experiment |
| `make figures` | regenerate figures (syncs the explainer copy) |
| `make help` | everything else |

CI re-runs the tests, the calibration gates, **and the kill test** on every push.
If the founding claim ever stops holding, the build fails.

### Status

**Phases 0–3 complete. Next: Phase 4** — hierarchical Bayesian CATE with abstention,
which is the research contribution the rest of this exists to support.

| Phase | | Gate |
|---|---|---|
| 0 | Simulator + kill test | ✅ churn-score targeting provably loses money |
| 1 | Canonical schema, point-in-time features, ingest | ✅ leakage suite green in CI |
| 2 | Dunning + Churn Autopsy report | 🟨 built; gate is **a paying client**, not code |
| 3 | Survival hazard + CLV | ✅ beats Cox and RSF 10/10 on Telco, ties DeepSurv |
| 4 | Hierarchical CATE + abstention | ⬜ next |

Validated against three real randomised experiments (Hillstrom, Criteo, Lenta) and two
public survival datasets (Telco, GBSG2). See [CHANGELOG.md](CHANGELOG.md).

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
