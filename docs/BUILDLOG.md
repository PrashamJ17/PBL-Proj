# Build Log

Chronological record of what was built, what was tested, and what the results were.
Reasoning behind design choices lives in [DECISIONS.md](DECISIONS.md).

---

## Phase 0 — SubSim (the simulator)

**Goal (plan §12):** a subscription-churn simulator emitting ground-truth
counterfactuals, able to generate data where a churn-score-ranked policy provably
loses money.

**Why first:** everything else is blocked on it. It is also paper 1.

---

### Step 0.1 — Repo scaffold

Created the package layout from plan §11 (`sim/`, `models/`, `policy/`,
`experiments/`, `core/`, `ingest/`), `pyproject.toml`, and a `tests/` tree.

Dependency policy: Phase 0 runs on numpy + pandas + scipy only. The causal stack
(econml, causalml, pymc), survival stack (lifelines, scikit-survival, lightgbm) and
BTYD stack (pymc-marketing) are optional extras, pulled in by the phase that needs
them. Rationale in D-008.

Environment check: Python 3.13.9 (anaconda), numpy 2.3.5, pandas 2.3.3, scipy 1.16.3,
sklearn 1.7.2. lightgbm **not** installed — a Phase 3 concern, not a blocker.

---

### Step 0.2 — Configuration and latent customer model

`retainiq/sim/config.py` — every generative parameter, named and documented with its sign
convention. Nothing is a magic number inside the simulation loop, because paper 1's
contribution *is* the calibration of these values.

`retainiq/sim/latents.py` — eight per-customer latent traits with Beta marginals.
`attention` and `engagement_base` are drawn correlated through a Gaussian copula
(D-002); this is the mechanism that makes the whole project necessary.

**One thing redone:** the first version hand-rolled an incomplete-beta series and an
`erf` approximation to stay dependency-free. It was buggy and pointless — scipy was
already present. Replaced with `scipy.stats.norm.cdf` + `scipy.stats.beta.ppf`, which
is both correct and the defensible thing to cite in a paper.

---

### Step 0.3 — Lifecycle and hazard engine

`retainiq/sim/hazard.py` — the monthly churn-hazard logit, isolated so that the stochastic
historical simulation and the semi-analytic counterfactual window share one definition.
If those two ever diverged, every causal result in the project would be silently wrong.

`retainiq/sim/subsim.py` — month-by-month simulation emitting a person-period panel of
**observable features only** (sessions, engagement trend, features used, support
tickets, payment failures, seat activity, price-to-median). Voluntary and involuntary
churn are separate processes (D-001).

**First run — out of calibration:**

```
monthly voluntary churn      13.41%   (target 3-7%)
involuntary share of churn   19.9%    (target 20-40%)
still active at 24mo          3.0%
```

Diagnosis: engagement decayed geometrically toward zero, so by month 12 every customer
had ~3% engagement, saturating the dominant hazard term. Everyone became high-risk and
almost nobody survived — which also destroyed the right-censoring the project needs.

---

### Step 0.4 — Calibration harness

`retainiq/sim/calibration.py` — explicit targets sourced from published 2026 SMB-SaaS
benchmarks, a `check()` that verifies them, `sweep_seeds()` for stability, and
`calibrate_intercept()` which *solves* for the hazard intercept by bisection rather
than letting anyone hand-tune it (D-005).

Building this before tuning was the right call: it turned an open-ended fiddling
exercise into a solve, and it immediately exposed a real bug in the targets themselves.

**Fixes applied:**

| Fix | Change | Effect |
|---|---|---|
| D-003 | Engagement decays to a habit-set floor, not zero | voluntary churn 13.4% → 9.3% |
| — | `engagement_decay` mean 0.21 → 0.051/month | (same) |
| — | Payment failure rate 5.5% → 3.5%, passive recovery 38% → 42% | involuntary share into mid-band |
| D-005 | Intercept solved by bisection: −3.1 → **−3.8125** | voluntary churn → 4.5% |
| D-004 | `habit_strength` left-skewed Beta(2.2, 1.6) | retention curve flattens realistically |
| D-006 | Retention target widened [0.30,0.60] → [0.22,0.50] | targets became jointly satisfiable |

**D-006 is the notable one.** The original targets were *mutually inconsistent* — 40%
retention at 24 months implies ~3.75% total monthly churn, which contradicts a 3–7%
voluntary band before involuntary is even added. No parameterisation could have
satisfied them. This is invisible if you tune one target at a time, and it is a
genuinely useful methodological point for paper 1.

**Final calibration — all targets met:**

```
[PASS] monthly_voluntary_churn        0.045   target [0.030, 0.070]
[PASS] involuntary_share_of_churn     0.299   target [0.200, 0.400]
[PASS] month_24_retention             0.237   target [0.220, 0.500]
[PASS] early_late_hazard_ratio        2.031   target [1.150, 3.000]
```

**Stability across 8 seeds** (a simulator calibrated on one lucky seed is not
calibrated):

```
monthly_voluntary_churn        0.0452 +/- 0.0008
monthly_involuntary_churn      0.0205 +/- 0.0010
involuntary_share_of_churn     0.3116 +/- 0.0086
month_24_retention             0.2270 +/- 0.0095
early_late_hazard_ratio        2.0484 +/- 0.0775
```

Caveat recorded: 24-month retention sits ~1.8 seed-sd above its lower bound. Tight.
Revisit if hazard coefficients change.

---

### Step 0.5 — Test suite

`tests/test_simulator.py` — **11 tests, all passing** (0.75s).

The two that matter most are fairness tests, not realism tests:

- `test_latents_do_not_leak_into_panel` — no latent may appear as an observable. A
  simulator whose panel carries its own latents is an answer key, not a test bench.
- `test_no_observable_is_a_perfect_proxy_for_attention` — asserts r < 0.95 between
  every observable and `attention`. If one observable recovered `attention` exactly,
  spotting sleeping dogs would be trivial and the simulator would have assumed away
  the problem it exists to pose.

The rest cover determinism under seed, seed sensitivity, all calibration targets,
seed stability, voluntary/involuntary disjointness, censoring existence and flagging,
declining hazard with tenure, engagement predicting churn, and at-risk-only panel rows.

---

### Step 0.6 — Counterfactual intervention response

`retainiq/sim/counterfactual.py` — the reason SubSim exists. Emits **exact** ground-truth
treatment effects, in two deliberately separate regimes (D-009):

- **Analytic τ**: the forward window evolves state along its *expected* trajectory, so
  survival probabilities and therefore τ are closed-form with zero Monte Carlo error.
  This is what an uplift model should be scored against.
- **Realised Y(0), Y(1)**: the same uniform draws are applied to both arms (common
  random numbers), giving correctly *paired* outcomes — what a perfect experiment
  would have observed.

Treatment effect = two opposing forces with **different timing** (D-010):
saveability is protective and holds through the discount period; salience is harmful,
and spikes immediately then fades — the damage from contacting a dormant payer happens
at the moment of contact.

Also added the offer ladder (`LADDER`), 6 rungs ordered by margin cost, from
`feature_nudge` to `discount_40_6mo`.

**First run — all four quadrants present, but a problem:**

```
persuadable 43.6%   sleeping_dog 30.0%   sure_thing 26.1%   lost_cause 0.3%
mean tau = +0.0044
```

30% sleeping dogs is **not credible** — the uplift literature reports them as a
minority segment. Getting the headline result at that setting would have invited
exactly the charge D-005 exists to prevent. Ran a sensitivity sweep over
`salience_scale` and moved to the *harder* case (D-011).

---

### Step 0.7 — Quadrant calibration

Added `QUADRANT_TARGETS` and `check_quadrants()` so the quadrant mix is a calibration
gate rather than an assumption. `salience_scale` 2.6 → **1.8**.

```
[PASS] sleeping_dog_share         0.1676   target [0.080, 0.220]
[PASS] persuadable_share          0.5341   target [0.250, 0.650]
[PASS] mean_tau                  -0.0100   target [-0.050, 0.000]
```

