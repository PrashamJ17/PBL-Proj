# Pre-registration — Phase 5 decision layer

**Written before any of the changes below were run.** Committed on its own, ahead of the
implementation commit, so the git history shows the predictions preceded the results.

D-056 required that the correction to the abstention rule be *specified before it is run*,
because the alternative — fix, re-run, then describe whatever happened as the intended
outcome — is unfalsifiable after the fact. Implementing that requirement produced a second
reason to write this down: the first change below is a **bug fix**, and "we fixed a bug and
our numbers improved" is the single easiest way to launder a result. Both corrections are
therefore stated with what they predict and what would refute them.

---

## Correction 1 — the decision rule multiplies log-odds by currency

### The defect

`HierarchicalCATE` fits `logit P(churn) = a + x'b + T(tau_0 + x'gamma)`, so `tau_i` is a
**log-odds ratio** (`bayesian.py` says so explicitly: "Posterior mean of tau_i on the
log-odds scale"). `AbstentionPolicy.decide` then computes

```
mean_benefit = -posterior.mean * value - cost
```

which is only meaningful if `tau_i` is a **difference in probability**. It is not. The rule
multiplies a log-odds ratio by a currency amount and compares the product to an offer cost.

Measured on one draw (n = 4000, seed 11, reference offer): the rule believes the mean
benefit of treating is **-104.5**; the true mean benefit is **+20.5**; the offer costs
**31.5**. The quantity being thresholded has no economic meaning.

The distortion is not a constant factor. For a baseline churn probability `p0`, a log-odds
shift `t` produces a probability change of `expit(logit(p0) + t) - p0`, whose ratio to `t`
is approximately `p0(1 - p0)`. So the overstatement is worst for **low-baseline-risk**
customers — the rule systematically inflates the apparent value of treating people who were
never going to leave. That is the Sure Thing quadrant, i.e. precisely the error this project
exists to characterise, reintroduced inside our own decision rule.

### The fix

Convert on the probability scale before touching money, using an estimated baseline risk:

```
delta_p_i = expit(logit(p0_i) + tau_i) - p0_i        # <= 0 when the offer helps
benefit_i = -delta_p_i * V_i - c_i
```

`p0_i` is the probability customer `i` churns over the decision horizon **if untreated**,
estimated from the control arm of the pilot (Phase 3's discrete-time hazard). It is not
available from ground truth in any production path, and `potential_outcomes` columns
(`p_churn_control`) are oracle-only and must not be used by a policy.

Because `delta_p` is a nonlinear function of `tau`, the posterior over `benefit` is no
longer Gaussian and the closed form is lost. It will be computed by sampling the mixture
posterior, and the resulting rule must still reduce to the point-estimate threshold as the
posterior concentrates (the existing test pins this).

### Predictions

| # | Prediction | Refuted if |
|---|---|---|
| **1a** | Estimated mean benefit lands on the same order as the true mean benefit (tens, not hundreds, and correctly signed on average) | it stays off by more than ~3x, or keeps the wrong sign |
| **1b** | The corrected rule treats **more** customers on cheap rungs (`feature_nudge`) and **fewer** on expensive ones (`discount_20_3mo`) than the buggy rule | the direction of either change reverses |
| **1c** | The gate still **fails** on `discount_20_3mo` — the rule does not beat do-nothing | it passes |
| **1d** | The gate **passes** on at least one cheap rung (`feature_nudge` or `checkin_call`): beats do-nothing on >50% of draws | no rung passes |

**1c is the important one.** The oracle ceiling — that only 5.8% of customers are worth
treating with the reference discount — was computed from ground-truth `tau_true` and is a
property of the simulator's economics, untouched by this bug. A correct fix therefore
*cannot* make the reference discount profitable. If it does, the fix is wrong, or the D-055
arithmetic is wrong, and the discrepancy must be resolved before anything is claimed.

**1d is the one that would rescue the phase.** It is a real prediction and it may fail:
the estimator's correlation with the true effect is only **0.13** on the diagnostic draw
above, and a decision rule cannot beat inaction using a signal it does not have. If 1d
fails, Phase 5's honest report is that the units bug was real, its repair was necessary,
and it was *not sufficient*.

---

## Correction 2 — alpha as a function of payoff asymmetry

### Status: conditional, and possibly unnecessary

D-056 concluded that a constant `alpha` is wrong by construction, from the observation that
the best `alpha` per rung moves from 0.49 (a 0.10 nudge) to 0.05 (a 33 discount).

**That evidence is now suspect.** With Correction 1's bug present, the benefit term is
inflated relative to cost by roughly `1 / (p0(1-p0))`, so the effective decision threshold
was already mis-scaled *per offer* — cheap offers barely affected, expensive offers badly
so. Tightening `alpha` on expensive rungs is exactly what compensates for that. The
observed `alpha` dependence may therefore be an artifact of Correction 1 rather than a
property of the rule.

### Predictions

| # | Prediction | Refuted if |
|---|---|---|
| **2a** | After Correction 1, the spread in best-`alpha` across rungs **shrinks** | it is unchanged or widens |
| **2b** | If 2a holds strongly (a single `alpha` within noise of the per-rung best on every rung), D-056's "constant alpha is wrong by construction" is **withdrawn as an artifact** and Correction 2 is not implemented | — |

This is written down now because the tempting move later is to implement Correction 2
regardless, since it was already announced. If the bug fix removes the phenomenon, the
correct action is to retract the claim, not to ship a fix for a problem that no longer
exists.

---

## What this does to already-published results

D-054, D-055 and D-056 report policy comparisons computed with Correction 1's bug present.
Per the update protocol, past entries are **never edited**; a superseding entry will state
precisely which findings survive:

- **Expected to survive** (computed from ground truth, no estimator involved): the
  break-even arithmetic (`|tau|` = 0.040 required vs 0.010 delivered), the 5.8% oracle
  ceiling, the per-rung economics of the ladder, and the sleeping-dog collapse under larger
  effect sizes.
- **Expected to need restating** (estimated policies): every win rate against do-nothing and
  against ranking, in D-054 and both axes of D-055; the regret matrix; and the per-rung
  `alpha` table underpinning D-056.
- **Unaffected**: Phases 0-3 entirely. The bug is in `retainiq/models/uplift/abstention.py`,
  which nothing before Phase 4 imports.

Paper section 8 and section 8.1 will be rewritten from the corrected numbers. The refuted
minimax-regret hypothesis (D-056) stays in the paper either way: it was refuted on data
computed the same way for every policy, and a withdrawn conjecture is worth keeping.
