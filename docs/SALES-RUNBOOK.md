# Churn Autopsy — operator runbook

**Phase 2's gate is one paying client.** No code closes it. This is the procedure for the
part that does, and the constraints that keep it honest.

Read `docs/DECISIONS.md` D-054, D-055, D-058 before the first call. They determine what
you are allowed to promise, and the answer is narrower than the product looks.

---

## 1. What you are selling

**A fixed-fee diagnostic, not a model.** You are telling a founder where their money is
leaking, in their own numbers, with the parts you could not measure marked as such.

Deliverable: one self-contained HTML report. Retention curves, revenue vs logo churn,
involuntary churn quantified, and a ranked list of leaks with money attached.

Price: a few hundred to ~1,500 (₹40k–1.2L), fixed. The point of the fee is not the
revenue — it is that a paid diagnostic qualifies the buyer and buys you the right to
ask follow-up questions.

## 2. What you may not claim

These are not modesty. They are what the experiments found.

| Do not say | Because |
|---|---|
| "We predict who will churn" | You can, but D-055 shows the score points at the wrong 79% of the money. Selling the score sells the thing this project exists to argue against. |
| "Our AI will tell you who to save" | D-058: the optimiser beats a single well-chosen offer on **58% of draws, CI [0.42, 0.72]**. That is not distinguishable from chance. |
| "This will increase retention by X%" | Nothing here has ever been measured on a live customer base. Phase 6 is the infrastructure that would make such a claim checkable. |
| Anything per-customer, under ~250 customers | Below that, nothing in our own benchmarks beats a population average. `preflight` warns you. |

**What you may say**, and it is enough to sell a diagnostic:

- Failed payments are 20–40% of churn for most subscription businesses and are usually
  unmeasured. We quantify yours, from your invoices.
- Value at risk and churn risk are different lists — ours overlapped by **21%**. Most
  businesses are working the wrong list, and this is arithmetic, not a model.
- Blanket retention discounts routinely lose money. We can show, in your data, how much
  of your at-risk revenue sits with customers a discount would not have changed.

## 3. Who to approach

Narrow, on purpose. From the plan's §8.3:

- Subscription (contractual) business — **not** a marketplace or one-off e-commerce.
  Non-contractual churn is a different mathematical problem (Fader & Hardie) and is
  Phase 7. RetainIQ's Olist result (D-060) is the cautionary example: a 90-day churn
  label on a marketplace produced a 99.4% base rate and a meaningless model.
- Billed through Stripe, Paddle, Chargebee or Razorpay — so the export is two clicks.
- **200–2,000 customers.** Below 200 there is not enough to say; above ~5,000 they
  probably have an analyst and a different objection.
- **At least 12 months of history.** `preflight` blocks under 6.

Best-fit first: seed-stage B2B SaaS. Clean data, literate buyers, they already think in
NRR.

**Where to find them is a filtering problem, not a search problem** — a business this small
is not in any directory. `docs/PROSPECTING.md` has the channels that work (founders who
publish their own MRR, Shopify/Chrome app developers), the qualification order, and the
lines not to cross when finding contact details.

## 4. The ask

Exactly two files, and say it in one line so nobody has to involve an engineer:

> Could you send a CSV export of your **customers** and your **subscriptions** from
> Stripe? Dashboard → Customers → Export, and Billing → Subscriptions → Export. If you
> can also send **invoices/charges**, I can quantify failed-payment churn, which is
> usually the biggest single number in the report.

Ask for invoices whenever you can. Involuntary churn is the finding that pays for the
engagement and needs no modelling at all.

Templates for the cold email, the LinkedIn version, the reply when they say yes, and the
graceful no are in `docs/OUTREACH.md` — including an **India/Razorpay D2C variant**, where
the hook is failed UPI/e-NACH mandates rather than expired cards. **Charge for the first one** — a free diagnostic
does not close a gate whose definition is *first revenue*.

**Before they send anything:** confirm in writing that this is a one-off analysis, that
you will delete the files afterwards, and that you will not share them. If they are in
the EU or India you are a data *processor* — have the DPA ready (D-039, plan §13.3).
Never ask for anything with names or emails you do not need; customer ids are enough.

## 5. Running it

```bash
python -m keel.cli preflight --customers customers.csv --subscriptions subscriptions.csv
```

**Never skip this and never send a report it blocked.** It exists because the way this
engagement dies is not a crash — it is a confident report with the client's own revenue
wrong in it, which they will notice (D-062).

It will usually raise two things:

- **Amounts in minor units.** Stripe exports cents. Re-run with `--divide-amounts-by 100`
  once the client confirms.
- **No billing interval.** Ask directly: *"are any of your plans annual?"* Assuming
  monthly on an annual book overstates MRR twelvefold.

Then:

```bash
python -m keel.cli autopsy \
  --customers customers.csv --subscriptions subscriptions.csv \
  --invoices invoices.csv --divide-amounts-by 100 --interval month \
  --name "Their Company" --out their_company_autopsy.html
```

Every assumption preflight printed is a question for the client. Ask them **before**
sending. An assumption they discover themselves costs more than the engagement is worth.

## 6. After the report

The report is not the product; the conversation it earns is. Three outcomes worth having,
in order of value:

1. **They have material involuntary churn.** This is the wedge — Phase 2 is built, it
   needs no causal claim, and the improvement is attributable. Offer implementation.
2. **They want to know who to save.** Be honest: you can run a randomised pilot that
   would tell them, and that is Phase 6. Do not sell the optimiser as if D-058 said
   something it did not.
3. **They say the numbers look wrong.** The most useful outcome. Find out why — it is
   either a real defect in the ingest or a real fact about their business, and both are
   worth more than the fee.

**Ask every one of them the same closing question:** *what would you have had to see for
this to be worth paying for?* Ten answers to that reshape the roadmap more than ten more
experiments.

## 7. Tracking

Keep a simple log per prospect: business, size, billing system, what they sent, what
preflight said, what you charged, what they did next. Ten rows of that is the evidence
for whether this is a business, and it is the input to paper 3.

---

*The gate is one paying client. Everything above is procedure; none of it is done until
somebody has paid.*
