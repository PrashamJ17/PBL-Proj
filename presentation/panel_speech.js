// Panel presentation: verbatim speech synced to the 8-slide deck, the success metrics, and
// Q&A preparation. Every number here is one the repository can reproduce; the source command
// or document is named beside it so an answer can be defended, not just recited.
//
//   cd presentation && node panel_speech.js
const fs = require("node:fs");
const path = require("node:path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, Footer, PageNumber, LevelFormat, PageBreak, VerticalAlign,
} = require("docx");

const OUT = process.env.OUT || path.join(__dirname, "RetainIQ_Panel_Speech_and_QA.docx");
const INK = "12263A", TEAL = "0B7A6B", CORAL = "C2410C", MUTED = "5F6F80", MIST = "F2F5F8", LINE = "D5DDE5";
const W = 9638; // A4 portrait content width in DXA

// "**bold**" inside any string becomes a bold run.
const rich = (text, o = {}) => text.split("**").map((part, i) =>
  new TextRun(Object.assign({ text: part, bold: i % 2 === 1 }, o)));
const P = (text, o = {}) => new Paragraph(Object.assign(
  { children: typeof text === "string" ? rich(text) : text, spacing: { after: 110 } }, o));
const H1 = (t) => new Paragraph({ children: [new TextRun(t)], style: "Heading1" });
const H2 = (t) => new Paragraph({ children: [new TextRun(t)], style: "Heading2" });
const H3 = (t) => new Paragraph({ children: [new TextRun(t)], style: "Heading3" });
const bullet = (t) => P(t, { numbering: { reference: "bullets", level: 0 }, spacing: { after: 70 } });
const note = (t) => P(t, { spacing: { after: 130 }, indent: { left: 200 } });

const border = { style: BorderStyle.SINGLE, size: 4, color: LINE };
const borders = { top: border, bottom: border, left: border, right: border };
const cell = (children, width, fill) => new TableCell({
  width: { size: width, type: WidthType.DXA }, borders,
  shading: fill ? { type: ShadingType.CLEAR, fill, color: "auto" } : undefined,
  margins: { top: 80, bottom: 80, left: 110, right: 110 },
  verticalAlign: VerticalAlign.TOP,
  children: (Array.isArray(children) ? children : [children]).map((c) =>
    typeof c === "string" ? P(c, { spacing: { after: 0 } }) : c),
});
const table = (widths, rows) => new Table({
  width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
  rows: rows.map((r, i) => new TableRow({
    tableHeader: i === 0, cantSplit: true,
    children: r.map((c, j) => i === 0
      ? cell(P([new TextRun({ text: c, bold: true, color: "FFFFFF", size: 19 })], { spacing: { after: 0 } }), widths[j], INK)
      : cell(c, widths[j], i % 2 === 0 ? MIST : undefined)),
  })),
});

// A block of words to be said out loud.
const say = (text) => new Paragraph({
  children: rich(text, { size: 25 }),
  shading: { type: ShadingType.CLEAR, fill: "E8F4F1", color: "auto" },
  indent: { left: 160, right: 160 }, spacing: { before: 60, after: 160, line: 300 },
});
const cue = (label, text) => P([
  new TextRun({ text: label.toUpperCase() + "   ", bold: true, color: TEAL, size: 16 }),
  ...rich(text, { size: 20, color: "1B2733" }),
], { spacing: { after: 90 } });

