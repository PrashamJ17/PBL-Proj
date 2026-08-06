# 07 — Risks and limitations

*This document exists to be adversarial toward our own project.*

A project that only presents its strengths has told you it has weaknesses it does not
want discussed. Everything below is stated because we would rather you evaluate it than
discover it.

---

## Part 1 — What we have not proven

**No real business has used this.** Every result in [05](05-the-evidence.md) comes from a
simulation. The simulation is calibrated to published benchmarks and deliberately
configured to make our claim harder, but it is still a model of reality, not reality.

**The size of the effect in the real world is unknown.** We know the *direction* of the
argument is right — contacting a disengaged customer can cause them to leave, and churn
models rank such customers highest. We do not know whether real businesses lose a little
or a lot to this.

**Our headline comparison uses a perfect-knowledge version of our own method.** The
"contact only where it's worth it" row in [05](05-the-evidence.md) assumes the system
knows each customer's true responsiveness. It does not — that is what must be estimated
from data, and estimating it reliably from a few hundred customers is **the unsolved
research problem this project exists to address.** We have proven the prize is real. We
have not yet built the thing that claims it.

**The share of sleeping dogs is our most consequential assumption.** We used 17%, chosen
to sit inside the range published literature supports. If a particular business has very
few, our advantage shrinks toward ordinary. The argument's direction holds at any
non-zero level, but its commercial value scales with this number, and it will vary by
industry.

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
Uplift modelling is roughly two decades old and well published. Our contribution is
making it work at small scale, packaging it for people without data teams, and proving
results in money. A better-resourced team could replicate any of that.

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

---

## Part 5 — What would change our minds

Falsifiable conditions. If these occur, we should stop or change direction.

1. **Real-world sleeping dogs turn out to be negligible** (under ~3%) across several
   businesses. The advantage would shrink to ordinary optimisation.
2. **Small-sample estimation proves intractable** — if, at 300–1,000 customers, our
   method cannot beat simple rules on real data, the core research claim fails. This is
   the primary risk in Phase 4.
3. **A payment processor ships a competent free version.** The window closes.
4. **Businesses refuse control groups.** If clients will not accept holding back 5–10% of
   customers, we cannot prove results, and the pricing model collapses.
5. **Failed-payment recovery turns out to be the whole business.** Possible. It would be
   a smaller, simpler, less defensible company — and we should recognise it rather than
   subsidise research with it.

Condition 2 is the one to watch. It is the difference between a research contribution and
an interesting observation.

---

## The honest summary

We have strong evidence that the industry standard is broken, obtained under conditions
we deliberately made unfavourable to ourselves. We have a coherent explanation for why,
a design that addresses it, and a business model the market already accepts in adjacent
form.

We have no customers, no real-world validation, and the central technical problem —
making causal estimates reliable with very little data — remains unsolved. The market is
crowded, the buyers are difficult, and the largest platforms could enter.

**This is an early-stage project with a validated premise and unvalidated execution.**
Anyone evaluating it should weight the premise highly and the execution not at all yet.

---

**Next:** [08 — Glossary](08-glossary.md) or [09 — Status and roadmap](09-status-and-roadmap.md).
