# Driving AI outreach from RetainIQ

**Can this system work with AI agents, workflow tools, personalised email and synthetic
voice calls? Technically yes, and the engineering is the easy part. The reasons to be
careful are economic and legal, and both are quantified or cited below rather than
asserted.**

---

## 1. The finding that governs the design

`make ai-channels` (D-064) prices the automation argument directly. Its premise —
"a human call costs 6, an AI call costs 0.5, so make twelve times as many" — is arithmetic
about **cost per contact**, and cost per contact is not what causes harm. Contacting a
dormant payer can itself trigger the cancellation, so every rung carries a
`salience_multiplier`. Cheapness does not touch salience.

| channel | cost | salience | harmed | value per customer if sent to all |
|---|---|---|---|---|
| Human check-in call | 6.00 | 0.55 | 27% | **+3.97** |
| AI email | 0.02 | 0.35 | 30% | **+5.41** |
| AI voice, *matched* salience | 0.50 | 0.55 | 34% | **+5.31** |
| AI voice, salience 1.0 | 0.50 | 1.00 | 55% | **−4.93** |
| AI voice, salience 2.0 | 0.50 | 2.00 | 76% | **−38.09** |

**Break-even salience is 0.80** — *below* neutral. For mass AI calling to pay, an
unsolicited synthetic voice would have to be **less intrusive than a generic retention
email**. Three consequences:

1. **AI email is fine and worth building.** It is the strongest channel in the table. The
   finding is about intrusiveness, not about who writes the copy.
2. **AI voice is the highest-risk rung on the ladder** and belongs late in it, used rarely
   and on high-value accounts, or not at all.
3. **A cheap actuator makes selection matter *more*.** As salience rises the oracle's
   treat share falls from 70% to 14%. A free channel removes the felt need to choose
   whom to contact exactly when choosing correctly is most valuable.

The salience of a synthetic call is **not measured anywhere in this project** and would
need a live experiment. The number swept above is an assumption; the threshold is the
result.

---

## 2. The architecture, and the line that must not move

**RetainIQ is the decision layer. The AI is the execution layer. The AI never decides *who*,
*whether*, or *how much*.**

```
  billing data ──► preflight ──► canonical schema ──► models ──► LadderOptimiser
                                                                       │
                                                     Recommendation {rung | ABSTAIN,
                                                     expected_value, confidence, reasons}
                                                                       │
                                    ┌──────────────────────────────────┴───────────┐
                                    │            POLICY GATE (deterministic)       │
                                    │  consent · frequency cap · discount cap ·    │
                                    │  channel allow-list · quiet hours · holdout  │
                                    └──────────────────────────────────┬───────────┘
                                                                       │
                       ┌───────────────────────────────────────────────┤
                       ▼                       ▼                       ▼
                  LLM copywriter        ESP / CRM webhook        voice platform
                  (wording only,        (Klaviyo, Customer.io,   (human-approved,
                   from a template)      HubSpot, Intercom)       consented, rare)
                                                                       │
                                    every send logged ◄────────────────┘
                                    outcome joined back at horizon
```

**What the LLM is allowed to do:** choose wording, tone and length, inside a template, for
a rung and a discount depth **that RetainIQ has already fixed**. It receives the reason codes
(D-059) as facts to phrase, not as inputs to a decision.

**What the LLM must never do:** pick recipients, pick the rung, set or vary a discount, or
decide to contact someone RetainIQ abstained on. Letting a generative model choose recipients
discards every result this project established. Letting it choose discount depth re-opens
the personalised-pricing exposure ruled out by D-039 and plan §13.2 — an LLM inferring
willingness-to-pay and pricing against it is exactly the surveillance-pricing pattern that
attracts regulators.

**The policy gate is deterministic code, not a prompt.** Prompts are not a control
surface: they are advisory, they drift between model versions, and they can be talked out
of constraints. Caps belong in code with tests, upstream of anything generative.

---

## 3. Integration options, honestly compared

| Approach | Effort | Fits when | Real drawback |
|---|---|---|---|
| **CSV worklist → their existing tool** *(built today)* | none | Always. Start here. | Manual. That is a feature at first: a human sees every list before it sends. |
| **Webhook into their ESP/CRM** (Klaviyo, Customer.io, HubSpot, Intercom) | days | They already have the sending stack | You inherit their consent state, which you must verify rather than assume |
| **n8n / Zapier / Make workflow** | days | Non-technical operator wants to self-serve | Silent failures; needs its own dead-letter handling |
| **LLM copywriter behind the gate** | 1–2 weeks | Volume makes templates repetitive | Cost, latency, and hallucinated commitments — see §5 |
| **AI voice calls** | 3–4 weeks | Rarely, on high-value accounts, with explicit consent | The legal exposure in §4 and the economics in §1 |

**Be the brain, not the pipes.** Businesses already pay for a sending stack. Writing
another email sender competes on a commodity and adds deliverability, bounce handling and
suppression lists to your surface area for no differentiation.

---

## 4. Legal constraints, and one of them is genuinely dangerous

**Not legal advice. Get a lawyer before any voice channel ships.**

