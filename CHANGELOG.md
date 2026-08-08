# Changelog

Checkpoint history. One entry per completed phase, newest first.
Technical detail lives in [`docs/BUILDLOG.md`](docs/BUILDLOG.md); the reasoning behind
each choice in [`docs/DECISIONS.md`](docs/DECISIONS.md).

---

## Lenta — an out-of-sample test of the correlation principle

**Third real RCT, added specifically to try to break D-026.**

### The prediction, made before downloading

Retail SMS promotion should fall **between** advertising (+0.61) and subscription
retention (−0.19) on `corr(treatment effect, outcome propensity)`.

### Result: +0.177 — as predicted

| setting | corr | uplift advantage | % predicted negative |
|---|---:|---:|---:|
| Hillstrom (mens) | +0.63 | +4.7% | 0.2% |
| Criteo | +0.61 | +0.6% | 19.2% |
| **Lenta** | **+0.18** | **+10.4%** | 24.9% |
| Hillstrom (womens) | +0.07 | +3.9% | 10.2% |
| SubSim (churn) | −0.19 | +106.8% | 25.7% |

### What is NOT confirmed

Whether the *consequence* follows. Lenta's +10.4% uplift advantage is nominally the
largest of the positive-correlation settings, but the intervals make it meaningless:
class-transform [359, 1601] vs outcome-propensity [309, 1477], random at [343, 1007].
**Nothing is distinguishable from anything.**

