# Outreach templates — Churn Autopsy

**Drafts for a human to review and send.** Adjust the voice to sound like you; a message
that reads as generated will be deleted, and rightly.

Every claim below is traceable to something we measured or to a published benchmark, and
`docs/SALES-RUNBOOK.md` §2 lists what may not be said. The temptation in a cold email is
to imply the model works. It does not yet (D-058), and a founder who buys on that basis
is a refund and a bad reference.

---

## Why the first one should be paid

The plan (§8.4) suggests a free Autopsy for the first ten in exchange for case studies.
That is reasonable and it **does not close Phase 2's gate**, which is *first revenue*.

Charge something small — ₹8,000–15,000, or $100–200 — for the first few. It:

- closes the gate, which is the whole point of the phase;
- filters out people who will take a free report and never reply;
- earns you the right to ask follow-up questions, which is the actual asset;
- makes a case study worth quoting ("a paying client") rather than a favour.

Template A is the paid version and is the recommended one. Template B is free-in-exchange-
for-a-case-study, for a prospect you especially want or who is clearly hesitant.

---

## Template A — cold email, paid (recommended)

> **Subject:** what share of your churn is failed payments?
>
> Hi {Name},
>
> Quick question rather than a pitch: do you know what proportion of your cancellations
> last year were people who actively decided to leave, versus cards that just failed?
>
> Most subscription businesses can't separate the two, and the second group is usually
> 20–40% of total churn. It's also the cheapest to recover, because nobody in that group
> wanted to leave.
>
> I'm a final-year CS student building retention tooling for small subscription
> businesses, and I'm doing a small number of paid diagnostics to test it against real
> data. For ₹10,000 I'll send you back:
>
> - your retention curve by signup cohort,
> - revenue churn vs logo churn (they usually differ more than people expect),
> - failed-payment churn quantified separately, in rupees,
> - and a ranked list of where the money is actually leaking.
>
> What I need is two CSV exports from Stripe — customers and subscriptions — plus
> invoices if you can. It takes about two minutes on your side, no engineering. I'll
> delete the files afterwards and I don't need names or emails, just IDs.
>
> Turnaround is a week. If the report tells you nothing you didn't already know, don't
> pay me.
>
> Worth a look?
>
> {Your name}
> {GitHub / one-line credential}

**Why it is built this way**

- **Opens with a question they cannot immediately answer.** That is the hook, and it is
  honest: most founders genuinely cannot split voluntary from involuntary churn.
- **The 20–40% figure is a published industry benchmark, not our finding**, and is
  phrased as "usually" rather than "your". Do not attribute it to our experiments.
- **Says "student"**. It is true, it is checkable, and it explains the low price without
  making you sound cheap. Pretending to be a consultancy is both dishonest and one
  LinkedIn search from collapsing.
- **The refund line does the work of a guarantee** without promising a result. You are
  promising effort and honesty, which you can deliver, not lift, which you cannot.
- **No claim about prediction anywhere.** Deliberate. See the runbook.

---

## Template B — free, in exchange for a case study

Same body, with the offer paragraph replaced:

> I'm building retention tooling for small subscription businesses and I need real data
> to test it against. I'll do this free for the first few businesses. All I'd ask in
> return is 20 minutes afterwards to hear which parts were useful and which were
> obvious — and, if it turns out useful, permission to describe the result anonymously.

**Use sparingly.** It does not close the gate, and "free" lowers the reply quality.

---

## Template C — LinkedIn / DM (short)

> Hi {Name} — do you know what share of your churn last year was failed payments rather
> than actual cancellations? It's usually 20–40% and most Stripe dashboards don't split
> it out.
>
> I'm a CS student building retention tooling and doing a few paid diagnostics against
> real data (₹10k). Two CSV exports from you, a report back in a week, don't pay if it's
> not useful. Interested?

---

## Template D — the reply when they say yes

Send this immediately; the momentum is worth more than the polish.