// ---------------------------------------------------------------- the speech
const SLIDES = [
  {
    n: 1, title: "Title — who you are and what this is",
    screen: "Title slide: RetainIQ, your details, and the three numbers on the right.",
    speech:
      "Good morning. I am **Prasham Jain**, registration number 2427030155, and this is **RetainIQ**, " +
      "my project under the guidance of **Dr. Rishi Gupta**. RetainIQ is a decision system for " +
      "subscription businesses. It answers one question: when a customer looks likely to leave, " +
      "should the business spend money on them, and if so, on what? The three numbers on the right " +
      "are the whole argument in miniature, and I will come back to them. In the next few minutes I " +
      "will show you what the system does, what the evidence says, and where it stops.",
    point: "Rest your hand on the three tiles for a second, then move on. Do not explain them yet.",
    ask: "If asked “is this deployed?” — answer now, briefly: “The delivery path is; the decision engine is validated offline only. Slide 8 states that precisely.”",
  },
  {
    n: 2, title: "Context — why churn prediction is the wrong question",
    screen: "42% and 30% statistics, the standard approach, the four-quadrant diagram.",
    speech:
      "Subscription businesses lose about **4.5% of customers every month**, which compounds to roughly " +
      "**42% in a year**, and about **30% of that churn is involuntary** — failed payments, not decisions. " +
      "So retention matters. The standard answer is a churn model: score every customer's risk, then " +
      "send the riskiest ones a discount. That answer is wrong, and this diagram is why. " +
      "Treating a customer has four possible effects. A **Sure Thing** would have stayed anyway, so the " +
      "offer is wasted money. A **Lost Cause** leaves either way. A **Persuadable** would have left but " +
      "stays if contacted — that is the only customer worth paying for. And a **Sleeping Dog** would have " +
      "stayed, but leaves *because* you contacted them: a dormant payer reminded that they are paying you. " +
      "A churn score cannot tell these apart, because risk is not responsiveness. In our simulated " +
      "business, Sleeping Dogs are **59.1% of the churn model's highest-risk decile** and only **5.3% of " +
      "its lowest**. So the highest-risk customers are exactly the ones an offer is most likely to harm. " +
      "That is why this project asks four different questions: who to treat, which offer, at what cost, " +
      "and did it actually work.",
    point: "Walk the quadrants in this order: Sure Thing, Lost Cause, Persuadable, Sleeping Dog. Then the 59.1% line.",
    ask: "“Is the sleeping-dog effect real or assumed?” — In the simulator it is built in, deliberately, because no public dataset contains it. On real data we do not claim it; that is why the worse-than-random result is scoped (slide 6).",
  },
  {
    n: 3, title: "Data and pipeline",
    screen: "Six-stage pipeline, the dataset table, the tools card.",
    speech:
      "This is the pipeline. A billing export, from Stripe or Razorpay, or data from our simulator, " +
      "goes into **preflight**, which asks whether the file means what it appears to mean, and refuses it " +
      "if not. Then features, where every fact carries both when it happened and **when it became known**, " +
      "so the model can never see the future. Then the models, then the money layer that turns a " +
      "predicted effect into rupees, then the outputs: a report, a dashboard, worklists, and a holdout " +
      "ledger for measurement. " +
      "For evidence we use **four real randomised experiments** — Hillstrom with 64,000 customers, " +
      "Criteo with 14 million, Lenta with 687,000, and the Telco and GBSG2 datasets for survival — " +
      "plus our own simulator, SubSim. The simulator exists for one reason: real data never contains " +
      "the counterfactual. You see what happened to the customer you treated, never what would have " +
      "happened if you had left them alone. SubSim generates both, so a model can be scored against " +
      "**per-customer truth**. It is an instrument, not a result: every claim that rests only on the " +
      "simulator is labelled as such.",
    point: "Trace the six boxes left to right with your hand. Pause on box 2 and box 3.",
    ask: "“Why should we believe the simulator?” — Its calibration is enforced in CI against published benchmarks: monthly voluntary churn 0.044, involuntary share 0.32, 24-month retention 0.228. If a change breaks those, the build fails.",
  },
  {
    n: 4, title: "Methodology and architecture",
    screen: "Three model cards, the training-discipline panel, the iteration timeline.",
    speech:
      "Three models, and one decision. " +
      "**First, survival.** A discrete-time hazard model on a person-month table, which handles " +
      "censoring — a customer who has not left yet is not a negative example — and treats voluntary and " +
      "involuntary churn as separate competing risks. " +
      "**Second, the causal effect.** A hierarchical Bayesian model of the treatment effect, where the " +
      "effect on the log-odds of churn is a linear function of the customer's features, with shrinkage so " +
      "that at small sample sizes it defaults to the population effect rather than to noise. We get a " +
      "posterior, not a point estimate. " +
      "**Third, and this is the actual contribution, the decision.** We convert the log-odds effect into " +
      "a change in probability, multiply by what the customer is worth, subtract what the offer costs, " +
      "and treat only if the posterior probability of making money exceeds **70%**. Otherwise the system " +
      "**abstains** — it recommends doing nothing, which is a valid answer. " +
      "On the right is the discipline that makes the numbers trustworthy: strictly temporal splits, " +
      "splitting by customer and never by row, and a leakage audit. That audit matters: with leaky " +
      "features our churn model scores **0.954 AUC**; done honestly, **0.603**. Most of that gap is the " +
      "future leaking into the past. " +
      "At the bottom is the project's own history, including the red marker — a **units error** where a " +
      "log-odds value was multiplied by money. It survived **337 passing tests**, because every test was " +
      "self-consistent. We fixed it, pre-registered what we expected the corrected numbers to be, and " +
      "**two of five predictions failed**. They are in the paper.",
    point: "On the red 'fix' dot, slow down. This is the moment a panel decides whether to trust you.",
    ask: "“How is the Bayesian model fitted?” — A Laplace approximation to the posterior, validated against NUTS sampling, with the shrinkage scale marginalised over a grid.",
  },
  {
    n: 5, title: "Results I — the prediction layer, judged honestly",
    screen: "ROC curve, confusion matrix, feature importance, metric tiles, survival table.",
    speech:
      "Now the metrics. The churn model is a gradient-boosted classifier on eleven observable features, " +
      "trained only on months before the decision month and evaluated on **3,589 customers it had never " +
      "seen**. Its **AUC is 0.700**, and its average precision is **0.118 against a 3.3% base rate**, a " +
      "3.6-fold lift. At the threshold the policy actually uses, the top 20% by risk, it recovers **44.5% " +
      "of the customers who churned**, with **7.4% precision** and an **F1 of 0.127**. " +
      "Note the accuracy tile: **79.6%**, and beside it **96.7%** — which is what you score by predicting " +
      "that nobody ever churns. With a 3% event rate, accuracy rewards doing nothing, so we never report " +
      "it alone. That is the first honest-measurement point in the project. " +
      "On the survival side, our discrete-time hazard model reaches an integrated Brier score of " +
      "**0.0824 on the Telco dataset**, beating Cox regression and Random Survival Forests on **ten of ten " +
      "resplits**, and **tying DeepSurv** — 0.0824 against 0.0825, which is a tie, not a win, and we " +
      "report it as one. On GBSG2, a clinical dataset with fixed covariates, our model **loses**, exactly " +
      "as we predicted in advance, because its advantage is handling covariates that change over time.",
    point: "Point at the 96.7% tile. Say “that is the number that would flatter us, and it is meaningless here.”",
    ask: "“Why is precision only 7.4%?” — Because 3.3% of customers churn in a month. Precision of 7.4% is 2.2× the base rate at a 20% budget. It also does not matter much: the project's argument is that the ranking is the wrong tool, not that it needs tuning.",
  },
  {
    n: 6, title: "Results II — decisions, and the success metrics",
    screen: "Policy value chart, the correlation table, the four stat cards.",
    speech:
      "Here is what those predictions are worth as decisions. Same budget, same 3,589 customers. " +
      "Treating everyone loses **89,869**. Targeting at random loses **17,035**. Targeting by churn score " +
      "loses **22,823** — **worse than random**, on six out of six seeds. That is the founding result: a " +
      "model with respectable AUC, used the standard way, is not merely useless, it is **anti-informative**. " +
      "The last two rows use the simulator's true effects, so they are an upper bound and labelled as one: " +
      "targeting by effect earns 5,877, and adding abstention earns **8,610 while contacting only 209 " +
      "customers instead of 718**. " +
      "The table on the right is our main research contribution. Whether effect-based targeting pays is " +
      "predicted by a single measurable quantity: the **correlation between the estimated effect and the " +
      "estimated risk**. When it is high, the two rankings agree and the simpler model wins: at +0.69, " +
      "uplift modelling is **5.6% worse**. As the correlation falls, the advantage rises: +12.7%, +20.3%, " +
      "and at a negative correlation, **+106.9%**. Subscription retention is the adversarial case. We " +
      "tested this out of sample: before obtaining the Lenta dataset we predicted where it would fall, " +
      "and it landed there. " +
      "The four cards are the honest summary. At 500 customers, the best method beats random on **75% of " +
      "draws** — a business gets one draw, so we report win rate, not the average. Abstention beats risk " +
      "ranking on **93% of draws**, but it does **not** beat doing nothing, because the break-even effect " +
      "is four times the effect the offer delivers. The per-customer offer optimiser wins **58% of the " +
      "time, with a confidence interval from 42 to 72%** — indistinguishable from chance, and we report it " +
      "as a failed gate rather than rounding it up. And the last card is the most consequential finding: " +
      "to detect the retention lift this offer actually delivers, a business needs about **119,500 " +
      "customers**. Below that, a small business cannot measure its own retention campaign at all.",
    point: "Say “worse than random” slowly. Then move to the table without pausing for effect — the argument is the correlation, not the shock.",
    ask: "“So your system does not work?” — See Q&A section F, question 1. Answer with what was established, not with a defence.",
  },
  {
    n: 7, title: "The working system",
    screen: "Dashboard and report screenshots, terminal output, code, engineering chips.",
    speech:
      "This is not only a paper. The system runs end to end. A business sends a billing export; " +
      "**preflight refuses it** if it is unsafe. On screen is a real refusal: Stripe exports amounts in " +
      "cents, so a report built from that file would state every revenue figure **a hundred times too " +
      "high**. It does not silently convert — it asks, and it exits with an error code so an automated " +
      "pipeline stops. " +
      "Once the units are confirmed, it produces the Churn Autopsy report: every loss ranked by money, " +
      "each finding tagged as measured from the data or estimated from benchmarks. " +
      "The dashboard is the decision layer. On a simulated business it recommends contacting **142 of 472 " +
      "customers and leaving 330 alone**, each recommendation carrying an expected gain, a probability " +
      "that it pays, and the reasons behind it — computed exactly from the model, not approximated. The " +
      "first thing on the page is a warning that cannot be switched off, stating that the engine beat one " +
      "well-chosen offer on only 58% of tests. " +
      "Underneath it: **467 automated tests**, continuous integration on three Python versions with four " +
      "gates — tests, calibration, leakage, and the founding experiment itself — and the code, data and " +
      "paper archived on Zenodo with DOIs.",
    point: "If the panel wants to see it live, this is the moment to offer: “I can run it now, it takes about a minute.”",
    ask: "“Can we see it run?” — Yes: `make demo-data`, then preflight, then the dashboard. Have the terminal open on desktop 2.",
  },
  {
    n: 8, title: "Conclusion, readiness and next steps",
    screen: "Three takeaways, production readiness, next steps, references and DOIs.",
    speech:
      "Three takeaways. First, **a churn model can be accurate and still lose money** — ours has an AUC " +
      "of 0.700 and its top slice returns minus 22,823. Second, **one measurable number tells you in " +
      "advance whether causal targeting is worth it**, and we confirmed it on four real randomised trials. " +
      "Third, at the scale of a small business, the binding limits are **reliability and measurability**, " +
      "not the choice of algorithm. " +
      "On readiness I want to be precise, because it differs by component. **Ready**: the delivery path " +
      "from a billing export to a report, the dashboard, and the engineering around them. **Validated " +
      "offline only**: the survival model, the causal model, the offer ladder — on simulation and public " +
      "data. **Not yet shown**: a return on investment for a real client, a policy that beats doing " +
      "nothing, and an optimiser that beats one well-chosen offer. " +
      "So the next steps are a first paying client for the diagnostic report, a live pilot with a " +
      "permanent randomised holdout, and pooling evidence across businesses, because no single small " +
      "business can get past that measurement floor alone. " +
      "The code, the data and the paper are public, with DOIs. Thank you — I am happy to take questions.",
    point: "Say the three readiness levels while pointing at each row. Then stop. Do not fill the silence.",
    ask: "Stop talking after “questions”. Let the panel open.",
  },
];