The `mean_tau` target is the important one and it is deliberately *adverse to the
thesis*: it forces the average treatment effect to be **beneficial**. A blanket
campaign helps on average. So any money churn-score targeting loses must come purely
from bad targeting, not from a bad offer.

---

### Step 0.8 — THE KILL TEST ✅

`retainiq/experiments/kill_test.py`. Plan §14.3 gate. Three choices make it honest:

1. The churn model is real — `HistGradientBoostingClassifier` on **observable features
   only**, trained with a **strictly temporal split** (months < T, predict at T).
   Holdout AUC ≈ **0.70**, a decent model. Using true probabilities would be a
   strawman; the claim is not "churn models are inaccurate", it is "**even an accurate
   churn model is the wrong targeting rule**".
2. The offer's average effect is beneficial (enforced above).
3. Value is measured against **doing nothing** — the real alternative, and the baseline
   vendor case studies quietly omit.

**Result at 20% budget, n=6,000, 3,589 eligible:**

| policy | n treated | expected value | realised | saved | harmed |
|---|---:|---:|---:|---:|---:|
| do_nothing | 0 | 0 | 0 | 0 | 0 |
| treat_all | 3,589 | **−89,869** | −80,144 | 83 | 44 |
| random_20pct | 718 | **−17,035** | −23,296 | 15 | 9 |
| churn_score_top20pct | 718 | **−22,123** | −16,858 | 21 | 19 |
| oracle_uplift_top20pct | 718 | **+5,877** | +2,736 | 27 | 0 |
| oracle_uplift_abstain | 209 | **+8,610** | +6,876 | 11 | 0 |

**Robustness — 6 seeds, unanimous:**

- churn-score targeting loses money **6/6**
- churn-score targeting is **worse than random 6/6** (mean −26,903 vs −16,949)
- oracle abstention is profitable **6/6** (mean +9,742)

**Three findings worth writing up:**

1. **Churn-score targeting is worse than random.** Random targeting is merely
   uninformed; a churn score is *anti-informative* for this decision, because it
   actively sorts toward sleeping dogs. This is stronger than the plan predicted.
2. **Abstention beats ranking.** `oracle_uplift_abstain` treats 209 customers and
   earns more than `oracle_uplift_top20pct` treating 718 — **more money, 29% of the
   contacts**. Direct support for the plan's §7.5 abstention thesis.
3. **Every policy that treats everyone loses badly.** `treat_all` at −89,869 is the
   real-world default for most SMBs running a blanket win-back campaign.

---

### Step 0.9 — Figure 1

`retainiq/experiments/figures.py` → `papers/figures/fig01_kill_test.png`. Two panels,
because an outcome without a mechanism reads as a simulation artifact:

- **Left (outcome):** expected value vs budget, averaged over 6 seeds with ±1 sd
  bands. Churn-score sits below random at every budget. The curves converge at 100%
  budget by construction (all rankings treat everyone) — asserted in tests.
- **Right (mechanism):** true quadrant composition by *predicted*-risk decile.

**The mechanism panel is the finding: sleeping dogs are 48% of decile 1 (targeted
first) vs 2% of decile 10.** That single contrast explains the entire left panel.

---

### Step 0.10 — Edge-case coverage

`tests/test_edge_cases.py`. **58 tests total, all passing** (8.6s).

Degenerate inputs (n=0, n=1, zero months, single month, empty snapshot, horizon=1),
boundary correlations (0.0, ±0.5, 0.95, 1.0 → must not NaN via `sqrt(1-ρ²)`), extreme
intervention scales (3×3 grid), extreme hazard intercepts, zero/total payment failure,
`expit` at ±1e4, every ladder rung, and small-n (300) kill-test runs.

Sign-invariant tests that pin the mechanism:

- `salience_scale=0` ⟹ τ ≤ 0 everywhere and **no sleeping dogs can exist**
- `saveability_scale=0` ⟹ τ ≥ 0 everywhere and **no persuadables can exist**
- under common random numbers with salience off, **nobody can be harmed** — the
  property that makes paired outcomes valid
- oracle abstention **never loses money** and **never selects a sleeping dog**

**One test failure worth recording**, because it caught a misunderstanding of mine
rather than a bug: `test_extreme_hazard_intercepts` asserted that with the voluntary
hazard switched off (intercept −20) every customer would be censored. It failed —
customers still churned **involuntarily**, since payment failure is an independent
process. The code was right and the assertion was wrong. Replaced with
`test_involuntary_churn_survives_zero_voluntary_hazard`, which now asserts the
separation positively. This is D-001 made testable.

---

## Phase 0 status: **COMPLETE** — gate passed

The plan's week-3 kill test was the go/no-go on the entire thesis. It passes
unanimously, and at *conservative* parameter settings chosen to make the claim harder
rather than easier. Phase 1 (canonical schema, point-in-time feature store, Stripe
ingest, leakage suite) is unblocked.

---

## Phase 1 — Canonical schema, point-in-time feature store, ingest

**Goal (plan §12):** connect to real billing data and make it structurally impossible
to train on information that did not exist at prediction time.
**Gate:** leakage suite green in CI.

---

### Step 1.1 — Canonical schema

`retainiq/core/schema.py` — six tables: `customers`, `subscriptions`, `invoices`, `events`,
`tickets`, `interventions`.

Two decisions shaped everything downstream:

- **Timestamp-native, not period-indexed** (D-018). SubSim adapts *upward* into
  timestamps rather than the schema adapting down into months.
- **Every fact carries `occurred_at` AND `available_at`** (D-014). Validation rejects
  `available_at < occurred_at` — a fact cannot be knowable before it happens, and that
  invariant is what every point-in-time guarantee rests on.

`interventions` is the table no competitor keeps: every retention action *including
deliberate non-actions* (`arm='holdout'`). Without a record of what was tried, on whom,
and who was held back, causal effects cannot be estimated at all.

### Step 1.2 — Point-in-time feature store

`retainiq/core/features.py`. 15 standard features across billing, engagement, support, and
contact fatigue.

The guarantee is **structural, not procedural** (D-015): every feature reads source
rows through exactly one function, `_visible`, which applies the temporal filter. There
is no other path to the data, so a feature that bypasses it cannot be written.

Features are declarative (`FeatureSpec`) rather than lambdas so they can be *audited* —
we can ask which rows a feature may touch without running it.

### Step 1.3 — SubSim → canonical adapter

`retainiq/ingest/subsim_adapter.py`. Expands aggregate counts into individual timestamped
rows and injects **realistic availability lag** (0.24–6h for events, 0.5–2 days for
decline codes). Without that lag the point-in-time machinery would be untested —
filtering on either timestamp would give identical answers.

### Step 1.4 — Leakage suite

`retainiq/core/leakage.py`. Three independent checks: availability audit (structural),
time-travel consistency (behavioural), and canary injection (adversarial).

**The suite is required to have teeth** (D-017). It must *fail* on deliberately leaked
vintages and *catch* a planted canary, while *not* flagging honest features. A leakage
suite that has never caught a leak is evidence of nothing.

### Step 1.5 — Leakage penalty measured ⭐

`retainiq/experiments/leakage_penalty.py`. Built the same features three ways:

| vintage | apparent AUC | inflation | what it is |
|---|---:|---:|---|
| `correct` | **0.603** | — | filters on `available_at` |
| `occurred_only` | 0.613 | +0.010 | ignores settlement/upload lag — the subtle bug |
| `no_filter` | **0.954** | **+0.351** | no temporal filter — the catastrophic bug |

**0.954 versus 0.603.** A model that looks near-perfect and is worthless.

The mechanism is worth stating plainly: "total sessions ever" looks like an innocent
activity feature, but a customer who churned in month 4 generates no rows in months
5–24. The feature encodes the outcome almost perfectly. The model appears excellent and
has learned only who stopped producing data.

That 0.35 gap is not performance — it is the amount by which a backtest would have
overstated the model, and the number a business would have staked a budget on.

### Step 1.6 — Stripe and CSV adapters