> Great — here's exactly what I need.
>
> **In Stripe:** Customers → Export, and Billing → Subscriptions → Export. If you can
> also grab Invoices (or Payments), I can quantify the failed-payment side properly,
> which is usually the biggest single number in the report.
>
> **Two things before you send:**
>
> 1. Please strip names and email addresses if that's easy — customer IDs are all I use.
>    If it's not easy, send as-is and I'll drop those columns on arrival.
> 2. To confirm in writing: this is a one-off analysis, I won't share the files with
>    anyone, I won't use them to train anything, and I'll delete them once you have the
>    report. Happy to sign whatever your side needs first.
>
> **One question I'll almost certainly need to ask, so ahead of time:** are any of your
> plans billed annually rather than monthly? It changes how the revenue figures are
> calculated and I'd rather get it right than guess.
>
> I'll have something back to you within a week.

**Why the annual-plan question is in the first reply.** `preflight` asks it every time,
and getting it wrong overstates MRR twelvefold (D-062). Asking early is cheaper than
asking mid-analysis and much cheaper than getting it wrong.

---

## Template E — graceful no

Send it. A clean no from someone who remembers you is worth more than a chase.

> No problem at all — thanks for reading. If you ever want the failed-payment number
> pulled out, the offer stands. Good luck with {company}.

---

## Sending notes

- **Ten at a time, individually.** No mail-merge tools, no BCC. This is research
  outreach, not a campaign, and it should read like one.
- **Personalise the first line for real.** One specific true sentence about their
  product. If you cannot write one, they are not a good enough fit to email.
- **One follow-up, after a week, and then stop.** "Just bumping this in case it got
  buried — no worries if not a fit."
- **Do not claim a shared connection you do not have**, do not invent urgency, and do
  not imply you have already looked at their data.
- **Log every send** — who, when, reply, outcome — per runbook §7. Ten rows of that is
  the evidence for whether this is a business.

## Qualification, before you write anything

From runbook §3: subscription (contractual, **not** a marketplace), billed through
Stripe/Paddle/Chargebee/Razorpay, roughly 200–2,000 customers, at least 12 months of
history. Seed-stage B2B SaaS first.

Emailing someone outside that is worse than not emailing: `preflight` will block the
export, and you will have spent your one introduction discovering it.

---

# India / Razorpay D2C variant

**Not a find-and-replace of the templates above.** Three things differ materially, and the
first is why the hook is *stronger* here than in the US/EU version.

## What is actually different

**1. Involuntary churn in India is a mandate problem, not a card-expiry problem.**
Recurring payments run on UPI AutoPay, e-NACH or card e-mandates, all under RBI rules that
have no Western equivalent: an Additional Factor of Authentication above ₹15,000, a
mandatory 24-hour pre-debit notification, and the 2022 card-tokenisation change that broke
a large number of existing mandates outright. A customer can also revoke a UPI mandate
inside their payments app in two taps, with nothing appearing in the merchant's cancel
flow.

The consequence: a meaningful share of Indian D2C "churn" is a mandate that stopped
working, from a customer who never decided anything and often has not noticed. That is
exactly the group worth recovering, and almost nobody measures it separately.

**2. The economics are smaller and tighter.** Typical D2C subscription ARPU is
₹400–2,000/month against $50–500 for B2B SaaS, on physical goods with real COGS. A ₹200
retention discount is a much larger share of margin than a 20% SaaS discount, so the
offer-ladder argument — try the free rungs first — lands harder. Price the diagnostic
accordingly: **₹5,000–8,000**, not ₹10,000.

**3. Delivery experience is a churn driver, and it is in their data.** RetainIQ's Olist
analysis (D-060) found delivery delay among the strongest features. For a subscription
box, a late or missed shipment is frequently the proximate cause of a cancellation, and it
is visible in order data rather than needing a survey.

## Qualification — the trap to avoid

**Confirm there are real subscriptions, not "subscribe and save".** Many Indian D2C brands
run repeat-purchase discounts with no binding subscription, which is *non-contractual*
churn: nobody cancels, they just stop. That is a different mathematical problem (Fader &
Hardie), it is Phase 7 here, and RetainIQ's Olist result is the cautionary tale — a 90-day
churn label on a marketplace produced a 99.4% base rate and a model with ROC-AUC 0.543.

