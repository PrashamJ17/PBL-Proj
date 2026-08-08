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

---

## D-024 — Criteo's file is sorted by treatment; prefix reads are invalid

**What happened.** The 297MB download was running at ~16 KB/s (≈5 hours), so the loader
was built to read a *prefix* of the partially-downloaded gzip — legitimate in principle,
since gzip is a stream format.

`check_representative` reported **`treatment_rate = 1.0000`** on the first 196,287 rows.
Confirmed directly: the first 251,999 rows are *all* `treatment=1`.

**Why this matters more than a normal sampling bias.** A prefix of Criteo is not a
skewed sample — it contains **no control group at all**, so uplift is *undefined*, not
merely noisy. Every downstream number would have been meaningless while looking
perfectly plausible.

**Resolution:** `load_criteo` always reads the full file and subsamples **randomly**
afterwards. A single-arm sample is rejected outright.

**The check earned its place.** It was written speculatively, on the general principle
that a subset should be verified against published full-file statistics before use. It
caught a fatal problem within minutes of first contact with the data.

**Follow-on fix:** the relative-tolerance test was too permissive to catch this on its
own — |1.0 − 0.85| = 0.15 sits inside a 20% band around 0.85. A degenerate rate (0 or 1)
is now a categorical failure. This was surfaced by
`test_representativeness_check_rejects_single_arm`, which failed on first run.

---

## D-025 — Mirror choice is a real engineering decision here

Criteo's own blob mirror delivered ~16 KB/s (≈5 hours for 297MB). The HuggingFace
mirror delivered ~1.3 MB/s — **80× faster**, completing in 3m16s, byte-identical
(311,422,618 bytes).

HuggingFace is therefore the primary URL and Criteo's blob store the fallback, with the
measurement recorded in a comment so the ordering is not silently "corrected" later.

Worth generalising: when a dataset download looks like it will dominate the work,
**probe throughput on each mirror before committing to one**. Sixty seconds of measuring
saved roughly five hours.

---

## D-026 — The correlation between treatment effect and outcome propensity is the
## governing quantity

**The problem.** Two real datasets appeared to contradict each other. On Hillstrom,
uplift models clearly beat outcome models (Qini 168 vs 36). On Criteo, they clearly
lost, at *every* training size (3617 vs 2811 incremental at n=500). Neither was a fluke.

**The reconciliation.** Measure `corr(estimated treatment effect, estimated outcome
propensity)`:

| setting | corr | uplift's advantage | % predicted negative |
|---|---:|---:|---:|
| Hillstrom (mens) | +0.63 | +4.7% | 0.2% |
| Criteo (advertising) | +0.61 | +0.6% | 19.2% |
| Hillstrom (womens) | +0.07 | +3.9% | 10.2% |
| **SubSim (churn)** | **−0.19** | **+106.8%** | 25.7% |

An outcome model ranks by *likelihood of responding*; an uplift model ranks by *how much
treatment changes the response*. **When those orderings coincide, the outcome model wins
— not because it measures the right thing, but because it solves an easier estimation
problem.** Estimating one probability is far more stable than estimating a difference
between two, and at small n that variance advantage dominates.

**This reframes the project's claim.** It is *not* "uplift modelling is better" — that is
false in advertising, and we can now show it with real data. It is that **retention has
an adversarial structure that advertising does not**.

**A refinement to D-020.** Sleeping dogs existing is *not sufficient*. Criteo has 19.2%
predicted-negative customers — more than Hillstrom-womens' 10.2% — and uplift still adds
nothing. What matters is whether the harmed customers sit **where the outcome model ranks
highest**, which is exactly what a negative correlation measures.

**It also strengthens the abstention argument.** A practitioner cannot tell in advance
which regime they occupy, and choosing wrongly is expensive in both directions. A method
that quantifies its own uncertainty and declines to act is the honest response.

**Stated honestly:** four settings is a contrast, not a fitted relationship. The ordering
among the three positive-correlation points is within noise. The signal is the
order-of-magnitude gap at negative correlation, and the figure says so explicitly.

---

## D-027 — Scale-dependent scores must not be compared across estimators

**The bug.** The first spectrum run reported Criteo at `corr = 1.00` with "100% predicted
negative" — nonsense, and it came from selecting whichever uplift model scored best and
then correlating *its* raw scores against propensity.

`ClassTransform` outputs `p/p_treat − (1−p)/(1−p_treat)`. Under Criteo's 85/15
assignment that is negative unless `p > 0.85`, so nearly every customer scores negative
even though the **ranking is perfectly good**. It is also a monotone function of a
propensity-like quantity, hence the spurious correlation of 1.0.

