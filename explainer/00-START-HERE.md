# Start here

**These documents assume you know nothing about this field.** No statistics, no machine
learning, no subscription-business jargon. Every technical term is explained the first
time it appears, and there is a [glossary](08-glossary.md) at the end.

---

## The project in ninety seconds

Businesses that charge you every month — Netflix, a gym, a software company — live or
die by one number: how many customers leave each month. Losing 5% of customers monthly
means losing **46% of your customer base in a year**. For a small business that is
often fatal.

So companies try to predict who is about to leave, and send those people a discount to
stay. This is a large industry. Nearly every business tool sells some version of it.

**It doesn't work, and we can now show precisely why.**

Predicting *who will leave* is a different question from knowing *who you can help* —
and treating them as the same question is not merely wasteful, it actively destroys
money. Some customers cancel **because you contacted them**. You reminded a person who
had forgotten they were paying you.

We built a system that answers the second question instead: **who should we actually
help, with what, at what cost — and when should we do nothing at all?**

We have proven the core claim in simulation. A retention campaign targeted the standard
way loses money, and loses *more than targeting customers completely at random*. Our
approach turns that same budget profitable. See [the evidence](05-the-evidence.md).

---

## What to read, depending on who you are

| You are | Read, in order | Time |
|---|---|---|
| **An academic evaluator** | 01 → 02 → 03 → 05 → 07 | ~35 min |
| **An investor** | 01 → 03 → 06 → 05 → 07 | ~35 min |
| **Technical reviewer** | 03 → 04 → 05, then `docs/DECISIONS.md` | ~30 min |
| **In a hurry** | 03 alone — it is the whole idea | ~8 min |

**If you read only one document, read [03 — The core insight](03-the-core-insight.md).**
Everything else is consequence.

---

## The documents

| # | Document | What it answers |
|---|---|---|
| 01 | [The problem](01-the-problem.md) | What is churn, why does it destroy businesses, how big is this |
| 02 | [How the big companies do it](02-how-the-big-companies-do-it.md) | What Netflix, Spotify, Amazon and telecoms actually do — and where they are weak |
| 03 | **[The core insight](03-the-core-insight.md)** | **Why predicting who leaves is the wrong question** |
| 04 | [What we are building](04-what-we-are-building.md) | The product and how it works, in plain language |
| 05 | [The evidence](05-the-evidence.md) | What we have proven so far, and why you should believe it |
| 06 | [The business case](06-the-business-case.md) | Market, competitors, pricing, defensibility |
| 07 | [Risks and limitations](07-risks-and-limitations.md) | What could go wrong and what we have *not* proven |
| 08 | [Glossary](08-glossary.md) | Every term, defined plainly |
| 09 | [Status and roadmap](09-status-and-roadmap.md) | Where we are today, what comes next |

---

## Three things to hold onto

**1. The industry is solving the wrong problem.** Nearly every churn tool ranks
customers by likelihood of leaving. That ranking is not just unhelpful for deciding who
to contact — we measured it to be *worse than random*.

**2. The hardest part is not the prediction.** It is deciding what to do, proving it
worked, and doing both when you only have a few hundred customers to learn from. That
is where every existing tool stops and where our work begins.

**3. We are deliberately trying to disprove ourselves.** Several design decisions in
this project make our own claim *harder* to demonstrate, not easier — documented in
[07](07-risks-and-limitations.md). A result that only holds under flattering
assumptions is not a result.

---

## Honest statement of status

We have a **calibrated simulation** and a **result proven within it**. We do **not** yet
have paying customers or real-world validation. [Document 09](09-status-and-roadmap.md)
is precise about what is done and what is not, and
[07](07-risks-and-limitations.md) is precise about what could still go wrong.

Please treat anything not explicitly claimed in 05 or 09 as not yet demonstrated.
