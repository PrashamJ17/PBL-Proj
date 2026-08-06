# 03 — The core insight

**If you read one document, read this one. Everything else follows from it.**

*No prior knowledge assumed. No mathematics.*

---

## A story

You run a small software business. 1,000 customers, ₹500 a month each.

You build a churn model — a program that learns from customers who left in the past and
scores your current customers on how likely they are to leave. It works well. The
strongest pattern it finds is obvious in hindsight: **people who stop logging in are the
ones who leave.**

So it hands you a ranked list. At the very top is Priya. She hasn't logged in for two
months. The model says she is 85% likely to cancel.

You do the sensible thing. You email her:

> *"Hi Priya — we've noticed you haven't been around lately. Here's 20% off the next
> three months. We'd love to have you back!"*

Priya opens the email and thinks:

> *"Wait. I'm still paying for this?"*

**She cancels.**

She had forgotten. The ₹500 was going out every month and she had not noticed. She might
have kept paying for another two years without ever logging in. Your email cost you a
customer — and you paid to send it.

---

## This is not a rare edge case

Priya is not unusual. **She is exactly who the model ranks highest**, and that is the
problem.

The model's strongest signal is "stopped logging in". But "stopped logging in" describes
two completely different people:

- **Someone frustrated and about to leave.** Contacting them might genuinely help.
- **Someone who forgot they are paying you.** Contacting them is the *worst* thing you
  can do.

They look identical in the data. And a churn model, working exactly as designed, puts
**both** at the top of your list.

The industry has a name for the second type: **sleeping dogs.** As in, let them lie.

---

## The real question

The industry asks: **"Who is likely to leave?"**

The question that actually matters: **"Whose behaviour will my action change, and in
which direction?"**

These sound similar. They are completely different, and the gap between them is where
the money is.

An analogy that makes it obvious. Imagine you are a doctor with a drug and 100 patients.
You could give the drug to whoever *looks sickest*. But what you actually need to know is
who the drug *helps*. Some patients:

- get better because of the drug — **treat them**
- would have got better anyway — **don't waste the drug**
- won't get better either way — **the drug can't help**
- **are harmed by the drug** — treating them is malpractice

A doctor who dosed everyone who "looked sick" would harm the fourth group. That is
precisely what a churn score does.

---

## The four kinds of customer

Every customer falls into one of four boxes, defined by what happens *with* and
*without* your intervention:

|  | **Stays if you contact them** | **Leaves if you contact them** |
|---|---|---|
| **Stays if you don't** | 🟦 **Sure Thing**<br>Would have stayed anyway.<br>*Your discount is a pure giveaway.* | 🟥 **Sleeping Dog**<br>Contacting them **causes** them to leave.<br>*You paid to lose a customer.* |
| **Leaves if you don't** | 🟩 **Persuadable**<br>Your action genuinely saved them.<br>**The only group worth paying for.** | ⬛ **Lost Cause**<br>Leaving regardless.<br>*Their budget was cut. Nothing helps.* |

Only the green box makes you money. One box actively loses you money — twice over, since
you pay for the contact *and* lose the customer.

**A churn score cannot tell these apart.** It measures the *rows* of this table — how
likely someone is to leave if you do nothing. It says nothing about the *columns*, which
is the entire question.

---

## We measured it, and the result is worse than expected

We built a simulation of a subscription business (details in
[05](05-the-evidence.md)) where — unlike in real life — we know the true answer for every
customer: what they would do if contacted, *and* what they would do if left alone. Real
data can never contain both.

Then we ran the standard industry approach: train a good churn model, rank customers,
contact the top 20%.

**It lost money.** Every time, across every random variation we tried.

Then we compared it against contacting a *randomly chosen* 20% — no model, no data, just
picking names out of a hat.

**Random targeting lost less money than the churn model.** Every single time.

Read that again, because it is the finding this project is built on:

> **Using a good churn model to decide who to contact was worse than using no model at
> all.**

---

## Why — and this is the crux

Random targeting is merely *uninformed*. It picks up sleeping dogs at the same rate they
occur in the population — about 17% of customers, in our setup.

