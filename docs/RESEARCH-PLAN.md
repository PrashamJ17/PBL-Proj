# Research plan: learning it, publishing it, protecting it

Written 10 August 2026. **§2 revised 5 October 2026** after the prior work was read in
full (D-068); §1 gained one reading-list row and one question, and §3 item 5 was
corrected. Three separate questions that get confused with each other:

1. **How do I understand this well enough to defend it?** (§1)
2. **How do I turn it into a paper with real value?** (§2)
3. **Should I patent it?** (§3)

The honest short answers: §1 is four to six weeks of real work and is the prerequisite for
everything else. §2 has a short list of checks and one hard addition that separate
"publishable" from "worth citing". §3 is almost certainly **no**, for reasons that are worth understanding rather
than taking on faith — but the decision is time-sensitive and reversible only in one
direction, so read §3 before publishing anything.

---

# §1 — Understanding the project

## Why this comes first

You did not write most of this code, and pretending otherwise would be both wrong and
trivially exposed. What you *can* legitimately own is the understanding: what the results
mean, why the design choices are what they are, and where the whole thing breaks. That is
also the only thing that survives a technical question from a prospect, a reviewer, or a
viva examiner.

The test is not "can I read the code". It is: **can I explain, without notes, why each
result is what it is, and what would change it?**

## Prerequisites: the maths you actually need

Not a degree's worth. Six things, in dependency order.

### 1. Potential outcomes (the Rubin causal model) — 2 days

`Y_i(0)` and `Y_i(1)`: what happens to customer *i* if you leave them alone, and if you
treat them. `τ_i = Y_i(1) - Y_i(0)`.

**The fundamental problem of causal inference:** you never observe both. Every causal
method is a strategy for coping with that. Randomisation works because it makes treatment
independent of the potential outcomes, so group averages are comparable.

*Read:* Imbens & Rubin, *Causal Inference for Statistics, Social and Biomedical Sciences*,
chapters 1–3. Or Hernán & Robins, *What If*, chapters 1–3 (free online) — shorter and
enough.

*In this repo:* `retainiq/sim/counterfactual.py`. The simulator's entire reason for existing
is that it can give you **both** potential outcomes, which no real dataset can. Understand
`potential_outcomes()` and what common random numbers buy you.

### 2. Why CATE is harder than propensity — 1 day

`π(x) = E[Y|X=x]` is a conditional mean. `τ(x) = E[Y(1)-Y(0)|X=x]` is a *difference* of
two conditional means, so its variance is roughly the sum of theirs. That single fact is
why uplift modelling is unreliable at small *n* and is the spine of the paper's argument.

*In this repo:* this is the argument of paper §3 and §6, and the reason for D-023.

### 3. Log-odds versus probability — half a day, and do not skip it

`logit(p) = log(p/(1-p))`. A logistic regression coefficient is a shift in log-odds, not
in probability. Converting: `Δp = expit(logit(p₀) + τ) − p₀`, and
`∂(Δp)/∂τ ≈ p₀(1−p₀)`.

**This is D-057.** Multiplying a log-odds τ by money as though it were a probability
inflated the benefit by `1/(p₀(1−p₀))` — four times at `p₀ = 0.5`, twenty-five times at
`p₀ = 0.05` — and it ran for an entire phase because every test was self-consistent.

*Exercise, by hand, no code:* a customer with `p₀ = 0.25` receives an offer worth `τ =
−0.8` in log-odds. What is the change in churn probability? Now do it for `p₀ = 0.03`. If
you cannot do this on paper, you cannot defend the most interesting thing in the project.

### 4. Survival analysis and censoring — 3 days

A customer who has not churned *yet* is not a negative example; they are **censored**.
Treating them as negatives biases everything, which is why the project uses discrete-time
hazard models rather than a binary classifier.

Understand: hazard `h(t) = P(churn at t | survived to t)`, the survival function
`S(t) = Π(1−h)`, Kaplan–Meier, and why calibration matters more than discrimination when
you are going to multiply a probability by money.