// Timings are derived from the words above, at a measured speaking pace, so the schedule in
// the document can never drift from the script it is printed beside.
const WPM = 135, GAP = 4;
let clock = 0;
for (const s of SLIDES) {
  s.words = s.speech.replace(/\*\*/g, "").trim().split(/\s+/).length;
  s.start = clock;
  clock += (s.words / WPM) * 60 + GAP;
  s.end = clock;
}
const TOTAL = clock;
const mmss = (x) => `${Math.floor(x / 60)}:${String(Math.round(x % 60)).padStart(2, "0")}`;

// ------------------------------------------------------------------- Q&A bank
const QA = [
  ["A. The questions you will almost certainly be asked", [
    ["What exactly is new here? Ascarza already showed risk targeting is ineffective.",
      "Correct, and I say so in the paper — that is prior work and I do not claim it. My contribution is the **condition**: whether effect-based targeting pays is predicted by corr(τ, π), the correlation between the estimated effect and the estimated risk. I measured it across four real randomised trials and one simulator, it orders them monotonically, and I used it to make an out-of-sample prediction about the Lenta dataset before I obtained the data, which landed. The second contribution is the measurement floor: a business needs about 119,500 customers to detect the effect these offers deliver."],
    ["In one sentence, what does your system do?",
      "It decides which customers are worth spending retention money on, prices that decision in rupees with an explicit uncertainty, and declines to act when the evidence is too thin."],
    ["Why not just use a churn prediction model, like everyone else?",
      "Because risk is not responsiveness. On our simulated business, targeting the top 20% by churn score loses 22,823 while random targeting loses 17,035 — the score actively sorts toward customers an offer harms. The churn model is still in the system; it is just not the targeting rule."],
    ["What are your accuracy numbers?",
      "AUC 0.700 on held-out customers; average precision 0.118 against a 3.3% base rate; at a 20% budget, recall 44.5%, precision 7.4%, F1 0.127. Accuracy is 79.6%, but predicting that nobody churns scores 96.7%, so accuracy is not a meaningful metric at this event rate."],
    ["Did you beat the state of the art?",
      "On survival prediction, yes on two of three baselines: our discrete-time hazard beats Cox and Random Survival Forests on ten of ten resplits on the Telco dataset by integrated Brier score, and ties DeepSurv — 0.0824 against 0.0825. I call that a tie, not a win. On the decision layer, the honest answer is that two of my own gates were not met, and I report them as failures."],
    ["What is your dataset?",
      "Four real randomised trials — Hillstrom 64,000 customers, Criteo-UPLIFT 14 million, Lenta 687,000, plus Telco 7,043 and GBSG2 686 for survival — and SubSim, our own calibrated simulator. Only the simulator has individual ground-truth treatment effects, which is why it exists."],
    ["Is this simulated data? Then how is it valid?",
      "The decision-layer results are simulated, and I label them as such throughout. The simulator's calibration is enforced in continuous integration against published benchmarks. The correlation criterion, which is the main contribution, is measured on **real randomised experiments**, not on the simulator."],
    ["How much of this did you build yourself?",
      "The design, the experiments, the decisions and the verification are mine, and every one is logged with its reasoning in a decision log of 67 entries. I used AI-assisted programming tools for parts of the implementation, under my direction, and the paper declares that explicitly. Every number in the paper was reproduced from the released code before submission."],
    ["Where is it published?",
      "The paper is archived on Zenodo with a DOI, along with the software and a dataset of ground-truth counterfactuals, which is the artifact no public dataset provides. The repository is public under Apache 2.0."],
    ["What is the practical use for a business?",
      "Three things today: it tells them what churn actually costs them and which losses are mechanical, it recovers failed payments, which are about 30% of churn and need no modelling, and it tells them which customers not to spend on. The full decision engine needs a pilot before I would let a business act on it."],
  ]],
  ["B. Methodology", [
    ["Why survival analysis instead of classification?",
      "Because of censoring. A customer who has not churned yet is not a negative example; they are censored. A classifier trained on them is biased, and it cannot answer *when*, which is what sizes the intervention window."],
    ["What is a competing risk, and why separate voluntary and involuntary churn?",
      "They are different processes with different fixes. Involuntary churn is a failed payment and is fixed with retry timing; voluntary churn is a decision and needs a causal approach. Summing them hides the cheapest win a business has."],
    ["What is CATE, and how do you estimate it?",
      "The conditional average treatment effect: how much an offer changes a given customer's churn probability. I model it on the log-odds scale as a linear function of features with hierarchical shrinkage, fitted by a Laplace approximation to the posterior, validated against NUTS sampling."],
    ["Why Bayesian rather than a causal forest or an X-learner?",
      "Because at 500 customers the point estimate is noise and I need the width of the posterior to decide whether to act at all. That said, S-, T- and X-learners are implemented as baselines and appear in the comparisons."],
    ["What is the abstention rule, precisely?",
      "Convert the log-odds effect to a probability change, multiply by customer value, subtract offer cost, and treat only if the posterior probability that this is positive exceeds 1 − α, with α = 0.30. Otherwise recommend nothing."],
    ["How do you prevent data leakage?",
      "Every fact carries an occurrence time and an availability time, and features read only what was available at the decision point. There is an automated leakage suite in CI, including canary injection. Without it, the same model scores AUC 0.954 instead of 0.603."],
    ["How do you split the data?",
      "Strictly temporally: train on months before the decision month, predict at it. Person-month rows are split by customer, never by row, so the same customer cannot appear on both sides. Public datasets with no calendar time are split by subject, and the paper says so."],
    ["How does the simulator generate counterfactuals?",
      "Each customer has latent traits; the hazard is evaluated twice, once treated and once not, under **common random numbers**, so the difference is the true individual effect rather than simulation noise."],
    ["What stops the simulator from being an answer key?",
      "Two CI-enforced guards: no latent trait may appear in the observable panel, and no single observable may correlate with the attention latent above 0.95. Otherwise spotting sleeping dogs would be trivial and the problem would be assumed away."],
    ["What is the offer ladder?",
      "Interventions ordered by margin cost: do nothing, a nudge, a pause, a downgrade, then discounts last. The optimiser picks a rung per customer. On the dashboard, most recommendations are downgrades and only ten are discounts."],
    ["Why is calibration more important than discrimination here?",
      "Because we multiply probabilities by money. A model that ranks well but is miscalibrated produces a confidently wrong budget. That is why we report integrated Brier score and calibration slope, not only C-index."],
    ["What would you do differently with more time?",
      "Derive the correlation criterion analytically rather than only measuring it, and run a real pilot. The derivation is the single change that would most raise the paper's level."],
  ]],
  ["C. Results and statistics", [
    ["Why report win rate instead of the mean?",
      "Because a business gets one draw, not the average of twenty. A method with a good mean that fails half the time is not usable. At n = 500 the best method beats random on 75% of draws; one standard estimator manages 55%."],
    ["Your confidence interval is 42 to 72%. Isn't that just a small sample?",
      "Partly, and more seeds would narrow it. But the honest reading today is that I cannot distinguish the optimiser from chance, so I report it as a gate that was not met rather than as a win."],
    ["Why does abstention not beat doing nothing?",
      "Because break-even requires an effect of 0.040 and the offer delivers 0.010. Even an oracle that knew every customer's true effect would treat only 5.8% of them. The rule correctly declines on about three-quarters of draws and scores exactly zero, which is the right answer, not a profitable one."],
    ["What is the minimum detectable effect, and why does it matter?",
      "It is the smallest effect a holdout of a given size could detect at 80% power. At 10,000 customers it is 0.0374, while the offer delivers 0.0108. To detect that you need about 119,500 customers. So a small business that reports a positive campaign result is usually reporting noise — campaigns looked significant on 0 to 10% of runs, which is just the false-positive rate."],
    ["How do you know the holdout estimator is right?",
      "It was validated against the simulator's known effect: bias centred on zero and interval coverage between 88 and 98%, which is close to the nominal 95%."],
    ["Is 6 out of 6 seeds enough to claim a result?",
      "For the founding experiment yes, because the effect is large and the direction is consistent; the paper states the seed count. For the marginal results — 58%, for instance — I do not claim significance, precisely because the interval is wide."],
    ["Why did worse-than-random not replicate on the real datasets?",
      "Because those are advertising and retail promotions, where the effect and the risk correlate positively. The condition for harm is negative correlation, which is a property of subscription retention. That is the scoping, and it is why the correlation criterion is the contribution rather than the shock result."],
    ["What is the effect size you are targeting, in business terms?",
      "About one percentage point of retention per month on the treated group. Small, which is exactly why measurement is the binding constraint."],
    ["Were any results discarded?",
      "No. Two of five pre-registered predictions failed after a bug fix and they are in the paper, along with two of my own errors and two unmet gates."],
    ["What was the units error, and how did it survive the tests?",
      "The decision rule multiplied a log-odds effect by customer value as if it were a probability difference. On one draw it valued treating at −104.5 when the truth was +20.5. All 337 tests passed because every test was a self-consistency check, and a units error is self-consistent. The fix makes it unrepresentable: the decision function now accepts money only."],
  ]],
  ["D. Engineering and implementation", [
    ["What is the technology stack?",
      "Python 3.11 to 3.13, NumPy, pandas, SciPy, scikit-learn for the churn baseline, lifelines and scikit-survival for Cox and Random Survival Forest baselines, PyTorch for DeepSurv, matplotlib for figures, pytest and ruff, GitHub Actions for CI. The Phase 0 result runs on numpy, pandas and scipy alone."],
    ["How is it tested?",
      "467 automated tests across 22 files, including edge cases, fairness checks and a leakage suite. CI runs four gates on every push: the test suite on three Python versions, the calibration gates, the leakage gate, and the founding experiment. If the founding claim ever stops holding, the build fails."],
    ["How long does the whole thing take to run?",
      "The full check is about two and a half minutes. The founding experiment is a second or two. The dashboard, including a simulated pilot, is about two seconds."],
    ["How would you deploy this for a real client?",
      "Shadow mode first: predict, do not act, for four to eight weeks, and verify calibration on their data. Then a randomised exploration phase. Then policy mode with a permanent 5 to 10% holdout. The holdout ledger is append-only, so nobody can quietly shrink it when results disappoint."],
    ["Does it scale?",
      "The datasets here go to 14 million rows, so ingestion and the survival layer scale. The Bayesian layer is fitted per tenant on hundreds to thousands of customers, which is small by design. Cross-tenant pooling is future work."],
    ["What happens with bad input data?",
      "That is what preflight is for: currency units, date ordering, dates that parse to 1970, insufficient history, no churn signal, and sample size. It blocks rather than converts, because a silent conversion is exactly how a report ends up a hundred times wrong."],
    ["What are the known defects?",
      "Two open: the report formats every amount in rupees even for a dollar-denominated export, and when no invoice file is supplied it shows 0% involuntary churn and still advises fixing involuntary churn first — a zero that means “not measured”. Both are logged and both are being fixed separately."],
    ["Is the code public? Can we run it?",
      "Yes, github.com/PrashamJ17/PBL-Proj, Apache 2.0, with a DOI. `make check` reproduces the verification; `make killtest` reproduces the founding result in seconds."],
  ]],
  ["E. Business, ethics and privacy", [
    ["Who is the customer, and what would they pay?",
      "Subscription businesses with roughly 200 to 2,000 customers, which is the segment enterprise tools ignore. The entry product is a fixed-fee diagnostic report; the long-term model is a base fee plus a share of measured incremental revenue, which is only credible because of the permanent holdout."],
    ["Who are the competitors?",
      "Churn Buster and Paddle Retain for failed payments, Baremetrics and ProfitWell for analytics, Churnkey for cancel flows, Klaviyo for marketing, Gainsight for enterprise customer success. None of them answer the causal question: who is worth treating, and did it work. That gap is the wedge."],
    ["Is it ethical to use AI to decide who gets a discount?",
      "That is why three rules are encoded in the project. Never personalise the base price — only retention offers. Never use protected attributes or their proxies, such as pincode or device type. And log every decision with its reason, so it can be audited and explained."],
    ["What about privacy — GDPR, or India's DPDP Act?",
      "The system would be a data processor, not a controller, so it needs a data-processing agreement with each business. It uses billing and product-usage data, no special-category data, and GDPR Article 22 pushes toward explainability, which is why every recommendation carries its reasons."],
    ["Could this be used manipulatively?",
      "Yes, and the project refuses that version explicitly: no dark patterns in cancellation, discount depth capped, deeper discounts need human approval. Making cancellation hard also invites regulatory attention and destroys the trust the data access depends on."],
    ["What if a business has only 300 customers?",
      "Then the honest answer is that they cannot measure a campaign, and the system should say so rather than sell them a number. They still get the diagnostic and the failed-payment recovery, which do not need a causal model."],
    ["How would you prove ROI to a client?",
      "With a randomised holdout and an interval, not a save rate. Save rate counts customers who would have stayed anyway. The system reports the difference against the holdout, in rupees, with the uncertainty attached."],
    ["What is the business status today?",
      "No paying client yet. That is an open gate and I state it as one on the last slide."],
  ]],
  ["F. Hostile or trap questions — stay calm, answer with evidence", [
    ["So your system does not actually work?",
      "Part of it works and part of it does not, and I can tell you exactly which. The diagnosis works: the churn model, the survival model, the pipeline, and the finding that risk targeting destroys value. The measurement layer works and is validated. What is not yet shown is that the decision engine makes money on a real client, and I report that as an unmet gate rather than dressing it up. A project that only reported its wins would be less useful to you, not more."],
    ["You spent a year building something that recommends doing nothing.",
      "Recommending nothing is worth money here: treating everyone loses 89,869 and targeting by churn score loses 22,823. Knowing not to spend that is the result. It is also why the next step is a pilot, where abstention costs nothing to test."],
    ["Isn't the negative result just because your model is weak?",
      "No, and that is why the oracle rows are in the table. Even with the simulator's **true** effects, an ideal targeter would treat only 5.8% of customers, because break-even needs four times the effect the offer delivers. The limit is the economics, not the estimator."],
    ["This looks like a literature survey with code, not original work.",
      "The correlation criterion is original, it is measured across five settings, and it made a correct out-of-sample prediction before the data was seen. The measurement floor result is original. The simulator with exact counterfactuals is released as a dataset because no public dataset provides it."],
    ["How much of this did an AI write?",
      "AI tools assisted with implementation under my direction, and the paper declares it. What is mine is the problem framing, the experimental design, every decision in a 67-entry log, the pre-registrations, and finding my own units error. I can walk you through any file or any decision and explain why it is that way."],
    ["Why should we accept simulated results at all?",
      "You should not accept them alone, and I do not ask you to. The central claim is measured on four real randomised trials. The simulator is only used where real data cannot help: nowhere on earth is there a dataset that contains both outcomes for the same customer."],
  ]],
  ["G. Fundamentals they may check", [
    ["Churn, MRR, CLV", "Churn is the rate at which customers leave. MRR is monthly recurring revenue. CLV is the expected revenue a customer generates before leaving, discounted."],
    ["Voluntary vs involuntary churn", "A decision to cancel versus a failed payment. About 30% of churn is involuntary."],
    ["Censoring", "A customer who has not left by the end of the data is censored: we know only that they survived past that point, not when they will leave."],
    ["Hazard", "The probability that a customer leaves in this month given that they were still here at the start of it."],
    ["AUC", "The probability that a randomly chosen churner is ranked above a randomly chosen non-churner. 0.5 is random."],
    ["Precision and recall", "Precision is the share of targeted customers who actually churned; recall is the share of churners the model caught."],
    ["Confusion matrix", "Predictions against outcomes: ours at a 20% budget is 53 true positives, 665 false positives, 66 false negatives, 2,805 true negatives."],
    ["Brier score", "Mean squared error of a probability forecast; it measures calibration as well as ranking. Lower is better."],
    ["Confidence interval", "A range that would contain the true value in 95% of repeated experiments. Ours for the optimiser is 42 to 72%, which includes 50%, so chance is not excluded."],
    ["Statistical power and MDE", "Power is the chance of detecting an effect that is really there; the minimum detectable effect is the smallest effect a given sample size can detect at 80% power."],
    ["Holdout / control group", "A randomly chosen set of customers deliberately left untreated, so the difference in outcomes measures the campaign rather than the customers."],
    ["Overfitting and leakage", "Overfitting is learning noise in the training data; leakage is training on information that would not have been available at prediction time. Leakage inflated our AUC from 0.603 to 0.954."],
  ]],
];

