# Research plan: learning it, publishing it, protecting it

Written 10 August 2026. Three separate questions that get confused with each other:

1. **How do I understand this well enough to defend it?** (§1)
2. **How do I turn it into a paper with real value?** (§2)
3. **Should I patent it?** (§3)

The honest short answers: §1 is four to six weeks of real work and is the prerequisite for
everything else. §2 has one specific gap that separates "publishable" from "worth
citing". §3 is almost certainly **no**, for reasons that are worth understanding rather
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

*In this repo:* `keel/sim/counterfactual.py`. The simulator's entire reason for existing
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
*In this repo:* `keel/models/survival/discrete.py`, and D-046/050 on why extrapolation
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

*In this repo:* `keel/models/uplift/bayesian.py`.

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
| 2 | `CLAUDE.md` — thesis and the 13 invariants | Each invariant is a mistake someone can make. Learn what breaks without it. |
| 3 | `docs/DECISIONS.md`, selectively | The *why*. Start with **D-002, D-011, D-013, D-020, D-023, D-026, D-031, D-054, D-055, D-057, D-058, D-060**. |
| 4 | `papers/paper1/main.tex` | Now the argument will read as familiar rather than new. |
| 5 | `keel/sim/counterfactual.py` → `models/uplift/bayesian.py` → `policy/economics.py` | The three files that carry the intellectual content. |
| 6 | `docs/BUILDLOG.md` | What was built and tested, in order. Skim. |

## Exercises that prove you understand it

Reading is not evidence. Each of these produces something checkable.

1. **Predict before you run.** Open `keel/sim/config.py`, pick one coefficient, write down
   which direction the churn rate will move and roughly how much, then run
   `make calibrate`. Being wrong is the useful outcome — find out why.
2. **Re-derive break-even by hand**, then verify against `make sensitivity`.
3. **Do the log-odds conversion on paper** for `p₀ ∈ {0.5, 0.25, 0.05}` and reproduce the
   `1/(p₀(1−p₀))` inflation factor. This is D-057 from first principles.
4. **Break something on purpose.** Delete the `available_at` filter in
   `keel/core/features.py` and watch the leakage suite fail. Now you know what invariant 9
   is *for*, rather than that it exists.
5. **Re-run the kill test** (`make killtest`) and explain each number in the output to
   somebody who has not seen it.
6. **Write the counter-argument.** One page: the strongest honest case that this project's
   central claim is wrong or unimportant. If you cannot write it, you do not yet
   understand the claim well enough to defend it.

## The five questions to answer without notes

The bar for talking to anyone about this:

1. Why does a churn score point at the wrong money? (the 21% decile overlap; value ≠ risk)
2. What is a sleeping dog, and why does contacting one cost money?
3. Why does the report refuse to predict who will churn?
4. What is the cents check, and why does it block instead of dividing by 100?
5. What did you get wrong, and how did you find out? (D-057)

Question 5 is the one that earns credibility. A student who says *"I found a units bug in
my own decision rule that every test missed, here is how"* is more believable than one who
says everything works.

**Realistic budget: four to six weeks part-time.** There is no shortcut, and attempting
the paper or a sales call before this is done is how you get exposed.

---

# §2 — The paper

## What is genuinely valuable here

Three things, in order:

1. **`corr(τ, π)` as a governing quantity**, with a mechanism, ordering five settings —
   and, crucially, **an out-of-sample prediction that landed** (Lenta, D-031). Predicting
   before seeing data is rare in applied ML papers and reviewers notice.
2. **Reliability rather than expectation at small *n***: win rate over draws, not mean
   improvement, holding the evaluation set fixed while shrinking only training.
3. **Honest negatives with mechanism.** The Phase 4 gate failed; §8.1 shows it was
   unachievable as written; §8.2 reports a units bug in the authors' own rule. Papers that
   report why their method did not work are rarer and more useful than papers that do not.

## What is weak, stated plainly

- **Four settings is thin for a "governing quantity" claim.** Three real RCTs plus one
  simulator, and the negative-correlation regime — the interesting one — is carried
  entirely by the simulator. A reviewer will say this, and they will be right.
- **The correlation is measured, not derived.** There is no theory saying *why* this
  quantity governs, only evidence that it does.
- **The abstention contribution is a partial negative.** Defensible, but it is not the
  headline the abstract would like.

## The single highest-value addition

**Derive the condition, do not only measure it.**

Take the simplest model where both quantities are tractable — a logistic outcome with
Gaussian covariates, or even a two-point discrete covariate — and derive when
targeting on `τ̂` beats targeting on `π̂` under a budget constraint. Even a result of the
form *"effect-targeting dominates iff `corr(τ, π) < f(budget, noise)`"* in a toy model
would transform the paper: the empirical work stops being a curiosity and becomes
confirmation of something derived.

This is a genuinely hard piece of work, it is the right hard piece, and it is what
separates a paper people cite from one they skim. It is also the part that must be yours —
a derivation you cannot reproduce at a whiteboard is worse than no derivation.

Second and third priorities: **more settings** (each additional real RCT with a measurable
`corr` strengthens the ordering), and **a new pre-registered prediction** on a dataset not
yet obtained, following the Lenta pattern exactly.

## Venue

- **arXiv first** — but read §3 before posting. This is the irreversible step.
- Then, in order of fit: **European Journal of Operational Research**, **Decision Support
  Systems**, or **Journal of Marketing Analytics**.
- **Not** *Journal of Marketing Research*. Ascarza (2018) is there, marketing journals
  want field experiments on real customers, and you have none. That is not a failing of
  the work; it is a mismatch of evidence type to venue.
- **Workshops are a good intermediate step** and are underused by students: a causal-ML
  workshop gives you referee feedback in weeks instead of months, with no prejudice to a
  later journal submission.

## Order of work

1. Finish §1. Do not write about what you cannot explain.
2. Attempt the derivation (§2's highest-value item). Time-box it — four weeks. If it does
   not come, say so in Limitations and submit anyway; an honest "we could not derive this"
   is a legitimate contribution to the next person.
3. Re-read the paper end to end against `docs/DECISIONS.md` and check every number is
   current. §8 numbers post-date the D-057 correction; anything restored from an older
   revision is wrong.
4. Have someone hostile read it. Your mentor, ideally. Ask specifically: *what is the
   weakest claim here?*
5. Decide on §3. Then arXiv. Then the journal.

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

**5. Most of the value is in results, and results are not patentable at all.** "Churn-score
targeting loses money" and "`corr(τ, π)` governs when uplift pays" are discoveries. No
jurisdiction patents those. They are protected by being *first and cited*, which is what
publication does.

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
| 1–4 | §1: prerequisites, reading order, exercises | Answer the five questions without notes |
| 3–5 | Write the counter-argument; re-read the paper against DECISIONS | You can state the weakest claim in your own paper |
| 5–9 | Attempt the derivation (§2). Time-boxed | Either a toy-model result, or an honest Limitations paragraph |
| 9 | Decide the IP question (§3) | A decision, recorded, with reasons |
| 10 | arXiv, then licence the repo, then make it public | Preprint up |
| 10+ | Journal submission; workshop in parallel | Referee feedback |

**Run outreach in parallel throughout.** It is not sequenced after the research — a single
paying client changes both the paper (a real ROI number) and the business, and it is the
only gate no amount of study will open.
