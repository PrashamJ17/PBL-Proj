# Decision Log

Why each modelling choice was made. Separate from the build log on purpose: the build
log records *what happened*, this records *why*, which is what a referee will ask about
and what future-you will have forgotten.

Format: decision, the alternative rejected, and the reason.

---

## D-001 — Voluntary and involuntary churn are modelled as separate processes

**Alternative rejected:** one binary `churned` outcome, as in nearly all published
churn work and every Kaggle dataset.

**Reason:** they are different business problems with different fixes. Voluntary churn
needs a causal retention policy; involuntary churn needs decline-code-aware retry
timing. Involuntary churn is 20–40% of the total, so conflating them makes roughly a
third of the outcome variable unaddressable by the model that is supposed to explain
it — and it silently inflates reported churn-model performance, because payment
failures are partly predictable from billing metadata that has nothing to do with
customer intent.

**Consequence:** `panel` carries `churn_voluntary` and `churn_involuntary` separately.
Any model that sums them is doing something wrong.

---

## D-002 — `attention` is correlated with `engagement_base` via a Gaussian copula

**Alternative rejected:** independent latents.

**Reason:** this is the single most important modelling decision in the project. It
encodes the mechanism that makes naive churn targeting destroy value:

- low engagement is the **strongest observable predictor of churn**, so a churn model
  ranks low-engagement customers at the top;
- low attention marks a **dormant payer** who has half-forgotten the charge, and whom
  contacting *causes* to cancel.

Because the two are correlated, the top of a churn-score ranking is dense in sleeping
dogs. If the latents were independent, a naive policy would merely be *wasteful*;
with the correlation it is *actively value-destroying*. That distinction is the entire
thesis.

**Consequence:** `SimConfig.attention_engagement_corr` is the key sensitivity
parameter. A sweep over it is a required figure in paper 2 — the honest version of
this project has to show where the naive policy stops being harmful.

---

## D-003 — Engagement decays toward a habit-set floor, not toward zero

**Alternative rejected:** pure geometric decay `base * (1-rate)^t`.

**Reason:** with pure decay, every customer's engagement reached ~0 by month 12, which
saturated the hazard term and drove 24-month retention to 7%. That is unrealistic and,
worse, it destroys the right-censoring that survival analysis exists to handle — the
project's core modelling argument would have been untestable on its own simulator.

Real customers with an embedded routine keep using a product at some baseline level
indefinitely. The floor is set by `habit_strength`, which also ties the Spotify/Prime
"habit beats prediction" lesson to an observable.

**Measured effect:** monthly voluntary churn 13.4% → 9.3%; retention 3% → 7%.

---

## D-004 — `habit_strength` is left-skewed (Beta(2.2, 1.6)), not symmetric

**Alternative rejected:** symmetric Beta(2.5, 2.5).

**Reason:** the symmetric version produced a purely exponential retention curve. Real
cohort retention curves **flatten**: the fragile churn early and the surviving pool is
progressively hardier. Reproducing that flattening requires a genuinely sticky core in
the population, which needs left skew.

This is a structural property worth getting right, not a nuisance — a simulator with an
exponential retention curve would make survival models look better than they are,
because the hazard would be near-constant and therefore trivially estimable.

**Measured effect:** `early_late_hazard_ratio` ≈ 2.0, i.e. first-6-month hazard is
twice the 12-month-plus hazard.

---

## D-005 — The hazard intercept is solved for, never hand-tuned

**Alternative rejected:** picking an intercept by eye until the numbers looked right.

**Reason:** hand-tuning a generative process is how you accidentally fit it to flatter
your own method — the first thing a referee will suspect, and usually correctly.
`calibration.calibrate_intercept` bisects on the intercept to hit a target monthly
churn rate, averaged over seeds. Bisection is valid because the hazard is monotone in
the intercept.

**Consequence:** re-run the solver after changing *any* hazard coefficient or latent
distribution — they all shift the mean hazard. The current value (−3.8125) is an
output of that procedure, not an input.

---

## D-006 — Calibration targets were widened after being found mutually inconsistent

**Original:** 24-month retention target of [0.30, 0.60].

**Problem found:** 40% retention at 24 months implies ~3.75% **total** monthly churn.
The voluntary band alone was 3–7%, before adding ~2% involuntary. The targets could
not all be satisfied by any parameterisation — the constraint set was empty.

**Resolution:** widened to [0.22, 0.50], the range actually implied by the other two
targets. The original figure describes mid-market/enterprise SaaS; this simulator
models SMB, which churns harder.

**Note:** the achieved value (~0.237) sits close to the lower bound, roughly 1.8 seed
standard deviations above it. Worth revisiting if the hazard coefficients change.