`retainiq/ingest/stripe.py` — pure functions over fetched JSON, no API key needed, so the
logic most likely to be quietly wrong (money and time) is actually covered. Handles
zero-decimal currencies (JPY 2000 is ¥2000, not ¥20), interval normalisation (an annual
plan must not look 12× more valuable), and the `canceled_at` vs `ended_at` distinction
— a customer who cancels on the 1st with service until the 31st has *not* churned yet.

`retainiq/ingest/csv_ingest.py` — the Churn Autopsy delivery path. Forgiving about shape
(alias table for column names), unforgiving about meaning. Assumes a **conservative
lag** rather than none (D-019), because a CSV cannot tell us when facts became knowable
and assuming zero would be a lie the feature store cannot detect.

### Step 1.7 — Tests

**137 total, all passing** (9.5s). Phase 1 added 79:

- `test_schema.py` (23) — validation catches impossible timestamps, duplicate keys,
  orphan references; nullable `ended_at` is *right*, not missing data.
- `test_leakage.py` (24) — the gate. Includes the adversarial pair above.
- `test_stripe_ingest.py` (23) — money and time edge cases.
- `test_csv_ingest.py` (22) — aliasing, lag defaults, error quality.

CI gained a **leakage job** that fails if the correct vintage ever looks implausibly
good, or if the gap to the unfiltered vintage closes — either would mean the safeguard
or the demonstration stopped working, and we need to know which.

---

## Phase 1 status: **COMPLETE** — gate passed

Leakage suite green in CI. Phase 2 (dunning / involuntary churn — first revenue) is
unblocked.

---

## External validation — the Hillstrom benchmark

**Goal:** test the thesis against real randomised data instead of our own simulator.
Everything to this point was simulator-only, which is not evidence a referee would
accept and should not be evidence we accept either.

**Prediction recorded before running** (D-021, committed in `run.py`): Hillstrom is
email marketing, not churn retention; its harm mechanism is weaker; worse-than-random
might well fail there, and that would be a result about *scope* rather than a
refutation.

---

### Step B.1 — Harness

`retainiq/benchmarks/` — dataset loaders with row-count verification (a truncated CSV parses
fine and silently changes every result; the first download attempt did in fact truncate
at 907KB of 3.96MB), five targeting models, and policy evaluation on RCT data.

The estimator: because treatment was randomised, the control group is a valid
counterfactual for any subgroup selected on **pre-treatment covariates**. For a policy
selecting set S, `uplift(S) = mean(Y|treated, S) - mean(Y|control, S)`, with bootstrap
intervals. Randomisation does all the work, which is why `RCT.X` excludes anything
measured after assignment — a test enforces it.

Primary metric carries **no prices** (D-022).

### Step B.2 — Main result

```
hillstrom[womens/visit]: n=42,693  treated 50.1%
  ATE +0.0452 (+42.6% lift)

policy                targeted  uplift/1000  incremental          95% CI   qini
treat_all                21347        43.73        933.4              --     --
s_learner                 6404        72.88        466.7  [356.9, 591.6]  167.8
t_learner                 6404        71.15        455.6  [333.4, 577.5]  149.9
response_model            6404        70.14        449.2  [324.7, 572.8]   84.9
class_transform           6404        65.89        422.0  [313.8, 524.7]  159.8
outcome_propensity        6404        64.91        415.7  [291.8, 532.6]   35.6
random                    6404        43.92        281.3  [207.9, 363.2]    0.0
```

**Uplift beats outcome models — confirmed.** Qini roughly doubles (167.8 vs 35.6).

**Worse-than-random — did NOT replicate.** Outcome-model targeting beat random, 416 vs
281.

### Step B.3 — Diagnosis, not rationalisation ⭐

Sorted the test set into deciles of predicted uplift and measured *true* uplift in each:

| campaign | ATE | % predicted negative | decile 1 | decile 5 | decile 10 |
|---|---|---|---|---|---|
| womens | +0.045 | 10.2% | +0.028 | +0.028 | +0.074 |
| mens | +0.077 | **0.2%** | +0.096 | +0.067 | +0.098 |

**Every decile has positive true uplift. Hillstrom has no sleeping dogs.** The mens
campaign is worse still — decile 1 outperforms decile 5, so the ranking is close to
noise.

When a treatment helps everyone, any rule correlated with responsiveness beats random,
and worse-than-random is *structurally impossible* regardless of model quality. The
claim is now scoped (D-020): it requires a harmed segment correlated with outcome
propensity, which subscription retention has and promotional email does not.

This also converts the simulator from a convenience into a necessity — no public dataset
contains the mechanism.

### Step B.4 — Small-n reliability ⭐ the important one

Hillstrom cannot test the harm mechanism, but it *can* test the question this project
exists to answer. Evaluation set held fixed; only training size shrinks; 20 seeds.

**Probability a method beats random on the same seed:**

| train n | outcome_prop | response | t_learner | s_learner | class_transform |
|---|---|---|---|---|---|
| 500 | 70% | 60% | 70% | **75%** | **55%** |
| 1,000 | 65% | 60% | 85% | 90% | 75% |
| 2,000 | 75% | 90% | 95% | **100%** | 90% |
| 5,000 | 95% | 95% | 100% | 100% | 90% |
| 20,000 | 90% | 100% | 100% | 100% | 100% |

Coefficient of variation falls from ~21% at n=500 to ~11% at n=20,000.

**At n=500 the best method fails to beat random one time in four**, and class-transform
is a coin flip — while its *mean* looks respectable. Reliability, not expectation, is
what a single business experiences (D-023).

Reliability arrives around **n=2,000**. Below that, deploying a conventional uplift model
is closer to a gamble than a decision — and that is exactly the regime this project
targets. Strongest support yet for abstention, and the first such evidence from real
data.

### Step B.5 — Figure 2 and tests

`papers/figures/fig02_small_n_reliability.png`. Left panel: the conventional view (means
rise with data). Right panel: win rate against random. The two tell different stories,
and only the second is what a business experiences.

`tests/test_benchmarks.py` — **23 tests**. Estimator correctness is tested on synthetic
RCTs with known ground truth, including a `harm_fraction` parameter that creates the
sleeping-dog segment Hillstrom lacks — so the machinery is verified on data that
contains the phenomenon even though the real dataset does not. Dataset-dependent tests
skip when the download is absent, keeping the suite runnable offline.

`test_hillstrom_has_no_sleeping_dogs` locks in the scoping finding as a regression test.

**160 tests total, all passing.**

---

### What this did to the claims

| Before | After |
|---|---|
| "Churn-score targeting is worse than random" | "...**where a harmed segment exists that resembles the highest-ranked customers**" |
| Novelty: risk-based targeting fails | Novelty: **when it becomes actively harmful**, plus small-n reliability (Ascarza 2018 established the former) |
| Evidence: simulator only | Simulator **and** real RCT, with the boundary between them mapped |

Every affected claim in `explainer/` was rewritten, including the honest-status section.

---

## Criteo benchmark — and the quantity that reconciles the results

### Step C.1 — Getting the data

Two problems before a single number was computed.

**Throughput.** Criteo's blob mirror ran at ~16 KB/s — ≈5 hours for 297MB. The
HuggingFace mirror ran at ~1.3 MB/s, **80× faster**, completing in 3m16s byte-identical.
Sixty seconds of probing saved five hours (D-025).

**The file is sorted by treatment.** While the slow download ran, the loader was built to
read a *prefix* of the partial gzip — legitimate in principle, since gzip is a stream
format. `check_representative` immediately reported `treatment_rate = 1.0000`. Confirmed
directly: the first 251,999 rows are all `treatment=1`.

This is worse than ordinary sampling bias — a prefix contains **no control group at
all**, so uplift is *undefined* rather than noisy, and every downstream number would have
looked plausible and meant nothing. The loader now always reads fully and subsamples
randomly (D-024).

The check was written speculatively, on the general principle that a subset should be
verified against published statistics before use. It caught a fatal problem within
minutes of first contact.

### Step C.2 — Main result: the opposite of Hillstrom

