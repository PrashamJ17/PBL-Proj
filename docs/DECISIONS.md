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

---

## D-040 — Reports before dashboards

**The question:** should a business receive a report, or log into a dashboard?

**Decision: reports, and not as a compromise.**

Four reasons, in descending order of force:

1. **Your differentiator is a decision, not a view.** This project's whole argument is
   that the industry fails by stopping at "here's a risk score". A dashboard is the
   canonical way to stop at a view. Building one first would place the product in the
   exact category D-020 and D-026 criticise.
2. **Sequencing.** A dashboard needs live data → which needs integration → which needs
   trust not yet earned. A report needs a CSV export the customer can produce in ten
   minutes. **The report is what earns the trust that makes the integration possible.**
3. **Dashboards duplicate free incumbents.** Baremetrics and ProfitWell Metrics exist,
   are good, and are checked roughly monthly. That is the one axis with no advantage.
4. **The buyer has no analyst.** They do not want to explore data; they want to be told
   what happened and what to do.

**The form actually built:** a report that lives at a URL. Push the link, let them click
through for detail. One artifact serving both jobs, no auth system, no uptime
obligation.

**Three jobs that must not be conflated:** the monthly push drives action; the detail
page answers objections; the demo sells. A single dashboard attempting all three serves
none.

**The rule that prevents dashboard bloat:** every screen must answer a question someone
actually asked. If the question cannot be named, the screen is not built.

**What would change this:** ten Churn Autopsy conversations in which prospects say "I
want to see it live". That is real signal. Building UI to answer an objection nobody has
raised is the most expensive way to guess.

---

## D-041 — Three usage modes, and why dunning is the first rung of a trust ladder

How a business actually uses this, in the order it can happen:

**Mode 1 — the report** (built). Export three CSVs, receive a diagnostic with money
attached. No integration, no engineer. They act manually.

**Mode 2 — dunning autopilot** (not built). Connect Stripe once. On
`invoice.payment_failed`: read the decline code, pick a schedule, retry via the API,
hold back 5-10% to prove it worked. Needs a webhook receiver, a scheduler, write scope,
and the holdout ledger — ordinary engineering, no research.

**Mode 3 — the retention decision layer** (not built). Nightly scoring → hazard → CLV →
uplift → offer ladder → act or abstain, written into the tools they already use. Needs
Mode 2's *intervention history* first, and that is not a scheduling preference: treatment
effects cannot be estimated without a record of treatments.

**Why dunning goes first, beyond it being easy.** Retrying a failed payment is something
the business *already does* — we simply do it better, using a decline code they already
have. It asks nobody to trust an algorithm with their customer relationships on day one.
By the time Mode 3 is proposed, six months of quietly recovering their money has built
the standing to propose it. **Ordering by trust required, not by technical difficulty.**

**Design principle for all three: the best version is invisible.** The failure mode of
every analytics product is a dashboard nobody opens. If the owner must log in and
interpret a churn score, the wrong thing was built. The product is a scheduled retry and
a monthly number.

**And: be the brain, not the pipes.** We never send the email ourselves; decisions are
written into their existing marketing or CRM tool. Lower adoption friction, and no
competing with commodity email vendors on price.

---

## D-042 — Research positioning: the novelty is small-n abstention, not "churn scores are bad"

**The collision.** Ascarza, *"Retention Futility: Targeting High-Risk Customers Might Be
Ineffective"* (Journal of Marketing Research, 2018; Paul E. Green Award) already
established, with two field experiments, that the highest-churn-risk customers are not
the best targets and that targeting on *sensitivity to intervention* beats risk-based
targeting by up to 6.8pp. That is the core of what the Phase 0 kill test demonstrates.

**Consequence:** a paper led by "churn-score targeting is the wrong rule" gets desk-
rejected with that citation. The claim is not ours.

**What survives, in descending order of strength:**

1. **Abstention under posterior uncertainty at small n.** Not in Ascarza, not
   productised anywhere. Supported by real data (D-023: 75% win rate at n=500).
2. **The corr(τ, propensity) principle** (D-026), with an out-of-sample confirmation
   (D-031). Ascarza shows risk-targeting is *ineffective*; this characterises **when it
   becomes actively harmful**, which is a distinct and sharper claim.
3. **Ground-truth individual treatment effects.** Field experiments give average
   effects, never individual ones. The simulator can score CATE estimates against exact
   per-customer truth.
4. **Decision-quality evaluation under budget** — money earned, not Qini.

**Paper structure:** merge the planned papers 1 and 2. The simulator is the *instrument*;
the finding is the lead. A standalone "we built a simulator" resource paper lands in
workshops — reviewers reward findings over tools.

**Venues:** arXiv preprint immediately (priority, and it doubles as lead generation),
then *EJOR* or *Decision Support Systems*, which have published this line. **Not** *JMR*
— that is Ascarza's home turf and needs field experiments we do not have.

**Also check before drafting:** Verbeke et al. on cost-sensitive causal classification
and "To do or not to do: cost-sensitive causal decision-making" — close to the planned
paper 3.

---

## D-043 — Survival is modelled in discrete time on a person-period frame, not with Cox

**Alternative rejected:** Cox proportional hazards, which is the default in the
survival literature and would have been less work — `lifelines` is one call.

**Reason.** Four, specific to what this project needs rather than to survival analysis
in general.

1. **Time-varying covariates are the point, and Cox handles them badly *here*.**
   Engagement, support pain and payment failures move every month and are what carry
   the churn signal. Cox can take them via a start-stop dataset — and that construction
   is exactly where availability leakage is easiest to introduce and hardest to see.
   In the person-period form each row **is** one point-in-time feature build, so the
   Phase 1 guarantee (`FeatureStore._visible`, D-015) extends to the survival model
   with no new machinery. The representation and the safeguard are the same object.

2. **We need absolute probabilities, not a ranking.** CLV is
   `sum_t margin * S(t) / (1+d)^t` — a functional of the *level* of the survival
   curve. Cox's partial likelihood profiles the baseline hazard out as a nuisance and
   absolute survival arrives afterwards via Breslow, which nothing in the fit
   optimised. A model can rank perfectly and value a customer at twice their worth.

3. **Proportional hazards is false in subscriptions and cheap to drop.** A
   month-to-month customer and an annual one do not share a baseline hazard scaled by
   a constant; the shapes differ. Here the baseline is a free function of the period
   and covariate-by-period interactions cost nothing.

4. **Billing is genuinely discrete.** Churn happens at a renewal boundary. Tied event
   times are not a nuisance to be approximated away — they are simultaneous events in a
   monthly cycle, which is what the data actually is.

**Cost, stated plainly:** the frame is `sum_i d_i` rows rather than `n`, i.e. larger by
the mean duration. Irrelevant at thousands of customers; it would matter at tens of
millions. And discretising *continuous* data costs real resolution — see the GBSG2
result, where we lose.

