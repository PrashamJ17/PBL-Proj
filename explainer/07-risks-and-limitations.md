# 07 — Risks and limitations

*This document exists to be adversarial toward our own project.*

A project that only presents its strengths has told you it has weaknesses it does not
want discussed. Everything below is stated because we would rather you evaluate it than
discover it.

---

## Part 1 — What we have not proven

**No real business has used this.** The central result in [05](05-the-evidence.md) comes
from a simulation. The simulation is calibrated to published benchmarks and deliberately
configured to make our claim harder, but it is still a model of reality, not reality. Our
tests on real data use public experiments from email, advertising and retail. **None of
them is a subscription business.**

**The size of the effect in the real world is unknown.** Published field experiments by
other researchers report that retention contact can make customers leave, and that the
riskiest customers are not the most responsive ([05](05-the-evidence.md)). So the
*direction* of the argument has support outside this project. We do not know whether real
businesses lose a little or a lot to this.

**Our headline comparison uses a perfect-knowledge version of our own method.** The
"contact only where it's worth it" row in [05](05-the-evidence.md) assumes the system
knows each customer's true responsiveness. It does not — that is what must be estimated
from data, and estimating it reliably from a few hundred customers is **the unsolved
research problem this project exists to address.** We have since built the version that
has to estimate it (Phase 4, in [09](09-status-and-roadmap.md)). It beats the standard
approach on 93% of runs and does **not** beat doing nothing. The prize exists in our
simulation; our method does not yet claim it.

**The share of sleeping dogs is our most consequential assumption.** We used 17%, chosen
to sit inside the range published literature supports. If a particular business has very
few, our advantage shrinks toward ordinary. The argument's direction holds at any
non-zero level, but its commercial value scales with this number, and it will vary by
industry.

**The picture of five results is not one measurement.** In [05](05-the-evidence.md), four
points are real experiments in which two fitted methods were compared. The fifth is our
simulator, set up so that risk and responsiveness pull apart, and it uses perfect knowledge
of each customer. It shows the most that could be gained, not what a real method gains.
The four real points are each one run with no margin of error, and their order is within
noise.

**We have not tested our method against the closest published one.** A 2020 study includes
its own rule for deciding how many customers to contact. Until ours is compared with it on
the same data, we cannot say ours is better.

**A small business cannot verify our results on its own data.** Our measurement work
(Phase 6, in [09](09-status-and-roadmap.md)) found that with offers of the size we tested,
detecting the effect takes roughly 120,000 customers. For a small client, an honest report
would say "somewhere between a loss and a gain".

**A technical caveat we disclose in our own notes:** the forward-looking portion of our
simulation is slightly less random than reality, which marginally understates
variability. This affects estimates of *uncertainty*, not of *direction*.

---

## Part 2 — Ways this could fail commercially

**Cold start — the most serious risk.**
The system needs evidence about what interventions actually cause. That evidence only
exists once someone runs properly controlled campaigns. Nobody lets an unproven system
experiment on their customers. This is genuinely circular, and it is why the plan starts
with paid diagnostic services rather than a software product.

**A payment processor could build this.**
Stripe and its peers have the data and the distribution. If one shipped a competent
version, it would be free and built-in. Our answer is to work *across* billing systems
and to own the accumulated causal evidence rather than the plumbing — but this is a
mitigation, not a defence.

**Small businesses are the hardest customers in software.**
Expensive to reach, reluctant to pay, and they go out of business. We will experience our
own product's problem.

**Distribution is the weak point, not technology.**
A founder without an existing network selling business software is attempting the
hardest go-to-market in the industry. Publishing research and giving away early
diagnostics are plans, not evidence.

**The core technique is not novel.**
Uplift modelling is roughly two decades old and well published, and so are the two ideas
we once described as ours: that targeting the riskiest customers can do harm, and that
methods should be judged by profit. Our contribution is narrower: measuring how these
methods behave at small scale (often unreliably), finding what a small business can and
cannot measure, and packaging the parts that do work for people without data teams. A
better-resourced team could replicate any of that.

---

## Part 3 — Ethical and legal boundaries

These are not compliance footnotes. Two of them constrain what the product is allowed to
do.

### Personalised pricing — a line we will not cross

There is a version of this technology that charges different customers different prices
based on a prediction of what each will tolerate. We will not build it.

| Acceptable | Not acceptable |
|---|---|
| Personalised **retention offers** to existing customers | Personalised **base prices** inferred from willingness to pay |
| Discounts on verifiable status (student, non-profit) | Discounts inferred from browsing behaviour or device |
| One published price everyone can see | Different headline prices for different people |

Why this matters beyond ethics: inferred personalised pricing attracts regulatory
attention, creates discrimination exposure the moment your data stands in for protected
characteristics, and has a documented history of public damage when discovered.

**Rules we build into the product:**

- Never use protected characteristics — **or anything that stands in for them.** A
  postcode can encode caste, religion, or race. Device type encodes income. These are
  audited, not assumed.
