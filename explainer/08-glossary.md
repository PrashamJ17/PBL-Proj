# 08 — Glossary

Plain definitions. Terms you will meet elsewhere in this field are included even where we
don't use them, so these documents also serve as a way into the wider literature.

---

## The essential five

**Churn** — a customer leaving. "5% monthly churn" means 5 of every 100 customers cancel
each month. Compounds brutally: 5% monthly means losing ~46% of customers in a year.

**Sleeping dog** — a customer who would have stayed if you left them alone, but leaves
*because you contacted them*. Usually someone who had forgotten they were paying you.
Your "we miss you" email reminds them. The central problem in
[document 03](03-the-core-insight.md).

**Persuadable** — a customer who would leave if ignored but stays if you act. **The only
customers worth spending money on.**

**Uplift** — the *change* your action causes in someone's behaviour, as opposed to their
likelihood of leaving. Can be positive (helped) or negative (harmed). The number this
project is built around. Also called **treatment effect**.

**Counterfactual** — what *would* have happened under the choice you didn't make. You can
never observe it in real life, which is why measuring cause and effect is hard, and why
we built a simulation where we can.

---

## Kinds of churn

**Voluntary churn** — the customer chose to leave.

**Involuntary churn** — their payment failed. Expired card, insufficient funds, bank
decline. They never decided anything. **20–40% of all churn.**

**Dunning** — the process of recovering failed payments: retrying the card at sensible
times, emailing the customer, requesting a new card. Unglamorous and highly profitable.

**Winback** — persuading someone who already left to return. Often cheaper than
preventing the departure, and consistently underused.

---

## Measuring a business

**MRR (Monthly Recurring Revenue)** — total predictable monthly income.

**CLV / LTV (Customer Lifetime Value)** — total profit expected from a customer over the
whole relationship. Determines how much an intervention is worth.

**CAC (Customer Acquisition Cost)** — what it costs to win one customer. If CAC exceeds
CLV, the business loses money on every sale.

**Retention curve** — the percentage of a group of customers still present after 1, 2, 3…
months. Healthy ones **flatten** — the fragile leave early and the survivors are sturdier.

**Cohort** — a group of customers who joined in the same period, tracked together. Mixing
cohorts hides whether things are improving.

**Gross margin** — revenue left after direct costs. Matters because a discount comes
straight out of it.

**NRR (Net Revenue Retention)** — revenue from existing customers this year versus last,
counting both losses and increased spending. Above 100% means existing customers grow
enough to offset departures.

---

## Types of business

**Contractual** — there is an explicit cancel event you can observe. Netflix, software
subscriptions. **Our focus.**

**Non-contractual** — no cancellation exists; customers simply stop buying. Retail. You
must *infer* whether someone has gone, which is a genuinely harder problem requiring
different mathematics. A later phase.

---

## Statistics and machine learning

**Model** — a program that learns patterns from past data to make predictions about new
cases.

**Churn score** — a model's estimate of how likely a customer is to leave, usually 0 to 1.
Useful for forecasting; **the wrong basis for deciding who to contact.**

**Survival analysis** — statistics developed for medical trials, for the situation where
most subjects haven't had the event *yet*. Handles the fact that a customer who joined
last month and one who has stayed four years are not both simply "didn't churn". Also
answers *when*, not just *whether*.

**Censored** — a customer who hasn't left yet. Not the same as one who won't. Treating
censored customers as "didn't churn" throws away most of your information and biases
results.

**Hazard** — the chance of leaving in a given month, *given* you're still here. Usually
high early (people who never got started), falling as habits form.

**Uplift modelling** — estimating how much your action changes behaviour, per person, so
you can target people you'll *help* rather than people likely to leave. Invented by
telecom companies. Central to this project.

**CATE (Conditional Average Treatment Effect)** — the technical term for "the effect of
acting on a customer like this one."

**Holdout / control group** — customers deliberately *not* contacted, so you can compare
and know your real effect. The only honest way to measure retention work.

**A/B test** — comparing two approaches by randomly assigning people to each. A holdout
is an A/B test where one option is "do nothing".

**Calibration** — whether predicted probabilities are *true*. If you say 20% and it
happens 20% of the time, you're calibrated. More important than accuracy here, because we
make budget decisions with these numbers.

**AUC** — a common accuracy score, 0.5 being random and 1.0 perfect. Around 0.70 is a
respectable churn model. **A better AUC can mean a worse business outcome** — see
[05](05-the-evidence.md).

**Data leakage** — accidentally letting a model use information unavailable at prediction
time. Produces brilliant test results and useless production systems. The most common
serious error in this field.

**Temporal split** — training on earlier data and testing on later, mimicking reality.
The alternative — splitting randomly — leaks the future into the past.

**Overfitting** — memorising the training data instead of learning general patterns.
Especially dangerous with few customers, which is exactly our situation.

**Bayesian methods** — an approach that produces a *range* of plausible answers with their
likelihoods, rather than a single number. Valuable here because with 500 customers, a
confident single number is fiction. Lets the system say "we don't know."

**Hierarchical / multilevel model** — a Bayesian technique where each group (here, each
business) is informed by patterns across all groups. Small businesses borrow strength
from larger ones. The basis of our long-term advantage.

**Prior** — what a Bayesian model assumes before seeing your data. Good priors are what
allow useful answers from small samples.

**Abstention** — declining to make a recommendation when evidence is insufficient. Rare in
commercial systems, and one of our core contributions.

**Qini curve / AUUC** — standard scores for uplift models. Both assume you rank customers
and treat the top slice. Neither accounts for a budget, varying costs, or the option to
do nothing — which is why we also measure **money earned**.

**Simulation** — a computer model of a business used to test methods where reality can't
answer the question. Only meaningful if calibrated against real benchmarks.

**Common random numbers** — a simulation technique using identical random draws across
compared scenarios, so differences reflect the change being tested rather than noise.

---

## The four customer types (summary)

|  | **Stays if contacted** | **Leaves if contacted** |
|---|---|---|
| **Stays if not contacted** | **Sure Thing** — wasted money | **Sleeping Dog** — you caused this |
| **Leaves if not contacted** | **Persuadable** — worth paying for | **Lost Cause** — unreachable |

---

**Back to:** [Start here](00-START-HERE.md) · [The core insight](03-the-core-insight.md)