// -------------------------------------------------------------- the document
const children = [];
children.push(
  P([new TextRun({ text: "RetainIQ", font: "Cambria", size: 52, bold: true, color: INK })], { spacing: { after: 40 } }),
  P([new TextRun({ text: "Panel presentation: speech, success metrics and Q&A preparation", font: "Cambria", size: 32, color: TEAL })], { spacing: { after: 160 } }),
  P([new TextRun({ text: "Prasham Jain · Reg. No. 2427030155 · Mentor: Dr. Rishi Gupta · Department of Computer Science and Engineering, Manipal University Jaipur", size: 21, color: MUTED })], { spacing: { after: 200 } }),
  table([2600, W - 2600], [
    ["Item", "Detail"],
    [P("Talk length"), `About ${Math.round(TOTAL / 60)} minutes of speech across 8 slides, then questions. A shorter cut and a longer expansion are marked in Section 2.`],
    [P("Pace"), "Roughly 135 words a minute. The speech is written to be said, not read — short sentences, numbers spoken in full."],
    [P("Rule for every number"), "Say it once, clearly, and stop. Do not repeat a figure for emphasis; the panel reads the slide."],
    [P("Sources"), "Every figure comes from the repository: `make killtest`, `make holdout`, `make check`, the paper (DOI 10.5281/zenodo.22009470) and the decision log."],
  ]),
  P([new PageBreak()]),
);

