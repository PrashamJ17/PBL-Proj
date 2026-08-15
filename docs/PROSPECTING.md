# Finding prospects — where 200–2,000-customer subscription businesses actually are

**The honest headline: I could not produce a verified list of named companies, and neither
will a search engine.** That is not a tooling failure, it is the shape of the problem, and
understanding why changes the strategy.

## Why searching for them does not work

A business with 200–2,000 customers is, by construction, not famous. Every source a search
returns is one of:

- **Listicles** ("Top 15 subscription boxes in India") — written for SEO, frequently years
  stale, and listing whichever brands paid for placement or are large enough to be known.
- **Funding databases** — Tracxn lists ~32,000 Indian SaaS startups, of which ~3,800 are
  funded and ~1,000 are Series A or later. **Series A is already past your ceiling.** The
  ones you want are in the unfunded 28,000, which is exactly the segment no database
  profiles usefully.
- **Payment-processor case studies** — Razorpay's own showcase features Rentomojo (40% of
  users on 2-year subscriptions) and Emergent. Both are an order of magnitude too big.

So this is a **filtering problem, not a discovery problem**. The winning move is to source
from places where founders *publish their own size*, because that collapses qualification
from a research task into a filter.

## Channel 1 — founders who publish revenue (best)

These self-qualify on the hardest criterion. Target **₹1.5L–20L / $2k–20k MRR**, which at
Indian micro-SaaS's typical ₹999/month price point is roughly 150–2,000 customers.

| Source | Why it fits | Filter |
|---|---|---|
| **Indie Hackers** — Products directory | Founders list MRR voluntarily | MRR $2k–20k, 12+ months old |
| **r/SaaS, r/IndieBiz** monthly revenue threads | Self-reported, recent, replyable in-thread | Same band; subscription not one-off |
| **X / build-in-public** | MRR screenshots; warm intro via reply | Indian founders posting ARR milestones |
| **Product Hunt**, launches 12–24 months old | Old enough to have churn history, small enough to fit | Subscription pricing on their site |

Only ~6% of revenue-generating startups clear $10k MRR, so this band is where almost
everyone actually is — the pool is much larger than the funded-startup lists suggest.

## Channel 2 — Shopify / Chrome extension app developers (underrated)

App developers **are** subscription businesses: recurring billing, a few hundred to a few
thousand subscribers, real churn, and a public size proxy in their review count. They are
also technically literate, so the CSV ask is trivial for them.

Shopify App Store and Chrome Web Store are browsable and filterable by category and review
count. An app with 50–500 reviews is usually in your range.

## Channel 3 — Indian D2C, with a large caveat

Subscription-first categories where a genuine cancellable subscription exists: **coffee and
tea** (roasters with monthly plans), **pet food**, **supplements and nutrition**, **baby
and hygiene consumables**, **meal kits**.

**Verify the subscription is real before anything else.** Most Indian D2C "subscribe and
save" is a repeat-purchase discount with no binding subscription and no cancel event. That
is *non-contractual* churn — a different mathematical problem, Phase 7 here, and precisely
the RetainIQ-PBL/Olist failure (99.4% base rate, ROC-AUC 0.543). One question settles it:

> *Do customers hold a subscription they can cancel, or do they just reorder when they want?*

## Channel 4 — acquisition marketplaces, as intelligence only

Acquire.com lists small SaaS with MRR ranges public, and customer count plus **churn**
visible after a buyer NDA. Buyer search filters are literally built on MRR, churn and LTV,
so the population is exactly yours, and a seller whose churn is suppressing their valuation
has an unusually acute reason to care.

**Do not sign a buyer NDA to source consulting leads.** Registering as a buyer to obtain
confidential metrics and then pitching a service is misrepresenting your intent, and it is
the kind of thing that follows you. Use the public tier to calibrate what this market looks
like; do not mine it under a false persona.

## The hidden disqualifier: billing model

Revenue filters find the right *size* and tell you nothing about whether the business has
churn you can analyse. Four billing models appear constantly in this band and **all four
fail**, none of them visibly:

| Model | Example seen in the wild | Why it fails |
|---|---|---|
| **Credit-based** | "affordable, credit-based platform" | A customer who stops buying credits never cancels. There is no churn event, so this is non-contractual — the Olist trap in B2B clothing. |
| **Usage-based** | SMS / messaging platforms | Revenue drifts without anyone leaving; MRR and churn are both ill-defined. |
| **App-store billing** | Consumer subscription apps | Apple/Google hold the subscription. The exports are different, and the merchant often cannot see cancellation reasons at all. |
| **Agency / services** | "product teams on demand" | Not a subscription business. Retainers end by conversation, not by cancel button. |

Read the pricing page before the revenue figure. The words to look for are **"per month"**
and a **cancel** action; the words that should stop you are **credits**, **pay as you go**,
**top up**, and **App Store**.

## Qualify before spending an introduction

You have a limited number of first impressions. Check, from their public site, in this
order — the first failure disqualifies:

1. **Is there a real subscription with a cancel action?** (not repeat-purchase)
2. **Is it contractual and recurring?** (not a marketplace, not one-off e-commerce)
3. **Roughly 200–2,000 customers?** From disclosed MRR ÷ price, or review count as a proxy.
4. **At least 12 months live?** `preflight` blocks under six months of history.
5. **Billed through Stripe / Razorpay / Chargebee / Paddle?** Usually visible at checkout.

Anything failing 1 or 2 is worse than no email: `preflight` will block the export and you
will have spent the introduction discovering it.

## Contact, without harvesting

Use what the company publishes for inbound contact — the address on their site, their
support address, or the founder's own public profile where they invite contact. Reply in
the thread where they posted their revenue; that is a warm, invited context and converts
far better than a cold address.

**Do not** buy contact lists, scrape personal addresses, or use an email-finder tool to
guess a founder's inbox. Under the DPDP Act and GDPR you would be processing personal data
with no basis, and for ten emails it buys you nothing anyway.

## What to expect

Ten qualified, hand-written emails is a realistic first batch. Two or three replies and one
conversation is a normal outcome; one paid diagnostic out of ten is a good one. If you get
zero replies from ten *well-qualified* prospects, that is information about the pitch, not
a reason to send fifty more — revise and send another ten.

Log every one (runbook §7). Ten rows is the evidence for whether this is a business.

---

*Templates: `docs/OUTREACH.md`. Constraints on what may be claimed: `docs/SALES-RUNBOOK.md` §2.*
