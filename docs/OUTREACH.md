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