children.push(H1("1. Before you speak"));
[
  "Open the deck in presenter view and check the notes are visible to you only. Every slide's notes name the command behind its numbers.",
  "Have a terminal open on a second desktop, in the repository, with `make demo-data` already run. If the panel asks to see it live, you are 20 seconds away.",
  "Have the demo video ready as a fallback in case a live run misbehaves.",
  "Decide your cut before you start: if the panel looks impatient, drop the pipeline detail on slide 3 and the iteration timeline on slide 4. Never drop slide 6 or the readiness rows on slide 8.",
  "Put the one-page number sheet (Section 5) where you can see it. You will be asked for at least three of those figures.",
].forEach((t) => children.push(bullet(t)));
children.push(note("**Posture on the negative results.** Two gates were not met and you will say so out loud, twice. That is deliberate. A panel that finds an unreported weakness stops trusting everything else; a panel that is told the weakness up front tends to trust the rest."));

children.push(H1("2. The speech, slide by slide"));
children.push(P("The shaded text is what you say. Everything else is for you.", { spacing: { after: 160 } }));
SLIDES.forEach((s) => {
  children.push(H2(`Slide ${s.n} — ${s.title}`));
  children.push(cue("On screen", s.screen + "   ·   " + mmss(s.start) + " – " + mmss(s.end)
    + "   ·   " + s.words + " words"));
  children.push(say(s.speech));
  children.push(cue("Delivery", s.point));
  children.push(cue("If asked here", s.ask));
});
children.push(note("**7-minute cut:** keep slides 1, 2, 5, 6, 8 in full; compress 3 and 4 to two sentences each (“the pipeline refuses unsafe data and never lets the model see the future; three models, and a decision rule priced in rupees that can abstain”); on slide 7 say only the preflight refusal and the test count."));
children.push(note("**15-minute expansion:** after slide 4, add the leakage figure (0.954 against 0.603) and what caused it; after slide 6, add the offer-ladder result and why choosing the offer beats choosing the customer; on slide 7, run the demo live."));