### AI voice calls — the serious one

- **United States (TCPA).** Automated or artificial-voice calls to mobile numbers require
  **prior express written consent**. Statutory damages are **$500–$1,500 per call**, and
  it is a well-developed class-action area. The FCC confirmed in February 2024 that
  AI-generated voices count as "artificial" under the TCPA. A 5,000-customer campaign
  without consent is a company-ending number.
- **India (TRAI TCCCPA).** Commercial voice and SMS require DLT registration, registered
  headers and templates, and scrubbing against the **DND registry**. Penalties and
  disconnection follow non-compliance.
- **EU AI Act.** Transparency obligations apply to AI systems interacting with humans —
  a synthetic voice must disclose that it is one.
- **Consent is not transferable.** "They accepted our terms of service" is not consent to
  be robocalled, in any of these regimes.

### Everything else

- **GDPR Art. 22 / India DPDP.** Automated decisions with significant effects need a
  human-review path and an explanation. RetainIQ's reason codes (D-059) exist and satisfy the
  explanation side; the review path must be built.
- **You are a processor, not a controller.** The client is the data fiduciary. DPA before
  data moves.
- **Email.** CAN-SPAM/GDPR: honour unsubscribes immediately, and note that a retention
  offer to someone who unsubscribed from marketing is still marketing.

### What this implies

**Ship AI email first. Treat voice as a separate product decision requiring counsel,
explicit per-customer consent, and volumes small enough to review by hand.** The economics
in §1 point the same way, which is convenient but not the reason.

---

## 5. Failure modes, and what catches each

The engineering is easy; these are what actually break.

| Failure | Consequence | Control |
|---|---|---|
| LLM invents a promise ("we'll refund you") | Contractual exposure | Constrained templates; regex/LLM-judge validation before send; log the exact text sent |
| LLM varies discount depth | Personalised pricing exposure | Depth is fixed by RetainIQ and never in the prompt; validate the rendered text contains only the approved figure |
| Duplicate sends on retry | Same customer contacted repeatedly | Idempotency key per (customer, campaign); at-least-once delivery means exactly-once handling is yours |
| Contacting someone RetainIQ abstained on | The Phase 0 harm, at scale | Abstentions are an explicit deny-list, not an absence from the send list |
| Holdout contaminated | You can never measure whether any of it worked | Holdout membership assigned by deterministic hash upstream of the gate; immutable ledger |
| Stale decisions | Acting on a customer who already cancelled | TTL on recommendations; re-check subscription status at send time |
| Frequency stacking | Three "personalised" touches in a week | Global per-customer frequency cap across all campaigns, not per campaign |
| Quiet hours / timezone | Calls at 2am | Per-customer timezone, hard windows, cultural calendars |
| Provider outage mid-campaign | Half a segment contacted | Dead-letter queue; resumable with idempotency; alert on partial completion |
| Cost blowout | Voice inference and telephony billed per minute | Hard budget ceiling in code, enforced before the API call not after |

**None of this is exotic.** It is the ordinary discipline of an automated outbound system,
and it is roughly three times the work of the integration itself. Budget accordingly.

---

## 6. What must be built first, and why it is not the actuator

**Phase 6 — holdout and incrementality infrastructure — comes before any automated
sender.**

The reason is not caution, it is measurement. D-058 measured the optimiser beating a single
well-chosen offer on **58% of draws, CI [0.42, 0.72]** — a coin flip. An automated system
that sends without a permanent randomised holdout produces confident activity and **no
evidence about whether it worked**, forever. Save rate among the treated is not evidence;
it is contaminated by selection, which is the error this entire project exists to
characterise.

Wiring the actuator first is how a retention product becomes unfalsifiable. With a voice
channel it is also how it becomes a regulatory incident.

### Order

1. **Phase 6:** deterministic-hash assignment, immutable holdout ledger, incrementality
   report. Buildable now against the simulator.
2. **AI email behind the policy gate.** Copy generation only, human approval of the first
   campaigns, full send logging.
3. **Measure.** One full cycle with a holdout. Report the incremental number, including if
   it is zero.
4. **Only then** consider voice, with counsel, consent, and hand-reviewed volumes.

---

## 7. So: can the system work?

**Yes, with three qualifications, none of which is negotiable.**

1. **AI as the execution layer, never the decision layer.** RetainIQ picks who, what and
   whether; the model writes words inside a fixed template.
2. **Channel choice is an economic decision, not a technical one.** AI email is the best
   channel in the table. Synthetic voice needs salience below 0.80 to pay when used
   broadly, which is not plausible — use it rarely, on high-value accounts, with consent,
   or not at all.
3. **Measurement before automation.** No permanent holdout, no automated sending.

The version of this that fails is easy to describe and common: an LLM picks who to contact
from a churn score, writes something warm, and a voice agent calls them. That is Phase 0's
kill test with a better user interface — the same policy that lost money in 6 of 6 seeds,
executed faster and at lower unit cost. **Cheaper wrong decisions are still wrong
decisions, and automation is a multiplier on whichever sign you already had.**