**Resolution:** correlation and "share predicted negative" are measured on the
**T-learner specifically**, whose output is a difference of two probabilities and
therefore lives on the treatment-effect scale, where "negative" means "predicted to be
harmed". The ranking-quality comparison still uses the best of each family, since there
only the ordering matters.

**General rule:** only compare estimators on a quantity they all express on the same
scale. Rankings are comparable across all of them; raw scores are not.

---

## D-028 — Lint rules are pinned explicitly; an unpinned linter makes CI non-reproducible

**The failure.** CI went red on the test matrix across all three Python versions while
the calibration, leakage and kill-test gates stayed green. `make check` passed locally.
The failing step was **Lint**, not the tests.

**Root cause.** `[tool.ruff]` set only `line-length` and `target-version`, so the *rule
set* came from ruff's defaults — and those expand between releases. With `ruff>=0.5` in
the dev extra, CI installed the newest release and linted a strictly larger rule set than
a developer's pinned local install. Same command, same repo, different rules: 21 errors
in CI, 0 locally (`RUF046/059/100/022`, `UP035/037`, `I001`).

**Fix, in two parts:**

1. **`[tool.ruff.lint] select`** is now explicit — `E, W, F, I, UP, B`. The rule set is a
   property of the repository rather than of whichever ruff version got installed.
   Adding `select` reproduced all 20 errors locally *on the old ruff*, confirming the
   diagnosis: it was the rule set, not the version.
2. **`ruff>=0.12,<0.13`** — belt and braces. Bumping it is a deliberate act.

`RUF` is deliberately excluded: those are ruff's own opinions, they churn most between
releases, and they were the bulk of the drift. Determinism is worth more than the nits.

**Lesson worth generalising:** any tool that can fail a build must have its *behaviour*
pinned, not just its presence. A version floor (`>=`) pins nothing.

---

## D-029 — Dataset test guards check completeness, not existence

**The bug.** `HAS_LENTA = (DATA_DIR / "lenta_dataset.csv.gz").exists()` — five tests
errored mid-session because a download in progress leaves a file that *exists*, passes
the guard, and then fails to parse.

**Fix:** guards compare `stat().st_size` against the known byte count.

**Why this keeps recurring.** It is the third instance of the same mistake in this
project: a truncated Hillstrom CSV (caught by row count), a partial Criteo gzip with no
control arm (caught by `check_representative`), and now this. **Presence is not
validity.** Any external artifact needs a completeness check, and "the file is there" is
never one.

---

## D-030 — Tests must not assert on library-version-specific behaviour

**The failure.** `test_dates_are_parsed_from_strings` asserted
`dtype == "datetime64[ns]"`. It passed locally on pandas 2.3 and failed in CI on
pandas 3, which infers **microsecond** resolution when parsing `"2024-01-01"`.

**This is D-028 again in different clothing.** Both CI failures came from the same
structure: a `>=` dependency floor, CI resolving to something newer than the local
install, and a check that was sensitive to the difference. The linter case was fixed by
pinning behaviour; this one is fixed by *not depending on the behaviour at all*.

**Why the test was wrong rather than the dependency.** Nothing in this project depends
on timestamp resolution. Comparisons, ordering, and the schema's
`available_at >= occurred_at` invariant all work across units — verified directly. The
assertion was testing pandas' internals, not our behaviour. It now uses
`pd.api.types.is_datetime64_any_dtype` plus a value check.

**Runtime dependencies stay permissive on purpose.** Pinning `pandas` tightly would be
wrong for a library other people install. The correct discipline is that tests assert on
*our* semantics and never on a dependency's incidental representation.

**Residual risk, stated plainly:** local and CI still resolve different dependency
versions, so `make check` passing is not proof CI will pass. The mitigation is
discipline, not machinery — if a future failure is again a version divergence rather
than a real defect, a constraints file for CI becomes worth the complexity.

---

## D-031 — Lenta: the correlation principle survives an out-of-sample prediction

**The prediction, made before the data was downloaded.** D-026 proposed that
`corr(treatment effect, outcome propensity)` governs whether uplift modelling pays.
Lenta (retail SMS promotion) was added specifically as a test: retail was predicted to
fall **between** advertising (Criteo, +0.61) and subscription retention (−0.19). A
prediction that cannot fail is not worth making.

**Result: +0.177.** Between the two, as predicted.

| setting | corr | uplift advantage | % predicted negative |
|---|---:|---:|---:|
| Hillstrom (mens) | +0.63 | +4.7% | 0.2% |
| Criteo | +0.61 | +0.6% | 19.2% |
| **Lenta** | **+0.18** | **+10.4%** | 24.9% |
| Hillstrom (womens) | +0.07 | +3.9% | 10.2% |
| SubSim (churn) | −0.19 | +106.8% | 25.7% |