**Lesson worth keeping:** state calibration targets as a *system* and check they are
jointly satisfiable before tuning anything. An empty constraint set is invisible when
you tune one target at a time.

---

## D-007 — Latents are returned alongside the panel, but never inside it

**Alternative rejected:** a single flat table.

**Reason:** models see `panel`. Oracle analysis and ground-truth validation need
`latents`. Keeping both on one object is convenient but makes leakage a one-typo
mistake. They are separate attributes with a docstring warning, and
`test_latents_do_not_leak_into_panel` enforces the boundary in CI.

There is a second, subtler guard: `test_no_observable_is_a_perfect_proxy_for_attention`
asserts no single observable correlates with `attention` above r=0.95. If one did,
detecting sleeping dogs would be trivial and the simulator would have assumed away the
very problem it exists to pose.

---

## D-008 — Phase 0 depends only on numpy/pandas/scipy

**Alternative rejected:** pulling in the full causal stack (econml, causalml, pymc)
from the start.

**Reason:** the week-3 kill test is a go/no-go gate on the entire thesis. It must be
runnable by anyone in seconds, with no build-heavy dependencies. Heavy ML libraries are
declared as optional extras in `pyproject.toml` and arrive with the phases that need
them.

---

## D-009 — Two counterfactual regimes: analytic tau and realised outcomes

**Alternative rejected:** Monte Carlo only — sample forward paths in both arms and
difference them.

**Reason:** Monte Carlo tau at the individual level is almost pure noise. Per-customer
treatment effects are on the order of 0.01–0.15 in probability, while a single sampled
path is a Bernoulli draw. You would need thousands of replications per customer to
resolve it.

Instead the forward window evolves state along its *expected* trajectory, making
survival probabilities — and therefore tau — closed-form and **exact**:

```
P(churn within H) = 1 - prod_t (1 - h_t)
tau = P_treated - P_control
```

Realised Y(0), Y(1) are still produced, under **common random numbers** (the same
uniform draws applied to both arms), so they are correctly *paired*. That is a standard
variance-reduction technique; without it the per-customer difference would be swamped
by simulation noise.

**Consequence:** uplift models are scored against exact individual tau — something no
real dataset can offer. Policies are scored on realised outcomes. The two are reported
side by side and agreed in sign for every policy in the kill test.

**Cost of this choice, stated honestly:** the forward window is *less* stochastic than
the historical period, so it slightly understates outcome variance. Acceptable, because
the quantity of interest is the treatment effect, not the outcome distribution — but it
belongs in the paper's limitations section.

---

## D-010 — Saveability and salience have different time profiles

**Alternative rejected:** one static treatment effect applied uniformly over the window.

**Reason:** the two forces are physically different events.

- **Salience** (harmful) is a *reminder*. The damage happens at the moment of contact.
  Modelled as a sharp spike decaying with an ~0.8-month constant.
- **Saveability** (protective) is an *inducement*. It holds while the discount is live,
  then tapers with a 2-month half-life.

This matters for the policy layer: it means the harm from a bad contact is essentially
irreversible and immediate, while the benefit of a good one is earned over time. A
policy that can abstain is therefore worth much more than one that can only re-rank.

---

## D-011 — `salience_scale` set to make the claim HARDER, not easier

**Alternative rejected:** `salience_scale = 2.6`, which produced 30% sleeping dogs and
a *negative* average treatment effect (mean tau = +0.0044).

**Reason:** at that setting the headline result is trivially true — a blanket campaign
increases churn on average, so of course targeting it badly loses money. It is also not
credible: the uplift literature reports sleeping dogs as a minority segment, and a
referee would reasonably conclude the simulator had been tuned to flatter the method.

Set to **1.8**, giving ~17% sleeping dogs and mean tau = **−0.010**. The average
treatment effect is now **beneficial**: a blanket campaign *helps* on average.

**Why this is the right call:** any money that churn-score targeting loses is now
attributable purely to *targeting*, not to a bad offer. That is the harder claim, and
it is the one actually worth making. The result survived the change — churn-score
targeting still loses money 6/6 seeds and is still worse than random 6/6.

**Enforced by a calibration target**, not left to discipline: `mean_tau` has target
range [−0.05, 0.0], which *fails the build* if the average effect ever becomes harmful.

---

## D-012 — The kill test's churn model is real, not a strawman

**Alternative rejected:** ranking by the simulator's true churn probability.

**Reason:** the claim under test is not "churn models are inaccurate". It is "**even an
accurate churn model is the wrong targeting rule**". Those are completely different
claims, and only the second is interesting or defensible.

So the kill test trains an actual `HistGradientBoostingClassifier` on **observable
features only**, with a **strictly temporal split** (train on months < T, predict at T).
It reaches holdout AUC ≈ 0.70 — a respectable churn model by published standards.