children.push(P([new PageBreak()]));
children.push(H1("3. Success metrics, stated precisely"));
children.push(P("If you are asked “what are your results?”, this table is the answer, in this order. The last column is what makes it credible: gates that were not met are reported as not met."));
children.push(table([2500, 3500, 2000, W - 8000], [
  ["Layer", "Metric", "Result", "Verdict"],
  ["Simulator realism", "7 calibration targets vs published benchmarks", "all within range", "Met, CI-enforced"],
  ["Leakage control", "Honest AUC vs leaked AUC", "0.603 vs 0.954", "Met"],
  ["Churn prediction", "AUC / average precision (base rate 3.3%)", "0.700 / 0.118", "Met"],
  ["Survival model", "Integrated Brier, Telco, 10 resplits", "0.0824", "Met: beats Cox and RSF 10/10; ties DeepSurv"],
  ["Negative control", "GBSG2, fixed covariates", "loses, as predicted", "Met as a control"],
  ["Causal criterion", "corr(τ, π) across 5 settings", "−5.6% → +106.9%", "Met; out-of-sample prediction landed"],
  ["Value of money layer", "Realised value vs churn-score targeting", "−22,823 vs −17,035 random", "Met: the founding result, 6/6 seeds"],
  ["Small-sample reliability", "Share of draws beating random at n = 500", "75%", "Reported, not a pass/fail"],
  ["Abstention", "Draws beating a ranking policy", "93%", "Partial: does not beat doing nothing"],
  ["Offer optimiser", "Draws beating one well-chosen offer", "58%, CI 42–72%", "Not met, reported as such"],
  ["Measurement", "Bias and interval coverage vs known truth", "≈0 bias, 88–98%", "Met"],
  ["Measurement floor", "Customers needed to detect the delivered effect", "≈119,500", "Met as a finding"],
  ["Engineering", "Tests, CI gates, Python versions", "467, 4 gates, 3.11–3.13", "Met"],
  ["Research output", "Paper, software and data archived", "3 Zenodo DOIs", "Met"],
  ["Commercial", "A paying client", "none yet", "Open"],
]));
children.push(note("**Say this line if they push on the unmet gates:** “Two gates were not met. I could have loosened them until they passed. I kept them, because a gate you move is not a gate.”"));

