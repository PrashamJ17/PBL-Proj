# 04 — What we are building

*Assumes [03](03-the-core-insight.md).*

---

## In one sentence

A system that connects to a small subscription business's existing billing account,
works out which customers are worth intervening with, chooses the cheapest intervention
that will work, sends it through tools they already use, and **proves in money what it
earned.**

---

## The five layers

Think of it as a pipeline. Value concentrates in layers 3–5 — which is exactly where
every competing product stops.

```
1. CONNECT      Read data from where it already lives
       ↓
2. ORGANISE     Turn it into one clean, consistent shape
       ↓
3. UNDERSTAND   Who will leave · who can be helped · what they're worth
       ↓
4. DECIDE       Who to contact, with what, within budget  ← the differentiator
       ↓
5. ACT & PROVE  Send it · hold back a control group · report real earnings
```

---

### Layer 1 — Connect

The business connects their payment processor (Stripe first, then others). That single
connection provides who their customers are, what they pay, when payments failed, and
who has already left.

Optionally they connect product-usage data and support tickets, which improves accuracy.
But **the system must be useful from the billing connection alone**, because that is the
only integration most small businesses will complete. Anything requiring an engineer to
instrument their product will never be adopted.

This layer is unglamorous and it is where most such projects die.

---

### Layer 2 — Organise

Every business's data is shaped differently. This layer translates all of it into one
consistent structure: customers, subscriptions, invoices, usage events, support tickets,
and — importantly — **a record of every intervention we have ever sent**.

One rule governs this layer and it is worth stating precisely, because violating it is
the most common way projects like this produce impressive results that turn out to be
worthless:

> **Every fact carries a timestamp of when it became knowable, and a prediction may
> only use facts that were knowable before the prediction was made.**

This sounds obvious. It is violated constantly. Suppose you include the feature "opened a
support ticket about refunds". Your model will look superb — that ticket is a
*consequence* of deciding to leave, not a cause. Your model has learned to predict the
past. In production it collapses, because at the moment you need a prediction, that
ticket does not exist yet.

We enforce this automatically in our test suite. It is not a guideline.

---

### Layer 3 — Understand

Four models:

**Who is likely to leave, and when.** Not a simple yes/no prediction. We use **survival
analysis** — the branch of statistics developed for medical trials, which handles a
problem that ordinary prediction cannot: most of your customers **haven't left yet**.

That is not the same as "didn't leave". Someone who joined last month and is still here
tells you very little; someone who has been here four years tells you a lot. Treating
both as "did not churn" throws away most of your information and biases everything.
Survival analysis handles this properly and additionally answers *when*, which is what
tells you how urgent the situation is.

**Which failed payments can be recovered, and when to retry.** Separate model, separate
problem. Covered in [01](01-the-problem.md) — this is the fastest source of real money.

**What each customer is worth.** Expected future profit, so the system can judge whether
an intervention is worth its cost. Crucially this carries a **range, not a single
number** — with a few hundred customers, a confident point estimate is a fiction.

**Who our actions will actually change** — the uplift model of [03](03-the-core-insight.md).
This is the hard one and the research contribution.

**Plus plain-language explanations.** Not "feature importance 0.34", but *"This customer
has logged in three times fewer than last month, and four of their six licences are
unused. Similar customers who received an onboarding call stayed 61% of the time versus
34% without."* A small business owner has no analyst to translate for them.

---

### Layer 4 — Decide

The layer that makes this a product rather than a dashboard, and the one nobody else
builds.

Given a monthly budget, choose the set of customers and offers that **maximises expected
profit**, subject to real constraints: don't exceed budget, don't go below a margin
floor, don't contact the same person repeatedly, don't offer a deep discount without
approval — and **don't act at all when the evidence is too thin.**

The offer ladder, ordered by what it costs you:

| Rung | What we do | Cost to you | When |
|---|---|---|---|
| 0 | **Nothing** | Zero | Sleeping dog, or too uncertain to justify spending |
| 1 | Helpful nudge about an unused feature | ~Zero | They've only ever used part of the product |
| 2 | Check-in call | Staff time | High-value customer, struggling early |
| 3 | Temporarily unlock a feature | ~Zero | They've hit a limit on their plan |
| 4 | **Offer to pause** | Deferred, not lost | Seasonal or temporary budget pressure |
| 5 | **Offer a cheaper plan** | Some revenue | Price objection, low usage |
| 6 | Switch to annual with a small incentive | Discount, but locks in a year | Price-sensitive but committed |
| 7 | Time-limited discount | Direct margin | Genuinely persuadable, nothing above worked |
| 8 | Deeper discount | Heavy margin | Rare, requires explicit human approval |

**Rungs 0 to 5 are where the money is. Every competing product starts at rung 7.**

---

### Layer 5 — Act and prove

**Act:** we send nothing ourselves. We push decisions into the email, messaging, or CRM
tools the business already pays for. Being the *brain* rather than the *plumbing* means
lower adoption friction and no competing with commodity email providers on price.

**Prove:** this is the part that makes the business viable.

A randomly chosen 5–10% of eligible customers are **deliberately never contacted**, on
an ongoing basis. Comparing them against the customers we did contact gives the one
number that matters:

> *"This month we retained ₹340,000 in revenue that would otherwise have been lost. It
> cost ₹47,000 in offers. Here is the held-back group proving it."*

No competitor for small businesses can produce that sentence for voluntary churn,
because none of them hold back a control group.

---

## Why this compounds — and why a competitor can't simply copy it

This is the most important structural idea in the project.

```
   You MUST hold back a control group to learn what actually works
                          │
                          ▼
        That produces clean evidence of cause and effect
                    ╱               ╲
                   ▼                 ▼
        A provable ROI number      Training data for the model
                   │                        │
                   ▼                        │
        You can charge based on             │
        proven results — which              │
        removes the buyer's risk            │
                   │                        │
                   ▼                        │
             More customers  ───────────────┤
                   │                        ▼
                   │              Knowledge pooled across
                   │              ALL businesses using it
                   ▼                        │
        Business #41 gets good predictions ◄─┘
        on day one, because 40 similar
        businesses already taught the system
```

**The thing that makes the model work is the same thing that makes the sale.**

And the pooling is real, not marketing language. It is a specific statistical technique
(**hierarchical modelling**) in which each business's estimates are informed by the
pattern across all businesses. A new customer with 300 subscribers gets useful answers
immediately because forty similar businesses have already contributed.

A competitor can copy every line of our code and still not have that, because it is not
in the code. It is in the accumulated record of what worked, for whom, across many
businesses. That record only exists if you were disciplined enough to hold back control
groups from the very first customer.

---

## What it looks like to the customer

1. Connect your billing account. Ten minutes.
2. **We watch and predict, but do nothing, for 4–8 weeks.** We verify our predictions are
   accurate on *your* data before we are trusted with your customers.
3. We begin sending offers — deliberately varying them at first, because that is how the
   system learns what works for your business specifically.
4. Monthly: a report showing what we earned you, with the held-back group as proof.

Step 2 costs us two months of revenue per customer and we do it anyway. A retention
system that starts contacting customers before it has been validated on that business's
actual data is a liability, not a product.

---

**Next:** [05 — The evidence](05-the-evidence.md).
