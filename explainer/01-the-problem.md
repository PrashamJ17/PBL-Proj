# 01 — The problem

*No prior knowledge assumed.*

---

## What is a subscription business?

A business you pay repeatedly rather than once. Netflix, Spotify, a gym membership,
Amazon Prime, the software your office uses, a monthly coffee delivery.

The economics are different from a shop. A shop makes its money at the moment of sale.
A subscription business makes almost nothing at the moment of sale — it usually *loses*
money acquiring you, and only becomes profitable if you stay long enough.

A concrete example. Say a small software company:

- spends **₹4,000** on advertising to win one customer
- charges that customer **₹500 per month**
- keeps **₹400** of that after costs

They are ₹4,000 down on day one. It takes **ten months** just to break even. Everything
after month ten is profit.

**So the entire business rests on one question: how long do customers stay?**

---

## What is churn?

**Churn** is a customer leaving. If you start the month with 1,000 customers and 50
cancel, your monthly churn rate is 5%.

That sounds small. It is not.

| Monthly churn | Customers left after 1 year | Average customer lifetime |
|---|---|---|
| 2% | 78% | ~4 years |
| 5% | **54%** | ~1 year 8 months |
| 8% | 37% | ~1 year |
| 10% | 28% | 10 months |

At 5% monthly churn, **you lose nearly half your customers every year**. You are
running up an escalator that is moving down. Every new customer your marketing team
wins is partly just replacing someone who left.

Return to the example above: break-even was month ten. At 5% monthly churn the *average*
customer stays about 20 months. That works, but barely. At 8% churn the average customer
stays 12 months and the business is **barely breaking even on every customer it
acquires**. At 10%, it loses money on every single sale, and grows itself into
bankruptcy.

This is why churn is not a marketing metric. It is a survival metric.

---

## The two kinds of churn (this distinction matters more than it sounds)

**Voluntary churn** — the customer *decided* to leave. Too expensive, not using it,
found something better, business closed.

**Involuntary churn** — the customer never decided anything. **Their payment simply
failed.** Card expired, insufficient funds on the day, bank declined it as suspicious.
They still want the product. They may not even know they have been cut off.

Here is the surprising part: **involuntary churn is 20–40% of all churn.**

Between a fifth and two fifths of the customers a subscription business loses did not
choose to leave. They were lost to an expired card.

These need completely different responses:

- Voluntary churn needs you to understand and address a human decision.
- Involuntary churn needs better *timing of payment retries*. A card declined at 2am on
  a Sunday and one declined at 10am on a Tuesday recover at very different rates. A
  "insufficient funds" decline should be retried near payday; a "do not honour" decline
  needs a different card entirely.

Yet almost every published churn study, and most commercial tools, lump them into one
number called "churned". Doing so makes roughly a third of the problem invisible to the
model that is supposed to explain it.

**This is the first easy win in the entire field, and most small businesses do nothing
about it.** Typical operators recover 30–45% of failed payments. Good ones recover
55–70%. That gap is pure profit requiring no clever mathematics at all.

---

## What businesses currently do about it

The standard playbook, used almost everywhere:

1. Collect data about customers — how often they log in, what they have bought, how
   long they have been a customer.
2. Build a **predictive model** — a program that learns patterns from past customers who
   left, and scores current customers on how likely they are to leave. Typically a
   number from 0 to 1. This is called a **churn score**.
3. Take the customers with the highest scores.
4. Send them something to make them stay. Usually a discount.

This is intuitive, it is what every tool sells, and step 4 is where it goes wrong.

[Document 03](03-the-core-insight.md) explains why. It is the heart of this project.

---

## Why small businesses are worse off than large ones

Large companies handle this with teams of data scientists and millions of customers to
learn from. Small businesses have neither.

The tools that exist for them fall into gaps:

| What they can buy | What it does | What it doesn't do |
|---|---|---|
| Payment-recovery tools | Retries failed cards | Nothing about customers who *chose* to leave |
| Analytics dashboards | Shows churn *after* it happened | Tells you nothing about what to do |
| Marketing tools | Flags "high risk", sends an email | No sense of cost, benefit, or whether it worked |
| Enterprise platforms | Comprehensive | Priced for large companies; needs a dedicated team |

And there is a harder problem underneath. Most of these tools need **a lot of
customers** before they say anything useful — one major marketing platform requires at
least 500 customers with three or more purchases each and six months of history before
its predictions activate.

**A business with 400 customers gets nothing.** Not a worse answer — no answer at all.

That is a large number of businesses, and they are the ones for whom losing customers
is most dangerous.

---

## The size of the opportunity

- Every business billed through a subscription payment processor is a potential customer.
- Churn is the number that determines whether they live or die.
- The single largest, easiest component of it — failed payments — is unaddressed by
  most small businesses.
- The harder component — customers choosing to leave — is addressed *badly* by everyone,
  including large companies, for reasons document 03 explains.

---

**Next:** [02 — How the big companies do it](02-how-the-big-companies-do-it.md), or skip
to [03 — The core insight](03-the-core-insight.md) if you want the central idea now.
