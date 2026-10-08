# Pre-registration — the correlation checks, and the Lemmens & Gupta baseline

**Written on 8 October 2026, before either experiment was implemented or run.** Committed on
its own, ahead of the code, so the history shows the predictions preceded the results. The
form follows `docs/PREREG-phase5.md`.

D-068 recorded two things as owed before the paper can make its claims: checks on the
correlation result, and Lemmens & Gupta's (2020) method as a baseline against the abstention
rule. Both are comparisons in which the project's own method or its own favourite quantity
is on one side. That is the situation in which a design chosen after seeing results is
worth nothing, so the design and the predictions are fixed here.

---

## Part A — the correlation checks

### What is checked, and how

For each public experiment (Hillstrom men, Hillstrom women, Criteo, Lenta), **30 random
splits** of the same sample `spectrum.py` uses, seeds 0 to 29. On each split, fitted on the
training half and scored on the test half:

1. **Two correlation coefficients:** Pearson and Spearman.
2. **Two scales:** probability (the effect is `p1 − p0`, the risk is `p`), and log-odds (the
   effect is `logit p1 − logit p0`, the risk is `logit p`). Probabilities are clipped to
   [0.0001, 0.9999] before taking logits.
3. **Three definitions of risk:**
   - *pooled*: an outcome model fitted on both arms, as `spectrum.py` does now;
   - *control, same data*: the outcome model fitted on control customers only, which is
     Ascarza's (2018) definition and is the T-learner's own control model;
   - *control, independent*: the control-only model fitted on one half of the training
     data and the T-learner on the other half, so the two share no estimation noise.
4. **The advantage of the best uplift model over the best outcome model**, as
   `spectrum.measure` computes it, without the bootstrap.

Every figure is reported as its mean over the 30 splits with the 2.5th and 97.5th
percentiles across splits.

**The simulator, like for like.** A simulated population large enough to be comparable with
Hillstrom (60,000 customers, 24 months, seed 7; decision month 6, horizon 6), treatment
assigned at random with probability one half, outcome observed for the assigned arm only,
and the same pipeline as above over 30 splits. Beside it, the correlation between the
**true** benefit and the **true** untreated risk, on both scales. The oracle figure
(+106.9%) is reported next to the fitted one and is not replaced by it.

### Predictions

| # | Prediction | Refuted if |
|---|---|---|
| **A1** | Pearson and Spearman have the same sign in every real setting, on the probability scale with pooled risk | the signs differ in any setting |
| **A2** | Risk fitted on control with the *same* data as the T-learner gives a lower correlation than pooled risk in every setting, because the two share the control model's noise with opposite sign. Fitted *independently*, it returns to within 0.10 of the pooled value | the same-data figure is not lower, or the independent one stays more than 0.10 away |
| **A3** | On the log-odds scale the Pearson correlation is **lower** than on the probability scale in all four real settings. Part of the positive correlation is the mechanical link Ascarza warns of: a constant log-odds effect is a larger probability effect where the baseline is higher | it is not lower in at least three of the four |
| **A4** | The two high-correlation settings (Hillstrom men, Criteo) and the two low ones (Hillstrom women, Lenta) remain separated: the split-to-split intervals of the correlation do not overlap between the groups. The intervals of the *advantage* overlap across all four | the correlation intervals overlap between groups, or the advantage intervals separate |
| **A5** | In the simulator, the fitted correlation between estimated benefit and estimated churn risk is negative, and the fitted uplift model's advantage over the churn score is positive but **well below** the oracle's +106.9% | the fitted correlation is not negative, or the fitted advantage is within a quarter of the oracle's |

**A3 is the one that can hurt.** If the correlation in the positive settings is mostly a
property of the probability scale, then "where the correlation is high the uplift model does
not pay" is partly a statement about arithmetic. **A5 is the one that decides what the figure
is allowed to show**: if a fitted model in the simulator gains little, the hollow point is an
upper bound that nothing approaches, and it should be described that way.

---

## Part B — Lemmens & Gupta (2020) as a baseline

### Their method, as read from the authors' manuscript