*Read:* Kleinbaum & Klein, *Survival Analysis: A Self-Learning Text*, chapters 1–3.
*In this repo:* `retainiq/models/survival/discrete.py`, and D-046/050 on why extrapolation
past observed support raises rather than guesses.

### 5. Bayesian shrinkage and partial pooling — 3 days

Prior, likelihood, posterior. Why a hierarchical prior on the heterogeneity scale
`σ_γ` makes small-*n* estimation survivable: when heterogeneity is not identifiable, the
marginal likelihood drives `σ_γ → 0` and the model degrades gracefully into "estimate one
average effect well" instead of "estimate 500 individual effects badly."

Then: the Laplace approximation (a Gaussian at the posterior mode) and why it was
validated against NUTS rather than trusted (D-053).

*Read:* Gelman et al., *Bayesian Data Analysis*, chapter 5 (hierarchical models) — the
eight-schools example is exactly this mechanism. McElreath's *Statistical Rethinking*
chapter 13 is gentler and just as good.

*In this repo:* `retainiq/models/uplift/bayesian.py`.

### 6. Decision theory, and why a win rate is not a mean — 1 day

Expected value, and why **a business gets one draw**. A policy with a good average and a
wide spread is a gamble. D-023 reports the proportion of draws on which a method beats
random, not the average improvement, and that choice is load-bearing throughout.

Also: break-even. Treating pays iff `−τ_i · V_i > c_i`, so the break-even effect is
`c_i / V_i`. **Derive this yourself and then compute it for the reference offer** (median
cost 33, median CLV 770). You should get ≈ 0.043 against a delivered mean effect of 0.010,
which is the entire explanation for why Phase 4 failed.

## Reading order in this repository

Do not start with the code.

| Order | What | Why |
|---|---|---|
| 1 | `explainer/00`–`09` | Written for a reader with no background. Gets you the shape in an evening. |
| 2 | `CLAUDE.md` — thesis and the 14 invariants | Each invariant is a mistake someone can make. Learn what breaks without it. |
| 3 | `docs/DECISIONS.md`, selectively | The *why*. Start with **D-002, D-011, D-013, D-020, D-023, D-026, D-031, D-054, D-055, D-057, D-058, D-060, D-068**. |
| 4 | `papers/paper1/main.tex` | Now the argument will read as familiar rather than new. |
| 5 | `retainiq/sim/counterfactual.py` → `models/uplift/bayesian.py` → `policy/economics.py` | The three files that carry the intellectual content. |
| 6 | `docs/BUILDLOG.md` | What was built and tested, in order. Skim. |
| 7 | The four papers in D-068, in full, appendices included | A claim is only as good as your knowledge of what was already shown. D-068 exists because this step was skipped; the correlation this project led with is in an appendix of the paper it cited. |

## Exercises that prove you understand it

Reading is not evidence. Each of these produces something checkable.

1. **Predict before you run.** Open `retainiq/sim/config.py`, pick one coefficient, write down
   which direction the churn rate will move and roughly how much, then run
   `make calibrate`. Being wrong is the useful outcome — find out why.
2. **Re-derive break-even by hand**, then verify against `make sensitivity`.
3. **Do the log-odds conversion on paper** for `p₀ ∈ {0.5, 0.25, 0.05}` and reproduce the
   `1/(p₀(1−p₀))` inflation factor. This is D-057 from first principles.
4. **Break something on purpose.** Delete the `available_at` filter in
   `retainiq/core/features.py` and watch the leakage suite fail. Now you know what invariant 9
   is *for*, rather than that it exists.
5. **Re-run the kill test** (`make killtest`) and explain each number in the output to
   somebody who has not seen it.
6. **Write the counter-argument.** One page: the strongest honest case that this project's
   central claim is wrong or unimportant. If you cannot write it, you do not yet
   understand the claim well enough to defend it.

## The six questions to answer without notes

The bar for talking to anyone about this:

1. Why does a churn score point at the wrong money? (the 21% decile overlap; value ≠ risk)
2. What is a sleeping dog, and why does contacting one cost money?
3. Why does the report refuse to predict who will churn?
4. What is the cents check, and why does it block instead of dividing by 100?
5. What did you get wrong, and how did you find out? (D-057)
6. What had Ascarza (2018) already shown, and what exactly do you add? (D-068)