Ask before you agree to anything: *"do customers hold an active subscription with a
cancel action, or do they just reorder when they want?"* If it is the second, decline
politely and say why. It is not sellable yet and the report would be worthless.

Also confirm they are **past the pilot stage**: 200+ subscribers and 12+ months of
history, or `preflight` will block.

## Template A-IN — cold email

> **Subject:** how much of your churn is failed mandates?
>
> Hi {Name},
>
> A question rather than a pitch: of the subscribers you lost last quarter, do you know
> how many actually cancelled, versus how many had a UPI AutoPay or e-NACH mandate that
> simply stopped working?
>
> Most D2C brands can't separate the two. The second group matters more than it looks —
> those customers didn't decide to leave, and a lot of them haven't realised they've
> stopped being charged. Between the ₹15,000 AFA rule, the 24-hour pre-debit notification
> and the 2022 tokenisation changes, mandate failure in India is a bigger share of churn
> than most dashboards make visible.
>
> I'm a CS student building retention tooling for subscription businesses, and I'm doing
> a few paid diagnostics against real data. For ₹6,000 I'll send back:
>
> - your retention curve by signup month,
> - revenue churn vs subscriber churn (usually further apart than expected),
> - **failed-mandate churn separated from real cancellations, in rupees**,
> - and where the money is actually leaking, ranked.
>
> I need two CSV exports from Razorpay — Customers and Subscriptions — plus Payments if
> you can, which is what makes the mandate number possible. Two minutes, no developer.
> I don't need names, emails or phone numbers, just IDs, and I'll delete the files after.
>
> A week's turnaround. If it tells you nothing you didn't already know, don't pay me.
>
> Worth a look?
>
> {Your name}
> {GitHub}

## Template C-IN — WhatsApp / LinkedIn DM

> Hi {Name} — quick one. Of the subscribers you lost last quarter, do you know how many
> actually cancelled vs how many just had a UPI mandate stop working? Most Razorpay
> dashboards don't split it.
>
> I'm a CS student building retention tooling, doing a few paid diagnostics on real data
> (₹6k, week's turnaround, don't pay if it's not useful). Two CSV exports from you.
> Interested?

WhatsApp is normal for Indian founder outreach in a way it is not in the US. Keep it to
this length, send it in business hours, and do not follow up more than once.

## Template D-IN — the reply when they say yes

> Great. Here's what I need.
>
> **In Razorpay Dashboard:** Subscriptions → export, and Customers → export. If you can
> also export **Payments** (or Invoices), I can separate failed mandates from genuine
> cancellations, which is the part most brands have never seen.
>
> **Two things first:**
>
> 1. Please drop names, emails and phone numbers if that's easy — customer IDs are all I
>    use. If it's easier to send as-is, I'll strip those columns on arrival.
> 2. In writing: one-off analysis, not shared with anyone, not used to train anything,
>    deleted once you have the report. Happy to sign an NDA or a data-processing
>    agreement first — under the DPDP Act I'd be a processor and you'd be the fiduciary,
>    so it's reasonable to want that on paper.
>
> **Two questions I'll need answered either way:**
>
> - Are any plans billed quarterly or annually rather than monthly? It changes how the
>   revenue figures are computed.
> - Do subscribers hold an actual subscription they can cancel, or is it a repeat-order
>   discount they simply stop using? The analysis is different and I'd rather know now.
>
> Report back within a week.

## Notes on the Indian version

- **Razorpay exports are already handled.** The loader parses its epoch-second
  timestamps and paise amounts, and `preflight` blocks on the latter rather than guessing
  (tested; D-062). You will need `--divide-amounts-by 100` for essentially every
  Razorpay export.
- **DPDP Act**, not GDPR. You are a *data processor*, the brand is the *data fiduciary*.
  Offering the DPA before they ask is a credibility signal in a market where most tool
  vendors do not.
- **Do not claim you can fix mandate failures.** You can *measure* them. Recovery is
  Phase 2's dunning work and has never been run against a live Indian payment stack.
- **Do not quote the 20–40% Western benchmark for India.** It is a different payment
  regime and I have no Indian figure to cite. Say "most brands can't separate the two"
  — which is true and is the actual selling point — rather than inventing a percentage.