Lenta is underpowered rather than noisy — ATE +0.0075 on a 10.3% base (7.4% lift,
against Hillstrom's 42.6%). Its small-n sweep is flat from n=500 to n=20,000: more data
does not help because there is barely a signal to learn.

**One confirming observation, not two** (D-031).

### Secondary observation

24.9% of Lenta customers are predicted harmed — comparable to churn's 25.7% — yet
uplift still buys almost nothing. The share of harmed customers is not what matters;
their **correlation with outcome propensity** is.

**172 tests passing.**

---

## Criteo benchmark — and the quantity that reconciles everything

**Second real dataset, an apparently contradictory result, and the principle that
explains both.**

### Added

- `load_criteo` — 13.98M-row advertising RCT, 85/15 assignment.
- `keel/benchmarks/spectrum.py` + figure 3 — when uplift modelling is worth it.

### The contradiction

| dataset | uplift vs outcome models |
|---|---|
| Hillstrom | uplift clearly **wins** (Qini 168 vs 36) |
| Criteo | uplift clearly **loses**, at every training size (3617 vs 2811 at n=500) |

### The reconciliation — `corr(treatment effect, outcome propensity)`

| setting | corr | uplift's advantage | % predicted negative |
|---|---:|---:|---:|
| Hillstrom (mens) | +0.63 | +4.7% | 0.2% |
| Criteo | +0.61 | +0.6% | 19.2% |
| Hillstrom (womens) | +0.07 | +3.9% | 10.2% |
| **SubSim (churn)** | **−0.19** | **+106.8%** | 25.7% |

An outcome model ranks by likelihood of responding; an uplift model by how much
treatment *changes* the response. **When those orderings coincide the outcome model
wins** — it solves an easier estimation problem, and at small n that variance advantage
dominates.

This reframes the claim: not "uplift modelling is better" (false in advertising, and we
can show it), but **retention has an adversarial structure that advertising does not**.

It also refines D-020: sleeping dogs existing is *not sufficient*. Criteo has more
predicted-negative customers than Hillstrom-womens and uplift still adds nothing. What
matters is whether they sit where the outcome model ranks **highest**.

### Two traps caught, both by guards written before the data arrived

- **Criteo's file is sorted by treatment.** The first 251,999 rows are 100% treated, so
  a prefix read yields data on which uplift is *undefined*. `check_representative`
  caught it within minutes (D-024). The loader now always reads fully and subsamples
  randomly.
- **`exposure` is post-randomisation** and is excluded from covariates — using it would
  silently convert the RCT into observational data.

### Fixed

- `check_representative` was too permissive to catch a 100% treatment rate on its own
  (0.15 sits inside a 20% relative band around 0.85). Degenerate rates are now a
  categorical failure — surfaced by a test that failed on first run.
- Spectrum measurement corrected to use the T-learner: `ClassTransform`'s score is
  scale-dependent under imbalance and produced a spurious `corr = 1.00` (D-027).

**167 tests passing.**

---

## External validation — Hillstrom benchmark

**First test of the thesis against real randomised data rather than our own simulator.**

### Added

- `keel/benchmarks/` — RCT loaders with integrity checks, five targeting models
  (outcome propensity, response model, T/S-learner, class transform), policy evaluation
  on RCT data with bootstrap intervals, Qini metrics, and an abstention sweep.
- Figure 2 — small-n reliability (`papers/figures/fig02_small_n_reliability.png`).

### Results

| Claim | Outcome |
|---|---|
| Uplift beats outcome-model targeting | ✅ confirmed (467 vs 416 incremental visits) |
| Outcome-model targeting is worse than random | ❌ **did not replicate** (416 vs 281) |
| Uplift methods are unreliable at small n | ⭐ **new finding, real data** |

**Why the second one failed, diagnosed rather than rationalised:** Hillstrom contains no
sleeping dogs. Every decile of predicted uplift has positive true uplift; the mens
campaign predicts only 0.2% of customers negative. When a treatment helps everyone,
worse-than-random is structurally impossible. The claim is now scoped (D-020).

**The new finding.** Holding evaluation fixed and shrinking only the training set, the
probability a method beats random *on the same seed*:

| train n | 500 | 1,000 | 2,000 | 5,000+ |
|---|---|---|---|---|
| best uplift method | **75%** | 90% | 100% | 100% |

At n=500 the class-transform estimator wins on 55% of seeds — a coin flip — while its
mean looks respectable. Reliability, not expectation, is what a single business
experiences (D-023).

### Notable

- The expected outcome was **written into the code before the experiment ran** (D-021),
  including that worse-than-random was likely to fail on this dataset. That is the only
  reason the scoping interpretation is credible rather than convenient.
- The primary metric carries **no prices** (D-022) — Hillstrom records neither a value
  per visit nor a cost per email, so monetary conclusions would follow from our own
  invented numbers.
- Prior art acknowledged: Ascarza (*JMR* 2018) already established that risk-based
  targeting is ineffective. Our contribution is narrower and better defined as a result.

---

## Phase 1 — Canonical schema, point-in-time features, ingest

**Making it structurally impossible to train on information that did not exist yet.**

### Added

- **Canonical schema** (`keel/core/schema.py`) — six timestamp-native tables. Every
  fact carries both `occurred_at` (when it happened) and `available_at` (when it became
  knowable). Includes `interventions`, the holdout ledger no competitor keeps.
- **Point-in-time feature store** (`keel/core/features.py`) — 15 features, with the
  leakage guarantee enforced structurally: one gate function, no other path to the data.
- **Leakage suite** (`keel/core/leakage.py`) — availability audit, time-travel
  consistency, and adversarial canary injection.
- **Ingest adapters** — Stripe (pure, fixture-tested, no API key), CSV (the Churn
  Autopsy path), and SubSim → canonical for end-to-end testing.

### Results — the leakage penalty

Same features, built three ways:

| vintage | apparent AUC | what it is |
|---|---:|---|
| `correct` | **0.603** | filters on `available_at` |
| `occurred_only` | 0.613 | ignores settlement lag — the subtle bug |
| `no_filter` | **0.954** | no temporal filter — the catastrophic bug |

**0.954 vs 0.603.** "Total sessions ever" looks innocent, but a customer who churned in
month 4 generates no rows afterwards, so the feature encodes the outcome. The model
appears excellent and has learned only who stopped producing data.

That 0.35 gap is not performance. It is how far a backtest would have overstated the
model before production — and the number a business would have staked a budget on.

### Notable

- **The leakage suite is required to have teeth** (D-017). It must *fail* on
  deliberately leaked vintages and *catch* a planted canary, while not flagging honest
  features. A suite that has never caught a leak is evidence of nothing.
- Unsafe feature modes exist **on purpose** (D-016), so the safeguard's value is
  measured rather than asserted. Default is safe; a test enforces it.
- Stripe mapping handles the three things that are quietly wrong everywhere:
  zero-decimal currencies, interval normalisation, and `canceled_at` ≠ `ended_at`.

### Fixed

- `scikit-learn` was declared only in an optional extra despite being imported by the
  Phase 0 kill test — a fresh install would have failed.
- Tests only passed under `python -m pytest`; bare `pytest` could not import the
  package.

**137 tests passing.** CI gained a leakage gate alongside the calibration and kill-test
gates.

---

## Phase 0 — SubSim and the kill test

**The founding claim was tested and survived.**

### Added

- **SubSim** (`keel/sim/`) — a subscription-business simulator emitting *exact*
  ground-truth counterfactuals: both potential outcomes per customer, which no real
  dataset can provide.
- **Kill test** (`keel/experiments/kill_test.py`) — the go/no-go experiment on the
  project's central thesis.
- **Figure 1** (`papers/figures/fig01_kill_test.png`) — outcome and mechanism.
- 58 tests, calibration gates, and full documentation
  (`docs/`, `explainer/`, `CLAUDE.md`).

### Results — 6/6 seeds, unanimous

| Finding | Detail |
|---|---|
| Churn-score targeting loses money | −22,123 at 20% budget |
| **It is worse than random targeting** | random −17,035 vs churn-score −26,903 (mean) |
| **Abstention beats ranking** | 209 contacts (+8,610) earned more than 718 (+5,877) |
| Mechanism | Sleeping dogs are 48% of the top risk decile vs 2% of the bottom |

A more accurate churn model makes this *worse* — accuracy at detecting disengagement
means precision at finding sleeping dogs.

### Calibration

Matched to published 2026 SMB-SaaS benchmarks and stable across 8 seeds: 4.5% monthly
voluntary churn, 30% involuntary share, 23% two-year retention, 2.0× early-to-late
hazard ratio.

### Notable

- **An earlier, more favourable result was rejected.** The first configuration produced
  30% sleeping dogs and a *harmful* average treatment effect, making the headline
  trivially true and not credible. Reconfigured so the offer **helps on average**
  (mean τ = −0.010), making the claim harder to demonstrate. It held anyway (D-011).
- The churn baseline is a real gradient-boosted model on observables with a strict
  temporal split (AUC ≈ 0.70), not a strawman (D-012).
- Calibration targets were found **mutually inconsistent** and corrected — 30–60%
  two-year retention cannot coexist with a 3–7% voluntary churn band (D-006).