**Consequence:** any split of a person-period frame must be **by subject, not by row**.
Rows from one customer in consecutive months share covariates and an outcome, so a
row-wise split leaks. `test_calibration_split_is_by_subject_not_by_row` enforces it for
the isotonic calibration step, which is the one place inside the model where a split
happens.

---

## D-044 — Competing risks are combined at the survival level, never at the label level

**The tension.** Invariant 5 says voluntary and involuntary churn stay separate
processes and are never summed. But a survival curve has to account for both: a
customer lost to an expired card is not available to be lost voluntarily.

**Resolution:** a **separate cause-specific hazard per cause**, sharing nothing but the
at-risk structure. They meet only in

```
S(t)     = prod_{s<=t} (1 - sum_k h_k(s))
CIF_k(t) = sum_{s<=t} h_k(s) * S(s-1)
```

No label is ever merged. Each cause keeps its own model, its own coefficients and its
own interpretation, and `test_each_cause_keeps_its_own_model` asserts the two fitted
hazards actually differ — otherwise the split would be decorative.

**Why this is not the error D-001 forbids.** D-001 objects to fitting one binary
`churned` target, which makes a third of the outcome unaddressable by the model meant
to explain it. Composing separately-estimated cause-specific hazards is the opposite
operation: the split survives all the way to the output, and
`S(t) + sum_k CIF_k(t) = 1` holds exactly (tested).

**What it buys commercially.** The CLV shortfall decomposes by cause with **no
residual** — `sum_k shortfall_k = V0 - V` exactly — so "72% of the leak is voluntary,
28% is billing" is a measurement rather than an apportionment. Those two have different
fixes and, per Phase 2, wildly different effort-to-recovery ratios. A blended churn
number cannot express the distinction.

**One honest wrinkle:** the cause-specific hazards are fitted independently, so their
sum can exceed 1 for a customer every model considers doomed. It is clipped. The clip
rate is worth watching rather than hiding; a joint multinomial fit would remove the
issue and is the obvious refinement if it ever bites.

---

## D-045 — The headline survival metric is the integrated Brier score, not concordance

**Alternative rejected:** reporting Harrell's C, as essentially the whole survival
literature does.

**Reason.** Concordance is a *rank* statistic. It cannot distinguish a model that says
"you have a 90% chance of still being here in a year" from one that says 60%, provided
they order customers the same way. CLV multiplies that number by money, so the
distinction is the entire product.

**But calibration error alone is worse**, and this was a live trap rather than a
hypothetical. `cal_mae` on Telco: Kaplan-Meier **0.0268**, Cox 0.0439. The model with
no covariates at all beats the covariate model, because a marginal prediction is
trivially calibrated — it is right on average by construction. Reporting calibration
error as the headline would have made "predict the average for everyone" the winning
strategy.

**So the headline is the integrated Brier score**, a proper scoring rule, which
penalises miscalibration *and* lack of discrimination together. Kaplan-Meier scores
0.1823 there against 0.0824 for the discrete model — no longer competitive at all. The
rank metric and the calibration diagnostics are reported beside it, never instead of
it, and `KaplanMeierBaseline` stays in every table specifically so this failure mode
is visible rather than argued about.

**A correction that had to be made to D-calibration.** `S(T) ~ Uniform(0,1)` holds for
*continuous* distributions. On a monthly grid `S(T_i)` lands at the bottom of the
interval the event fell in, so the top bin is systematically starved. Measured on a
correctly-specified synthetic fit: chi2 = **61.7** using `S(t)` against **2.3** using
the interval midpoint `(S(t) + S(t-))/2`. The rejection was an artifact of the grid,
not a defect of the model. The midpoint is the standard randomised-PIT correction for
discrete distributions, and the harness applies it to **every** model through one code
path — the left limit is just `survival_at(X, t - 1e-9)`, well defined for any step
function. Applying it to our model alone would have been exactly the asymmetry this
project exists to avoid.

---

## D-046 — CLV is capped at the observed support and refuses to extrapolate

**Alternative rejected:** the standard `ARPU / churn_rate` formula, or equivalently
summing the survival curve to infinity.

**Reason.** That formula is the sum of an infinite geometric series, so it assumes a
**constant hazard forever**. Retention hazards decline with tenure — D-004 built that
in deliberately, and measured `early_late_hazard_ratio ~ 2.0` — so a constant-hazard
extrapolation is not merely uncertain, it is *biased*. Worse, the survival model has no
information whatsoever about periods beyond its training window: the curve keeps
returning numbers, and they are the tail assumption talking, not the data.

**Implementation:** `clv()` takes `observed_support` and raises `ExtrapolationError`
when the horizon exceeds it. A warning was rejected — a warning in a notebook is a
warning nobody reads. `allow_extrapolation=True` exists, so the assumption becomes a
visible line of code owned by whoever wrote it.

**Two smaller choices in the same formula, for the record.** Margin rather than
revenue, because revenue-based CLV overstates every customer by the cost of serving
them and overstates the expensive ones most — precisely the ones a retention budget
would then chase. And discounting compounded monthly rather than `annual/12`, which
differs by ~5% of the rate and compounds again over a multi-year horizon.

---

## D-047 — Telco's `TotalCharges` is a duration proxy, and the split cannot be temporal

Two decisions about the public dataset, both worth naming because both are places where
the obvious move is wrong.

**`TotalCharges` is excluded.** It is cumulative billing to date, so it is very nearly
`MonthlyCharges * tenure`: measured **r = 0.83** with tenure. As a fixed covariate in a
survival model it is a direct encoding of the duration being predicted. It is named in
`EXCLUDED_FROM_TELCO` with its reason, and `test_total_charges_is_excluded_because_it_
encodes_the_duration` asserts both the exclusion and the correlation, so the reason
cannot rot away from the rule.

**The split is by subject, not temporal, and this is an exception to invariant 1.**
Invariant 1 requires temporal splits, and it should be — it is what prevents the
0.35 AUC inflation measured in D-016. But Telco and GBSG2 carry **no calendar time at
all**: there is only tenure, which *is* the outcome. There is no "train on months < T"
available to perform, so a random subject-level split is the only honest option and is
what the survival literature uses for these sets. Where calendar time does exist —
SubSim, and any real tenant — the temporal split applies unchanged.

Recorded rather than glossed, because a silent exception to an invariant is how
invariants stop meaning anything.

---

## D-048 — Two evaluation bugs, both caught by an external check rather than by reading

Neither was in the model. Both were in the metric, and both changed the ranking.

**1. The censoring distribution needs the events-before-censorings tie convention.**
The IPCW Brier score reweights by `1/G(t)`, and `G` was first estimated as
Kaplan-Meier with the event indicator flipped. That is wrong when events and censorings
are **tied**, which on monthly data is almost every time point: the denominator must be
`at_risk - events`, not `at_risk`. The error was ~2% on the integrated Brier score —
small enough to look like noise, large enough to reorder near-tied models. Caught by
`test_brier_matches_scikit_survival`, which was written to check agreement with the
reference implementation rather than to trust ours.

