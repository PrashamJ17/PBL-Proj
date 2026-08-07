# 09 — Status and roadmap

**This document is updated as the project progresses. Everything else in this folder is
relatively stable; this is the living record.**

**Last updated:** Phase 1 complete, plus first external validation on real data.

---

## Where we are in one line

**The founding claim has been tested and survived, and the data plumbing that keeps
future results honest is built. Nothing has been sold to a real customer yet.**

---

## What is actually done

| | Status | Evidence |
|---|---|---|
| **The core claim tested** | ✅ Done | Standard approach loses money, 6/6 runs — [05](05-the-evidence.md) |
| **Realistic business simulator** | ✅ Done | Calibrated to published benchmarks, stable across 8 variations |
| **Connecting to real billing data** | ✅ Done | Stripe and CSV adapters; one common data shape |
| **Guard against using future information** | ✅ Done | Measured: prevents a 0.35 inflation in apparent accuracy |
| **Quality controls** | ✅ Done | 137 automated tests, all passing |
| **Written record** | ✅ Done | Every decision and its reasoning documented |
| Failed-payment recovery | ⬜ Not started | — |
| Production prediction models | ⬜ Not started | — |
| **The practical version of our method** | ⬜ Not started | **The main research risk** |
| Customer-facing product | ⬜ Not started | — |
| Proof with a real business | ⬜ Not started | — |
| Paying customers | ⬜ **None** | — |

**Six rows of twelve.** But note *which* six: everything complete so far is
groundwork and evidence. Nothing yet earns anyone money.

---

## What Phase 1 was about, in plain terms

There is a failure mode in this field that ruins projects quietly. A model is
accidentally given information that would not have existed at the moment it had to make
its prediction — for example, counting a customer's activity across their *whole*
history, including months after the decision point. The model then looks superb in
testing and fails completely in real use.

It is dangerous precisely because it makes results look **better**. Nobody investigates
a number that improved.

Phase 1 built machinery that makes this structurally impossible, and then **measured
what it is worth**. The same features, computed correctly and incorrectly:

| how the features were built | apparent accuracy |
|---|---|
| Correctly | **0.60** |
| Ignoring reporting delays (subtle error) | 0.61 |
| With no time filter at all (common error) | **0.95** |

That 0.95 is a mirage. A business shown that number would reasonably conclude the
system works almost perfectly, and would allocate a retention budget accordingly.

We also built the connections to real billing systems, so the work from here runs on the
same data shape a real customer would provide.

---

## The plan, in order

Each phase has a **gate** — a condition that must be met before moving on. Gates exist to
force early failure rather than late failure.

| Phase | What | Gate | Status |
|---|---|---|---|
| **0** | **Build the simulator; test the founding claim** | Standard approach provably loses money | ✅ **Passed** |
| **1** | **Connect to real billing data; guard against using future information** | Automated checks pass | ✅ **Passed** |
| **2** | **Failed-payment recovery** | **First paying client** | ⬜ **Next** |
| **3** | Prediction models for who leaves and what they're worth | Beat established methods on public data | ⬜ |
| **4** | **The practical version of our method** | Beat existing approaches on money earned, at small scale | ⬜ |
| **5** | Decision engine, plain-language explanations, dashboard | An owner can act without asking us | ⬜ |
| **6** | Control-group infrastructure; proof-of-results reporting | **A real client's verified return** | ⬜ |
| **7** | Cross-business learning; retail support | Client #10 outperforms client #1 on day one | ⬜ |

### Why revenue comes at Phase 2, before the clever work

Failed-payment recovery is 20–40% of all churn, needs almost no sophisticated technology,
and produces money immediately. Putting it early:

- funds the research,
- earns the billing integration everything else depends on,
- and — most importantly — **generates the evidence about what interventions actually do
  that Phase 4 cannot exist without.**

This ordering is deliberate. A project that built the sophisticated method first would
have no data to fit it with.

---

## The three research papers

| # | Subject | Depends on | Status |
|---|---|---|---|
| 1 | The simulator as a shared benchmark for the research community | Phase 0 | ⬜ Ready to draft |
| 2 | **Estimating causal effects reliably with very little data** | Phase 4 | ⬜ The core contribution |
| 3 | Choosing interventions under a budget, with real client results | Phase 6 | ⬜ |