children.push(P([new PageBreak()]));
children.push(H1("4. Question and answer preparation"));
children.push(H2("How to answer anything"));
[
  "**Answer in one sentence first.** Then give the number. Then, only if it helps, the implication. Panels lose patience with preamble.",
  "**Quote a figure you can defend.** Every number in Section 5 has a command behind it. If you are not sure of a figure, say the direction, not a fabricated value.",
  "**If you do not know:** “I do not know. Here is how I would find out, and here is the closest thing I did measure.” That answer is respected; a bluff is not.",
  "**Do not oversell.** If an answer is “this is simulated” or “that gate was not met”, say it plainly and move on. Understating is safer than overstating and the evidence is strong enough.",
  "**Take the question you were asked.** If it is hostile, answer the factual core and skip the framing.",
].forEach((t) => children.push(bullet(t)));

QA.forEach(([section, items]) => {
  children.push(H2(section));
  items.forEach(([q, a], i) => {
    children.push(H3(`${i + 1}. ${q}`));
    children.push(P(a, { spacing: { after: 150 } }));
  });
});

children.push(P([new PageBreak()]));
children.push(H1("5. The numbers, on one page"));
children.push(table([3200, W - 3200], [
  ["Area", "Figures to have ready"],
  ["Founding experiment", "3,589 customers, 20% budget. Do nothing 0 · treat everyone −89,869 · random −17,035 · churn score −22,823 · oracle +5,877 · oracle with abstention +8,610 treating 209. Holds on 6 of 6 seeds."],
  ["Churn model", "AUC 0.700 · average precision 0.118 vs 3.3% base rate · recall 44.5% · precision 7.4% · F1 0.127 · accuracy 79.6% vs 96.7% for “nobody churns” · confusion 53 / 665 / 66 / 2,805."],
  ["Sleeping dogs", "59.1% of the top predicted-risk decile, 5.3% of the bottom, 25.7% of the population."],
  ["Correlation criterion", "Hillstrom men +0.69 → −5.6% · Criteo +0.58 → +0.6% · Hillstrom women +0.19 → +12.7% · Lenta +0.17 → +20.3% · SubSim −0.19 → +106.9%."],
  ["Survival", "Telco IBS: ours 0.0824 · DeepSurv 0.0825 · Cox 0.0914 · RSF 0.0964 · Kaplan–Meier 0.1823. C-index 0.865. GBSG2: ours 0.1867, loses as predicted."],
  ["Reliability and gates", "75% of draws beat random at n = 500 · abstention beats ranking on 93% · optimiser 58%, CI 42–72% · break-even effect 0.040 vs delivered 0.010 · an oracle treats 5.8%."],
  ["Measurement", "Bias ≈ 0, coverage 88–98% · MDE at 10,000 customers 0.0374 vs delivered 0.0108 · ≈119,500 customers needed · campaigns looked significant on 0–10% of runs."],
  ["Leakage", "0.603 honest against 0.954 leaked. Value-at-risk and churn-risk top deciles overlap by only 21%."],
  ["Engineering", "467 tests, 22 files · 4 CI gates · Python 3.11–3.13 · 67 logged decisions · Apache 2.0."],
  ["Outputs", "Paper: ~7,500 words, 12 tables, 5 figures, 27 references. DOIs: paper 10.5281/zenodo.22009470 · software 10.5281/zenodo.22025879 · data 10.5281/zenodo.22025123."],
  ["Demo figures", "Dashboard: 1,500 customers, 472 assessed, 142 to contact, 330 left alone, 131 downgrades, 10 discounts, 1 pause. Sample report: 900 customers, ₹2.6 lakh a year lost, 31% involuntary."],
]));