The churn model is **anti-informed**. It doesn't ignore sleeping dogs, it *seeks them
out*, because the thing that makes someone a sleeping dog — being disengaged and
inattentive — is also the strongest signal that they might leave.

Here is the measurement. We sorted customers by their predicted churn risk into ten
groups, then looked at what type they truly were:

- **Highest-risk group** (the ones you contact first): **48% sleeping dogs**
- **Lowest-risk group** (the ones you never contact): **2% sleeping dogs**

Nearly half the people at the top of your list are people you will harm by contacting.

**A better churn model makes this worse.** The more accurately it identifies
disengagement, the more precisely it locates sleeping dogs. Improving your model's
accuracy can *reduce* your profit. This is deeply counterintuitive and it is why the
problem has persisted — everyone is optimising a number that is pointing away from the
goal.

---

## What we do instead

Three changes, in increasing order of importance.

### 1. Estimate the *effect* of contacting, not the *risk* of leaving

Rather than "how likely is this person to leave", we estimate "**how much does
contacting this person change their behaviour, and in which direction?**" That number
can be positive (helps) or negative (harms). Sleeping dogs have it pointing the wrong
way, and are automatically excluded.

This technique is called **uplift modelling**. It was invented by telecom companies for
exactly this reason and it is well established — but it is nearly absent from tools that
small businesses can buy.

### 2. Weigh the money, not just the effect

Even a genuinely persuadable customer isn't worth saving at any price. A ₹300 discount to
retain a customer worth ₹200 is a loss. So for each person we compare:

> *(how much contacting them helps) × (how much they're worth) — (what the offer costs)*

Only act when that is positive.

We also insist on trying the **cheapest thing that could work first**. The industry
reaches for a discount immediately. A discount is the *most expensive* tool available.
Before it:

> do nothing → a helpful nudge → a check-in → unlock a feature → offer to **pause** →
> offer a **cheaper plan** → *only then*, a discount

A customer who pauses for two months and returns costs you nothing. A customer on a
cheaper plan is far better than a cancelled one. Most of the money is won in these
earlier rungs, and almost every competing product starts at the last one.

### 3. Know when to say nothing — and admit when you don't know

This is the part nobody else does, and it is the heart of the research contribution.

With only a few hundred customers, you often **cannot tell** whether contacting someone
will help or hurt. The honest answer is "we don't have enough evidence about this
person."

Every existing method produces a confident-looking number anyway. Ours produces a number
*and a measure of how uncertain it is* — and when the uncertainty is too large to justify
spending money, **it recommends doing nothing.**

That sounds like a limitation. It is the opposite. In our experiments, the strategy that
contacted **209 customers** made **more money** than the one that contacted **718** —
because the extra 509 contacts included people it was harming.

> **Knowing when not to act was worth more than being better at ranking.**

---

## Why this is hard, and therefore worth doing

If it were easy, the large companies would have shipped it. Two genuine obstacles:

**You cannot learn this from ordinary data.** To know whether contacting someone helps,
you need to see both what happened when you contacted them *and* what would have happened
if you hadn't. You only ever observe one. The only escape is to deliberately **not
contact a random group** and compare. Most companies won't do this — it feels like
leaving money on the table. It is actually the only way to know if you have any money on
the table at all.

**Small businesses have very little data.** Techniques that work on ten million telecom
subscribers fall apart on 600 customers. Making causal estimates reliable at that scale
is an unsolved research problem, and it is precisely the problem small businesses have.

That second obstacle is the whole project. It is simultaneously the research
contribution and the commercial opportunity, which is a rare and fortunate alignment.

---

## In one paragraph

Every churn tool answers "who is likely to leave?" That is the wrong question. The right
question is "whose behaviour will my action change, and is that change worth what it
costs?" Answering the wrong question is not merely unhelpful — we measured it to be
worse than acting at random, because the customers a churn model ranks highest are
disproportionately the ones an offer will drive away. We estimate the *effect* of acting
rather than the *risk* of leaving, weigh it against cost, try the cheapest effective
intervention first, and **abstain when the evidence is too thin** — which turns out to be
worth more than any improvement in ranking.

---

**Next:** [04 — What we are building](04-what-we-are-building.md) for the product, or
[05 — The evidence](05-the-evidence.md) for the proof.