It still loses money, and still loses more than random. The better the churn model
gets at its own job, the more precisely it finds sleeping dogs.

**Corollary worth stating in the paper:** improving churn-model AUC can *worsen*
business outcomes under a top-k targeting policy. That is a genuinely counterintuitive
and useful result.

---

## D-013 — Value is measured against doing nothing

**Alternative rejected:** reporting save rate among the treated, which is what most
vendor case studies report.

**Reason:** save rate is contaminated by selection. If you target people who were going
to stay anyway, your save rate looks superb and your P&L does not move. The only
meaningful baseline is the counterfactual where you ran no campaign at all.

`do_nothing` is therefore a first-class policy in the comparison, pinned to exactly
0.0 by construction and asserted in tests. Every other policy is reported as a
difference from it.

---

## D-014 — Every fact carries `occurred_at` AND `available_at`

**Alternative rejected:** one timestamp per fact, as nearly every churn dataset uses.

**Reason:** they answer different questions. `occurred_at` is when something happened
in the world; `available_at` is when we could first have *known* about it. A card
decline settles up to two days after the attempt. A nightly sentiment batch scores
yesterday's tickets this morning. Mobile clients upload events hours late.

Training on `occurred_at` while serving on data that arrives with lag gives the model a
look ahead that it will not have in production. The backtest looks excellent and the
deployment collapses — and because the error makes results *better*, nobody
investigates it.

`keel.core.features` filters on `available_at`, never on `occurred_at`.

**Consequence:** `available_at` is required, not optional. Where a source genuinely has
no lag the adapter sets it equal to `occurred_at` *explicitly*. Making it implicit
invites people to forget it exists. Schema validation rejects any row where
`available_at < occurred_at`, since a fact cannot be knowable before it occurs — that
invariant is what every point-in-time guarantee rests on.

---

## D-015 — The leakage guarantee is structural, not procedural

**Alternative rejected:** a documented convention that feature authors filter correctly.

**Reason:** guarantees that depend on remembering to do the right thing are not
guarantees. Every feature in `keel.core.features` reads its source rows through exactly
one function, `_visible`, which applies the temporal filter. There is no other path to
the data, so a feature that bypasses the filter cannot be written.

Features are also *declarative* (`FeatureSpec`) rather than lambdas, specifically so
they can be **audited** — we can ask which source rows a feature is permitted to touch
without executing it. A lambda cannot be interrogated that way.

---

## D-016 — Unsafe feature modes exist on purpose

**Alternative rejected:** only implementing the correct path.

**Reason:** "we have leakage safeguards" is an assertion. `FeatureStore` therefore
supports two deliberately incorrect modes — `UNSAFE_OCCURRED_ONLY` (ignores
availability lag) and `UNSAFE_NO_FILTER` (no temporal filter at all) — so the cost of
getting it wrong can be *measured* rather than claimed.

Measured result: correct **0.603 AUC**, occurred-only **0.613**, unfiltered **0.954**.

The 0.35 gap is not performance. It is the amount by which a backtest would have
overstated the model before it reached production, and it is the number a business
would have staked a retention budget on.

**The risk this creates, and how it is contained:** an unsafe mode is a footgun. The
default is `SAFE`, `test_default_mode_is_safe` asserts it, and nothing in the
production path may construct a store any other way. Judged worth it — a safeguard
whose value is only asserted tends to get removed by someone optimising later.

---

## D-017 — The leakage suite must be proven to have teeth

**Alternative rejected:** checks that verify correct behaviour only.

**Reason:** **a leakage suite that has never caught a leak is evidence of nothing.** It
might be working, or it might be checking a condition that is trivially true. There is
no way to tell from a passing run.

So the suite is adversarial in both directions:

- `test_audit_catches_unsafe_modes` — the audit must **fail** on the deliberately
  leaked vintages.
- `test_canary_is_caught` — a planted feature built from the outcome must be flagged.
  The canary has 10% of its labels flipped, because a perfect copy would be caught by
  even a broken detector.
- `test_clean_features_are_not_flagged` — the complement. Without it, a detector that
  flags everything would pass the canary test.

---

## D-018 — Canonical schema is timestamp-native; SubSim adapts upward

**Alternative rejected:** letting the canonical layer use period indices, since that is
what the simulator produces and it would have been less work.

**Reason:** real billing data arrives as timestamped events. If the schema spoke in
months because the simulator does, every real integration would have to fight it, and
the convenience of a test fixture would have shaped the production data model.

The adapter therefore expands *upward*: `sessions_30d = 12` becomes twelve individual
`session_start` rows spread across that month.

It also injects **realistic availability lag**. Without it, filtering on `available_at`
and on `occurred_at` would give identical answers, the point-in-time machinery would be
untested, and a bug in it could never surface.