children.push(H1("6. Rehearsal checklist"));
[
  "Read the speech aloud three times with the deck advancing. Time it against the per-slide targets in Section 2; if you run long, cut from slides 3 and 4, never from 6 or 8.",
  "Rehearse slide 6 alone until you can say “worse than random” without hesitating, and until the correlation table comes out as a story, not a list.",
  "Have someone ask you five questions from Section F, the hostile ones, and answer them standing up.",
  "Practise the sentence “I do not know” once, out loud, so that it is available to you under pressure.",
  "Check the room: HDMI or Type-C adapter, the deck exported to PDF as a backup, the demo video on the laptop, and the repository open in a terminal.",
].forEach((t) => children.push(bullet(t)));
children.push(note("**Last thing before you walk in:** the strongest thing about this project is that it says what it cannot do. Do not lose that in the room. It is what will separate it from every other presentation the panel sees that day."));

const doc = new Document({
  creator: "Prasham Jain", title: "RetainIQ — panel speech and Q&A preparation",
  styles: {
    default: { document: { run: { font: "Calibri", size: 22, color: "1B2733" } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Cambria", size: 34, bold: true, color: INK },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0, keepNext: true } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Calibri", size: 26, bold: true, color: TEAL },
        paragraph: { spacing: { before: 240, after: 100 }, outlineLevel: 1, keepNext: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Calibri", size: 22, bold: true, color: CORAL },
        paragraph: { spacing: { before: 160, after: 60 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 240 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
      new TextRun({ text: "RetainIQ · panel speech and Q&A · page ", size: 16, color: "8A97A6" }),
      new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "8A97A6" }),
    ] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("wrote " + OUT); });
