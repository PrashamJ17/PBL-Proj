# Keel — Retention Decisioning Under Small-Sample Causal Uncertainty

**Comprehensive Project Report and Technical Defence**

---

| | |
|---|---|
| **Student** | Prasham Jain |
| **Registration Number** | 2427030155 |
| **Programme** | B.Tech, Computer Science and Engineering |
| **Semester / Year** | V Semester, 3rd Year |
| **Mentor** | Dr. Rishi Gupta |
| **Date** | 11 August 2026 |
| **Repository** | `https://github.com/PrashamJ17/PBL-Proj` (private at time of submission) |

---

## Table of contents

1. [What is the project?](#1-what-is-the-project)
2. [Why is it necessary? What problem does it solve?](#2-why-is-it-necessary-what-problem-does-it-solve)
3. [The solution](#3-the-solution)
4. [Technical explanations: models, algorithms, and why these and not others](#4-technical-explanations-models-algorithms-and-why-these-and-not-others)
5. [Results](#5-results)
6. [How do we know it is trustworthy?](#6-how-do-we-know-it-is-trustworthy)
7. [Data, training, and the cold-start problem](#7-data-training-and-the-cold-start-problem)
8. [Architecture and codebase](#8-architecture-and-codebase)
9. [Testing and engineering discipline](#9-testing-and-engineering-discipline)
10. [What did not work](#10-what-did-not-work)
11. [Comparison with a sibling project (RetainIQ)](#11-comparison-with-a-sibling-project-retainiq)
12. [Limitations](#12-limitations)
13. [Future work](#13-future-work)
14. [Anticipated examination questions](#14-anticipated-examination-questions)
15. [References](#15-references)

---

## 1. What is the project?

**Keel** is a retention *decisioning* system for small subscription businesses. It does
not primarily answer "who will churn." It answers three harder questions:

1. **Who should we treat**, given that treating some customers actively destroys value?
2. **With which intervention**, from a ladder ordered by margin cost?
3. **Does it pay**, measured in currency against doing nothing?

And it does something unusual for an ML system: **it abstains** when the evidence is too
thin to justify spending money, rather than producing a confident recommendation anyway.

The project comprises a calibrated agent-based simulator with exact ground-truth
counterfactuals, a point-in-time-correct feature store, a discrete-time survival model
with competing risks, a hierarchical Bayesian treatment-effect estimator, an offer-ladder
optimiser, a client-facing diagnostic report, and a research paper drafted from the
results.

**Scale:** 12,551 lines of Python, 4,957 lines of tests, 433 automated tests, 63
documented design decisions, 7,221 lines of documentation, 34 commits, continuous
integration across Python 3.11, 3.12 and 3.13 with four gates.

---

## 2. Why is it necessary? What problem does it solve?

### The commercial problem

Subscription businesses lose customers continuously. A 5% monthly churn rate compounds to
roughly 46% of the customer base lost per year. The standard industry response is to rank
customers by predicted churn probability and send the top slice a discount.

**This response is not merely ineffective. Under identifiable conditions it loses money.**

### Why ranking by churn risk fails

There are four types of customer, defined by what happens with and without an
intervention:

| | **Stays if treated** | **Churns if treated** |
|---|---|---|
| **Stays if untreated** | *Sure Thing* — money wasted | ***Sleeping Dog*** — you caused the churn |
| **Churns if untreated** | ***Persuadable*** — the only profitable group | *Lost Cause* — money wasted |

A churn score ranks by *risk*, not by *responsiveness*. The customers it ranks highest
include dormant subscribers who have half-forgotten they are paying. A retention email to
such a customer is a reminder to cancel. **You have paid money to destroy revenue.**

This is the Sleeping Dog mechanism, and it is why retention is adversarial in a way that
advertising and promotion are not.

### What is already known, and what is not

Ascarza (2018, *Journal of Marketing Research*) established with two field experiments
that risk-based targeting is **ineffective** — the highest-risk customers are not the most
responsive. That result is prior art and this project does not restate it as its own.

Three questions remain open, and they are the ones this project addresses:

1. **When is effect-based targeting worth its extra statistical cost?** Estimating a
   treatment effect is harder than estimating a probability; when does paying that cost
   buy anything?
2. **Can risk-based targeting be actively harmful, not merely ineffective?**
3. **At the sample sizes of the businesses that need this most — hundreds of customers,
   not millions — is any of it reliable?**

### Why small businesses specifically

Published uplift results come from datasets of 10⁴ to 10⁷ customers. The subscription
businesses where retention economics are most acute have *hundreds*. Existing tooling
requires roughly 500 customers with substantial history before it produces any prediction
at all. Below that threshold, nothing exists.

---

## 3. The solution

A five-layer architecture. The value concentrates in layers 3–5, which is where existing
tools are absent.

```
1. CONNECT      Stripe / Razorpay / Chargebee / CSV exports
                     |
2. CANONICAL MODEL + POINT-IN-TIME FEATURE STORE
                Every fact carries occurred_at AND available_at.
                As-of joins only; leakage is structurally impossible.
                     |
3. THE MODELS   Voluntary churn: discrete-time competing-risks hazard
                Involuntary churn: retry-timing and decline-code model
                Customer value:   CLV with uncertainty, refusing to extrapolate
                Treatment effect: hierarchical Bayesian CATE with a posterior
                     |
4. THE POLICY   maximise  E[-Delta_p * V - c]  over the offer ladder,
                subject to budget, and ABSTAIN when too uncertain
                     |
5. ACT + PROVE  Client report, CSV worklists, dashboard,
                permanent randomised holdout (Phase 6, not yet built)
```

### The offer ladder — the product opinion

Interventions are ordered by **margin cost, ascending**. Discounts are the last resort,
not the first.

| Rung | Intervention | Margin cost |
|---|---|---|
| 0 | Do nothing (abstain) | 0 |
| 1 | Feature nudge / education | ~0 |
| 2 | Check-in call | staff time |
| 4 | Pause subscription | deferred revenue |
| 5 | Plan downgrade | partial revenue |
| 7 | Time-boxed discount | direct margin |
| 8 | Deep discount | heavy margin |

Rungs 0–5 are where margin is preserved. Most competing products begin at rung 7.

---

## 4. Technical explanations: models, algorithms, and why these and not others

### A. Discrete-time survival hazard (not a binary classifier)

**What:** one row per customer per month at risk; model the monthly hazard
`h(t) = P(churn at t | survived to t)`; chain to get the survival curve.

**Why not a binary classifier?** Three reasons, in order of severity:

1. **Censoring.** A customer who has not churned *yet* is not a negative example — they
   are censored. Treating them as negatives biases every estimate.
2. It answers "if" but not "when", and "when" sizes the intervention window.
3. The label requires an arbitrary horizon, which silently changes the target.

**Competing risks:** voluntary churn (a decision) and involuntary churn (a failed card)
are modelled as **separate processes and never summed**. Merging them — which most
published churn models do — makes 20–40% of the problem invisible to the model meant to
explain it.

**Calibration over discrimination.** These probabilities get multiplied by revenue, so
being correctly *scaled* matters more than being correctly *ordered*. The project reports
integrated Brier score and D-calibration, not only AUC.

### B. Hierarchical Bayesian CATE with adaptive pooling

**What:** `logit P(churn) = alpha + x'beta + T(tau_0 + x'gamma)`, where `tau_0` is the
average treatment effect and `gamma` its heterogeneity. The heterogeneity scale
`sigma_gamma` is given a prior and **estimated from the data** rather than fixed.

**Why this and not a T-learner or causal forest?** This is the core methodological choice.
When heterogeneity is not identifiable — the normal situation at n = 500 — the marginal
likelihood drives `sigma_gamma` toward zero, every individual estimate collapses onto the
population effect, and the model **degrades gracefully** into "estimate one average effect
well" instead of "estimate 500 individual effects badly."

A T-learner cannot do this: it fits two separate models and differences them, so its
per-customer estimates stay noisy no matter how little signal exists — and the noise is
exactly what a top-k rule then ranks on.

**Why Laplace rather than MCMC?** `tau_i` is linear in the parameters, so under a Gaussian
posterior on the coefficients its own posterior is exactly Gaussian: closed form, no Monte
Carlo error inside the decision rule. The approximation was **validated against NUTS** —
posterior widths agree within 1%, means correlate above 0.9998.

### C. The abstention rule

Treat customer *i* only when

```
P( -Delta_p_i * V_i > c_i | data )  >  1 - alpha
```

In words: only when we are confident enough that the **money** gained exceeds the money
spent. Not that the effect is positive — that it is large enough, on a customer valuable
enough, to be worth the offer.

Three properties, each tested:

- It **ranks on money, not effect**. A large effect on a cheap customer loses to a small
  effect on a valuable one.
- It **abstains rather than filling the budget**. Every top-k rule spends its whole budget
  by construction; there is no k at which it declines.
- It **degrades correctly**: as the posterior concentrates it becomes a point-estimate
  threshold; as it widens it treats nobody.

### D. Point-in-time correctness

Every fact in the canonical schema carries **two** timestamps: `occurred_at` (when it
happened) and `available_at` (when it became knowable). Features filter on the second,
never the first, and a single code path (`FeatureStore._visible`) is the only route to
source data.

**Why this matters is measured, not asserted** — see §5.

### E. Tooling choices

| Choice | Why |
|---|---|
| numpy / pandas / scipy only in the core | Heavy ML libraries are optional extras. The diagnostic must run anywhere. |
| Self-contained HTML reports (no server) | Can be emailed, opened offline, printed. Asks less trust than a login. |
| argparse CLI, no framework | The delivery path adds no dependency. |
| pytest + GitHub Actions, 3 Python versions | Four CI gates: tests, calibration, leakage, and the founding experiment. |

---

## 5. Results

Every number below is regenerable from the repository by a single command.

### 5.1 The founding result (Phase 0)

Using a simulator with **exact ground-truth counterfactuals**, a churn-score-ranked
retention campaign was compared against random targeting and against doing nothing.

- **Churn-score targeting loses money, and is worse than random targeting on 6 of 6
  seeds.**
- **Restraint beat ranking:** contacting 209 customers earned more than contacting 718.
- **A more accurate churn model can reduce profit**, because accuracy at detecting
  disengagement is precision at finding Sleeping Dogs.

![Churn-score targeting destroys value at every budget level, and the mechanism why](papers/figures/fig01_kill_test.png)

***Figure 1.*** *Left: expected incremental value against retention budget. Churn-score
targeting (red) sits below random targeting (dashed) at every budget, and both sit below
doing nothing. The oracle curve is an upper bound computed with ground-truth effects, not
an achievable policy; the gap to it at a 20% budget is roughly 34,000. Right: the
composition of each predicted-churn-risk decile. **Sleeping Dogs are 48% of decile 1 —
the customers targeted first — and 2% of decile 10.** That inversion is the mechanism: a
churn model ranks highest precisely the customers an offer harms.*

### 5.2 The cost of leakage (Phase 1)

The same features, computed correctly and incorrectly:

| Feature construction | Apparent AUC |
|---|---|
| Point-in-time correct | **0.603** |
| Ignoring reporting delays (subtle error) | 0.61 |
| No time filter at all (common error) | **0.954** |

**A 0.35 inflation.** The dangerous property is that leakage makes results look *better*,
and nobody investigates a number that improved.

### 5.3 External validation on real randomised experiments

The project's central claim did **not** replicate on the first real dataset. Rather than
discard it, the failure was diagnosed, producing the project's main contribution.

**Governing quantity: `corr(tau, propensity)`** — the correlation across customers between
the estimated treatment effect and the estimated outcome propensity.

| Setting | `corr(tau, pi)` | Value added by effect-based targeting |
|---|---|---|
| Criteo (advertising) | +0.61 | +0.6% |
| Lenta (retail promotion) | +0.18 | +10.4% |
| Hillstrom (e-mail marketing) | +0.07 | +3.9% |
| Subscription churn (simulator) | **−0.19** | **+107%** |

**Interpretation:** when effect-ordering and propensity-ordering coincide, the outcome
model wins — not because it estimates the right quantity, but because it solves an easier
one. As the correlation goes negative, effect-based targeting's advantage grows by an
order of magnitude. Retention is the adversarial case.

**An out-of-sample prediction that landed.** Before obtaining the Lenta dataset, it was
predicted that retail promotion would fall *between* advertising and retention. It came in
at +0.18, as predicted — though underpowered to test the downstream consequence.

**What is not claimed.** The *ordering among the positive-correlation settings is within
noise* — their confidence intervals overlap heavily, and the table above should not be
read as a monotone curve. The signal is the order-of-magnitude gap at negative
correlation, not the fine structure on the right of it.

![Uplift modelling's advantage against corr(treatment effect, outcome propensity) across five settings](papers/figures/fig03_when_uplift_pays.png)

***Figure 2.*** *Each point is one experimental setting. The x-axis is the correlation
across customers between estimated treatment effect and estimated outcome propensity; the
y-axis is how much effect-based targeting adds over an outcome model. Four settings with
positive correlation cluster near zero advantage and are not reliably distinguishable from
one another. The subscription-retention setting, at −0.19 correlation with 26% of customers
having a predicted-negative effect, is an order of magnitude away. Five settings, not a
fitted curve.*

### 5.4 Reliability at small *n*

Holding the evaluation set fixed and shrinking **only** the training set on a real
64,000-customer experiment:

- At n = 500, the best effect-based method beats random targeting on only **75% of draws**.
- One standard estimator manages **55%** — a coin flip.

Reported as a **win rate, not a mean**, because a business gets one draw. A method with a
good average and a wide spread is a gamble.

![Mean uplift performance rises with data, but the win rate against random is near a coin flip at small n](papers/figures/fig02_small_n_reliability.png)

***Figure 3.*** *Left: mean incremental visits at a 30% budget, by training-set size, for
five methods on the Hillstrom randomised experiment. Every method improves with data and
every one beats random on average — the shaded ±1 standard deviation bands show why that
is misleading. Right: the proportion of seeds on which each method actually beat random.
In the shaded region — the scale small businesses occupy — methods range from 55% to 75%.
**The left panel is the number usually reported; the right panel is the one a business
experiences.***

### 5.5 Survival benchmarks (Phase 3)

Against Cox proportional hazards, Random Survival Forest and DeepSurv on **Telco**, a
public dataset of 7,032 real subscription customers:

| Model | Integrated Brier (lower is better) |
|---|---|
| **Keel (discrete-time hazard)** | **0.0824** |
| DeepSurv | 0.0825 |
| Cox PH | 0.0914 |
| Random Survival Forest | 0.0964 |

**Beats two of three on 10 of 10 repeats; ties the third.** The DeepSurv difference is
0.0824 against 0.0825, which is noise, and calling it a win would be dishonest.

As predicted in advance, the method **loses** on GBSG2 (a medical dataset with no
time-varying covariates), because its advantage is handling covariates that change — which
that dataset does not have.

![Calibration against three baselines on Telco, and where the time-varying advantage disappears](papers/figures/fig05_survival_calibration.png)

***Figure 4.*** *Left: predicted against observed (Kaplan–Meier) survival at month 29 on
Telco. A perfectly calibrated model lies on the diagonal with slope 1. Cox (1.19) and
Random Survival Forest (1.25) are systematically off; DeepSurv (1.02) and the discrete-time
hazard (1.06) are close. This matters because these probabilities get multiplied by
revenue — being correctly scaled is worth more than being correctly ordered. Right: the
share of simulated businesses where using time-varying covariates beats a signup-time
snapshot. The advantage is decisive from 500 customers upward and **collapses to a coin
flip at 250**, which is the honest lower bound on who this can help.*

### 5.6 Involuntary churn: more dunning is not better dunning

Failed payments are 20–40% of subscription churn and need almost no machine learning. Six
retry-and-email policies were compared on simulated billing data with realistic decline
codes.

![Aggressive dunning uses far more retries and emails and recovers no more money](papers/figures/fig04_dunning_value.png)

***Figure 5.*** *Left: net value of six dunning policies. The aggressive policy uses roughly
two and a half times as many retries and nearly four times as many emails as the best
policy, and recovers **no more money** — it is strictly dominated. What works is
conditioning on the decline code: `insufficient_funds` means the money has not arrived yet
and wants a retry timed to payday, while an expired card cannot be charged again however
many times it is tried. Right: a sensitivity analysis on the one quantity that was assumed
rather than measured — the goodwill cost of a payment-failure email. It shows where the
conclusion would flip, so a reader can judge the assumption instead of taking it on trust.*

An early version of this experiment reported the aggressive policy recovering 21.7%, which
was wrong: retries against a dead card were allowed to compound. After correcting the
decline-code handling, the aggressive policy became **strictly dominated** — a cleaner and
more useful finding than the original.

### 5.7 Value at risk is not churn risk

Ranking customers by **probability of leaving** and by **money at risk** (value × that
probability) produces two top-decile lists that **overlap by only 21%**.

A churn score points at the wrong four-fifths of the money — before any causal argument is
made. This is arithmetic, not modelling.

### 5.8 The decision layer (Phases 4–5)

With ground truth withheld from every policy, 20 draws per size:

| n | Beats ranking | Beats doing nothing | Ties it | Treated (abstain / rank) |
|---|---|---|---|---|
| 250 | 95% | 20% | 70% | 5 / 23 |
| 500 | 85% | 5% | 70% | 12 / 46 |
| 1,000 | 95% | 5% | 80% | 14 / 90 |
| 2,000 | 100% | 0% | 70% | 27 / 181 |
| 4,000 | 90% | 0% | 80% | 21 / 359 |

**Abstention beats ranking on 93% of draws overall**, spending a fraction as much
(mean realised value −524 against −2,919 for ranking). It does **not** beat doing nothing,
and the third column explains why: on roughly three-quarters of draws the rule treats
nobody and scores exactly zero.

**The offer-ladder optimiser** (choosing *which* intervention per customer, learned from a
randomised multi-arm pilot):

| Policy | Mean realised value | Share of oracle |
|---|---|---|
| Optimiser | 655 / 1,039 / 2,252 | **28%** |
| Best rung chosen from the pilot | 502 / **−562** / 1,869 | 13% |
| Best single rung, chosen with hindsight | 1,997 / 2,554 / 5,892 | 73% |
| Oracle over rungs | 2,348 / 3,747 / 8,242 | 100% |

The optimiser is the first estimated policy in the project to make money on average, and
captures roughly twice what the achievable alternative does — but beats it on only
**58% of draws, 95% CI [0.42, 0.72]**, which is not distinguishable from chance.

**The claimable finding is about the comparator.** A pilot-chosen best rung agrees with the
true best rung on **13% of draws** — against 17% for a random guess among six — and returns
*negative* money at n = 1,000. **Choosing the right default offer is worth far more than
matching offers to customers, and it is what a small business is least able to do for
itself.**

---

## 6. How do we know it is trustworthy?

### 6.1 Ground truth, not proxies

The simulator emits **both potential outcomes** for every customer under common random
numbers, so `tau_i` is the exact counterfactual difference rather than an estimate of it.
No real dataset contains this. It is the only setting in which a CATE estimator can be
scored against per-customer truth.

### 6.2 Comparators are deliberately strong

The baseline ranks by `-tau_hat * V - c` using the **same estimator** and the **same
customer values**, so the comparison isolates *abstention* rather than the fact that
customers differ in worth. A weaker comparator would flatter the method for the wrong
reason. In Phase 5 the comparator is chosen **with hindsight** — an advantage no real
business has.

### 6.3 Predictions registered before results

Where a result could be shaped by knowing the answer, predictions were written down and
committed to version control **first**:

- The Lenta prediction (landed).
- Five predictions about the D-057 correction — **two of which failed**, and are reported
  as failures.
- A minimax-regret hypothesis, pre-registered and then **refuted** by its own
  out-of-sample test.

### 6.4 Invariants enforced by continuous integration

Thirteen invariants are documented, and the ones that can be are enforced automatically:
temporal splits only; latent variables never reachable from observable data; never
hand-tune the hazard intercept; voluntary and involuntary churn never summed; value always
measured against doing nothing; splits by subject and never by row; never extrapolate past
observed support.

CI runs on every push across three Python versions with four gates: tests, calibration,
**leakage**, and the founding experiment. The founding claim is re-verified on every commit.

### 6.5 What trustworthiness is *not* claimed

The client-facing report is **descriptive**: retention curves, revenue versus logo churn,
failed payments quantified. Every figure is a count or a sum from the client's own data,
and therefore checkable by them. The system deliberately does **not** promise per-customer
prediction, because §5.8 shows it cannot deliver it reliably.

---

## 7. Data, training, and the cold-start problem

### 7.1 Why a simulator, and why it is not the only data

| Purpose | Source | Why it is necessary |
|---|---|---|
| **Causal ground truth** | SubSim (own simulator) | Real data never contains the counterfactual. |
| **External validity** | Hillstrom, Criteo, Lenta (real RCTs) | Simulator-only results are desk-rejected, and reviewers are right to assume the simulator was tuned to favour the method. |
| **Benchmark comparison** | Telco (7,032 customers), GBSG2 | Standard datasets everyone reports on. |
| **Real-world proof** | Client engagements | Not yet obtained. Stated as an open gate. |

### 7.2 Calibration of the simulator

The simulator is not hand-tuned to produce a desired result. Its hazard intercept is
**solved by bisection** to hit a target churn rate, and a CI gate verifies four aggregate
properties against published industry benchmarks: monthly voluntary churn in
[3%, 7%], involuntary share of churn in [20%, 40%], 24-month retention in [22%, 50%], and
an early-to-late hazard ratio in [1.15, 3.0]. A second gate verifies the causal structure:
sleeping-dog share, persuadable share, and that the mean treatment effect stays beneficial.

During development, an early result was **rejected for being too favourable** — a
configuration producing 30% sleeping dogs and a harmful average effect made the headline
claim trivially true. The parameters were changed to make the claim *harder*, and it
survived.

### 7.3 The cold-start problem

A new business has no intervention data, so no treatment effect can be estimated. Three
mechanisms address this:

1. **The simulator** provides development and validation data before any client exists.
2. **Hierarchical priors** let a new tenant begin from what similar firms established
   rather than from ignorance. Measured effect: cross-tenant pooling cut mean losses from
   −457 to −62 at n = 500 by making a small firm treat 2 customers instead of 12.
3. **A deliberately budgeted randomised exploration phase** — the business is told
   explicitly that some spend is buying causal information.

### 7.4 Would this work for a different company?

The product is the **pipeline**, not a pre-trained model. A new tenant's own history is
ingested, its own features are computed under point-in-time rules, and its own models are
fitted. What transfers between tenants is the *prior*, not the parameters — and that
transfer is the mechanism in §7.3.

---

## 8. Architecture and codebase

```
keel/
├── core/        schema (occurred_at + available_at) · features (single data path)
│                leakage (availability audit, time-travel, canary injection)
├── ingest/      stripe · csv_ingest (alias resolution, recorded defaults)
│                preflight (is this export safe to compute from?) · subsim_adapter
├── sim/         config · latents (copula) · hazard · subsim
│                counterfactual (exact tau, common random numbers, offer ladder)
│                calibration · dunning
├── models/
│   ├── survival/  discrete (person-period hazard + competing risks)
│   │              metrics (KM, IPCW Brier, D-calibration — numpy only)
│   │              baselines (Cox · RSF · DeepSurv, each optional)
│   ├── uplift/    bayesian (Laplace posterior, validated vs NUTS) · abstention
│   └── clv/       value (CLV, value at risk, shortfall by cause)
├── policy/      dunning (6 retry policies) · economics (log-odds -> money)
│                ladder (per-customer rung choice from a multi-arm pilot)
├── report/      autopsy · render (HTML + print) · reasons (exact attribution)
│                worklist (CSV, descriptive only) · dashboard (self-contained)
├── experiments/ kill_test · leakage_penalty · dunning · survival_benchmark
│                clv · abstention · sensitivity · ladder · figures
├── benchmarks/  datasets (Hillstrom, Criteo, Lenta) · survival_data (Telco, GBSG2)
│                models · evaluate · small_n · spectrum
└── cli.py       preflight and autopsy against a real client export
```

**Design principles visible in the structure:**

- `core/features.py` exposes exactly one path to source data, so leakage cannot be
  introduced by accident elsewhere.
- Survival metrics are implemented in numpy so CI can run them without optional
  dependencies; they are validated against `lifelines` and `scikit-survival` separately.
- The decision layer consumes a posterior **already denominated in currency**, which makes
  a whole class of units error unrepresentable (see §10).

---

## 9. Testing and engineering discipline

**433 automated tests, 4,957 lines of test code**, run on every push across Python 3.11,
3.12 and 3.13.

Tests fall into five categories:

| Category | What it protects |
|---|---|
| **Correctness** | Known answers computed by hand, not self-consistency |
| **Leakage** | Availability-timestamp assertions, time-travel checks, canary injection |
| **Calibration gates** | Simulator must match published benchmark ranges |
| **Edge cases** | Degenerate inputs raise errors about the *data*, not the solver |
| **Absence of change** | That a sensitivity analysis did not move its own baseline |

**Errors raise messages about the data.** A survival model given a single-outcome dataset
does not report an optimiser convergence failure; it says the outcome is constant and no
effect is identifiable from it. NaN covariates raise rather than being imputed, because
filling them is a loader's decision, not a model's.

**A documented decision log.** 63 entries recording *why* each modelling choice was made,
appended and never edited, so a later reader can see what was believed when.

**Roughly half the failing tests in this project turned out to be the test, not the code** —
recorded explicitly, because the instinct to "fix" the code first is exactly what produces
a wrong system that passes.

---

## 10. What did not work

This section exists because a project that reports only successes is not credible, and
because these are among the most useful results obtained.

### 10.1 The central claim did not replicate on real data

"Churn-score targeting is worse than random" failed to replicate on Hillstrom. Diagnosis
rather than rationalisation: Hillstrom has **no sleeping dogs** — every uplift decile is
positive — so worse-than-random is structurally impossible there. Criteo then *contradicted*
Hillstrom. Reconciling the two produced `corr(tau, propensity)` (§5.3), which is now the
project's main contribution. **The claim was scoped rather than defended.**

### 10.2 A units error ran for an entire phase (D-057)

The decision rule multiplied a **log-odds** treatment effect by customer value as though it
were a probability difference. On one draw it believed treating was worth −104.5 when the
truth was +20.5, against an offer costing 31.5.

The distortion is `1/(p0(1-p0))` — a factor of 4 at p₀ = 0.5, **25 at p₀ = 0.05** — so it
was *worst for the customers least likely to leave*. That is the Sure Thing quadrant: the
project reproduced its own central criticism inside its own decision rule.

**Every test passed, and none of them was wrong.** They were all self-consistency checks,
and a units error is consistent with itself. The lesson is stated precisely: *a suite of
self-consistency tests cannot detect a units error.* The test that now catches it asserts a
value computed by hand.

Correcting it reduced losses from −3,531 to −1,070 and improved the win rate against
ranking from 75% to 93% — and **changed no qualitative conclusion**.

### 10.3 A gate that could not have been passed

Phase 4 required beating both ranking *and* doing nothing. A sensitivity analysis showed
these are in tension: as the effect size grows, beating ranking falls from 90% to 48% while
beating inaction rises from 5% to 68%, monotonically, and **at no setting is either
significantly above chance while the other also is.** The gate demanded two properties that
trade off. That is a defect in the gate, and it is reported as one rather than as evidence
for the method.

Underneath it is arithmetic: break-even requires |tau| > 0.040 while the offer delivers
0.010, so an *oracle* would treat only **5.8%** of customers.

### 10.4 A hypothesis proposed, then refuted by its own test

The sensitivity suggested the method was valuable as a *hedge* — never best, never
catastrophic. Because that reading was formed after seeing a failure, it was pre-registered
and tested on data that played no part in forming it. **It failed:** random assignment
hedged better (58.9% versus 85.7% maximum regret). Withdrawn and recorded.

---

## 11. Comparison with a sibling project (RetainIQ)

RetainIQ is a prior project by the same author: an e-commerce retention dashboard on the
Olist Brazilian dataset, using RFM segmentation, K-Means, an XGBoost churn classifier and
SHAP explanations, deployed with FastAPI and Next.js. It was analysed as an external
comparison, and **its code was executed rather than its report read**.

### 11.1 An independent replication of this project's leakage finding

RetainIQ's report states Accuracy 0.9987, F1 0.9992 and **ROC-AUC 1.0000**, describing the
model as having "learned the patterns flawlessly," with a footnote that recency acts as a
near-perfect deterministic feature. That footnote is the whole story: the label was "no
purchase in 90 days" and recency is days since last purchase, so `recency >= 90` **is** the
label.

A later commit correctly implemented an out-of-time split and resolved the leakage. **The
report was never re-run.** Executing the current code gives:

| Metric | Reported | Actual (current code) | Trivial baseline |
|---|---|---|---|
| Accuracy | 0.9987 | **0.8676** | 0.9945 (always predict churn) |
| F1 | 0.9992 | **0.9290** | 0.9972 (always predict churn) |
| ROC-AUC | 1.0000 | **0.5434** | 0.5000 |

A constant "everyone churns" beats the trained model on both accuracy and F1.

**This is an independent replication of this project's Phase 1 result** (0.603 correct
versus 0.954 leaked) at larger magnitude, on real data, in a different vertical, by a
different pipeline. It is the strongest available evidence that point-in-time correctness
earns its engineering cost.

### 11.2 A second finding: the problem statement was wrong

At a 99.4% churn base rate the task is degenerate. Olist is a *marketplace* — mostly
one-time buyers, non-contractual, where churn is latent and unobservable. A binary 90-day
label is the wrong construct (Fader & Hardie); it requires BTYD models such as Pareto/NBD.

This is precisely why Keel began with **contractual** subscriptions and deferred
non-contractual to a later phase behind a model router.

### 11.3 An honest accounting of what RetainIQ does better

| RetainIQ has | Keel has |
|---|---|
| A deployed frontend and live API | No user interface in production |
| SHAP per-customer explanations | Exact closed-form attribution (no dependency) |
| RFM segmentation, CRM activation layer | Neither |
| Docker orchestration, hosted deployment | Local CLI only |
| 0 automated tests, no CI | 433 tests, CI on 3 Python versions, 4 gates |
| Correlational churn prediction | Causal effect estimation with ground truth |
| Binary classifier (ignores censoring) | Survival model with competing risks |
| 2 documentation files | 63 decision entries, 7,221 documentation lines |

**Both directions are recorded.** RetainIQ's gate — "somebody can use it" — is met, and
Keel's is not.

---

## 12. Limitations

Stated plainly, because the alternative is having a reviewer state them.

1. **No paying client and no live deployment.** Every result is from simulation or public
   datasets. The commercial claim is untested.
2. **One simulator carries the negative-correlation regime.** Three real RCTs plus one
   simulator is thin for a "governing quantity" claim, and the interesting regime is the
   one no public dataset contains.
3. **The correlation is measured, not derived.** There is no theory explaining *why* this
   quantity governs — only evidence that it does.
4. **The decision layer does not beat doing nothing.** It reliably avoids the damage that
   ranking causes; it does not manufacture profit the data cannot support.
5. **The offer optimiser's advantage is not statistically significant.** 58% on 45 draws,
   CI [0.42, 0.72].
6. **Below roughly 250 customers, nothing beats a population average.** A real constraint
   on who this can help.
7. **The estimator has weak signal at these sample sizes.** `corr(tau_hat, tau_true) = 0.13`
   on the diagnostic draw. No decision rule repairs an input that weak.
8. **AI-assisted development.** Substantial portions of the implementation were written
   with AI coding assistance under the author's direction, specification and review. This
   is disclosed rather than obscured; the author's contribution is the problem framing,
   experimental direction, verification and interpretation. *(Retain, amend or remove this
   clause according to institutional policy on tool disclosure.)*

---

## 13. Future work

| Phase | Work | Gate |
|---|---|---|
| **6** | Randomised holdout infrastructure, incrementality reporting, cancel-flow widget | A real client's verified return |
| **7** | Cross-tenant hierarchical priors at scale; BTYD/Pareto-NBD router for non-contractual businesses | Tenant #10 outperforms tenant #1 on day one |

**Research priority.** The single highest-value addition is to **derive** the condition
under which effect-based targeting beats propensity-based targeting, rather than only
measuring it. Even a result of the form *"effect-targeting dominates iff
corr(tau, pi) < f(budget, noise)"* in a tractable model would convert the empirical work
from an observation into a confirmation.

**Commercial priority.** A single paying client simultaneously unblocks Phase 6, the first
step of Phase 7, and the third paper. It is the only remaining gate that no amount of
further engineering will open.

---

## 14. Anticipated examination questions

**Q: Why not just use a churn prediction model? They are well understood.**
Because a churn score answers a different question from the one that spends money. Ranking
by risk targets Sure Things and Sleeping Dogs; the project measured this losing money
against doing nothing on 6 of 6 seeds. Separately, the top decile by *money at risk*
overlaps the top decile by *churn risk* by only 21%, so even before the causal argument, a
risk score points at the wrong four-fifths of the value.

**Q: Your model does not beat doing nothing. Is the project a failure?**
No, but the claim is narrower than intended and is stated that way. What is established is
that ranking destroys value and that a rule which reliably returns to zero is worth real
money relative to current practice. The abstention rule ties do-nothing on roughly
three-quarters of draws — which is the safety property working, not a loss. Reporting only
"beats do-nothing" would score a rule that correctly declines identically to one that loses
money.

**Q: You built the simulator. Doesn't that mean you can make it say anything?**
It is a legitimate concern and three things address it. Its calibration targets come from
published industry benchmarks and are enforced by CI. An early result was rejected for
being *too favourable* and the parameters were made less flattering; the claim survived.
And every claim that could be tested externally was, on three real randomised experiments,
where the original claim **failed to replicate** and was scoped rather than defended.

**Q: How is this different from Ascarza (2018)?**
Ascarza established that risk-based targeting is *ineffective*. This project asks when it
becomes *actively harmful*, gives the governing quantity and its mechanism, and addresses
sample sizes two to four orders of magnitude smaller than the uplift literature reports on.
The novelty is not "churn scores are bad."

**Q: What is the single biggest weakness?**
That the negative-correlation regime — the interesting one — is carried entirely by the
simulator, because no public dataset contains the sleeping-dog mechanism. The honest
mitigation is that the *ordering* across four settings was confirmed by an out-of-sample
prediction, but a fifth real dataset in that regime would be worth more than any further
engineering.

**Q: What did you get wrong?**
A units error that ran for an entire phase: multiplying a log-odds effect by money as
though it were a probability. It was worst for the lowest-risk customers, meaning the
system reproduced the exact error it was built to criticise. Every test passed, because
they were all self-consistency checks. Fixed, with the correction pre-registered so the
improvement could not be claimed after the fact — and two of the five predictions failed.

---

## 15. References

1. Ascarza, E. (2018). Retention Futility: Targeting High-Risk Customers Might Be
   Ineffective. *Journal of Marketing Research*, 55(1), 80–98.
2. Imbens, G. W., & Rubin, D. B. (2015). *Causal Inference for Statistics, Social, and
   Biomedical Sciences*. Cambridge University Press.
3. Fader, P. S., & Hardie, B. G. S. (2009). Probability Models for Customer-Base Analysis.
   *Journal of Interactive Marketing*, 23(1), 61–69.
4. Künzel, S. R., Sekhon, J. S., Bickel, P. J., & Yu, B. (2019). Metalearners for
   estimating heterogeneous treatment effects using machine learning. *PNAS*, 116(10).
5. Athey, S., & Imbens, G. (2016). Recursive partitioning for heterogeneous causal effects.
   *PNAS*, 113(27), 7353–7360.
6. Gelman, A., Carlin, J. B., Stern, H. S., Dunson, D. B., Vehtari, A., & Rubin, D. B.
   (2013). *Bayesian Data Analysis* (3rd ed.). CRC Press.
7. Devriendt, F., Moldovan, D., & Verbeke, W. (2018). A Literature Survey and Experimental
   Evaluation of the State-of-the-Art in Uplift Modeling. *Big Data*, 6(1), 13–41.
8. Radcliffe, N. J., & Surry, P. D. (2011). Real-World Uplift Modelling with
   Significance-Based Uplift Trees. *Stochastic Solutions White Paper*.
9. Diemert, E., Betlei, A., Renaudin, C., & Amini, M. (2018). A Large Scale Benchmark for
   Uplift Modeling. *AdKDD & TargetAd Workshop, KDD*.
10. Katzman, J. L., et al. (2018). DeepSurv: personalized treatment recommender system
    using a Cox proportional hazards deep neural network. *BMC Medical Research
    Methodology*, 18(24).
11. Ishwaran, H., Kogalur, U. B., Blackstone, E. H., & Lauer, M. S. (2008). Random survival
    forests. *Annals of Applied Statistics*, 2(3), 841–860.
12. Haider, H., Hoehn, B., Davis, S., & Greiner, R. (2020). Effective Ways to Build and
    Evaluate Individual Survival Distributions. *JMLR*, 21(85).

---

*Project repository, including the full decision log, build log and reproduction commands
for every figure in this report: `https://github.com/PrashamJ17/PBL-Proj`*
