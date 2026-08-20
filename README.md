# RetainIQ

[![CI](https://github.com/PrashamJ17/PBL-Proj/actions/workflows/ci.yml/badge.svg)](https://github.com/PrashamJ17/PBL-Proj/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Software DOI](https://img.shields.io/badge/software-10.5281%2Fzenodo.22025879-1682D4.svg)](https://doi.org/10.5281/zenodo.22025879)
[![Data DOI](https://img.shields.io/badge/data-10.5281%2Fzenodo.22025123-1682D4.svg)](https://doi.org/10.5281/zenodo.22025123)

**Causal retention decisioning for small subscription businesses.**

Research software for the paper **[When Does Uplift Modelling Pay? A Correlation Criterion
and a Measurement Floor for Small-Scale Subscription
Retention](https://doi.org/10.5281/zenodo.22009470)**.

Uplift modelling — targeting customers by estimated treatment effect rather than by
predicted churn risk — is widely recommended and inconsistently useful. This repository
contains the evidence for *when* it pays, *by how much*, and *at what scale it stops being
measurable at all*.

---

## The three results

**1. Whether uplift beats risk targeting is governed by one measurable quantity.**

`corr(τ̂, π̂)` — the correlation across customers between estimated treatment effect and
estimated outcome propensity. As it falls, the advantage of effect-based targeting rises
monotonically. Measured on four real randomised trials and one calibrated simulator:

| Setting | corr(τ̂, π̂) | Advantage of uplift |
|---|---:|---:|
| Hillstrom — mens arm | +0.69 | **−5.6%** |
| Criteo-UPLIFT v2.1 | +0.58 | +0.6% |
| Hillstrom — womens arm | +0.19 | +12.7% |
| Lenta | +0.17 | +20.3% |
| SubSim — subscription churn | −0.19 | **+106.9%** |

When the two orderings coincide, the outcome model wins — it solves an easier estimand.
Retention is the adversarial case, and the mechanism is absent from advertising: the
customers a churn model ranks highest include dormant payers for whom *being contacted is
itself the reminder to cancel*. Lenta was an out-of-sample prediction, registered before
the data was obtained, and it landed (D-031).

![When uplift pays](papers/figures/fig03_when_uplift_pays.png)

**2. At the scale of the businesses this most concerns, neither method is reliable.**

Holding the evaluation set fixed and shrinking only the training set on a real
64,000-customer experiment, the best effect-based method beats random targeting on **75%
of draws at n = 500**. One standard estimator manages 55%. Mean performance at that size
looks respectable — but a business gets one draw, so we report win rate, not mean (D-023).

**3. A small business cannot measure its own retention campaigns.**

The holdout incrementality estimator is unbiased — it recovers the simulator's known
effect with bias centred on zero and 88–98% interval coverage. Its **minimum detectable
effect still exceeds the delivered effect at every business size tested, including
10,000 customers**. Detecting an effect of 0.0108 at 80% power with a 10% holdout needs
roughly **119,500 customers** (D-065).

![The measurement floor](papers/figures/fig06_measurement_floor.png)

---

## The founding experiment

A retention campaign targeted by churn score **loses money**, and loses *more than
targeting at random*. Verified 6/6 seeds against a real gradient-boosted churn model
(holdout AUC 0.700) trained on observables under a strictly temporal split.

At a 20% budget on a 3,589-customer eligible base:

| Policy | Treated | Expected value | Harmed |
|---|---:|---:|---:|
| do nothing | 0 | 0 | 0 |
| treat everyone | 3,589 | −89,869 | 44 |
| random 20% | 718 | −17,035 | 9 |
| **churn-score top 20%** | 718 | **−22,823** | 18 |
| oracle uplift top 20% | 718 | +5,877 | 0 |
| **oracle uplift with abstention** | **209** | **+8,610** | **0** |

1. **A churn score is anti-informative for targeting.** Random targeting is merely
   uninformed; a churn score actively sorts *toward* the customers an offer harms.
   Sleeping dogs are **59.1%** of the top predicted-risk decile against **5.3%** of the
   bottom, on a population that is 25.7% sleeping dogs overall.
2. **Abstention beats ranking.** Treating 209 customers earns more than treating 718.
3. **Improving churn-model AUC can worsen business outcomes** under top-*k* targeting.
   The better the model gets at its own job, the more precisely it finds sleeping dogs.

The setup is deliberately adverse to the thesis: the offer's *average* effect is
beneficial (mean τ = −0.0101, enforced by a calibration gate), so every unit of value lost
is attributable to targeting rather than to a bad offer.

> **Scope.** Worse-than-random did **not** replicate on the real RCTs, and the claim is
> scoped accordingly (D-020). It holds where `corr(τ, π)` is negative. That condition is
> the contribution; "churn scores are bad" on its own is Ascarza (2018).

---

## What did not work

This section is not modesty. Reporting only the wins would misrepresent what the evidence
supports, and three of these are the most useful things the project learned.

- **A units error survived 337 passing tests (D-057).** The abstention rule multiplied a
  log-odds τ by customer value as if it were a probability difference, inflating benefit
  by `1/(p₀(1−p₀))` — worst exactly for low-risk customers, which is the Sure Thing error
  reproduced inside our own decision rule. Every test passed because every test was a
  self-consistency check, and a units error is self-consistent. The fix makes the bug
  unrepresentable: `policy/economics.py` accepts money only.
- **The Phase 4 gate was unpassable as written (D-055/056).** Break-even |τ| is 0.040
  against a mean of 0.010, so an *oracle* treats only 5.8% of customers. Detectability and
  profitability move in opposite directions across the offer ladder. A minimax-regret
  reading was pre-registered and then **refuted** out of sample.
- **Per-customer offer optimisation does not beat one well-chosen offer (D-058).** It wins
  on 58% of draws, CI [0.42, 0.72] — indistinguishable from chance. A hindsight-uniform
  rung captures 73% of oracle value against the optimiser's 28%. **Choosing the offer
  beats choosing the customer.**
- **Two of five pre-registered predictions failed** after the D-057 fix. Recorded as
  failures rather than quietly dropped.

Every design decision, including the adverse ones, is in
[`docs/DECISIONS.md`](docs/DECISIONS.md) (D-001 … D-065). It is append-only.

---

## Quickstart

```bash
git clone https://github.com/PrashamJ17/PBL-Proj.git
cd PBL-Proj
make install     # or: pip install -e ".[dev,viz]"
make check       # lint + 463 tests + calibration gates
```

```python
from retainiq.sim import simulate, SimConfig
from retainiq.experiments.kill_test import run

sim = simulate(SimConfig(n_customers=6000, n_months=24, seed=7))
results, per_customer, auc = run(sim, decision_month=6, budget_fraction=0.20)

for r in results:
    print(f"{r.name:<32} {r.expected_value:>12,.0f}")
```

Phase 0 depends on numpy, pandas and scipy only. Heavier libraries are optional extras, so
the founding result can be reproduced on a machine with no ML stack installed.

---

## Reproducing the paper

Every number in the paper comes from one of these commands.

| Command | Produces |
|---|---|
| `make killtest` | The founding experiment (Table 1) |
| `make survival` | Survival head-to-head vs Cox / RSF / DeepSurv (Tables 6–7) |
| `make clv` | Customer value and the leak split by cause |
| `make abstention` | Phase 4 gate — abstention against ranking |
| `make sensitivity` | Why that gate failed — effect size and offer cost (D-055/056) |
| `make ladder` | Phase 5 gate — rung matching against one good offer (D-058) |
| `make ai-channels` | Break-even salience for automated outreach (D-064) |
| `make holdout` | The measurement floor (D-065) |
| `make figures` | Regenerate all six figures |
| `make zenodo` | Rebuild the archived data record byte-for-byte |
| `make help` | Everything else |

Survival baselines need `make install-survival` first (adds Cox, RSF and DeepSurv).

**Data.** The five third-party datasets are cited, not redistributed — they carry their
own terms. The loaders fetch them from canonical sources, and
[the data record](https://doi.org/10.5281/zenodo.22025123) publishes a SHA-256 for the
exact file used for each, so you can verify byte-for-byte that you have what we had.

---

## Why SubSim exists

Real data never contains the counterfactual. You observe what happened to the customer you
treated, never what would have happened had you left them alone. An uplift model evaluated
on real data can therefore only be scored on group-level proxies — Qini, AUUC — which
assume you rank and treat the top *k*.

SubSim knows both potential outcomes exactly, under common random numbers, so estimators
can be scored against **true individual treatment effects** and policies evaluated on
**realised net value under a budget constraint** — the question a business actually pays to
have answered.

Two guards keep it a test bench rather than an answer key, both enforced in CI:

- no latent trait may appear in the observable panel;
- no single observable may correlate with `attention` above r = 0.95 — otherwise spotting
  sleeping dogs would be trivial and the simulator would have assumed away the problem it
  exists to pose.

Calibrated against published SMB-SaaS benchmarks (4.5% monthly voluntary churn, 30%
involuntary share, flattening retention curve) and verified stable across seeds. The
hazard intercept is **solved for by bisection**, never hand-tuned.

A fixed seeded draw is archived at
[doi.org/10.5281/zenodo.22025123](https://doi.org/10.5281/zenodo.22025123): panels,
customer summaries and ground-truth counterfactuals at n = 500 / 2,000 / 10,000, plus
ground-truth effects for all six offer rungs on a common 2,000 customers.

---

## Repository layout

```
retainiq/
├── core/         Canonical schema (occurred_at + available_at on every fact),
│                 point-in-time feature store, leakage audit with canary injection.
├── sim/          SubSim — latents via copula, one hazard definition, exact ground-truth
│                 τ under common random numbers, offer ladder, dunning, calibration solver.
├── ingest/       Stripe · CSV (table-aware alias resolution) · preflight safety check ·
│                 SubSim adapter.
├── models/
│   ├── survival/ Discrete-time person-period hazard with competing risks; KM, IPCW Brier
│   │             and D-calibration in numpy; Cox / RSF / DeepSurv baselines (optional).
│   ├── uplift/   Hierarchical Bayesian CATE (Laplace posterior, validated vs NUTS) and
│   │             the money-denominated abstention rule.
│   └── clv/      Customer value, value at risk, exact shortfall by cause.
├── policy/       Dunning retry policies · economics (log-odds → money, D-057) ·
│                 offer ladder · holdout assignment, ledger and incrementality.
├── report/       Churn Autopsy · reason codes (exact, not SHAP) · worklists · dashboard.
├── benchmarks/   Hillstrom · Criteo · Lenta · Telco · GBSG2 loaders and evaluation.
├── experiments/  Every experiment in the paper, one module each.
└── cli.py        preflight and autopsy — argparse only, no runtime dependency.

tests/            463 tests — fairness, realism, edge cases, leakage gates
docs/
├── BUILDLOG.md   what was built, what was tested, what happened
└── DECISIONS.md  why each choice was made (D-001 … D-065), append-only
explainer/        10 documents for non-technical readers
papers/           RESEARCH_PAPER.md and the six figures
```

CI runs on every push across Python 3.11–3.13 and gates on four things: the test suite,
the calibration targets, the **leakage suite**, and the **kill test**. If the founding
claim ever stops holding, the build fails.

---

## Invariants

Breaking any of these invalidates results, so they are enforced in code and CI rather than
documented and hoped for. The full list is in [`CLAUDE.md`](CLAUDE.md); the load-bearing
ones:

1. **Temporal splits only.** Train on months < T, predict at T. Public datasets with no
   calendar time are split by subject, and said so explicitly.
2. **Latents never enter the observable panel.** CI-enforced.
3. **Every fact carries `occurred_at` and `available_at`.** Features filter on
   availability; `FeatureStore._visible` is the only path to source data.
4. **Any split of a person-period frame is by subject, never by row.**
5. **Never extrapolate past observed support.** Both `clv()` and `survival()` raise;
   `allow_extrapolation=True` makes the assumption a visible line of code.
6. **Value is measured against doing nothing**, never save-rate-among-treated.

---

## Status

Phases 0–5 are built; Phase 6's infrastructure is built and validated. The two open gates
are commercial, not technical — they need a business, not more modelling.

| Phase | | Gate | |
|---|---|---|---|
| 0 | Simulator + kill test | churn-score targeting provably loses money | ✅ |
| 1 | Schema, point-in-time features, ingest | leakage suite green in CI | ✅ |
| 2 | Dunning + retry timing + CLI delivery | first paying client | 🟨 open |
| 3 | Survival hazard + CLV | beats Cox and RSF 10/10 on Telco, ties DeepSurv | ✅ |
| 4 | Hierarchical Bayesian CATE + abstention | beats ranking 93%, not do-nothing | 🟨 partial |
| 5 | Offer ladder + reason codes + dashboard | owner can act unaided | ✅ |
| 6 | Holdout infra + incrementality | a real client ROI number | 🟨 open |
| 7 | Cross-tenant priors, BTYD router | tenant #10 beats tenant #1 on day 1 | ⬜ |

Phase 4's gate is reported as **partial** rather than met. Phase 5's optimiser is reported
as **not beating an achievable rival**. Neither was tuned until it passed.

---

## Citing

Please cite the paper rather than the code:

```bibtex
@article{jain2026uplift,
  title  = {When Does Uplift Modelling Pay? A Correlation Criterion and a
            Measurement Floor for Small-Scale Subscription Retention},
  author = {Jain, Prasham and Gupta, Rishi},
  year   = {2026},
  doi    = {10.5281/zenodo.22009470}
}
```

Software: [10.5281/zenodo.22025879](https://doi.org/10.5281/zenodo.22025879) ·
Data: [10.5281/zenodo.22025123](https://doi.org/10.5281/zenodo.22025123)

Department of Computer Science and Engineering, Manipal University Jaipur.

---

## Licence

Apache License 2.0 — see [LICENSE](LICENSE). The archived data record is CC BY 4.0. The
third-party datasets remain under their own terms and are not redistributed here.
