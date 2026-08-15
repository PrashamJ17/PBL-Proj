# Changelog

Checkpoint history. One entry per completed phase, newest first.
Technical detail lives in [`docs/BUILDLOG.md`](docs/BUILDLOG.md); the reasoning behind
each choice in [`docs/DECISIONS.md`](docs/DECISIONS.md).

---

## Phase 3 — Discrete-time survival hazard and CLV

**Turns "who might churn" into "what is this customer worth, and how much of it is at
risk from which cause". Gate met against Cox and RSF; a tie with DeepSurv.**

### Added

- `retainiq/models/survival/discrete.py` — person-period discrete-time hazard, two
  learners, three baseline-hazard bases, and a competing-risks wrapper that keeps
  voluntary and involuntary churn separate all the way to the output.
- `retainiq/models/survival/metrics.py` — Kaplan-Meier, IPCW Brier, integrated Brier,
  D-calibration and binned calibration, on numpy/scipy only so they run in CI, and
  cross-checked against `scikit-survival` where installed.
- `retainiq/models/survival/baselines.py` — Cox (lifelines), RSF (scikit-survival) and
  DeepSurv (written directly against torch, ~40 lines, Breslow ties).
- `retainiq/models/clv/value.py` — CLV, expected remaining months, value at risk, and an
  exact decomposition of the value shortfall by cause.
- `retainiq/benchmarks/survival_data.py` — Telco (IBM, real subscription churn), GBSG2,
  and SubSim adapters.
- `retainiq/experiments/survival_benchmark.py`, `retainiq/experiments/clv.py`, and figure 5.

### Results — Telco, mean over 10 resplits

| model | C-index | IBS | cal. slope | ours wins on IBS |
|---|---:|---:|---:|---:|
| **discrete-time (logistic)** | 0.8650 | **0.0824** | 1.02 | — |
| DeepSurv | 0.8661 | 0.0825 | 0.98 | 4/10 |
| Cox PH | 0.8565 | 0.0914 | 1.18 | **10/10** |
| Random Survival Forest | 0.8461 | 0.0964 | 1.18 | **10/10** |
| Kaplan-Meier | — | 0.1823 | — | 10/10 |

**Beats Cox and RSF on 10/10 resplits. Ties DeepSurv** — 0.0824 vs 0.0825 is noise and
is reported as a tie. On GBSG2, the benchmark those methods were developed on, **RSF
wins and we said so before running it** (D-021): discretising seven years of daily
follow-up onto months costs resolution the continuous-time models keep.

**What the phase actually bought is representation, not accuracy.** Time-varying
covariates through the existing point-in-time path, competing risks that never merge,
and calibrated absolute probabilities CLV can multiply by money. DeepSurv matches the
numbers, does none of those three, and needs a ~2GB dependency.

### CLV on 4,000 simulated customers

- Book value **2.22M**; shortfall against perfect retention **2.63M**, splitting
  **exactly** into 72.5% voluntary / 27.5% involuntary with no residual.
- **The top decile by value at risk overlaps the top decile by churn risk by 21%.**
  Ranking by churn probability finds the wrong 79% of the money.
- CLV **refuses to extrapolate** past the observed support (D-046). The standard
  `ARPU / churn_rate` formula is an infinite sum assuming a constant hazard forever,
  and hazards decline with tenure by construction (D-004).

### Notable

- **Two metric bugs, neither in the model** (D-048). The censoring estimator needed the
  events-before-censorings tie convention (~2% on IBS — noise-sized, but enough to
  reorder near-tied models), and `G(t)` hits exactly zero under administrative
  censoring, which produced integrated Brier scores of **2.6e7** on SubSim. Caught by
  agreement with `scikit-survival` and by a magnitude check, not by reading the code.
- **`TotalCharges` is excluded from Telco** (D-047) — cumulative billing, r = 0.83 with
  tenure, i.e. a direct encoding of the duration being predicted. Published Telco
  survival analyses ship this.
- **Calibration error alone is gameable and IBS is not** (D-045). On `cal_mae`,
  Kaplan-Meier beats Cox on Telco — a covariate-free model is trivially calibrated.
  Kaplan-Meier stays in every table so that failure mode is visible.
- **Below 250 customers nothing reliably beats Kaplan-Meier.** Not predicted, and the
  most useful number in the landmark experiment.

**277 tests passing.**

---

## Churn Autopsy — the first customer-facing artifact

**Closes the gap between the research and something a business can actually receive.**

### Added

