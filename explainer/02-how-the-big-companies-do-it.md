# 02 — How the big companies do it

*Assumes you have read [01](01-the-problem.md).*

A common assumption is that Netflix and Amazon keep customers because they have superior
prediction algorithms. **They mostly don't.** Their retention advantage is structural
and economic, not algorithmic — and understanding this changes what is worth building.

---

## Netflix — retention as product design

Netflix loses roughly 2% of subscribers a month in mature markets, exceptionally low.
There is no famous Netflix churn-prediction system doing this. What they actually do:

- **Spend enormously on content.** People stay because there is something to watch.
- **Personalise heavily** — the recommendation system exists to make sure you find
  something worth watching tonight.
- **Make cancelling deliberately easy**, and keep your profile and viewing history for
  months afterward, so rejoining is a single click.

That last one is counterintuitive and important. Netflix optimises for **lifetime
re-subscription**, not for preventing any single cancellation. Churn is treated as a
pause, not a death. Winning a lapsed customer back is far cheaper than acquiring a
stranger.

There is a second lesson here that the industry ignores. Netflix has largely avoided
aggressive "please stay, here's a discount" offers, because they **train customers to
threaten cancellation**. Once people learn that threatening to leave produces a
discount, they threaten to leave.

**Worth stealing:** win-back economics beat save economics. And the offer you give at
the moment of cancellation is teaching your customers something.

---

## Spotify — structural lock-in, and the downgrade

Three mechanisms, none of them predictive:

- **A free tier.** Users who won't pay any more *downgrade* instead of vanishing. They
  remain reachable, and can come back.
- **Family and Duo plans.** Once a subscription serves several people in a household,
  cancelling requires a negotiation with your family. Multi-person plans churn far less.
- **Student pricing.** This is price discrimination — charging different people
  different amounts — done in the one way that is legally and reputationally safe:
  based on a **verifiable status**, offered openly to everyone who qualifies.

**Worth stealing:** always offer a *downgrade* or *pause* before offering a discount. A
customer on a cheaper plan is worth far more than a cancelled one, and it costs you less
than a discount. Also: this is what legal price discrimination looks like, and
[07](07-risks-and-limitations.md) explains what illegal price discrimination looks like.

---

## Amazon Prime — the bundle is the strategy

Prime is not really a subscription. It is a bundle of habits: fast delivery, video,
music, photo storage, pharmacy, groceries.

The pattern in the data is consistent: **the more benefits a member actually uses, the
less likely they are to leave.** Someone who only uses free delivery is one bad delivery
experience from cancelling. Someone using delivery *and* video *and* photo storage has
three separate reasons to stay, and cancelling means losing all of them at once.

Prime also pushes annual plans. An annual plan converts **twelve chances to cancel per
year into one**.

**Worth stealing:** the strongest retention feature is usually a *second habit*, not a
discount. "This customer has only ever used one part of the product" is a serious risk
signal, and "get them to try the feature they've never opened" is an intervention that
costs you almost nothing.

---

## Telecom companies — where this field was born, and where it failed

Mobile operators invented churn prediction. They had contracts, lock-in, subsidised
handsets, and dedicated "retention desks" whose job was to talk you out of leaving with
an escalating series of offers.

They also discovered the field's central failure, expensively.

Ranking customers by churn score and sending them all a retention offer **destroyed
margin**. They were paying customers who would have stayed anyway. And worse — they were
prompting some customers to leave who had not been thinking about it.

**Uplift modelling — the technique at the centre of this project — was invented in
response to this problem, in this industry.** It is not new. It is roughly two decades
old, well studied, and used at large scale by large firms.

**It is almost entirely absent from tools available to small businesses.** That gap is
the opportunity.

---

## Business software companies (Salesforce, HubSpot and their ecosystem)

Business-to-business software uses a **customer health score** — a blended measure of
product usage, support tickets, survey sentiment, payment history, and whether the
customer's team is still active.

The strongest signal in this world is frequently one that almost no model includes:
**the person who championed the purchase has left the company.** The new person in that
seat did not choose your product, has no loyalty to it, and is often actively looking
for a reason to consolidate tools.

They also track **net revenue retention** rather than simple customer counts — because
an existing customer expanding their spend can offset several who left. Losing 10
customers while the remaining 90 double their spending is a good year.

**Worth stealing:** model *revenue* churn, not just customer-count churn. And track
personnel changes at business customers.

---

## Nike and consumer retail — identity first

Retail has a harder version of the problem. There is no "cancel" button. If you haven't
bought trainers in eight months, are you gone, or just not shopping right now? **Nobody
ever tells you they have left.** Churn must be *inferred*.

Nike's answer is membership. A membership programme turns an anonymous stream of
transactions into an identified, contactable relationship — converting the hard problem
into something closer to a subscription.

**Worth stealing:** for retail, identity is the prerequisite. This is why our project
starts with subscriptions, where the leaving event is observable, and treats retail as a
later phase requiring genuinely different mathematics.

---

## What is underdeveloped — everywhere, including at the giants

Six gaps. The first three are the important ones.

**1. Almost all of it is correlational, not causal.**
Models learn *who tends to leave*. They do not learn *who your actions will change*.
These are different questions and the industry routinely conflates them. This is
[document 03](03-the-core-insight.md).

**2. Retention spending is rarely measured for genuine effect.**
Most companies cannot tell you what their retention campaigns actually earned. They
report "save rate" — of the customers we contacted, how many stayed. That number is
meaningless, because most of them would have stayed anyway. To know the real effect you
must deliberately *not* contact a random subset and compare. Very few do this.

**3. Choosing what to offer is done by rules, not economics.**
Almost nobody asks: what is the *cheapest* thing that would work on this specific
person? The default is a discount, which is the most expensive option available.

**4. Failed payments are treated as an accounting problem**, not a churn problem —
despite being 20–40% of the total.

**5. Explanations are built for analysts, not operators.** A small business owner cannot
act on "feature importance 0.34". They can act on "four of their six licences haven't
been used in a month."

**6. Small businesses are simply unserved.** Below a few hundred customers, the tools
return nothing.

---

## The honest conclusion

You cannot out-predict Netflix, and you do not need to. Netflix's retention comes from a
content budget you cannot match.

But **nobody, at any size, has solved the causal question well** — and at small scale,
nobody has even attempted it. That is a defensible place to build.

---

**Next:** [03 — The core insight](03-the-core-insight.md). This is the one to read.