**2. `G(t)` reaches exactly zero at the end of follow-up.** Under administrative
censoring, nobody can be censored later than the last day of the study, so
`G(24) = 0` in a 24-month simulation and every weight there is undefined. Evaluating on
a grid that reached the end produced integrated Brier scores of **2.6e7** on SubSim —
six orders of magnitude out, with the model ranking scrambled rather than merely
inflated. It was invisible on Telco and GBSG2, where follow-up is staggered and `G`
stays positive, which is why it survived the first round of runs and only appeared when
the simulator was added to the same table.

Fixed by `estimable_horizon`, and `brier_score` now returns **NaN** rather than a number
when a weight is undefined. Clipping the weight or dropping those subjects would have
biased the score toward whichever model is optimistic about the customers we can no
longer weight — silently, and in a direction nobody would investigate.

**The generalisable point,** and it is the same one as D-024, D-029 and D-037: the
failure was not in the thing being measured but in the pipeline's ability to measure it.
Two questions earn their place on any new metric — *could this number be wrong in a way
that looks plausible?* and *is there an independent implementation to check it against?*
The second one is what caught the first bug in minutes.

---

## D-049 — Phase 3 gate: what was established and what was not

The gate reads "beats Cox/RSF/DeepSurv on public data; calibrated". Recorded here in
the D-021 spirit: the prediction was written into
`keel/experiments/survival_benchmark.py` before the first run, and this is the scoring
of it, including the parts that did not land.

**Telco (7,032 customers, the subscription dataset — mean over 10 resplits):**

| model | C-index | IBS | cal. slope | ours wins on IBS |
|---|---:|---:|---:|---:|
| **discrete-time (logistic)** | 0.8650 | **0.0824** | 1.02 | — |
| DeepSurv | 0.8661 | 0.0825 | 0.98 | 4/10 |
| discrete-time (GBM) | 0.8608 | 0.0865 | 1.00 | 10/10 |
| Cox PH | 0.8565 | 0.0914 | 1.18 | **10/10** |
| Random Survival Forest | 0.8461 | 0.0964 | 1.18 | **10/10** |
| Kaplan-Meier | — | 0.1823 | — | 10/10 |

**MET:** beats Cox and RSF on 10/10 resplits, and is the best-calibrated model in the
table alongside DeepSurv. **NOT MET:** it does not beat DeepSurv — 0.0824 against
0.0825 is a tie, and saying otherwise would be reading noise.