- `retainiq/report/autopsy.py` — retention curve, voluntary/involuntary split,
  failed-payment economics and decline-code mix, computed from billing data alone.
- `retainiq/report/render.py` — self-contained HTML: inline CSS, inline SVG charts, no
  external requests. Opens offline, prints, emails.

### How a business uses it

Export three CSVs from the Stripe dashboard (customers, subscriptions, invoices). Ten
minutes of clicking, no engineer, no integration. They receive a document with money
attached to every finding, ranked by value at stake.

### Honesty is enforced in the artifact, not just intended

- **Every finding is badged** `measured from your data` (green) or
  `estimated from industry benchmarks` (amber). The most persuasive finding — the
  recovery gap — is amber (D-035).
- **Caveats are printed.** If the export carried no decline codes, the report says so
  and explains why that field matters.
- **It refuses to name individual targets** (D-036). That is the most-requested feature
  and precisely what this project argues against: billing data cannot support causal
  claims, and targeting on outcome propensity is worse than useless in the adversarial
  setting retention occupies.

### Fixed

- The first run reported **0% recovery** — the SubSim adapter emitted payment failures
  but never the retries that succeeded, so the pipeline was representationally
  incapable of expressing recovery. Left unfixed, every report would have claimed a
  catastrophic recovery gap. Now reads 38.6%, consistent with SubSim's 0.42 (D-037).

**220 tests passing.**

---

## Phase 2 — Dunning and involuntary churn

**The module that earns money. Technical work complete; the phase gate is a paying
client and remains OPEN.**

### Added

- `retainiq/sim/dunning.py` — decline-code taxonomy, retry-success dynamics conditioned on
  code / attempt / timing, payday cycles, and dunning fatigue.
- `retainiq/policy/dunning.py` — six retry policies from `no_retry` to `aggressive`.
- `retainiq/experiments/dunning.py` — valuation in money, not recovery rate.
- Figure 4 (`fig04_dunning_value.png`).

### Results (n=40,000 failed payments)

| policy | recovery | attempts | emails | net value |
|---|---:|---:|---:|---:|
| processor_default | 42.0% | 3.09 | 2.47 | 17.15M |
| code_aware | **48.9%** | 2.10 | 2.03 | 20.24M |
| **code_aware_quiet** | 48.8% | 2.09 | 1.37 | **20.47M** |
| aggressive | 48.6% | 5.29 | 5.29 | 19.41M |

**Knowing which payment failed beats trying harder.** Code-aware scheduling gains
+6.9pp over the processor default while using **32% fewer attempts** — the processor
already tells you the decline reason and the default schedule ignores it.

**`aggressive` is strictly dominated.** 2.5x the retries, 3.9x the emails, and it
recovers *no more*. It does not even win on the vendor's own headline metric.

**Emailing a third less is worth +227k** at identical recovery — the timing does the
work, not the nagging.

### Notable

- **A test caught the simulator inflating its own headline** (D-033). Expired cards were
  "recovering" 21.7% because retries compounded — which cannot happen. Fixing it removed
  aggressive's only advantage and produced a cleaner finding.
- Calibrated on the passive band (30–45%), the model then reproduces the *dedicated
  dunning* figure (54.7% against a published 55–70%) **without further tuning** — an
  out-of-sample check on the generative structure (D-034).
- Dunning fatigue links voluntary and involuntary churn without merging them (D-032).
  Its magnitude is assumed, not measured, so figure 4 shows a sensitivity sweep: the
  policy ranking flips at 0.031 against our assumption of 0.055.

**200 tests passing.**

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
- `retainiq/benchmarks/spectrum.py` + figure 3 — when uplift modelling is worth it.

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

- `retainiq/benchmarks/` — RCT loaders with integrity checks, five targeting models
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

- **Canonical schema** (`retainiq/core/schema.py`) — six timestamp-native tables. Every
  fact carries both `occurred_at` (when it happened) and `available_at` (when it became
  knowable). Includes `interventions`, the holdout ledger no competitor keeps.
- **Point-in-time feature store** (`retainiq/core/features.py`) — 15 features, with the
  leakage guarantee enforced structurally: one gate function, no other path to the data.
- **Leakage suite** (`retainiq/core/leakage.py`) — availability audit, time-travel
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

- **SubSim** (`retainiq/sim/`) — a subscription-business simulator emitting *exact*
  ground-truth counterfactuals: both potential outcomes per customer, which no real
  dataset can provide.
- **Kill test** (`retainiq/experiments/kill_test.py`) — the go/no-go experiment on the
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