```
criteo[visit] n=2,000,000  treated 85.0%  ATE +0.0104 (+27.3%)

policy                targeted  uplift/1000  incremental             95% CI    qini
treat_all              1000000        10.96      10958.4                 --      --
t_learner               300000        30.44       9133.1   [8344.4, 9893.9]  3502.1
outcome_propensity      300000        30.28       9083.8  [7936.9, 10146.0]  3627.6
class_transform         300000        30.18       9054.5  [7985.1, 10103.2]  3665.9
response_model          300000        30.03       9009.6  [7887.6, 10123.2]  3628.7
s_learner               300000        29.89       8965.7   [7886.2, 9986.8]  3627.5
random                  300000        11.04       3313.3   [2885.4, 3757.4]     0.0
```

**Every method is tied.** Best to worst spans 1.9%, intervals overlap almost entirely,
and `outcome_propensity` has a *higher* Qini than `t_learner`.

**Small-n sweep — uplift LOSES at every size:**

| train n | outcome_prop | t_learner | s_learner |
|---|---|---|---|
| 500 | **3617±245** | 2811±778 | 2487±1321 |
| 20,000 | **3761±236** | 2968±282 | 3028±1052 |

Outcome models beat random on 100% of seeds at every size; `s_learner` manages 75–90%
with a coefficient of variation above 50% at n=500.

### Step C.3 — Reconciliation ⭐

Hillstrom said uplift wins; Criteo says it loses. Both are real. The governing quantity
is `corr(treatment effect, outcome propensity)` (D-026):

| setting | corr | uplift's advantage | % predicted negative |
|---|---:|---:|---:|
| Hillstrom (mens) | +0.63 | +4.7% | 0.2% |
| Criteo | +0.61 | +0.6% | 19.2% |
| Hillstrom (womens) | +0.07 | +3.9% | 10.2% |
| **SubSim (churn)** | **−0.19** | **+106.8%** | 25.7% |

An outcome model ranks by likelihood of responding; an uplift model by how much treatment
*changes* it. When the orderings coincide, the outcome model wins — it solves an easier
estimation problem, and at small n the variance advantage dominates.

**This refines D-020.** Sleeping dogs existing is not sufficient: Criteo has *more*
predicted-negative customers than Hillstrom-womens (19.2% vs 10.2%) and uplift still adds
nothing. What matters is whether they sit where the outcome model ranks **highest** —
which is what a negative correlation measures.

Figure 3 (`fig03_when_uplift_pays.png`). Stated as a contrast, not a fitted curve: with
four points the ordering among the three positive-correlation settings is within noise,
and the figure says so on its face. The signal is the order-of-magnitude gap at negative
correlation.

### Step C.4 — Two bugs found by tests

**`check_representative` was too permissive.** |1.0 − 0.85| = 0.15 sits inside a 20%
relative band around 0.85, so an all-treated sample passed the check on its own — only
the separate `load_criteo` guard caught it. Degenerate rates are now categorical
failures. Surfaced by `test_representativeness_check_rejects_single_arm`, which failed
on first run.

**Scale-dependent scores were compared across estimators.** The first spectrum run
reported Criteo at `corr = 1.00`, "100% predicted negative". `ClassTransform` outputs
`p/p_treat − (1−p)/(1−p_treat)`, negative unless `p > 0.85` under 85/15 assignment — so
nearly everything scores negative while the *ranking* stays fine. Correlation and
negative-share are now measured on the T-learner, whose output is a genuine probability
difference (D-027).

**167 tests passing.** Criteo tests lock in the treatment-sorting trap, the exclusion of
`exposure` from covariates, and the coupling finding as regressions.

---

## Lenta — out-of-sample test of the correlation principle

### Step L.1 — Getting the data

138MB from `sklift.s3.eu-west-2.amazonaws.com` at ~20 KB/s — ~100 minutes, measured
cleanly after killing four competing curl processes from an earlier retry storm. No
faster mirror exists (the HuggingFace hit for "lenta" is a Russian *news* corpus, not
this dataset), so unlike Criteo there was no 80x shortcut to find.

Loader written while the download ran, applying both Criteo lessons up front: the
single-arm guard, and a **60-feature cap**. The cap matters for the comparison — Lenta
has ~190 columns against Criteo's 12, and letting it use all of them would confound
"more features" with "different domain" in exactly the measurement under test.

### Step L.2 — The prediction

Recorded before the data landed: retail promotion should fall **between** advertising
(+0.61) and subscription retention (−0.19).

**Result: +0.177.** As predicted.

### Step L.3 — Main result

```
lenta[response]: n=687,029  treated 75.1%  ATE +0.0075 (+7.4% lift)

policy               targeted  uplift/1000  incremental             95% CI    qini
treat_all              343515         6.77       2326.1                 --      --
class_transform        103054         9.82       1011.5    [359.0, 1601.4]   201.7
s_learner              103054         8.92        919.4    [284.8, 1496.5]   182.2
outcome_propensity     103054         8.89        916.4    [309.3, 1477.2]   160.7
t_learner              103054         7.98        822.7    [253.7, 1330.5]    25.6
response_model         103054         7.36        758.5    [152.9, 1345.8]   145.5
random                 103054         6.85        705.8    [343.1, 1006.6]     0.0
```

Best uplift beats best outcome by 10.4% — **but every interval overlaps every other,
including random's.** With 343,515 test customers, nothing is distinguishable.

### Step L.4 — Small-n sweep: flat

| train n | outcome_prop | t_learner | s_learner | class_transform |
|---|---|---|---|---|
| 500 | 659±215 | 599±202 | 524±146 | 578±198 |
| 20,000 | 660±206 | 473±140 | 510±153 | 658±201 |

**Nothing improves with more data.** Lenta is underpowered rather than noisy: at a 7.4%
lift there is barely a signal to learn, so 40x more training data changes nothing.

### Step L.5 — What this does and does not establish

*Establishes:* the correlation lands where predicted. That is a genuine out-of-sample
hit for D-026 — the principle was formulated on Hillstrom and Criteo, and Lenta was
chosen because it should fall between them.

*Does not establish:* that the consequence follows. The +10.4% advantage is nominally
the largest among positive-correlation settings, consistent with the principle, but the
intervals make it meaningless.

**One confirming observation, not two** (D-031).

**Secondary observation worth keeping:** 24.9% of Lenta customers are predicted harmed —
comparable to churn's 25.7% — yet uplift buys almost nothing. The *share* of harmed
customers is not what matters; their **correlation with outcome propensity** is. That is
the sharpest available statement of the refinement to D-020.

**172 tests passing.** Figure 3 now carries five settings and states on its face that
the ordering among the four positive-correlation points is within noise.

---

## Phase 2 — Dunning and involuntary churn

**Goal (plan §12):** the module that earns money. Involuntary churn is 20-40% of all
churn, needs almost no causal machinery, and most small businesses do nothing about it.
**Gate: a paying client** — which is a sales task, not a code task, and remains open.

### Step 2.1 — The generative model

`retainiq/sim/dunning.py`. Six decline codes with distinct behaviour under retry:
`insufficient_funds` (40%, timing-driven, payday-sensitive), `expired_card` (18%,
unfixable by retry), `do_not_honor`, `generic_decline`, `processing_error` (transient,
immediate retry works), `lost_or_stolen_card` (unrecoverable).

Kept **separate from SubSim's aggregate model** rather than replacing it (D-034).
SubSim's single Bernoulli is what the Phase 0 gates were tuned against and is adequate
for overall churn; it is useless only for studying retry *policy*, which is what this
module is for. `calibrate_recovery_scale` solves for the scale that makes the passive
policy reproduce SubSim's 0.42, so the two agree by construction.

### Step 2.2 — Policies

`retainiq/policy/dunning.py`. Six, from `no_retry` to `aggressive`. The interesting one is
`code_aware`: it conditions on the decline reason the processor **already gave you** —
retry `processing_error` immediately, snap `insufficient_funds` to the next payday,
don't burn attempts on `expired_card`, stop after one on `lost_or_stolen_card`. No
machine learning involved.

### Step 2.3 — A test caught the simulator flattering itself ⭐

`test_expired_cards_are_not_recoverable_by_retry` failed: expired cards recovered 21.7%
under aggressive retrying. The cause was a gentle `attempt_decay` (0.90) letting eight
retries compound. But retrying a genuinely expired card cannot work — recoveries come
only from the customer updating their card, which does not become likelier because you
retried again.

