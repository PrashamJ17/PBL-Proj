# 09 — Status and roadmap

**This document is updated as the project progresses. Everything else in this folder is
relatively stable; this is the living record.**

**Last updated:** Phase 0 complete.

---

## Where we are in one line

**The founding claim has been tested and survived. Nothing has been built for real
customers yet.**

---

## What is actually done

| | Status | Evidence |
|---|---|---|
| **The core claim tested** | ✅ Done | Standard approach loses money, 6/6 runs — [05](05-the-evidence.md) |
| **Realistic business simulator** | ✅ Done | Calibrated to published benchmarks, stable across 8 variations |
| **Quality controls** | ✅ Done | 58 automated tests, all passing |
| **Written record** | ✅ Done | Every decision and its reasoning documented |
| Connecting to real billing data | ⬜ Not started | — |
| Failed-payment recovery | ⬜ Not started | — |
| Production prediction models | ⬜ Not started | — |
| **The practical version of our method** | ⬜ Not started | **The main research risk** |
| Customer-facing product | ⬜ Not started | — |
| Proof with a real business | ⬜ Not started | — |
| Paying customers | ⬜ **None** | — |

**Read that table honestly: one row of nine is complete.** It happens to be the row that
determines whether the other eight are worth doing.

---

## The plan, in order

Each phase has a **gate** — a condition that must be met before moving on. Gates exist to
force early failure rather than late failure.

| Phase | What | Gate | Status |
|---|---|---|---|
| **0** | **Build the simulator; test the founding claim** | Standard approach provably loses money | ✅ **Passed** |
| **1** | Connect to real billing data; guard against using future information | Automated checks pass | ⬜ Next |
| **2** | **Failed-payment recovery** | **First paying client** | ⬜ |
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

1. **Phase 1** — connect to real billing data, build the safeguards against using
   future information.
2. **Draft paper 1** while Phase 0 results are fresh.
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