**What is confirmed and what is not — stated separately, because they differ.**

*Confirmed:* the correlation lands where predicted. Retail promotion is less coupled
than advertising and far less adversarial than retention.

*Not confirmed:* whether the *consequence* follows. Lenta's uplift advantage is
nominally +10.4%, the largest of the positive-correlation settings, which is consistent
with the principle — but the confidence intervals make it meaningless:
class-transform [359, 1601] against outcome-propensity [309, 1477], with random at
[343, 1007]. **Nothing is distinguishable from anything.**

**Why: Lenta is underpowered, not noisy.** The ATE is +0.0075 on a 10.3% base — a 7.4%
lift, against Hillstrom's 42.6% and Criteo's 27.3%. The small-n sweep is flat from
n=500 to n=20,000, with every method's mean inside one standard deviation of every
other's. More training data does not help because there is barely a signal to learn.

**The honest summary:** Lenta supports the principle on the axis it was predicted to
land on, and is too underpowered to test the consequence. It is one confirming
observation, not two.

**A useful secondary observation:** 24.9% of Lenta customers are predicted to be harmed
— comparable to the churn setting's 25.7% — yet uplift modelling still buys almost
nothing. This reinforces the D-026 refinement: **the share of harmed customers is not
what matters; their correlation with outcome propensity is.**

---

## D-032 — Dunning fatigue links the two churn processes without merging them

**The tension.** Invariant 5 says voluntary and involuntary churn stay separate
processes and are never summed. But a dunning email is unambiguously a message telling
the customer they are paying you — the same salience mechanism that creates sleeping
dogs in voluntary retention (D-002), arriving through the billing path.

**Resolution:** they remain separate *processes*, with an explicit causal *link* from
one to the other. Dunning contact adds an increment to the customer's voluntary-churn
hazard (`contact_fatigue_per_email`, on the logit scale). Nothing is summed; a
mechanism is modelled.

**Why it matters commercially:** without it, every evaluation prefers "email them more",
because recovery rate rises monotonically with contact. Recovering the payment and
losing the customer is not a win, and a metric that cannot express that will always
recommend the wrong policy.

**Stated honestly:** the fatigue magnitude is *assumed*, not measured — no public
dataset gives the churn cost of a dunning email. Figure 4's right panel is therefore a
sensitivity sweep showing where the policy ranking flips (~0.031) relative to our
assumption (0.055), rather than a single number presented as fact.

---

## D-033 — A test caught the simulator inflating its own headline result

**What happened.** `test_expired_cards_are_not_recoverable_by_retry` failed: expired
cards were recovering 21.7% under aggressive retrying.

**The bug.** `expired_card` had a gentle `attempt_decay` (0.90), so eight retries
compounded to ~22% recovery. But retrying a genuinely expired card **cannot** work.
The only recoveries come from the customer updating their card of their own accord, and
that does not become more likely because you retried again. The decay for
`needs_new_card` codes is now steep (0.30), so later attempts contribute almost nothing.

**It changed the headline.** Before the fix, `aggressive` had the *highest* recovery
rate and lost on value — a tradeoff story ("more recoveries, less money"). After the
fix, aggressive's advantage disappears entirely: it uses 2.5x the retries and 3.9x the
emails and recovers **no more** (48.6% vs 48.9%). It is strictly dominated and does not
even win on the vendor's own metric.

**The corrected result is cleaner and stronger.** The original required arguing a
tradeoff; the corrected one says simply that the extra effort buys nothing. Worth
recording that a test written to pin a *mechanism* found a bug that was flattering the
conclusion — which is the direction that matters, since nobody investigates a result
that looks good.

**Consequence:** `recovery_scale` was re-solved (0.4533 → 0.4764) after the change, per
the standing rule that calibration is re-run whenever a generative parameter moves.

---

## D-034 — The detailed dunning model is calibrated to agree with SubSim, then checked
## against a second published figure it was NOT calibrated on

**Alternative rejected:** replacing SubSim's aggregate involuntary-churn model outright.

**Reason:** SubSim's single-Bernoulli model is what the Phase 0 calibration gates were
tuned against. Replacing it would have re-opened calibration for no benefit — the
aggregate model is adequate for overall churn and useless only for studying *retry
policy*, which is what the new module exists for.

So they coexist, and `calibrate_recovery_scale` solves for the scale that makes the
detailed model's **passive** policy reproduce SubSim's `passive_recovery_rate` (0.42).
Consistent by construction rather than by coincidence.