Question 6 is the one a specialist asks first, and "we measured it on small samples; she
set it in a simulation" is a complete answer. Question 5 is the one that earns credibility. A student who says *"I found a units bug in
my own decision rule that every test missed, here is how"* is more believable than one who
says everything works.

**Realistic budget: four to six weeks part-time.** There is no shortcut, and attempting
the paper or a sales call before this is done is how you get exposed.

---

# §2 — The paper

*This section first led with `corr(τ, π)` as a "governing quantity". That quantity is
Ascarza's (2018, Web Appendix A3.4), so the ranking below changed on 5 October 2026.*

## What is genuinely valuable here

Four things, in order:

1. **How small a pilot can be.** Ascarza (2018) names pilot size as an open question, and
   none of the four papers in D-068 fits a model on fewer than about 700 customers.
   D-023 holds the evaluation set fixed, shrinks only the training set, and reports the
   win rate over draws instead of the mean: 72.5% of 200 draws at *n* = 500, interval
   66% to 79% (D-072). A business gets one draw,
   so the win rate is the number it needs.
2. **The measurement floor at small-business scale.** Break-even effect 0.040 against a
   delivered 0.010 (D-055), and a holdout that cannot detect the delivered effect even at
   10,000 customers (D-065). The published studies work at 25–62% churn, or with tens of
   thousands of customers.
3. **The correlation measured on real experiments.** Not the idea; the measurement. It
   includes two settings where the uplift model gains nothing or loses, and **an
   out-of-sample prediction that landed** (Lenta, D-031). Predicting before seeing data is
   rare in applied ML papers and reviewers notice.
4. **Honest negatives with mechanism.** The abstention rule beats ranking and does not
   beat doing nothing (D-054); the target was unachievable as set (D-055); a units bug sat
   in our own decision rule for a whole phase (D-057). Papers that report why their method
   did not work are rarer and more useful than papers that do not.

## What is weak, stated plainly

- **The strongest claim rests on one dataset that is not retention data.** The 72.5% figure
  is Hillstrom, an email promotion.
- **The correlation result is weaker than the paper says, and now measured (D-074).** Over
  thirty splits the four real settings cannot be ordered, the figure quoted for Hillstrom
  men was the highest split of thirty, and most of the positive correlation is absent on
  the log-odds scale. What survives: fitted models recover the simulator's result on a
  simulated trial of 60,000, with no oracle. The negative-correlation regime is still
  carried entirely by a simulator configured to have it. A reviewer will say this, and
  they will be right.
- **Against the nearest rival, abstention is ahead only from about 1,000 customers
  (D-075).** Lemmens & Gupta's rule was re-implemented and run on the same pilots. At 250
  and 500 abstention is not ahead, and doing nothing beats both at every size. The
  paper's claim about abstention at small sizes has to be rewritten to this.
- **The small-sample result is measured, not derived.** There is no theory saying *when*
  an outcome model overtakes an uplift model, only evidence that it does.
- **The abstention contribution is a partial negative.** Defensible, but it is not the
  headline the abstract would like.

## The highest-value additions, in order

**1. The checks in D-068. DONE, 8 October 2026 (D-074).** `make correlation-checks`. Five
predictions were written first; one held, one held against the project, one failed and
two failed in part. The result shrank under its own checks and is still reportable. One
check is left: risk fitted on both arms of customers the effect model never saw, which
would say whether the drop under an independent risk model is shared noise or only less
data.

**2. The baseline. DONE, 8 October 2026 (D-075).** `make baseline`. Six predictions were
written first; two failed and two hold only pooled. Estimator and stopping rule were
crossed as planned: with the estimator held fixed the threshold beats their cutoff from
1,000 customers and not below, and their loss cannot be told from their first stage
alone. Read both entries before restating any claim. **What they leave open is a better
question than either answered:** the abstention rule made money on 25 of the 139 draws on
which it acted. Why it is wrong so often when it does act is now the thing to explain.

**3. Derive the finite-sample condition, do not only measure it.**

