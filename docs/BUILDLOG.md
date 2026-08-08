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

`keel/sim/config.py` — every generative parameter, named and documented with its sign
convention. Nothing is a magic number inside the simulation loop, because paper 1's
contribution *is* the calibration of these values.

`keel/sim/latents.py` — eight per-customer latent traits with Beta marginals.
`attention` and `engagement_base` are drawn correlated through a Gaussian copula
(D-002); this is the mechanism that makes the whole project necessary.

**One thing redone:** the first version hand-rolled an incomplete-beta series and an
`erf` approximation to stay dependency-free. It was buggy and pointless — scipy was
already present. Replaced with `scipy.stats.norm.cdf` + `scipy.stats.beta.ppf`, which
is both correct and the defensible thing to cite in a paper.

---

### Step 0.3 — Lifecycle and hazard engine

`keel/sim/hazard.py` — the monthly churn-hazard logit, isolated so that the stochastic
historical simulation and the semi-analytic counterfactual window share one definition.
If those two ever diverged, every causal result in the project would be silently wrong.

`keel/sim/subsim.py` — month-by-month simulation emitting a person-period panel of
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

`keel/sim/calibration.py` — explicit targets sourced from published 2026 SMB-SaaS
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

`keel/sim/counterfactual.py` — the reason SubSim exists. Emits **exact** ground-truth
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

`keel/experiments/kill_test.py`. Plan §14.3 gate. Three choices make it honest:

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

`keel/experiments/figures.py` → `papers/figures/fig01_kill_test.png`. Two panels,
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

`keel/core/schema.py` — six tables: `customers`, `subscriptions`, `invoices`, `events`,
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

`keel/core/features.py`. 15 standard features across billing, engagement, support, and
contact fatigue.

The guarantee is **structural, not procedural** (D-015): every feature reads source
rows through exactly one function, `_visible`, which applies the temporal filter. There
is no other path to the data, so a feature that bypasses it cannot be written.

Features are declarative (`FeatureSpec`) rather than lambdas so they can be *audited* —
we can ask which rows a feature may touch without running it.

### Step 1.3 — SubSim → canonical adapter

`keel/ingest/subsim_adapter.py`. Expands aggregate counts into individual timestamped
rows and injects **realistic availability lag** (0.24–6h for events, 0.5–2 days for
decline codes). Without that lag the point-in-time machinery would be untested —
filtering on either timestamp would give identical answers.

### Step 1.4 — Leakage suite

`keel/core/leakage.py`. Three independent checks: availability audit (structural),
time-travel consistency (behavioural), and canary injection (adversarial).

**The suite is required to have teeth** (D-017). It must *fail* on deliberately leaked
vintages and *catch* a planted canary, while *not* flagging honest features. A leakage
suite that has never caught a leak is evidence of nothing.

### Step 1.5 — Leakage penalty measured ⭐

`keel/experiments/leakage_penalty.py`. Built the same features three ways:

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

`keel/ingest/stripe.py` — pure functions over fetched JSON, no API key needed, so the
logic most likely to be quietly wrong (money and time) is actually covered. Handles
zero-decimal currencies (JPY 2000 is ¥2000, not ¥20), interval normalisation (an annual
plan must not look 12× more valuable), and the `canceled_at` vs `ended_at` distinction
— a customer who cancels on the 1st with service until the 31st has *not* churned yet.

`keel/ingest/csv_ingest.py` — the Churn Autopsy delivery path. Forgiving about shape
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

`keel/benchmarks/` — dataset loaders with row-count verification (a truncated CSV parses
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

`keel/sim/dunning.py`. Six decline codes with distinct behaviour under retry:
`insufficient_funds` (40%, timing-driven, payday-sensitive), `expired_card` (18%,
unfixable by retry), `do_not_honor`, `generic_decline`, `processing_error` (transient,
immediate retry works), `lost_or_stolen_card` (unrecoverable).

Kept **separate from SubSim's aggregate model** rather than replacing it (D-034).
SubSim's single Bernoulli is what the Phase 0 gates were tuned against and is adequate
for overall churn; it is useless only for studying retry *policy*, which is what this
module is for. `calibrate_recovery_scale` solves for the scale that makes the passive
policy reproduce SubSim's 0.42, so the two agree by construction.

### Step 2.2 — Policies

`keel/policy/dunning.py`. Six, from `no_retry` to `aggressive`. The interesting one is
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

`keel/experiments/dunning.py` values policies in money, not recovery rate: lifetime
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

`keel/report/autopsy.py` computes from customers + subscriptions + invoices alone:
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

`keel/report/render.py` produces one self-contained HTML file: inline CSS, inline SVG
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
