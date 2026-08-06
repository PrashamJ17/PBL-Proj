# 06 — The business case

*Assumes [03](03-the-core-insight.md). No finance background needed.*

---

## The market

Every business that bills customers on a recurring basis needs this. That is software
companies, subscription boxes, membership businesses, media services, and increasingly
ordinary retail brands.

We are deliberately **not** targeting all of them. Our initial focus:

> **Early-stage business software companies billing through Stripe, with 200–2,000
> customers.**

Why this specific group:

- Their data is clean and arrives from one integration.
- They already understand retention metrics — no education needed to make the sale.
- They are large enough that retention matters materially, small enough that no existing
  tool serves them.
- They are reachable online without a sales team.

A narrow beachhead beats a broad ambition. "Small businesses" is not a market you can
sell to; "seed-stage SaaS on Stripe" is a group you can find and talk to.

---

## The competitive landscape — and the gap

The market is crowded but **fragmented**. Every player solves one slice:

| Type of tool | What it does | What it does not do |
|---|---|---|
| Payment-recovery tools | Retries failed cards | Nothing about customers who *chose* to leave |
| Analytics dashboards | Reports churn after it happens | No action, no decision |
| Cancellation-flow tools | Intercepts at the moment of cancelling | Only that moment; recently moved upmarket |
| Marketing platforms | A three-band risk score feeding an email | No cost awareness, no proof, no causality |
| Enterprise retention suites | Comprehensive | Enterprise pricing; requires a dedicated team |

**Nobody in the small-business tier answers the three questions that determine profit:**

1. **Who should I actually contact?** (not "who will leave" — different sets)
2. **What is the cheapest thing that will work on this person?**
3. **Did it work, in money, compared to doing nothing?**

Two market signals confirm the opening is real:

**A leading cancellation-flow product removed its public pricing and now routes every
enquiry through a sales call.** That is the signature of a deliberate move upmarket, and
it vacates the self-serve small-business segment.

**A major player charges 10–15% of the revenue it recovers.** Performance-based pricing
is therefore already accepted in this category — but *only for failed payments*, because
that is the only outcome anyone can currently prove. Nobody prices on results for
voluntary churn, because nobody can measure it.

**We can.** That is the wedge, and it is a direct extension of a pricing model buyers
already accept.

---

## How we make money

**A base subscription** — roughly $99 / $249 / $499 a month depending on the customer's
size. This covers our costs and filters out unserious prospects.

**Plus a share of proven results** — 10–20% of the incremental revenue we can *prove* we
retained, capped monthly.

The second part is only credible because of the held-back control group described in
[04](04-what-we-are-building.md). It transforms the sales conversation:

> *"We'll show you what we earned you. If we earn you nothing, you pay us almost
> nothing."*

For a small business owner who has been sold analytics dashboards that changed nothing,
that is a materially different offer.

---

## How this starts — services first, then product

A pure software product requires the software to exist and customers to trust it. Neither
is true on day one. The realistic sequence, which also solves a critical technical
problem:

**Step 1 — the "Churn Autopsy."** A fixed-fee diagnostic (roughly $500–1,500 / ₹40,000–1,20,000).
The business sends a data export. They receive a report: how their customers are actually
retained over time, how much they lose to failed payments, what is driving departures,
and a ranked list of leaks **with money attached to each**.

This converts, because it is specific and it is about their money, not our technology.

**Step 2 — implementation** ($2,000–5,000). Connect their billing, fix failed payments,
run their first properly controlled retention campaign.

**Step 3 — ongoing subscription.** The recurring product.

**Why this order is not a compromise but a requirement:** our system needs data on what
happens when you intervene, and *nobody has that data* until somebody runs controlled
experiments. Our first clients' campaigns generate exactly the evidence our models need.
Services first is the only way to solve the cold-start problem.

A realistic first year is **5–15 clients and $30,000–100,000 in revenue.** That is a
deliberately unglamorous number. It is also the dataset that makes the research papers
possible.

---

## Why this gets harder to compete with over time

Most software has weak defences — anyone can rebuild the features. Ours strengthens with
use, for a specific structural reason.

Because we hold back control groups from the first customer onward, we accumulate
something rare: **a record of which interventions actually caused which outcomes, across
many different businesses.**

That record feeds a statistical technique in which every business's predictions are
informed by patterns learned from all the others. Practically:

> **Customer #41 gets useful predictions on day one, because forty similar businesses
> have already taught the system what works.**

Customer #1 had to wait months for the same quality.

A competitor can copy our entire codebase and still not have this, because it does not
live in the code. It lives in accumulated causal evidence, which takes years and
discipline to build — discipline most companies won't accept, because holding back a
control group feels like leaving money on the table.

The other advantage is simpler: **integrations are boring and take time.** Connecting to
billing systems, marketing tools, and support platforms is unglamorous work that
compounds.

---

## The honest risks

We would rather state these than have you find them.

| Risk | How serious | Our answer |
|---|---|---|
| **Cold start** — no clients means no causal data means no model | **Critical** | Simulator, pooled priors, and a deliberately funded randomisation phase with early clients |
| A payment processor builds this themselves | High | Be the decision layer *across* billing systems; own the causal evidence, not the plumbing |
| Small businesses are expensive to acquire and cheap to sell to | High | Services first; narrow niche; results-based pricing |
| Our own customers go out of business | Medium | Small businesses fail; annual terms and gradual move upmarket |
| Larger competitors move down-market | Medium | The main one just moved *up*, vacating this segment |

The first one is the real risk and it deserves emphasis: **this is a chicken-and-egg
problem.** The model needs evidence about what interventions do; that evidence only
exists once someone runs controlled experiments; nobody will let you run experiments
until the model works. The services-first path is not a fallback — it is the designed
solution.

---

## What an evaluator should be sceptical about

Four fair objections:

**"The model isn't the business."** Correct, and we agree. Distribution is the business.
The technique in [03](03-the-core-insight.md) is two decades old and published. Our
contribution is making it work at small scale, packaging it for people without data
teams, and proving results. Any of those could be replicated by a better-funded team.

**"Small business is the hardest market in software."** Also correct. High acquisition
cost, low willingness to pay, high failure rate. This is why the plan starts with
services and results-based pricing rather than a self-serve product.

**"No customers yet."** Correct. Everything in [05](05-the-evidence.md) is simulation. The
mechanism is demonstrated; commercial value is not.

**"A founder with no network selling to businesses."** Correct, and the weakest point.
Mitigations — publishing the research openly, giving away the first diagnostics for case
studies rather than fees — are plans, not proof.

We would rather you weigh these now than discover them later.

---

## Why it is worth doing anyway

The problem is severe and universal. The largest single component of it — failed
payments — is unaddressed by most small businesses and needs no clever technology to
fix. The harder component is handled badly by *everyone*, and we can now demonstrate
precisely why. The pricing model that makes it sellable is already accepted in the
category. And the segment most likely to buy it has just been vacated by the incumbent.

The technique is proven. The market is real. The open question is execution and
distribution — which is the honest position for any project at this stage.

---

**Next:** [07 — Risks and limitations](07-risks-and-limitations.md).