The population statement is settled and is not the interesting one: with the true effect
known, ranking by it cannot lose, which is Ascarza's result. The open question is about
*estimates*. Take the simplest model where both rankings are tractable — her own appendix
model, a threshold on `X − Z·offer + noise` with `(X, Z)` bivariate normal, is the
natural start — and derive when targeting on `τ̂` fitted from *n* customers beats
targeting on `π̂` under a budget constraint. Even a result of the form *"the outcome
model wins when `corr(τ, π) > f(n, budget, noise)`"* in a toy model would transform the
paper: the small-sample evidence stops being a curiosity and becomes confirmation of
something derived.

This is a genuinely hard piece of work, it is the right hard piece, and it is what
separates a paper people cite from one they skim. It is also the part that must be yours —
a derivation you cannot reproduce at a whiteboard is worse than no derivation.

After those: **more settings**, above all a real *retention* experiment, since none of
the public ones is; and **a new pre-registered prediction** on a dataset not yet
obtained, following the Lenta pattern exactly.

## Venue

- **A preprint first.** Done: the paper is public on Zenodo (D-066). That was the
  irreversible step §3 warns about.
- Then, in order of fit: **European Journal of Operational Research**, **Decision Support
  Systems**, or **Journal of Marketing Analytics**.
- **Not** *Journal of Marketing Research*. Ascarza (2018) is there, marketing journals
  want field experiments on real customers, and you have none. That is not a failing of
  the work; it is a mismatch of evidence type to venue.
- **Workshops are a good intermediate step** and are underused by students: a causal-ML
  workshop gives you referee feedback in weeks instead of months, with no prejudice to a
  later journal submission.

## Order of work

1. Finish §1, the four papers included. Do not write about what you cannot explain.
2. ~~Run the checks in D-068 and add the baseline.~~ Done (D-074, D-075). Read what moved:
   most of it did.
3. Restate the claims around what survived. Write the related-work section from your own
   notes on the papers, not from this repository's summaries of them.
4. Attempt the derivation. Time-box it — four weeks. If it does not come, say so in
   Limitations; an honest "we could not derive this" is a legitimate contribution to the
   next person.
5. Re-read the paper end to end against `docs/DECISIONS.md` and check every number is
   current. §8 numbers post-date the D-057 correction; anything restored from an older
   revision is wrong.
6. Have someone hostile read it. Your mentor, ideally. Ask specifically: *what is the
   weakest claim here?*
7. §3 is already settled by publication (D-066). Then the venue.

## What must not happen to this paper

Do not soften the negative results to make it more attractive. §8.1, §8.2 and the refuted
minimax hypothesis (D-056) are the parts a good referee will respect, and a paper that
reports only wins from a simulator its authors built is one a good referee will not
believe. `papers/paper1/README.md` records this; it is there to be obeyed later, when the
temptation arrives.

---

# §3 — Patents and IP

**I am not a lawyer and this is not legal advice.** It is an honest reading of the
landscape so you can decide whether to spend money on professional advice. If you want to
proceed, the person you need is a **registered Indian patent agent** with software
experience.

## The time-sensitive part, first

**The repository is private and the paper is unpublished. Nothing has been disclosed
yet.** That matters because:

- **India and the EPO require absolute novelty.** Any public disclosure before filing
  destroys patentability — no grace period. Posting to arXiv, making the repo public, or
  demonstrating to a prospect without an NDA all count.
- **The US allows a 12-month grace period** for the inventor's own disclosure, so a US
  provisional remains possible for a year after you publish.

So the sequence is forced: **decide about filing before you publish, not after.** It is
the one decision here that cannot be reversed.

## Why I think the answer is no

**1. Section 3(k) of the Indian Patents Act** excludes "a mathematical method or a
business method or a computer programme *per se* or algorithms" from patentability. This
project is a statistical method, embodied in software, applied to a business decision. It
is all three of the excluded categories at once. The 2017 CRI Guidelines ask for a
*technical contribution* — improved hardware functioning, a technical effect beyond the
normal running of a program. "Choose which customers get a discount, more profitably" is
not that.