- Personalise the *offer*, never the published price.
- Log every decision and its reason, permanently.
- Cap discount depth; anything deeper requires a human to approve it.

### Dark patterns — the other line

There is a version of this product that makes cancelling difficult, buries the cancel
button, and exploits inattention. It works in the short term. Some competitors quietly
sell it.

We will not build it, for three reasons. It is wrong. Regulators are actively moving
against it. And it destroys the trust required to get access to customer data in the
first place.

The strategic argument is in [02](02-how-the-big-companies-do-it.md): **Netflix makes
cancelling easy and has among the lowest churn in the industry**, because easy
cancellation improves the odds a customer comes back.

### Privacy

We process other companies' customer data, which makes us legally a data processor with
specific obligations. Where relevant, European rules give people rights regarding
significant automated decisions, and India's data protection framework imposes consent
and purpose-limitation duties. Practical implications: proper agreements with every
client, explanations available for every decision, and strict purpose limitation. These
must be handled early because buyers will ask.

---

## Part 4 — Ways we could be fooling ourselves

Specific failure modes in this kind of work, and what we do about each.

**Tuning the simulation to flatter ourselves.**
The most likely way this project produces a wrong answer. Countermeasures: benchmark
targets set before tuning; the key parameter solved automatically rather than adjusted by
eye; results checked across eight random variations; and — the strongest evidence —
**we rejected our own first result for being too favourable** and reran under harder
conditions ([05](05-the-evidence.md)).

**Letting the model see the future.**
The most common failure in published churn work. A model that uses information only
available *after* the outcome looks brilliant and fails completely in production.
Countermeasure: every fact carries a timestamp of when it became knowable, enforced
automatically on every code change.

**Testing on data that overlaps with training data.**
Splitting customer records randomly leaks future information into the past. We split
strictly by time.

**Measuring the wrong thing.**
Standard accuracy scores can improve while profit falls — we demonstrate exactly this in
[05](05-the-evidence.md). Countermeasure: our primary measure is money earned under a
budget, not a statistical score.

**Believing our own campaigns worked.**
Once you act on predictions, your actions contaminate all future data. The only defence
is a permanently held-back group, which is why it is a core product feature rather than
an occasional study.

**Reporting the flattering number.**
"Save rate among contacted customers" always looks good and means nothing. We measure
against doing nothing, always.

**Claiming as ours what was already known.**
This one happened. For several months these documents described three published ideas as
our own findings, because the closest earlier studies had not been read in full before we
wrote. It was found by reading them, and corrected in October 2026
([09](09-status-and-roadmap.md)). Countermeasure: read the nearest prior work in full
before describing anything as new, and name in writing what each earlier study already
showed.

**Putting unlike things on one chart.**
This also happened: a perfect-knowledge result from our simulator was drawn beside four
real measurements as if it were a fifth. Countermeasure: every point on that chart now
records how it was measured, and automated checks stop a perfect-knowledge result from
being drawn or tabulated as a measured one.

---

## Part 5 — What would change our minds

Falsifiable conditions. If these occur, we should stop or change direction.

1. **Real-world sleeping dogs turn out to be negligible** (under ~3%) across several
   businesses. The advantage would shrink to ordinary optimisation.
2. **Small-sample estimation proves intractable** — if, at 300–1,000 customers, our
   method cannot beat simple rules on real data, the core research claim fails. This is
   the primary risk in Phase 4. *Where this stands:* on simulated data it beats the
   standard ranking rule and does not beat doing nothing. On real data it is untested.
3. **A payment processor ships a competent free version.** The window closes.
4. **Businesses refuse control groups.** If clients will not accept holding back 5–10% of
   customers, we cannot prove results, and the pricing model collapses. *Where this
   stands:* our own measurement work found a harder version of this problem. Even with a
   control group, one small business cannot detect an effect of the size we tested. Unless
   evidence can be combined across businesses, results-based pricing for voluntary churn
   does not work at small scale.
5. **Failed-payment recovery turns out to be the whole business.** Possible. It would be
   a smaller, simpler, less defensible company — and we should recognise it rather than
   subsidise research with it.

Condition 2 is the one to watch. It is the difference between a research contribution and
an interesting observation.

---

## The honest summary

We have evidence that the industry standard can lose money. It comes from our own
simulation, run under conditions we deliberately made unfavourable to ourselves, and it
agrees with field experiments other researchers have published. We have a design that
addresses the problem, and a business model whose failed-payment part the market already
accepts.

We have no customers and no real-world validation. The central technical problem —
making causal estimates reliable with very little data — remains unsolved: our method
avoids the standard approach's losses but does not make money. We have found that a small
business cannot measure these results on its own. Part of what we thought was new was
already published. The market is crowded, the buyers are difficult, and the largest
platforms could enter.

**This is an early-stage project with a premise that has outside support and execution
that is unvalidated.** Anyone evaluating it should weight the premise, and the execution
not at all yet.

---

**Next:** [08 — Glossary](08-glossary.md) or [09 — Status and roadmap](09-status-and-roadmap.md).