Three stages on three samples. **Estimation** on a calibration sample: a first-stage uplift
estimate of the effect on retention is turned into an expected profit lift for each
customer, and a second model is fitted to those profit lifts by stochastic gradient boosting
with a profit-based loss (their Equation 7), each customer weighted by the size of their
expected profit lift. **Target size** on a validation sample: customers are ranked by the
model's score, and for every campaign size S the campaign's profit is estimated from the
randomised validation data as S times the difference, among the top S, between the mean net
outcome of the treated and the mean outcome of the controls (their Equations 8 and 9). The
size with the highest estimated profit is chosen. **Evaluation** on a test sample.

### How it is run here

The abstention experiment's draws are reused unchanged: the same simulated business, the
same pilot (the training half, treatment randomised), the same test half scored against
true potential outcomes, the same budget cap of 30%. Sizes 250, 500, 1,000, 2,000 and 4,000.
**100 draws per size** (seeds 1000 to 1099), so that win rates carry intervals (D-072).

**Their rule gets the pilot and nothing else, as ours does.** It must split the pilot into a
calibration part and a validation part; ours fits on all of it. That difference is the
comparison, not an unfairness in it.

**Primary configuration, fixed now:**

- calibration and validation are equal halves of the pilot, which is their ratio;
- the model fitted on the calibration half scores the test customers, as in their protocol;
- the estimator is a re-implementation of their profit-based loss with symmetric weights;
- the chosen fraction `S*/N` of the validation sample is the fraction of test customers
  targeted, from the top of the ranking, capped at the 30% budget.

**Departures from their paper, all stated:**

- The first stage is a T-learner with gradient boosting, not an uplift random forest.
- Cash flow is the simulator's customer value, known for each customer, not estimated by
  nearest neighbours.
- Expected profit lifts are divided by their standard deviation before the second stage is
  fitted, for numerical stability. Their rule uses only the ranking, which this preserves.
- **S = 0 is allowed**, with profit zero. Their enumeration runs from 1. Allowing zero is in
  their favour: it lets their rule decline to act, which ours can.
- A campaign size is considered only if at least **10** treated and 10 control customers
  fall in the top S. Below that the estimate is noise and a maximum over sizes would pick
  it. This is also in their favour.

**Secondary configurations**, reported separately and labelled:

- *Same estimator, their stopping rule*: the Bayesian posterior mean used as the ranking
  score, with their validated cutoff. Against abstention this isolates the stopping rule.
- *Their stopping rule, a plain estimator*: the first-stage uplift estimate turned into a
  profit lift, with no second stage. Against the primary this isolates their loss.
- *Their best case*: a 2:1 calibration-to-validation split, and the model refitted on the
  whole pilot after the fraction is chosen. If any variant of their method is going to
  beat abstention at these sizes it is this one, and it will be reported as theirs.

### Predictions

| # | Prediction | Refuted if |
|---|---|---|
| **B1** | No policy beats doing nothing on more than half the draws at any size. The oracle treats 5.8% of customers; no estimator changes that | any policy does |
| **B2** | Their validated cutoff chooses "treat nobody" **less often** than abstention does, and so treats more customers on average at n ≤ 1,000. The maximum of a noisy profit curve over many sizes is biased upward | it chooses zero at least as often, or treats fewer |
| **B3** | Abstention's mean realised value is at least that of their primary configuration at n ≤ 1,000, and over all draws on which the two differ, abstention is ahead on more than half | their primary has the higher mean at n ≤ 1,000, or abstention is ahead on half or fewer |
| **B4** | The gap closes with size: the difference in mean realised value at n = 4,000 is smaller in magnitude than at n = 500 | it is not |
| **B5** | With the estimator held fixed (the Bayesian mean), the posterior threshold does at least as well as the validated cutoff at n ≤ 1,000 | the validated cutoff has the higher mean |
| **B6** | Under their cutoff, the profit-based loss and the plain uplift estimate cannot be told apart at these sizes: the share of differing draws on which the profit-based loss is ahead has an interval containing one half | the interval excludes one half in either direction |

**B3 is the one that matters, and it can fail.** Their method is published, validated on two
real studies, and designed for exactly this decision. If it beats abstention here, the
paper's fourth claim is gone and that is what will be reported. **Their best case is run so
that a failure of B3 cannot be hidden behind a weak configuration of their method.**

Ties are reported separately from wins and losses in every comparison. A draw on which both
rules treat nobody is a tie, and counting it for either side would invent a result.