**2. The US position is not better.** Under *Alice/Mayo*, a claim to an abstract idea —
mathematical concepts, methods of organising human activity — needs an inventive concept
beyond "apply it on a computer". A method of selecting customers for retention offers sits
very close to the fact pattern *Alice* itself rejected.

**3. The cost is real and the timeline is long.** An Indian software patent with competent
attorney support runs to lakhs and takes years, with examination odds against you on 3(k).
For a student with no revenue, that is a poor allocation of both.

**4. It would not protect the thing that matters.** Your own plan says the moat is
cross-tenant priors — a data network effect, not an algorithm. A competitor cannot
replicate that from a published method. Meanwhile a patent would require you to *disclose*
the method in full, which is precisely the opposite of protecting it.

**5. Most of the value is in results, and results are not patentable at all.** "Uplift
modelling is unreliable on a pilot of 500 customers" and "a small business cannot detect
its own campaign's effect" are discoveries. No jurisdiction patents those. They are
protected by being *first and cited*, which is what publication does. Two results this
item used to name — that churn-score targeting loses money, and that the risk–lift
correlation explains when uplift pays — are not first (D-068). That is a further reason a
patent over them would fail: they are prior art.

## What to do instead

| Mechanism | Applies to | Action |
|---|---|---|
| **Copyright** | The code, automatically, on creation | Nothing to file. Add a `LICENSE` — the choice matters, see below. |
| **Defensive publication** | The method | Publishing prevents anyone else patenting it. This is a real strategy, not a consolation. |
| **Trade secret** | Cross-tenant priors, client data | The actual moat. Never publish the fitted priors; keep client data under DPA. |
| **Trademark** | The product name | Only once there is a business worth naming. Cheap, later. |
| **Contracts** | Client relationships | The DPA and engagement terms do more real protection than a patent would. |

**On the licence, and think about it before publishing.** MIT or Apache-2.0 maximises
citation and adoption, which is what an academic asset needs. AGPL prevents a competitor
running your code as a hosted service without contributing back. Apache-2.0 also includes
an express patent grant, which is worth understanding before you choose. If a commercial
future matters, consider keeping the simulator and benchmarks open — they are the
citeable artefact — and the cross-tenant machinery closed.

## If you want to pursue it anyway

Reasonable, and here is how to do it without wasting money:

1. Ask a registered patent agent one narrow question: *is there a system claim here with a
   technical effect that could survive 3(k)?* Expect a short paid consultation, not a
   filing. Most will tell you in an hour.
2. If they see a path, a **US provisional** is the cheap option — it establishes a priority
   date for twelve months at low cost, buying time to decide. Note it does not rescue
   India/EPO if you have already published.
3. **Do not publish or make the repo public until this is resolved.** Once you do, India
   and Europe are closed permanently.

## My recommendation

Publish. Do not file.

The asset is the finding, the instrument, and eventually the cross-tenant data — none of
which a patent protects and the first two of which publication protects better. Spend the
money and months on §1 and on the derivation in §2 instead. If this becomes a real
business with revenue and a defensible data moat, revisit trademark and trade-secret
protection then, with a lawyer and a budget.

---

## Sequence, end to end

| Weeks | What | Gate |
|---|---|---|
| 1–4 | §1: prerequisites, reading order, the four papers, exercises | Answer the six questions without notes |
| 3–5 | Write the counter-argument; re-read the paper against DECISIONS | You can state the weakest claim in your own paper |
| done | The checks in D-068 and the Lemmens & Gupta baseline (§2) | Met: D-074 and D-075 give each check a number and say what moved |
| 6–10 | Attempt the derivation (§2). Time-boxed | Either a toy-model result, or an honest Limitations paragraph |
| done | The IP question (§3) and the preprint | Settled by publication (D-066) |
| after | Revised paper to a journal; workshop in parallel | Referee feedback |

Weeks count from the start of the revision, not from the date this plan was first written.

**Run outreach in parallel throughout.** It is not sequenced after the research — a single
paying client changes both the paper (a real ROI number) and the business, and it is the
only gate no amount of study will open.