Paper 1 is writable now. Paper 2 is the one that matters, and it is gated on the hardest
technical problem in the project.

---

## Next immediate steps

1. **Phase 2 — failed-payment recovery.** The first thing that earns money. It is 20–40%
   of all churn, needs almost no sophisticated technology, and produces immediately
   attributable revenue.
2. **Draft paper 1** while the Phase 0 results are fresh.
3. **In parallel, start talking to businesses.** Twenty conversations with subscription
   founders will reshape this plan more than twenty more pages of it. This does not
   depend on the product existing.

---

## What would tell you this is going well

Concrete, checkable signals — in order of how much they should update your confidence:

| Signal | What it proves |
|---|---|
| Paying client from failed-payment recovery | Someone will pay us for something |
| Our method beats simple rules on **real** data at small scale | **The central research claim survives reality** |
| A client accepts a held-back control group | The business model works |
| A verified return figure from a real business | Everything |

The second row is the decisive one. Everything else is commercial execution; that row is
whether the idea is true outside a simulation.

---

## What would tell you to stop

From [07](07-risks-and-limitations.md), the falsifiable conditions:

- Real-world sleeping dogs turn out to be negligible.
- **Our method cannot beat simple rules on real data at small scale.** ← the one to watch
- A payment processor ships a competent free version.
- Clients refuse to allow control groups.

---

## Change log

Entries are appended as work completes. Older entries are never edited.

### External validation — first real-data test

Tested our central claim against a real 64,000-customer randomised email experiment
(Hillstrom, 2008) rather than our own simulation. Results in
[05](05-the-evidence.md).

**One claim was confirmed, one was corrected, and one new finding emerged.**

Confirmed: targeting by estimated *effect* beats targeting by *likelihood of responding*.

Corrected: our "worse than random" result did **not** replicate. We diagnosed why rather
than explaining it away — that dataset contains no customers whom the email harms, so
being worse than random is structurally impossible there. The claim is now stated with
its scope condition attached: it requires a harmed group resembling the people a model
ranks highest, which is a feature of subscription retention and not of promotional email.

New, and the most important result so far: **below roughly 2,000 customers, conventional
methods are unreliable.** At 500 customers the best method beats random on only 75% of
attempts; one estimator managed 55%. Average performance looks fine, which is precisely
how a small business ends up deploying something that does nothing. This is the
strongest evidence yet for our abstention approach, and it comes from real data.

### Phase 1 — complete

Built the connections to real billing systems (Stripe, and plain CSV exports for
businesses that would rather email a file than connect an account), and translated
everything into one common shape so nothing downstream needs to know where data came
from.

The substantive work was preventing a specific, quiet failure: giving a model
information that would not have existed when it had to predict. We made that
structurally impossible rather than a matter of care, then **measured what it is
worth** — computing the same features incorrectly inflated apparent accuracy from 0.60
to 0.95.

Two things worth noting about how this was verified. First, the safeguard is enforced in
a single place that all features must pass through, so a feature that bypasses it cannot
be written. Second, the leak *detector* is itself tested adversarially: we plant known
leaks and require it to catch them. A detector that has never caught anything might be
working, or might be checking nothing — there is no way to tell from a passing run.

79 new automated tests (137 total).

### Phase 0 — complete

Built a calibrated simulation of a small subscription business that, unlike real data,
contains the answer to "what would have happened if we hadn't contacted this customer?"

Tested the founding claim and **it survived under deliberately unfavourable conditions**.
Notably: our first result was *too favourable* and we rejected it, reconfiguring so that
the average effect of contacting customers is beneficial — making our own claim harder to
demonstrate. It held anyway.

Three findings emerged, one stronger than predicted:

1. Churn-score targeting is **worse than random targeting** (6/6 runs).
2. **Restraint beat ranking** — contacting 209 customers earned more than contacting 718.
3. **A more accurate churn model can reduce profit**, because accuracy at detecting
   disengagement means precision at finding sleeping dogs.

58 automated tests in place, including checks that prevent the models from cheating and
that verify the mechanism is wired correctly in both directions.

---

*Maintained alongside the project. For technical detail see `docs/BUILDLOG.md`; for the
reasoning behind each choice see `docs/DECISIONS.md`.*