**GBSG2 (686 patients, the baselines' own benchmark):** we predicted a loss and lost.
RSF leads on C (0.698 vs 0.678) and IBS (0.183 vs 0.187). The discrete model has the
best calibration slope (1.09 against Cox's 1.48) but discretising seven years of daily
follow-up onto a monthly grid costs resolution the others keep. **This is the correct
result to get here** and it is the reason GBSG2 is in the table at all.

**Landmark prediction (SubSim): partially confirmed, and weaker than predicted.** The
pre-registration said "expect a SUBSTANTIAL win". Against the controlled comparison —
the same model class restricted to signup-time covariates — the time-varying model wins
on **100% of seeds at n>=2,000 and 92% at n=1,000**, but by a modest +0.03 C-index.
Against Cox refitted at each landmark it is a wash (55-92% of seeds, no trend in n), so
the *pooling* hypothesis is **not established**. Below n=250 nothing reliably beats
Kaplan-Meier at all, which is the most useful number in the experiment and was not
predicted.

**Honest summary of what Phase 3 bought.** Not accuracy — on rank it is a tie with the
strongest baseline. What it bought is *what the model can represent*: time-varying
covariates through the same point-in-time path the rest of the system uses, competing
risks that stay separate to the output, and calibrated absolute probabilities that CLV
can multiply by money. DeepSurv matches the numbers and can do none of those three,
while requiring a ~2GB dependency. That is the claim, and it is narrower and more
defensible than "beats Cox".

---

---

## D-050 — Survival refuses to extrapolate past its observed support

**The inconsistency found in audit.** `clv()` raises past the observed tenure support
and forces `allow_extrapolation=True` to be a visible line of code (invariant 12,
D-046). `DiscreteTimeHazard.survival()` happily returned a 24-month curve fitted on 8
months of history, silently. The same epistemic concern, opposite handling — and the
CLV docstring already implied a guard that did not exist.

**Why it matters more here than it looks.** Beyond the observed support the period
basis is not estimating: the dummy basis has no coefficient for those periods and the
spline basis is running on its linear tail. The curve is a functional-form assumption
presented as an estimate — and `clv()` consumes exactly this curve, so an unguarded
survival call routes straight around the CLV guard.

**Fix:** `observed_support` is recorded at fit time and `survival()` refuses to project
past it unless `allow_extrapolation=True`. Invariant 12 now covers both.

---

## D-051 — Degenerate survival inputs get errors about the data, not the solver

**Found by probing rather than by reading.** Five situations a real tenant can be in
produced messages naming a scikit-learn optimiser:

| Input | Was | Now |
|---|---|---|
| Zero events (a young business) | `solver needs samples of at least 2 classes` | names the hazard as unidentified, suggests Kaplan-Meier |
| NaN in a covariate | `Input X contains NaN` | names the offending column |
| Empty dataset | `need at least one array to concatenate` | says the dataset is empty |
| `horizon=0` | `Found array with 0 sample(s)` | says horizon must be >= 1 |
| Undeclared event code | *silently accepted* | names the code and `cause_names` |

The last was the real defect. `event` is a **cause code**, so values above 1 are
legitimate — but an *undeclared* one silently censored those subjects, losing a whole
competing risk with no signal at all.

**Deliberately not fixed by imputing.** NaN covariates raise rather than fill, because
choosing a fill value is a modelling decision that belongs in the loader where it is
visible, not inside a model where it is invisible.

---

## D-052 — Two audit findings that were tests being wrong, not code

Recorded because both are traps that would recur.

**"No censoring" is not "no censored periods".** A subject with duration 5 who then
fails contributes four survived person-period rows and one event, so the expanded frame
has both classes even when no *subject* was censored. A test asserting refusal there
was wrong; the degenerate case the guard actually catches is every subject failing in
their first period.

**`duration == window` in a landmark slice is not "censored".** Durations are capped at
the window, so that value contains both customers who failed in its final month and
those still present at its edge. The invariant worth testing is the cap itself.

Both follow the pattern of D-037: the test encoded an assumption about the data model
rather than checking the data model. When a new test fails, the first question is which
of the two is wrong — and roughly half the time in this project it has been the test.

---

## D-053 — The Laplace posterior is validated against NUTS; the residual is empirical Bayes

**The worry.** `HierarchicalCATE` approximates the coefficient posterior with a Gaussian
at the mode. A logistic posterior at n=250 is skewed, and a Gaussian fitted at its mode
is narrower than what it approximates. If the posterior is over-confident, the
abstention rule built on it acts when it should not, and the phase's own claim is
inflated.

**Measured.** Same model fitted with NUTS (`keel/models/uplift/mcmc_check.py`), same
discipline the survival metrics use against lifelines and scikit-survival (D-048):

| n | posterior sd ratio (Laplace / NUTS) | mean correlation |
|---|---|---|
| 250 | 0.993 | 0.9998 |
| 500 | 1.003 | 1.0000 |
| 2000 | 0.988 | 1.0000 |

**The Laplace approximation is not the problem.** It reproduces NUTS to three decimals.

**What is.** Simulation-based calibration still shows narrow intervals — 90% covering
79% at n=250, 86% at n=2000 — and NUTS shows the same deviation. The cause is the
**empirical-Bayes treatment of `sigma_gamma`**: weighting a grid by marginal likelihood
is a posterior conditional on the grid being the prior, and it under-propagates
hyperparameter uncertainty. This is a known property of empirical Bayes, not a bug.

Mixing over the grid (rather than plugging in the mode) already narrowed the gap; it did
not close it.

**Why this is recorded rather than patched.** The error runs **against** the claim.
An over-confident posterior abstains *less* than it should, so the policy behaves more
like the top-k rule it is being compared to, and the differentiation this phase must
demonstrate gets *harder* to show. Inflating the variance until coverage looked right
would be tuning the estimator until the result improved — the thing D-005 and D-011
exist to prevent.

**Consequence for the paper:** the limitations section must state that intervals are
narrow at small n, that the direction is conservative for our claim, and that a fully
Bayesian treatment of `sigma_gamma` is the obvious next step.

---

## D-054 — Phase 4 gate: PARTIALLY MET. The rule prevents damage; it does not create profit

The gate was: *"beats baselines on net revenue at small n"*. Stated precisely, with
ground truth withheld from every policy and the comparator being the strong version
(same estimator's point estimate, same customer values, ranking and filling the budget),
the result is:

| n | abstention beats ranking | abstention beats doing nothing | treated (abstain vs top-k) |
|---|---|---|---|
| 250 | 75% | **10%** | 7 vs 23 |
| 500 | 80% | **10%** | 15 vs 46 |
| 1000 | 70% | **5%** | 32 vs 90 |
| 2000 | 65% | **0%** | 72 vs 181 |
| 4000 | 80% | **10%** | 127 vs 359 |

**What is established.** Abstention beats ranking on 65–80% of draws, and it does so by
spending roughly a third as much. Sweeping the confidence threshold shows the safety
property working exactly as specified: at `alpha = 0.05` the rule treats **zero**
customers and returns the do-nothing baseline rather than losing money. It correctly
recognises that it does not know enough.

**What is not.** There is no threshold at which it *makes* money. It either loses (loose
threshold) or does nothing (strict). Both it and the ranking comparator are
value-destroying against the do-nothing baseline at every size tested.

**Why, and why this was predictable.** D-023 established that conventional methods beat
random on only 75% of draws at n=500 -- the estimates are unreliable at this scale. A
decision rule inherits the quality of its inputs. Abstention makes the *consequences* of
unreliable estimates survivable; it cannot manufacture reliability that is not there.
The Phase 0 precursor (209 contacts beating 718) used **oracle** effects and was always
an upper bound on an estimated rule, which the paper said at the time.

**Cross-tenant pooling helps and does not close the gap.** A prior from ten established
firms cuts mean losses from −457 to −62 at n=500, by making the small firm treat 2
customers instead of 12. Damage limitation again, not profit.

**Not tuned until it passed.** The obvious moves -- widen the posterior until coverage
looks right, pick the alpha with the best realised number, drop the losing sizes -- are
exactly what D-005 and D-011 exist to prevent. The threshold sweep is reported in full,
including the settings where the rule loses money.

**The honest claim this supports:** *given that ranking loses money (Phase 0), a rule
that reliably returns to zero is worth real money relative to what businesses actually
do.* That is a defensible and useful statement. It is **not** the statement the gate
asked for, and the paper must say so.

**What would change it:** more informative data per customer rather than more customers;
a genuinely fully-Bayesian treatment of `sigma_gamma` (D-053); or a setting with larger
average treatment effects, since SubSim's calibrated `mean tau = -0.010` leaves very
little margin over the offer cost by construction (D-011).

---

## D-055 — The Phase 4 gate failed on arithmetic, and asked for two things that trade off

**Context.** D-054 closed by naming the untested explanation: SubSim's calibrated
`mean tau = -0.010` may simply leave too little margin over the offer cost. That is a
checkable claim and it was checked, as a **sensitivity** — no default was changed,
`SimConfig` and `REFERENCE_OFFER` are untouched, and the D-054 numbers stand.
`keel/experiments/sensitivity.py`; a test pins that the default path is unchanged.

**First, the arithmetic.** Treating pays iff `-tau_i * CLV_i > cost_i`, so the break-even
effect is `cost_i / CLV_i`. Under the reference offer that is **0.040** against a mean
effect of **0.010** — a factor of four. An oracle knowing every `tau_i` exactly would
treat **5.8%** of customers. That is the ceiling. Phase 4 asked an estimated rule to find
profit inside 5.8% of a population, from a pilot of a few hundred. The gate was
arithmetically out of reach before any decision theory ran.

**Axis 1 — effect size (20 seeds × {500, 1000}, Clopper–Pearson 95% CI).**

| `saveability_scale` | mean tau | sleeping dogs | beats ranking | beats do-nothing |
|---|---|---|---|---|
| **−2.0 (default)** | −0.0096 | 27% | **75% [.59,.87]** | 8% [.02,.20] |
| −3.0 | −0.0248 | 16% | 55% [.38,.71] | 20% [.09,.36] |
| −4.0 | −0.0381 | 10% | 55% [.38,.71] | 40% [.25,.57] |
| −5.0 | −0.0498 | 7% | 32% [.19,.49] | 57% [.41,.73] |
| −6.0 *(outside band)* | −0.0601 | 5% | 20% [.09,.36] | **72% [.56,.85]** |
| −8.0 *(outside band)* | −0.0772 | 3% | 20% [.09,.36] | **85% [.70,.94]** |

**The gate does flip — and the flip is worthless.** At no setting is either win rate
significantly above chance while the other also is; they move in *opposite* directions.
The regime where abstention beats inaction is the regime where blanket treatment beats
abstention (`treat_all` profits on 88% of draws at −6.0). And buying the gate costs the
mechanism: sleeping dogs fall 27% → 3%, so a passing row describes a world where this
project's thesis does not apply. Rows past −5.0 also leave the calibration band of
invariant 4.

**Axis 2 — offer choice, and this one is on us.** The ladder was fixed in Phase 0 and is
unmodified. Phase 4 ran on `discount_20_3mo` — cost 32, the second most expensive rung
the ladder has.

| offer | cost | break-even | oracle treats | beats do-nothing |
|---|---|---|---|---|
| `feature_nudge` | 0.10 | 0.0001 | **69%** | 8% |
| `checkin_call` | 6.00 | 0.0079 | 39% | 20% |
| `discount_20_3mo` **(Phase 4)** | 32.22 | 0.0399 | **6%** | 8% |
| `discount_40_6mo` | 127.39 | 0.1574 | 0% | 0% |

No rung passes, and the cheap rungs fail for the **opposite** reason to the expensive
ones: the discounts are detectable but unprofitable; the nudge is profitable but its
effect (−0.0021) is too small to detect at n≈250, so the rule abstains on half of draws
and picks badly on the rest. Detectability and profitability are anti-correlated across
the ladder. That squeeze, not the effect size, is the real Phase 4 finding.

**Conclusion.** The gate as written — beat ranking *and* beat inaction — is not
achievable anywhere in the swept range. That is a defect in the gate, not evidence the
method works: the correct response is to state what abstention is *for*, which D-056
does, and not to relabel the existing numbers as a pass.

---

## D-056 — A post-hoc hypothesis, refuted out-of-sample, that localised a real defect

**The hypothesis.** Axis 1 suggested abstention is never best but never catastrophic:
normalised max regret across the effect-size range was 34.9%, against 49.0% for ranking
and **100%** for both `do_nothing` (which forgoes 10,213 at −8.0) and `treat_all` (which
loses 4,735 at the default). That reads as a minimax-regret hedge — attractive, and
exactly the epistemic position a business is in, since it cannot know its own
`tau`/cost ratio in advance.

**It was generated after seeing the failure**, which is when a claim is most likely to be
self-serving. This project has a standard for that (D-031: predict, then test on data not
used to form the idea). Axis 2 varies cost on a Phase-0 ladder and played no part in
forming it, so it is a valid held-out test. The prediction was recorded first: abstention
lowest max regret, `do_nothing` catastrophic on `feature_nudge`, `treat_all` catastrophic
on `discount_40_6mo`.

**It failed.** `random_30pct` has lower max regret (58.9%) than abstention (85.7%).
The minimax reading is **refuted and withdrawn**, not quietly dropped.

**What the failure localised.** Abstention's worst regret is on the *cheap* rungs — 158
against `treat_all`'s 753 on `feature_nudge`. The rule demands `P(benefit > 0) > 1 - alpha`
with alpha fixed at 0.30 for every decision, i.e. the same evidential standard whether
being wrong costs 0.10 or 33. Sweeping alpha per rung confirms the diagnosis:

| offer | cost | best alpha |
|---|---|---|
| `feature_nudge` | 0.10 | **0.49** |
| `checkin_call` | 6.00 | **0.49** |
| `downgrade_offer` | 0.50 | **0.49** |
| `pause_offer` | 0.50 | **0.05** |
| `discount_20_3mo` | 33.50 | **0.05** |
| `discount_40_6mo` | 132.50 | **0.05** |

The optimum moves with the payoff, so **a constant alpha is wrong by construction**.
`pause_offer` shows the driver is not cost but *asymmetry*: it is cheap yet wants 0.05,
because its mean tau is **positive** (46% sleeping dogs) and treating is harmful on
average. Equation 8 conflates "I am uncertain" with "I should not act"; when the downside
is 0.10 and the upside is a retained customer worth 700, uncertainty is not
decision-relevant and the rule should act on the expected value.

**Deliberately not fixed here.** Diagnosing a flaw and repairing it in the same commit is
how a sensitivity becomes the tuning it was built to guard against. The correction —
alpha as a function of the payoff ratio rather than a constant — is a Phase 5 item, and
it must be specified before it is run, on the axis that refuted its predecessor.

**Residual gap even at the best alpha.** On `feature_nudge` the tuned rule reaches 260
against `treat_all`'s 753, so it still under-treats by a wide margin. Consistent with the
empirical-Bayes shrinkage of D-053: pooling pulls small-but-real effects toward zero, and
what is shrunk cannot be detected. Both defects point the same way, and neither is
addressed by more customers.

---

## D-057 — Phase 4 multiplied a log-odds ratio by money for an entire phase

**The defect.** `HierarchicalCATE` fits `logit P(churn) = a + x'b + T(tau_0 + x'gamma)`, so
`tau_i` is a **log-odds ratio** — `bayesian.py` says so in as many words. `AbstentionPolicy.
decide` then computed `-posterior.mean * value - cost`, which is money only if `tau_i` is a
difference in **probability**. On one diagnostic draw (n=4000, seed 11, reference offer) the
rule believed the mean benefit of treating was **-104.5**; the truth was **+20.5**, against
an offer costing 31.5. The quantity being thresholded was not money.

**Why it mattered rather than being untidy.** For baseline risk `p0`, a log-odds shift `t`
moves the probability by roughly `t * p0(1-p0)`, so treating log-odds as probability
overstates the benefit by about `1/(p0(1-p0))` — a factor of 4 at `p0 = 0.5` and **25 at
`p0 = 0.05`**. The inflation is worst for customers who were **never going to churn**. That
is the Sure Thing quadrant, and over-valuing it is the exact error this project exists to
characterise (D-002, D-013). We reintroduced it inside our own decision rule.

**Why nothing caught it.** Every Phase 4 test passed, and all of them were right about what
they tested. `test_rule_reduces_to_a_point_threshold_as_the_posterior_concentrates` checks
the rule against `(-mean * value - cost) > 0` — the same wrong formula. The estimator tests
compare against a synthetic `tau` generated on the logit scale, so they are internally
consistent. **Not one test asked what the number meant in currency.** The lesson is narrow
and worth stating: self-consistency tests cannot catch a units error, because a units error
is consistent with itself. `test_probability_effect_matches_the_definition` now checks a
value computed by hand.

**The fix** (`keel/policy/economics.py`). Convert before touching money:

```
delta_p = expit(eta0 + tau) - expit(eta0)      benefit = -delta_p * V - c
```

`eta0 = a + x'b` comes from the same fitted model, so no separate churn model is needed and
the two halves cannot disagree. `expit` is nonlinear, so Equation 8's closed form is gone;
the posterior over `benefit` is obtained by sampling `(eta0, tau)` **jointly**, since they
come from one coefficient vector and are correlated. The new rule consumes a
`MoneyPosterior` and nothing else, which makes the original mistake unrepresentable —
there is no way to hand it a log-odds quantity. `decide` is kept, with a warning, so
D-054/055/056 stay reproducible.

**Predictions were registered first** (`docs/PREREG-phase5.md`), because "we fixed a bug and
our numbers improved" is the easiest way to launder a result. Outcome, 20 seeds:

| # | Prediction | Result |
|---|---|---|
| 1a | corrected benefit within ~3x of truth, right sign | **held** (-46 vs -23; was -104) |
| 1b | treats more on cheap rungs, fewer on dear ones | **half** — dear yes (24→13, 28→1), cheap unchanged (25→26) |
| 1c | gate **still fails** on the reference discount | **held** — 6% beats do-nothing |
| 1d | gate **passes** on a cheap rung | **FAILED** — best is `feature_nudge` at 10%, CI [0.03, 0.24] |
| 2a | the best-`alpha` spread shrinks | **FAILED** — 2 distinct values became 3 |

**1c holding is the important one.** The 5.8% oracle ceiling of D-055 is computed from
ground truth and no estimator fix can beat it; a fix that made the reference discount
profitable would have been wrong. **1b's cheap half failed for a reason that was
foreseeable**: when cost is negligible the decision is driven by the sign of `delta_p`,
which `expit` preserves, so the bug barely moved it. **2a failing means D-056 stands** —
the per-rung `alpha` dependence is real and not an artifact, which we had suspected it was.

**What it changes.** Losses shrink sharply (n=2000: **-3,531 → -1,070**, treating 27 rather
than 72; `discount_40_6mo` at `alpha=0.05`: **-5,384 → 0**, i.e. correctly treating nobody)
and the rule now beats corrected ranking on **93%** of draws, up from 75%. **It does not
change any qualitative conclusion.** The gate still fails, for the reason D-055 gave: the
offer is four times too weak to pay for itself, and `corr(tau_hat, tau_true) = 0.13` at
these sample sizes. The bug was real, its repair was necessary, and it was **not
sufficient**.

---

## D-058 — Choosing the offer beats choosing the customer, and neither is reliable yet

**The reframing.** Phases 0-4 all asked one question with the offer held fixed: who gets
this discount? D-055 showed that question is close to degenerate — treat everyone when the
offer is nearly free, nobody when it is expensive. Phase 5 asks the one the ladder was
built for: **which rung for which customer.**

**The test is harder than Phase 4's, deliberately.** Effects are learned **per rung** from a
randomised multi-arm pilot, because `saveability_multiplier` is oracle knowledge a business
does not have. That splits a small pilot `K+1` ways — roughly 35 customers per arm at
n=500 — so learning six offers is *harder* than learning one. Partial pooling across rungs
(the D-041 cross-tenant mechanism, applied across arms) is what makes it survivable.

**Three comparators, one of them unfair on purpose.**

| | mean money | share of oracle | beats it |
|---|---|---|---|
| **optimiser** (`lambda = 0`) | 655 / 1,039 / 2,252 | **28%** | — |
| `pilot-pick` — best rung on the pilot, applied to everyone | 502 / **-562** / 1,869 | 13% | 58% [0.42, 0.72] |
| `hindsight` — best single rung, chosen on the test set | 1,997 / 2,554 / 5,892 | 73% | 13% [0.05, 0.27] |
| `oracle` — knows every tau, picks per customer | 2,348 / 3,747 / 8,242 | 100% | — |

**Gate NOT met**, and it is the closest this project has come. The optimiser is the first
estimated policy here to make money on average, and it captures roughly **twice** what the
achievable alternative does. But 58% is not distinguishable from a coin flip on 45 draws,
and it beats doing nothing on only 44%. D-023 again: a good mean with an unreliable draw.

**The finding that is actually worth selling.** `pilot-pick` agrees with the hindsight best
rung on **13%** of draws — barely better than the 17% a random guess among six rungs gives.
A small business running a six-arm pilot **cannot reliably identify which single offer is
best**, and gets a *negative* expected return at n=1000 by acting on it. Meanwhile the
hindsight uniform rung captures 73% of the oracle against the optimiser's 28%. So: **picking
the right default offer is worth far more than per-customer targeting, and it is the thing
small businesses are least able to do for themselves.** That is a smaller, cheaper and much
more defensible product than a targeting engine, and it points the go-to-market at offer
selection rather than personalisation (revising D-040/041's emphasis, not its ordering).

**Risk aversion did not help.** `lambda = 0` (risk-neutral expected value) dominated 0.5 and
1.0 on every size. Reported because it was swept rather than chosen, and because the
opposite is what the abstention thesis would have predicted.

**Not attempted here:** reason codes and the dashboard, so the phase gate ("an owner can act
without asking us") is not met on those grounds either, independently of the numbers.

---

## D-059 — Reason codes explain the decision, and admit when there is no reason

**Provenance.** Ported from RetainIQ (a sibling project of the author's) after a
head-to-head comparison. RetainIQ's version is SHAP over an XGBoost churn classifier,
producing "87% risk because days-since-purchase = 400". Two things were changed rather
than copied.

**1. It explains the decision, not the prediction.** "This customer has not bought in
400 days" is something the owner can already see; it does not tell them whether *doing
something* pays. So the explanation decomposes the money identity instead:

```
expected money  =  -delta_p * V  -  c
```

Every term is separately actionable — how much the offer moves this person, what keeping
them is worth, what the offer costs — and each implies a different response when it is
the binding constraint. The output also states **why this rung and not the next**, which
a risk score cannot express at all.

**2. The attribution is exact, and needs no dependency.** `tau_i = tau_0 + x_i'gamma` is
linear, and for a linear model the Shapley value of feature `j` is exactly
`gamma_j (x_ij - E[x_j])`. Features are standardised, so it is `gamma_j * xs_ij`. No
sampling, no background dataset, no approximation error, and no `shap` package —
invariant 7 keeps the core on numpy/scipy. A test asserts the rows sum to `tau_i - tau_0`.

`tau_0` is deliberately excluded from the attribution: "the offer works on people in
general" explains the policy, not the customer.

**Three honesty properties the SHAP-over-a-classifier pattern cannot express.**

- **"Nothing specific to this customer drives it."** When `sigma_gamma` collapses — the
  normal situation at these sample sizes — every contribution is near zero and the
  recommendation rests on the customer's *value* and the average effect. The explainer
  says exactly that instead of ranking three near-zero numbers and dressing them up.
  This is D-058's `corr(tau_hat, tau_true) = 0.13` surfaced at the point of use.
- **"Their profile argues against this."** When the top drivers sum the wrong way, the
  recommendation is being carried by value alone, and the text says so rather than
  listing three reasons that contradict the action. Caught by dogfooding: the first
  output read "here are three reasons this will not work, so do it".
- **Every recommendation carries D-058's reliability.** 58% [0.42, 0.72] is not
  distinguishable from chance, so a per-customer line reading "contact this customer, it
  will earn 340" would overclaim by exactly the margin this project has spent five
  phases refusing. `reliability_note` propagates to every treated customer and a test
  enforces it.

**Abstention now says which kind.** `Recommendation.budget_trimmed` separates "no offer
we can measure pays for itself here" from "the budget was spent on customers where it
earns more". These are a verdict about the customer and a verdict about the budget
respectively, and an owner told "no action" can act on the second (raise the budget) but
not the first.

**A direction bug found by reading the output.** The first implementation described every
driver as "higher than typical" regardless of the customer's actual value, because it
took the sign of the *contribution* and ignored the sign of the *feature*. Two
independent signs, conflated. Fixed, and pinned by a test that picks the customer
furthest below average and asserts the words say "lower".

**Phase 5's gate is still not met**: the dashboard is absent, and D-058's win rate is
unchanged by explaining it better. What this closes is the "without asking us" half —
the output is now legible to an owner without an analyst present.

---

## D-060 — RetainIQ compared: an independent replication of our leakage result

**What it is.** A sibling project by the same author — an e-commerce retention dashboard
on the Olist Brazilian marketplace dataset: RFM + K-Means segmentation, XGBoost churn
classifier, XGBoost CLV regressor, SHAP explanations, FastAPI + Next.js, deployed. Its
codebase was cloned and **its pipeline was run**, rather than reading its report, because
the report's numbers are the claim under examination.

**The finding, and it is ours as much as theirs.** RetainIQ's report headlines
**Accuracy 0.9987, F1 0.9992, ROC-AUC 1.0000**, describing the model as having "learned
the patterns flawlessly", with a footnote that "Recency acts as a near-perfect
deterministic feature". That footnote is the whole story: the label was "no purchase in
90 days" and `recency` is days since last purchase, so `recency >= 90` **is** the label.

Its commit `d513bc3` ("resolve feature leakage and implement OOT split") fixed this
correctly — features from before a cutoff, target after, recency measured to the cutoff.
**The report was never re-run.** Executing the current code gives:

| | reported | actual (current code) | trivial baseline |
|---|---|---|---|
| Accuracy | 0.9987 | **0.8676** | 0.9945 (always predict churn) |
| F1 | 0.9992 | **0.9290** | 0.9972 (always predict churn) |
| ROC-AUC | 1.0000 | **0.5434** | 0.5000 |
| churn rate | 80.2% | **99.4%** | — |

A constant "everyone churns" beats the trained model on both accuracy and F1.

**Why this matters to Keel.** It is an independent replication of P1 (0.603 correct vs
0.954 leaked) at larger magnitude — 0.543 vs 1.000 — on real data, by a different
pipeline, in a different vertical. Two projects, same trap, and in both cases the leaked
number was the one that looked like success. This is the strongest external evidence we
have that invariant 9 (`available_at` on every fact, `_visible` as the sole data path)
earns its cost, and it belongs in the paper's motivation: the failure is not hypothetical.

**A second lesson, which is about framing rather than leakage.** At a 99.4% base rate the
problem is degenerate — Olist is a *marketplace* with mostly one-time buyers, so churn is
latent and a binary 90-day label is the wrong construct entirely (Fader & Hardie). This
is exactly why Keel started with contractual subscriptions and deferred non-contractual
to Phase 7 behind a BTYD router. The comparison confirms that sequencing was right.

**What we took.** The reason-code layer (D-059), rebuilt rather than copied: theirs
explains a prediction with approximate SHAP over a classifier, ours explains a decision
with exact closed-form attribution over a linear CATE.

**What they have that we do not, and it is not nothing.** A deployed frontend, a live
API, Docker orchestration, RFM segmentation, and a CRM activation layer. Keel has 373
tests, CI and 60 decision entries, and **nothing a buyer can look at**. Their gate
("someone can use it") is met and ours is not; ours ("it demonstrably makes money") is
the harder one and is still open. Recorded because the comparison cuts both ways.

---

## D-061 — The dashboard is a file, and it leads with what it does not know

**Form: self-contained HTML, no server.** Same shape as the Churn Autopsy (D-035/036) --
inline CSS, inline SVG, no external requests. It can be emailed, opened offline, printed,
or put behind an unguessable URL, and none of that is a deployment. D-040 orders the
go-to-market by *trust required*, and a file someone opens asks for less than a login.

Rejected: Streamlit and Next.js. Both add a runtime, a build step and a hosting bill to a
project whose gate is still "does this make money", and invariant 7 keeps the core on
numpy/pandas/scipy. The plan said from the start that Streamlit would not survive a real
launch, so building on it now would be building something to throw away. RetainIQ's
deployed Next.js stack (D-060) is the counter-example worth respecting -- it is genuinely
more impressive to look at -- but it is also the part of that project that is cheapest to
rebuild later, and the part we would have to rebuild anyway.

**The design decision that matters: the reliability banner is first, above the
recommendations, and there is no argument that removes it.** The conventional retention
dashboard leads with a large red number -- "92.4% churn risk, SAVE NOW" -- and puts model
accuracy in a methodology tab if anywhere. We measured a sibling product doing exactly
that on top of ROC-AUC 0.543 (D-060). The failure there is not that a number is wrong; it
is that the page is arranged so nobody asks. So D-058's "58% of tests, CI [0.42, 0.72],
not distinguishable from a coin flip" sits at the top in the same weight as the headline,
and a test asserts it precedes the recommendation table.

**Weak rows are marked in the table, not inside the collapsed detail.** Found by looking
at the rendered page rather than the tests: the top-ranked recommendations included a 40%
discount costing ~1,972 at a **47%** chance of paying. That is a coin flip on a four-digit
spend, and it ranked fourth because the list sorts by expected value, which is correct and
also exactly why the uncertainty cannot be one click further away than the money it
qualifies. Rows below 60% now carry an inline warning.

**Both kinds of "no" are reported separately.** "No offer we can measure pays for itself
here" is a verdict about the customer and more budget will not change it; "the budget ran
out" is a verdict about the budget and raising it would. Collapsing them into one number
would make the largest group on the page unactionable.

**What it deliberately does not do.** No webhooks, no "fire discount to Klaviyo" button.
Phase 6 is the holdout and incrementality infrastructure, and wiring automated sends
before the thing that measures whether they worked is how a retention product becomes
unfalsifiable. The page ends by saying the randomised holdout must stay in place.

**Phase 5's gate is now met on its own terms** -- an owner can read the page and act
without us present -- and this changes none of the evidence. The optimiser still beats a
single well-chosen offer on 58% of draws. A better-presented recommendation is not a
better recommendation, and the banner exists to stop the page implying otherwise.

---

## D-062 — The delivery path was the blocker, not the modelling

**Context.** Phase 2's gate is a paying client, and CLAUDE.md has said for six checkpoints
that it is a sales task. That was true and also an excuse: there was **no command that
turned a business's export into a report**. The Autopsy was reachable only from Python,
against simulator output. Prospect number one would have failed before any conversation
about retention happened.

**Tested against a realistic Stripe dashboard export rather than assumed.** Four separate
failures, in order:

1. **`Created (UTC)` matched nothing.** Every Stripe export carries parenthetical timezone
   suffixes; the normaliser lowercased and swapped separators but kept `(utc)`. Fixed by
   stripping parentheticals.
2. **`id` on the subscriptions file loaded as `customer_id`.** A bare `id` was a global
   alias for `customer_id`, so subscription ids went into the customer column and the load
   then failed two steps later claiming `subscription_id` was missing. Resolution is now
   table-aware: `id` means the key of the entity the file is about.
3. **`Email` beat the real id column.** `email` is a plausible customer identifier and sat
   earlier in the alias list, so it won; every subscription then referenced a customer that
   did not exist. The table's own key now tries `id` **first**.
4. **Required columns a real export simply lacks** (`plan`, `interval`, `attempt_number`).
   Filled from `SAFE_DEFAULTS`, each one recorded rather than applied silently.

**The split that governs the defaults.** A missing *label* costs nothing to invent -- no
decision follows from a plan's name. A missing *measurement* must never be invented
quietly. `interval` is the case that matters: assuming monthly on an annual book
overstates MRR twelvefold, so its recorded note is deliberately alarming and the CLI
exposes `--interval` to set it explicitly.

**`keel/ingest/preflight.py` exists because of how this engagement actually fails.** Not a
crash -- a crash is recoverable and honest. It is a confident report with the client's own
revenue wrong in it, found by the client. The check that motivates the module:

> **Stripe exports amounts in minor units.** `Plan Amount = 2900` is $29.00. Loaded as
> MRR it makes every figure in the report 100x too large -- including "churn costs you X
> per year", which is the number the engagement is sold on. Nothing downstream can detect
> it, because 100x of a plausible number is still a plausible number.

That is **D-057 in a different costume**: a units error, self-consistent everywhere,
invisible to every test. It has now happened once inside our own decision rule and once at
the front door. The difference is that this one would have been printed on a document with
a prospect's name on it.

The heuristic requires two signals (implausible median *and* every value a whole number)
and **never converts** -- it blocks and makes a human answer. Silently dividing by 100
would be the same failure mode it exists to catch. `autopsy` re-runs the checks and refuses
to render on a blocker; `--force` exists and is recorded.

Other checks: end-before-start dates, under six months of history, zero cancellations,
over 90% ended (an export already filtered to churned accounts), free-tier records
inflating the denominator, and sample size below the 250 where our own benchmarks show
nothing beating a population average -- phrased so the operator knows a *report* is still
honest at that size and a *model* is not.

**A check was deleted for being unreachable.** Duplicate keys are rejected by
`Dataset.validate` during load, so a preflight check for them could never fire on the real
path. A safety net that cannot catch anything is worse than none, because it implies
coverage that does not exist. The test now pins the guard where it actually lives.

**`docs/SALES-RUNBOOK.md`** records the non-code half: who to approach, the two-line ask,
the data-protection precondition, and -- most importantly -- a table of things that must
**not** be claimed, each tied to the experiment that forbids it. D-058's 58% is in it.
Building the delivery path made it easier to oversell, so the constraints were written
down at the same time.

**The gate is still open.** This removed the reasons it would fail for engineering
reasons. Nobody has paid anything.

---

## D-063 — A test that passed locally and failed on every CI Python

**Symptom.** `test_razorpay_epoch_seconds_are_parsed_not_read_as_nanoseconds` failed on
3.11, 3.12 and 3.13 in CI while passing locally, with dates landing on
`1970-01-01 00:00:00.001683158`.

**Cause: the fixture, not the code.** It built epoch seconds as
`index.astype("int64") // 10**9`, which assumes the index has **nanosecond** resolution.
pandas 2 may give it microsecond resolution instead, in which case the expression is off
by a thousand and yields `1683158` where `1683158400` was intended. Local pandas 2.3.3
returns `datetime64[ns]`; CI's returns microseconds.

**The production code did exactly the right thing.** `1683158` is outside the 1990–2050
epoch window, so `_to_datetime` declined to treat it as a timestamp and fell through to
ordinary parsing — which is the designed behaviour, and the reason this was a broken test
rather than silent data corruption. The preflight backstop then blocks the resulting
pre-1990 dates, so nothing could have reached a client report.

Fixed with `index.astype("datetime64[s]").astype("int64")`, which is correct at ns, µs,
ms and s resolution; the old form is correct only at ns. A new test pins the behaviour CI
accidentally demonstrated: an integer a thousand times too small must **not** be silently
rescaled into a plausible date, and preflight must block it.

**Third instance of the same lesson** (D-052, D-012): roughly half the failing tests in
this project have been the test rather than the code. Worth noting what made this one
hard to see — it was not merely wrong, it was wrong *only in another environment*, so a
green local run carried no information about it. The general form is that any test
asserting on a derived timestamp is asserting on a pandas resolution default unless it
says otherwise.

---

## D-064 — A nearly-free actuator does not change the answer; it sharpens it

**Question.** Should Keel drive automated outreach — LLM-written email, AI voice calls —
so that retention runs without a human? The commercial argument is cost per contact: a
human check-in call costs ~6 units of staff time, an AI call ~0.5, so make twelve times
as many.

**The premise is correct and the conclusion does not follow.** Cost per contact is not
what causes the harm. Phase 0's founding result is that contacting a dormant payer can
*itself* trigger the cancellation, which is why every rung carries a
`salience_multiplier`. Making contact cheaper leaves salience untouched.

We do not know an AI voice call's salience — nothing here measures it, and it would take a
live experiment on real customers. So it was **swept** rather than assumed (D-055
discipline), and the break-even reported.

| channel | cost | salience | mean tau | harmed | treat-all per customer | oracle treats |
|---|---|---|---|---|---|---|
| human check-in call | 6.00 | 0.55 | −0.0048 | 27% | **+3.97** | 40% |
| AI email | 0.02 | 0.35 | −0.0023 | 30% | **+5.41** | 70% |
| AI voice, matched salience | 0.50 | 0.55 | −0.0012 | 34% | **+5.31** | 62% |
| AI voice | 0.50 | 1.00 | +0.0111 | 55% | **−4.93** | 42% |
| AI voice | 0.50 | 2.00 | +0.0503 | 76% | **−38.09** | 22% |
| AI voice | 0.50 | 3.00 | +0.1046 | 84% | **−85.92** | 14% |

**Break-even salience: 0.80.**

Three findings, in order of importance.

**1. The break-even sits *below* neutral.** A channel merely as intrusive as a standard
retention offer (salience 1.0) already destroys value when used on everyone. For mass AI
calling to pay, an unsolicited synthetic voice would have to be **less** intrusive than a
generic retention email. That is not plausible.

**2. The automation argument is valid on its own terms, and that is why it is dangerous.**
At *matched* salience the AI call does beat the human one — 5.31 against 3.97, at a
twelfth of the cost. The case fails on a parameter nobody in the pitch is measuring, which
is precisely how it gets adopted.

**3. Cheap actuators make selection matter more, not less.** As salience rises the oracle's
treat share collapses from 70% to 14%. A free channel removes the felt *need* to choose
whom to contact at exactly the moment choosing correctly becomes most valuable. That
inversion is the whole argument against "just send it to everyone, it costs nothing".

**AI is not the problem; intrusiveness is.** AI email at salience 0.35 remains the
strongest channel in the table. The finding is about channel, not about who writes the
copy.

**Architectural consequence, and it is a hard line.** If Keel drives an actuator, the
actuator must never decide *who*, *whether*, or *how much*. Keel decides those; the model
writes wording inside a template and a cap. Letting a generative model choose recipients
discards every result this project established, and letting it choose discount depth
re-opens the personalised-pricing exposure that D-039 and plan §13.2 rule out.

**Not built, deliberately.** Phase 6 (holdout and incrementality infrastructure) comes
first. Wiring an automated sender before the thing that measures whether sending worked is
how a retention product becomes unfalsifiable — and with a voice channel it is also how it
becomes a regulatory incident. See `docs/AUTOMATION.md` for the integration design and the
legal constraints that gate it.