**This changed the headline** (D-033). Before the fix, `aggressive` had the highest
recovery rate and lost on value: a tradeoff story. After, its advantage vanishes
entirely — it recovers *no more* than a code-aware schedule while using 2.5x the
retries.

Worth recording that the test was written to pin a *mechanism*, and it found a bug
flattering the conclusion. That is the direction that matters, because nobody
investigates a result that looks good.

`recovery_scale` re-solved after the change: 0.4533 → 0.4764.

### Step 2.4 — Results

```
policy               recovery  attempts  emails    net value
processor_default       42.0%     3.09     2.47   17,149,952
fixed_smart             44.8%     3.67     2.47   18,414,361
code_aware              48.9%     2.10     2.03   20,242,692
code_aware_quiet        48.8%     2.09     1.37   20,469,358
aggressive              48.6%     5.29     5.29   19,406,983
```

Three findings:

1. **Knowing which payment failed beats trying harder.** +6.9pp over the processor
   default using **32% fewer attempts**.
2. **`aggressive` is strictly dominated** — 2.5x retries, 3.9x emails, no more
   recovered. It does not even win on the vendor's own metric.
3. **Emailing a third less is worth +227k** at identical recovery. The timing does the
   work, not the nagging.

### Step 2.5 — Out-of-sample calibration check

One parameter was fitted, against the *passive* band (published 30-45%). The model then
reproduces the *dedicated dunning* figure at the other end **without further tuning**:

| configuration | recovery |
|---|---|
| processor default, no updater | 41.9% ← fitted here |
| code-aware + account updater | 54.7% ← published 55-70%, not fitted |

Recorded as "lower edge of the band", not "in the band" — it is 54.7%, not 62%.

### Step 2.6 — Economics and honesty about the assumption

`retainiq/experiments/dunning.py` values policies in money, not recovery rate: lifetime
value retained, minus lifetime value destroyed by contact (D-032), minus operational
cost. Recovering a payment retains a *customer*, not an invoice — and every dunning
email is also a reminder that they are paying you.

The fatigue magnitude is **assumed, not measured** — no public dataset gives the churn
cost of a dunning email. Figure 4's right panel is therefore a sensitivity sweep: the
policy ranking flips at ~0.031 against our assumption of 0.055. Stating where the
conclusion breaks is more useful than asserting the parameter.

**200 tests passing.**

---

## Phase 2 status: **BUILT — gate OPEN**

The technical work is done and the calibration is externally checked. The gate is a
paying client, and no amount of further code closes it. The realistic next step is the
Churn Autopsy outreach in `explainer/06`, not another module.

---

## Churn Autopsy — the first customer-facing artifact

**Goal:** close the gap between a research repo and something a real business can
receive. This is Mode 1 of the three usage modes: a report, not software.

### Step R.1 — What billing data can and cannot support

`retainiq/report/autopsy.py` computes from customers + subscriptions + invoices alone:
retention curve (Kaplan-Meier over pooled tenure rather than signup cohorts, since
small businesses have too few customers per month for cohort curves to be readable),
revenue vs logo churn, the voluntary/involuntary split, failed-payment economics, and
decline-code mix.

Three CSVs from the Stripe dashboard. Ten minutes of clicking, no engineer.

It computes nothing causal, and the report says so in its own footer (D-036).

### Step R.2 — The 0% recovery bug ⭐

The first run reported **0% payment recovery**. Not a modelling error — the SubSim
adapter emitted payment *failures* but never the *retries that succeeded*, so the
canonical data was representationally incapable of expressing recovery.

Left unfixed, every report would have opened with a catastrophic recovery gap and a
correspondingly large "opportunity". Wrong, and in the direction that flatters us.

Fixed by emitting the paid retry (1-6 days later) for any failure that did not end in
involuntary churn — which is, by SubSim's construction, exactly the set that recovered.
Recovery now reads 38.6%, consistent with SubSim's own 0.42 (D-037).

**Third instance of this class of bug**, after Criteo's treatment-sorted prefix (D-024)
and `.exists()` on a downloading file (D-029). The general question worth asking of any
new metric: *could this number be zero because the data cannot express the thing?*

### Step R.3 — Honesty enforced in the artifact

Every `Finding` carries a `measured` flag rendered as a visible badge: green for
*measured from your data*, amber for *estimated from industry benchmarks*. The most
persuasive finding in the report — the recovery gap — is amber (D-035).

Caveats are printed rather than omitted: an export with no decline codes produces a
visible note explaining why that field matters, instead of a silently missing section.

Tests assert both. `test_benchmark_based_findings_are_labelled_as_estimates` and
`test_report_states_what_it_will_not_do` are the two that matter — they pin the
honesty properties rather than the arithmetic.

### Step R.4 — Rendering

`retainiq/report/render.py` produces one self-contained HTML file: inline CSS, inline SVG
charts, no external requests, light and dark. It can be emailed, opened offline,
printed, or placed behind an unguessable URL without any of that being a deployment.

Money at the top, findings ranked by value at stake, retention curve, decline table,
caveats, and a footer stating what the report deliberately will not do.

**20 new tests, 220 total.**

---

### Where this leaves Phase 2

The technical work for the revenue gate is complete: the analysis, the retry policies,
and now the artifact a prospect actually receives. **The gate itself — a paying client
— is a sales task and no further module closes it.**

The next action is running this against ten real businesses.

---

## Phase 3 — Discrete-time survival hazard + CLV

**Goal:** convert "who is likely to churn" into "what is this customer worth, and how
much of it is at risk from which cause". Phases 0-2 argued about targeting; nothing in
them could put a number on a customer.

### Step 3.1 — The model

`retainiq/models/survival/discrete.py`. Each customer is expanded into one row per period
at risk, the row is labelled 1 if they failed in that period, and a binary classifier
is fitted. The fitted probability is the hazard; survival is the running product of its
complements.

Two learners (regularised logistic, histogram gradient boosting) and three baseline-
hazard encodings (saturated dummies with a pooled tail, a restricted cubic spline on
log time, raw period for tree learners). No per-dataset tuning anywhere — one
configuration for every dataset, for our model and for every baseline, since tuning one
side is how a benchmark becomes an advertisement.

Why not Cox, in four points, is D-043. The one that matters most: each person-period
row **is** one point-in-time feature build, so Phase 1's structural leakage guarantee
extends to the survival model unchanged. Cox with time-varying covariates needs a
start-stop frame, which is where that guarantee would have had to be rebuilt by hand.

`CompetingRisksHazard` fits one cause-specific hazard per cause and combines them only
at the survival level (D-044). `S(t) + sum_k CIF_k(t) = 1` holds exactly, and is tested.

### Step 3.2 — Metrics, written rather than imported

`retainiq/models/survival/metrics.py` implements Kaplan-Meier, the censoring distribution,
Harrell's C, the IPCW Brier score, integrated Brier, D-calibration and a binned
calibration curve — on numpy and scipy only.

The reason is not purity. `lifelines` and `scikit-survival` are Phase 3 *extras*, and
CI installs `[dev,viz]`. A metric that cannot run in CI is a metric that silently stops
being checked. They are cross-checked against those libraries where installed:
`test_concordance_matches_scikit_survival` and `test_brier_matches_scikit_survival`
assert agreement to 1e-9 and 1e-6 rather than trusting our own arithmetic.

### Step 3.3 — Two metric bugs, both caught by an external reference ⭐

Neither was in the model.

**The censoring estimator needs the events-before-censorings tie convention.** `G` was
first estimated as Kaplan-Meier with the indicator flipped, which is wrong when events
and censorings are tied — on monthly data, almost always. ~2% on the integrated Brier
score: small enough to look like noise, large enough to reorder near-tied models.
Caught by the scikit-survival agreement test.