---

## D-019 — CSV ingest assumes a conservative lag rather than none

**Alternative rejected:** setting `available_at = occurred_at` for CSV exports.

**Reason:** a CSV carries no record of when facts became knowable. Assuming zero lag is
a lie the feature store has no way to detect — it would pass every audit while training
on information that arrived late in reality.

`DEFAULT_LAG` applies a conservative uniform lag per table (2 days for invoices, 6
hours for events), overridable when a tenant knows their real settlement delay. The
assumption is recorded in the data rather than hidden in it.

The ingest layer is deliberately **forgiving about shape and unforgiving about
meaning**: column names are guessed at through an alias table, because exports arrive as
"Customer ID", "customer-id", and "CUSTOMER_ID" with equal frequency. But a missing
required column is refused outright, with the columns actually present listed in the
error — the person reading it is a founder looking at their own export.

---

## D-020 — The worse-than-random claim is SCOPED, not universal

**What we believed:** Phase 0 showed churn-score targeting losing money and
underperforming random selection, 6/6 seeds. The explainer stated this without
qualification.

**What the Hillstrom benchmark showed:** it does not replicate. On a real 64,000-customer
randomised email experiment, outcome-model targeting **beats** random (416 vs 281
incremental visits at 30% budget).

**Why — and this is the useful part.** We diagnosed rather than rationalised. Hillstrom
has **no sleeping dogs**. Sorting the test set into deciles of predicted uplift, *every
decile has positive true uplift* — the lowest is +0.028 for the womens campaign. The
mens campaign is more extreme: only 0.2% of customers are predicted negative, and the
decile ordering is barely monotone at all.

The treatment helps essentially everyone. When that is true, any rule correlated with
responsiveness beats random by construction, and worse-than-random is **structurally
impossible** regardless of what the model does.

**The corrected claim:**

> Outcome-model targeting is worse than random *when a negative-uplift segment exists
> and is correlated with outcome propensity*. That condition holds in subscription
> retention — dormant payers reminded that they are paying — and does **not** hold in
> promotional email, where contact is at worst ignored.

This is narrower and considerably more defensible. It also converts the simulator from a
convenience into a necessity: no public dataset contains the mechanism, which is
precisely why one had to be built.

**Consequence:** every claim in `explainer/` was rewritten to carry the scope condition.
Prior work (Ascarza 2018, *JMR*) already established that risk-based targeting is
*ineffective*; our contribution is characterising **when it becomes actively harmful**,
not asserting that it always is.

---

## D-021 — Prediction recorded in the code before the experiment ran

**Alternative rejected:** running the benchmark, then writing up whatever came out.

**Reason:** the outcome was genuinely uncertain, and the temptation to reinterpret a
disappointing result afterwards is strongest exactly when it disappoints. So
`keel/benchmarks/run.py` carries a docstring section, committed before the first run,
stating that Hillstrom is email marketing rather than churn retention, that its harm
mechanism is weaker, and that **worse-than-random was likely to fail there** — and that
such a failure would be a result about scope rather than a refutation.

That is what it turned out to be. Having written it down first is the only reason that
reading is credible rather than convenient.

**Worth repeating for every future benchmark:** state the expected outcome, and what
each possible result would mean, before running it.

---

## D-022 — Primary benchmark metric carries no prices

**Alternative rejected:** converting Hillstrom outcomes to money using an assumed value
per visit and cost per email.

**Reason:** Hillstrom records neither. Any monetary conclusion would follow from numbers
we invented, and the headline would be a function of our own assumption rather than of
the data.

The primary metric is therefore **incremental outcome per thousand contacts**, which
needs no economic assumptions at all. Economics enter separately as a *sweep* over
break-even thresholds (`abstention_sweep`), so the reader sees how conclusions vary with
price rather than being handed one.

---

## D-023 — Small-n reliability is measured by win rate, not by the mean

**Alternative rejected:** reporting mean performance across seeds, as the uplift
literature does.

**Reason:** a mean across many hypothetical draws is not what a business experiences. It
gets **one** draw. A method with a good average and a wide spread is a gamble, and
averaging hides exactly the risk that matters.

So the headline small-n metric is: **the proportion of seeds on which a method beats
random**, paired on the same split.

**Measured on Hillstrom** (real randomised data, evaluation set held fixed so only
training size varies):

| train n | best uplift beats random |
|---|---|
| 500 | **75%** |
| 1,000 | 90% |
| 2,000 | 100% |
| 5,000+ | 100% |

At n=500 the class-transform estimator wins on only **55%** of seeds — barely a coin
flip. Mean performance at that size looks respectable; reliability is close to a gamble.

This is the strongest available evidence for the abstention thesis, and unlike everything
before it, it comes from real data rather than our own simulator.
