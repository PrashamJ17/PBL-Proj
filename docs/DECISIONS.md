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