**`G(t)` hits exactly zero at the end of follow-up.** Under administrative censoring
nobody can be censored after the last day of the study, so every IPCW weight there is
undefined. Integrated Brier scores came out at **2.6e7** on SubSim — six orders of
magnitude wrong, with the ranking scrambled rather than merely inflated. Invisible on
Telco and GBSG2, where follow-up is staggered, so it survived the first round of runs
and only surfaced when the simulator joined the same table. `brier_score` now returns
NaN rather than a number where the weight is undefined, and `estimable_horizon` keeps
callers out of that region (D-048).

A third correction, smaller: D-calibration needs the discrete randomised-PIT midpoint,
or a correctly specified model is rejected by its own grid (chi2 61.7 vs 2.3). Applied
to every model through one code path, never to ours alone (D-045).

### Step 3.4 — Public data, and the leak everyone ships

`retainiq/benchmarks/survival_data.py`. Telco (IBM, 7,043 customers — real, public,
contractual subscription), GBSG2 (686 patients, the benchmark RSF and DeepSurv were
developed on), and SubSim.

**`TotalCharges` is excluded from Telco.** It is cumulative billing, r = **0.83** with
tenure — a direct encoding of the duration being predicted. Published Telco survival
analyses that feed the raw column set into a Cox model have this, and it flatters them
(D-047).

Telco's 11 zero-tenure customers are dropped explicitly rather than coerced to 1:
they completed no period at risk, and inventing one would invent it for the customers
least likely to have had it.

### Step 3.5 — Results

Mean over 10 resplits. IBS lower is better; calibration slope 1.0 is perfect.

**Telco** — the dataset that matches the vertical:

| model | C-index | IBS | cal. slope | ours wins on IBS |
|---|---:|---:|---:|---:|
| **discrete-time (logistic)** | 0.8650 | **0.0824** | 1.02 | — |
| DeepSurv | 0.8661 | 0.0825 | 0.98 | 4/10 |
| discrete-time (GBM) | 0.8608 | 0.0865 | 1.00 | 10/10 |
| Cox PH | 0.8565 | 0.0914 | 1.18 | 10/10 |
| Random Survival Forest | 0.8461 | 0.0964 | 1.18 | 10/10 |
| Kaplan-Meier | — | 0.1823 | — | 10/10 |