**The check that makes this more than bookkeeping.** One parameter was fitted, against
the *passive* band (published 30–45%). The model then reproduces the *dedicated
dunning* figure at the other end without further tuning:

| configuration | recovery |
|---|---|
| processor default, no updater | 41.9% ← calibrated here |
| code-aware + account updater | 54.7% ← published band is 55–70%, not fitted |

Landing at the lower edge of an independent published band, from a fit made at the
other end, is a genuine out-of-sample check on the generative structure. Recorded as
"lower edge", not "in the band" — it is 54.7%, not 62%.

---

## D-035 — The report labels measured numbers differently from estimated ones

**The temptation.** The Churn Autopsy is a sales artifact — it is the only thing a
prospect sees before paying anything. Every incentive points toward blending "we
computed this from your invoices" with "operators like you typically recover more" into
one confident-sounding paragraph.

**The rule:** every `Finding` carries a `measured` flag, rendered as a visible badge —
green for *measured from your data*, amber for *estimated from industry benchmarks*.
The recovery-gap finding, which is the most persuasive one in the report, is amber.

**Why this is not just scruples.** The report's entire job is to earn enough trust for
a billing integration. A founder who later discovers that the headline number was an
extrapolation dressed as a measurement will not grant that integration, and would be
right not to. Being visibly conservative in the first artifact is the cheapest trust
you will ever buy.

**Also printed rather than omitted:** what could *not* be computed. If the export
carried no decline codes, the report says so and explains why that field matters. A
report that hides its own gaps is not worth the trust it exists to build.

---

## D-036 — The report refuses to recommend individual targets

**What it will not do**, stated in the report's own footer: name which customers to
contact.

**Reason.** Billing data supports retention curves, churn splits, and payment
economics. It does not support causal claims. Recommending targets requires a record of
past interventions and their outcomes, which no billing export contains — and D-026
established that targeting on outcome propensity is *worse than useless* in exactly the
adversarial setting retention occupies.

Producing a "customers at risk" list from a CSV would be the single most requested
feature and precisely the thing this project exists to argue against. Declining it in
the first customer-facing artifact keeps the product honest at the point where it is
most tempting not to be.

---

## D-037 — The SubSim adapter emits successful retries

**The bug.** The first Churn Autopsy run reported **0% recovery**. SubSim recovers a
share of failed payments without the customer churning, but the adapter emitted only
the failure, never the retry that succeeded. Downstream, recovery correctly measured
zero — an artifact of the adapter, not of any business.

Left unfixed it would have made every report claim a catastrophic recovery gap, which
is both wrong and exactly the direction that flatters us.

**Fix:** a failure that did not end in involuntary churn was, by SubSim's construction,
recovered; the adapter now emits the paid retry 1-6 days later. Recovery reads 38.6%,
consistent with SubSim's own passive rate of 0.42.

**Third instance of the same class of bug** (after D-024 and D-029): the pipeline was
representationally incapable of expressing something real, and the resulting number
looked like a finding rather than a gap. Worth asking of any new metric: *could this
number be zero because the data cannot express the thing, rather than because the thing
did not happen?*

---

## D-038 — Chart chrome inherits the page colour; charts are not themed at render time

**The bug.** Axis labels, tick marks and gridlines were invisible in dark mode. The
SVGs were rendered with matplotlib's default dark text and embedded as-is, so the CSS
theme switched around them and the chart text stayed dark-on-dark.

**Rejected fix:** rendering two copies of every chart and hiding one per theme. That
doubles the file size, doubles render time, and still breaks the moment someone toggles
manually.

**Fix:** render with sentinel colours (`#abcdef` for text, `#123456` for axes), then
string-replace both with `currentColor`. The SVG then inherits `color` from its
container, so one chart renders correctly in every theme, including a mid-session
toggle. Data colours -- the green line, the red bars -- are deliberately left alone;
only chrome inherits.

---

## D-039 — Light is the default theme, and printing forces it

**Behaviour:** light by default; follows `prefers-color-scheme` when the system
expresses one; a toggle overrides in *both* directions (`[data-theme]` on the root
beats the media query); `@media print` forces the light palette and hides the toggle.

**Why light rather than system-only.** This report is emailed, forwarded and printed.
A dark page arriving unexpectedly in an inbox wastes ink and reads badly on paper, and
the reader has no context for why it happened. Following the system is a courtesy;
light is the safe fallback when there is no signal.

**Why a toggle at all,** given the earlier argument against building UI: it is fifteen
lines of inline JavaScript with no network dependency, and it is the difference between
a reader who can read the report and one who cannot. That is not a dashboard.