**GBSG2** — RSF wins (C 0.698 vs 0.678, IBS 0.183 vs 0.187), as predicted before the
run. Discretising seven years of daily follow-up onto months costs resolution the
continuous-time models keep. The discrete model still has the best calibration slope
in the table (1.09 against Cox's 1.48).

**Kaplan-Meier is the reason IBS is the headline.** On `cal_mae` alone, Kaplan-Meier
(0.0268) *beats* Cox (0.0439) on Telco — a model with no covariates is trivially
calibrated. On IBS it is not competitive at all (0.1823 vs 0.0824). Reporting
calibration error as the headline would have made "predict the average for everyone"
the winning strategy (D-045).

**Landmark prediction on SubSim** — at month L, using only what was observable at L,
predict the next six months. Against the same model restricted to signup-time
covariates:

| customers | 250 | 500 | 1,000 | 2,000 | 4,000 |
|---|---|---|---|---|---|
| time-varying ranks better | 55% | 100% | 92% | 100% | 100% |
| ...vs Cox refitted per landmark | 55% | 92% | 75% | 58% | 75% |

Seeing covariates move is worth having from ~500 customers up, by a modest +0.03
C-index. **Below 250 customers nothing reliably beats Kaplan-Meier** — the most useful
number here and one we did not predict. Against Cox refitted at each landmark it is a
wash with no trend in n, so the *pooling* hypothesis is **not established** (D-049).

### Step 3.6 — CLV

`retainiq/models/clv/value.py`. `CLV = sum_t margin * S(t) / (1+d)^t`, with three choices
that are not incidental: contribution margin rather than revenue, monthly-compounded
discounting, and a **finite horizon capped at the observed support**. `clv()` raises
rather than extrapolating (D-046) — the `ARPU / churn_rate` formula everyone uses is an
infinite geometric sum that assumes a constant hazard forever, and hazards decline with
tenure by construction here (D-004).

On 4,000 simulated customers at 75% margin and a 12% annual discount, over the observed
24-month support:

- book value **2.22M**, mean CLV 554, median 412, p90 1,126 — heavily right-skewed, so
  the mean alone says little;
- shortfall against perfect retention **2.63M**, splitting exactly into **72.5%
  voluntary / 27.5% involuntary** with no residual;
- **the top decile by value at risk overlaps the top decile by churn risk by only
  21%.** Ranking by churn probability finds the wrong 79% of the money.

That last number is the point of the phase. `treatment_value(clv, tau, cost)` is the
bridge to Phase 4: an identical treatment effect is worth a hundred times more on one
customer than another, and no amount of churn-model accuracy tells them apart.

### Step 3.7 — Figure 5

`fig05_survival_calibration.png`. Left: predicted vs observed survival on Telco, where
Cox and RSF sit visibly off the diagonal and the discrete model and DeepSurv sit on it.
Right: the win rate by business size, with the coin-flip line drawn and the n=250 bar
left honestly at 55%.

Deliberately not a bar chart of concordance — on rank this is a tie, and a figure
claiming otherwise would be the wrong figure.

**54 new tests, 277 total.**

### Where this leaves Phase 3

The gate — "beats Cox/RSF/DeepSurv on public data; calibrated" — is **met for Cox and
RSF (10/10 resplits on Telco) and a tie with DeepSurv**. Calibration is met: best or
tied-best slope on every dataset, D-calibration not rejected on Telco where Cox and RSF
are rejected at p < 1e-4.

What Phase 3 actually bought is not accuracy but *representation*: time-varying
covariates through the existing point-in-time path, competing risks that stay separate
all the way to the output, and calibrated absolute probabilities CLV can multiply by
money. DeepSurv matches the numbers, does none of those three, and costs a ~2GB
dependency.

---

## Pre-Phase-4 audit

A full re-verification before moving on, rather than trusting the documentation.
Everything was re-run from scratch: `make check`, `make survival`, `make clv`, and a
mechanical check of the paper.

### What held up

Every Phase 3 claim reproduced exactly:

| Claim | Verified |
|---|---|
| Telco IBS 0.0824 vs Cox 0.0914 / RSF 0.0964 | ✅ `ours_beats_it_on_ibs` = 1.000 for both (10/10) |
| Ties DeepSurv (0.0825) | ✅ win rate 4/10 — a genuine tie, reported as one |
| Loses GBSG2 to RSF | ✅ 0.1867 vs 0.1832, 2/10 — reported as a loss |
| CLV shortfall 72.5 / 27.5 | ✅ exact |
| 21% decile overlap | ✅ exact |

Paper: 22 citations all resolve, no broken `\ref`, and all 16 headline numbers match
the code. Section 8's `\todo` marker is intact and its README still states it is
specification only.

### What did not

**The paper contained no figures.** Five existed; `\includegraphics` count was zero.
Four are now placed and referenced in prose — the kill test, the correlation principle,
small-*n* reliability, and survival calibration. The dunning figure correctly stays out:
the paper does not discuss dunning at all (0 mentions), so its home is the explainer.

**The explainer stopped at Hillstrom.** Criteo, Lenta and the `corr(τ, π)` principle —
the paper's lead contribution — appeared nowhere in the non-technical documents. A new
section in `05-the-evidence.md` covers all three, with the figure. Phase 2's dunning
result and Phase 3's calibration argument likewise had no explainer home; both now do.

**The README was frozen at Phase 0.** It claimed 58 tests (actual: 277), "Status: Phase
0 complete", a layout listing two of eight packages, and a decision range of D-001…D-013
against an actual 49. Rewritten.

**Five degenerate survival inputs produced solver-internals errors** and one silently
lost a competing risk. Fixed with clear messages (D-051), each with a regression test.

**Survival extrapolated freely while CLV refused to** (D-050). `survival()` now records
its observed support and refuses to project past it unless asked, matching invariant 12.

**`survival_benchmark.py` (510 lines) was untested** — the largest untested module, and
the one producing the paper's Table 4. 14 tests added, covering the evaluation grid
(where an over-long horizon makes IPCW weights undefined rather than noisy), the
landmark slice (where the future can leak into a time-varying model), and the guarantee
that every model goes through one scoring path.

### Two tests that were wrong, not the code

Both recorded in D-052. "No censoring" at the subject level still yields non-event rows
at the person-period level; and `duration == window` in a landmark slice contains both
failures in the final month and censorings at the edge. Roughly half the failing tests
written during this project have been the test rather than the code — worth asking which
is wrong before reaching for the source.

**302 tests, up from 277. Lint clean, both calibration gates green.**

---

## Phase 4 — hierarchical Bayesian CATE with abstention

**Gate:** beat baselines on realised money at small *n*. **Result: PARTIALLY MET.**

### Step 4.1 — The estimator

`retainiq/models/uplift/bayesian.py`. Bayesian logistic with a treatment interaction, so
`tau(x) = tau_0 + x'gamma`. The split matters because identifiability differs wildly:
the sign of `tau_0` is usually settled by a few hundred subjects, `gamma` almost never
is.

`sigma_gamma` is **marginalised over a grid weighted by marginal likelihood**, not fixed
and not plugged in at its mode. When heterogeneity is unsupported the weight moves to
small values, every `tau_i` collapses onto `tau_0`, and the model degrades into
"estimate one average effect well" rather than "estimate n effects badly". Measured: at
n=2000 with no true heterogeneity, `sigma_gamma` → 0.0013 and the spread of estimated
`tau_i` → 0.0000.

`tau_i` is linear in the coefficients, so each mixture component is exactly Gaussian and
the decision rule needs no sampling.

### Step 4.2 — Is the posterior honest? ⭐ the useful detour

Coverage was under nominal: 90% intervals containing truth 83% of the time at n=250.
Over-confidence is the dangerous direction, so this needed diagnosis rather than a note.

**Suspected the Laplace approximation. It was not the cause.** Fitting the same model
with NUTS (`mcmc_check.py`, the discipline of D-048):

| n | posterior sd ratio (Laplace/NUTS) | mean correlation |
|---|---|---|
| 250 | 0.993 | 0.9998 |
| 500 | 1.003 | 1.0000 |
| 2000 | 0.988 | 1.0000 |

Laplace reproduces NUTS to three decimals, and **NUTS shows the same deviation**. The
cause is the empirical-Bayes treatment of `sigma_gamma` (D-053), a known limitation.

Mixing over the grid rather than plugging in the mode narrowed the gap; it did not close
it. **Not patched further, because the error runs against the claim**: an over-confident
posterior abstains *less*, making the differentiation harder to demonstrate. Inflating
variance until coverage looked right would be tuning until the result improved.

### Step 4.3 — The gate

Ground truth withheld from every policy. Comparator is the strong version: same
estimator's point estimate, same customer values, ranks and fills the budget — so the
comparison isolates **abstention**, not the fact that customers differ in worth.

| n | beats ranking | beats doing nothing | treated (abstain / rank) |
|---|---|---|---|
| 250 | 75% | **10%** | 7 / 23 |
| 500 | 80% | **10%** | 15 / 46 |
| 1,000 | 70% | **5%** | 32 / 90 |
| 2,000 | 65% | **0%** | 72 / 181 |
| 4,000 | 80% | **10%** | 127 / 359 |

**Beats ranking consistently, spending a third as much. Beats doing nothing almost
never.**

Threshold sweep: at `alpha=0.05` the rule treats **zero** customers and returns exactly
the do-nothing baseline. The safety property works — it correctly recognises it does not
know enough. There is no alpha at which it turns a profit.

Cross-tenant pooling with a prior from ten established firms cuts mean losses from −457
to −62 at n=500, by making the small firm treat 2 customers instead of 12. Same
character: damage limitation, not profit.

### Step 4.4 — What this means

The result is what Section 6 predicts. A decision rule inherits the quality of its
inputs; at these sample sizes the inputs are unreliable (D-023). Abstention makes the
*consequences* survivable, it cannot manufacture reliability that is not in the data.
The Phase 0 precursor used oracle effects and was always an upper bound — which is
exactly what these numbers demonstrate.

Paper §8 now reports results rather than a specification, and says plainly that the gate
is half met. The defensible claim is narrower than intended: *given that ranking
destroys value, a rule that reliably returns to zero is worth real money relative to
current practice*.

**25 new tests, 327 total.** They pin the mechanism — pooling collapse, the rule
reducing to a point threshold as the posterior concentrates and to treating nobody as it
widens, budget as a ceiling rather than a quota — because a negative result is only
worth anything if the thing that produced it demonstrably works.

---

## Step 4.5 — Probing the gate at larger effect sizes (D-055, D-056)

D-054 named an untested explanation for the Phase 4 failure: the calibrated effect may
simply be too small to pay for the offer. Tested as a **sensitivity** —
`retainiq/experiments/sensitivity.py`, `make sensitivity`. `run_once`/`sweep` gained optional
`config` and `offer` arguments; both default to the calibrated simulator and the reference
discount, and a test asserts the no-argument path is numerically identical, so every D-054
number is reproduced unchanged.

### What the arithmetic said before any policy ran

Treating pays iff `-tau * CLV > cost`. Break-even is **0.040**; the mean effect is
**0.010**. An oracle knowing every `tau_i` treats **5.8%** of customers. Phase 4 asked an
estimated rule to find profit inside that 5.8%, from a pilot of a few hundred people. The
gate was out of reach on arithmetic, not on decision theory.

### Axis 1 — effect size (requested)

The gate flips: `saveability_scale = -5` beats do-nothing on 57% of draws. It is not worth
having. The two win rates move in **opposite** directions — at no swept setting is either
significantly above chance while the other also is — and the regime where abstention beats
inaction is the regime where blanket treatment beats abstention. Sleeping dogs fall 27% →
3% along the way, so a passing row describes a world without the mechanism the project
studies. Past −5.0 the settings also leave the calibration band of invariant 4.

### Axis 2 — offer choice (free, and the one that mattered)

Phase 4 ran on `discount_20_3mo`, cost 32 — the second dearest rung of a ladder fixed in
Phase 0 and unmodified here. `feature_nudge` costs 0.10 and clears break-even for 69% of
customers. No rung passes the gate, and the failure modes are opposite: discounts are
detectable but unprofitable, the nudge is profitable but undetectable at n≈250.
**Detectability and profitability are anti-correlated across the ladder.**

### A hypothesis raised and refuted

Axis 1 made abstention look like a minimax-regret hedge (max regret 34.9%, versus 100%
for both `do_nothing` and `treat_all`). Formed *after* seeing the failure, so it was
pre-registered and tested on axis 2, which played no part in forming it. **It failed** —
`random_30pct` has lower max regret (58.9% vs 85.7%). Withdrawn.

The failure localised a real defect. The rule fixes `alpha = 0.30` for every decision; the
best alpha per rung is 0.49 on cheap offers and 0.05 on discounts, and `pause_offer` —
cheap but harmful on average — wants 0.05, showing the driver is payoff *asymmetry*, not
cost. A constant alpha is wrong by construction. **Not fixed in this commit**: repairing a
flaw in the same pass that found it is how a sensitivity becomes tuning. It is specified
as a Phase 5 item, to be run on the axis that refuted its predecessor.

### Measurement fix found on the way

`summarise` scored "beats do-nothing" with a strict `> 0`, which counts a rule that
correctly treats **nobody** (value exactly 0) as a failure, identically to one that loses
money. Since declining to act is the entire safety claim, that conflation hid the property
being claimed. Added `abstain_ties`, `abstain_not_worse`, and the `treat_all` comparator.
The D-054 headline is unaffected — at those settings the rule was treating and losing.

**10 new tests, 337 total.** Most assert *absence* of change: that parameterising `run_once`
left the default path identical, and that sweeping a nested config does not mutate the
shared default. A sensitivity that moved its own baseline would be indistinguishable from
the recalibration it exists to avoid.

---

## Step 5.1 — The decision layer, and a units bug that had been there all along (D-057, D-058)

Phase 5 began with the correction D-056 specified, pre-registered in
`docs/PREREG-phase5.md` and committed before any of it ran. Reading the rule in order to
change it surfaced something larger.

### The bug

`AbstentionPolicy.decide` computed `-tau * value - cost` where `tau` is a **log-odds
ratio**, not a probability difference. On one draw the rule believed treating was worth
**-104.5** where the truth was **+20.5** against a 31.5 offer. The overstatement scales as
`1/(p0(1-p0))` — 4x at `p0 = 0.5`, **25x at `p0 = 0.05`** — so it inflated the value of
treating customers who were never going to leave. That is the Sure Thing quadrant, i.e. the
error the whole project exists to characterise, reproduced inside our own decision rule.

Every Phase 4 test passed and none of them was wrong; they were all self-consistency checks,
and a units error is consistent with itself. The rule's own test compared it against the
same wrong formula. The estimator's tests used synthetic `tau` on the logit scale. **Nothing
asked what the number meant in currency.**

Fixed in `retainiq/policy/economics.py`: convert on the probability scale first, using the
baseline `eta0 = a + x'b` from the same fit, sampling `(eta0, tau)` jointly because they are
correlated and `expit` destroys the closed form. The new rule takes a `MoneyPosterior` and
nothing else, so the mistake is now unrepresentable.

### What the fix bought, against predictions made first

Losses fell sharply — n=2000: **-3,531 → -1,070**, treating 27 rather than 72; the deep
discount at `alpha=0.05` went **-5,384 → 0**, correctly treating nobody — and the rule now
beats corrected ranking on **93%** of draws. Of five registered predictions, two held, one
half-held, and **two failed**: no cheap rung passes the gate (1d), and the per-rung `alpha`
spread did not shrink (2a). 2a failing means D-056's claim survives a challenge we raised
against ourselves. **The bug was real, the repair necessary, and not sufficient.**

### Phase 5 proper — the offer-ladder optimiser

`retainiq/policy/ladder.py` fits one effect model per rung from a randomised multi-arm pilot
(never the simulator's `saveability_multiplier`, which is oracle knowledge), pools across
rungs using the D-041 cross-tenant machinery, and picks `argmax_k E[B_ik] - lambda*SD[B_ik]`,
abstaining when nothing clears zero.

**Gate not met, and the closest the project has come.** The optimiser is the first estimated
policy here to make money on average (655 / 1,039 / 2,252 at n = 500 / 1,000 / 2,000),
capturing 28% of the oracle against 13% for the achievable alternative — but it beats that
alternative on 58% of draws, CI [0.42, 0.72], which is not distinguishable from chance.

The result worth keeping: a pilot-chosen best rung agrees with the true best rung on **13%**
of draws, barely above the 17% of a random guess among six, and returns *negative* money at
n=1000. **Choosing the right default offer is worth far more than per-customer targeting,
and it is what small businesses are least able to do themselves.** Risk aversion did not
help; `lambda = 0` dominated throughout, which is the opposite of what the abstention thesis
predicted, and is reported because it was swept rather than chosen.

**20 new tests, 357 total.** Reason codes and the dashboard are not built, so the phase gate
is unmet on those grounds too, independently of the numbers.

---

## Step 5.2 — Reason codes (D-059), ported from RetainIQ-PBL and rebuilt

Closes the "without asking us" half of Phase 5's gate. `retainiq/report/reasons.py`.

**Explains the decision, not the prediction.** The donor implementation is SHAP over an
XGBoost churn classifier: "87% risk because days-since-purchase = 400". An owner can
already see that, and it does not say whether acting pays. Ours decomposes the money
identity `-delta_p * V - c` — how much the offer moves this person, what keeping them is
worth, what it costs — and states why this rung rather than the next best.

**Attribution is exact and dependency-free.** `tau_i = tau_0 + x_i'gamma` is linear, so
the Shapley value of feature `j` is exactly `gamma_j * xs_ij` after standardisation. No
sampling, no `shap` package, invariant 7 intact. A test pins that rows sum to
`tau_i - tau_0`.

**Three things it can say that a SHAP-over-a-classifier cannot.** That nothing specific
to this customer drives the recommendation (the normal case here — `sigma_gamma`
collapses at these sample sizes, D-058). That their profile argues *against* the offer
and it is recommended on value alone. And D-058's reliability, on every line, so no
per-customer output claims more than 58% [0.42, 0.72] supports.

**Two bugs found by reading the output rather than the tests.** Every driver was labelled
"higher than typical" regardless of the customer's actual value — the sign of the
*contribution* and the sign of the *feature* are independent and had been conflated, and
the first render read "here are three reasons this will not work, so do it". And
abstention could not distinguish "nothing pays here" from "the budget went to someone
better", which are a verdict about the customer and a verdict about the budget;
`Recommendation.budget_trimmed` now separates them.

**16 new tests, 373 total.** D-060 records the full comparison, including that running
RetainIQ-PBL's own pipeline reproduces our P1 leakage finding independently (ROC-AUC 0.543
against a published 1.000).

---

## Step 5.3 — The retention dashboard (D-061)

`retainiq/report/dashboard.py`, `make dashboard`. Self-contained HTML: inline CSS, inline SVG,
no server, no new dependency. Reuses the Autopsy's stylesheet, theme toggle and the D-038
sentinel-colour machinery, so the charts follow light/dark rather than baking a colour at
render time. `retainiq/experiments/dashboard_demo.py` runs the whole Phase 5 path end to end --
simulate a tenant, randomised multi-arm pilot, per-rung fits, rung choice, reason codes,
page -- so the numbers on it are the numbers the gate measured, not a mock-up.

Structure: reliability banner, headline counts, what we recommend (chart), who to contact
(sortable table, click a row for its reasoning, filter by offer), why we are leaving most
customers alone, and what this cannot tell you.

**Two things found by looking at the rendered page, not by running the tests.** The
top-ranked rows included a 40% discount costing ~1,972 at a **47%** chance of paying --
correct behaviour for an expected-value rule, and unreadable as presented, because the
caution was inside the collapsed detail. Sub-60% rows are now flagged inline. And the
first dark-mode render was checked visually rather than assumed, because D-038 was exactly
this failure.

Verified in the browser in both themes; row expansion and the offer filter exercised
directly. **15 new tests, 388 total** -- mostly that the page cannot become more confident
than the evidence: the banner is unconditional and precedes the table, weak rows are
marked where the money is, the two kinds of abstention stay distinct, and tenant-supplied
ids and business names cannot inject markup.

**Phase 5's gate is met on its own terms and the evidence is unchanged.** The optimiser
still wins 58% [0.42, 0.72]. Presenting a recommendation better does not make it better,
which is what the banner is there to say.

---

## Step 2.1 — Making the Autopsy deliverable (D-062)

Phase 2's gate is a paying client. It is a sales task, but there was an engineering
blocker hiding behind that description: **no command took a business's CSV export and
produced a report**. Tested against a realistic Stripe dashboard export and found four
failures in a row -- `Created (UTC)` matching nothing, bare `id` binding to the wrong
column, `Email` beating the real id column, and required columns a real export simply does
not contain. All fixed; the alias resolution is now table-aware.

`retainiq/ingest/preflight.py` is the new piece and the important one. It answers one question
before anything is computed: *is this file safe, and what have we had to assume?* The check
that motivates it is currency units -- Stripe exports cents, so a `Plan Amount` of 2900 is
$29.00, and loading it as MRR makes every figure in the report 100x too large. It blocks
rather than converting, because silently dividing by 100 would be the same class of error
as the one it catches (D-057).

`retainiq/cli.py` (`make preflight`, `make autopsy`) is argparse-only, no new dependency. The
report command re-runs the checks and refuses to render on a blocker.

`docs/SALES-RUNBOOK.md` covers the non-code half, including a table of claims that are
**not** permitted, each tied to the experiment that forbids it -- D-058's 58% among them.
Making delivery easy also made overselling easy, so the limits were written down in the
same pass.

**20 new tests, 408 total**, mostly pinning refusals. One preflight check was **deleted**
for being unreachable: duplicate keys are caught by `Dataset.validate` during load, so a
check at that level could never fire, and a safety net that cannot catch anything is worse
than none.

**The gate is unchanged: nobody has paid anything.** What changed is that it can no longer
fail for a reason we control.
