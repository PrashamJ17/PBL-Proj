// RetainIQ — 8-slide project presentation.
// Every number on these slides comes from a command in the repository; the source is
// named in each slide's speaker notes. Assets come from `python presentation/prepare_assets.py`.
// Run:  TESTS=<n> VIDEO_URL=<google-drive-link> node build_deck.js
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const path = require("path");

const A = path.join(__dirname, "build", "assets");
const VIDEO_URL = (process.env.VIDEO_URL || "").trim();
const TESTS = process.env.TESTS || "466";
const OUT = process.env.OUT || path.join(__dirname, "RetainIQ_Presentation.pptx");

const C = {
  INK: "12263A", INK2: "1D3651", MIST: "F2F5F8", LINE: "D5DDE5", TEXT: "1B2733",
  TEAL: "0F9D8A", TEAL_D: "0B7A6B", TEAL_L: "43C6B1", CORAL: "D9480F", CORAL_L: "FF8A66",
  GOLD: "F2A541", SLATE: "5B7A99", MUTED: "5F6F80", SOFT: "C9D6E3", DIM: "8FA3B8",
};
const HEAD = "Cambria", BODY = "Calibri", MONO = "Courier New";
const REPO = "https://github.com/PrashamJ17/PBL-Proj";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.author = "Prasham Jain";
pres.title = "RetainIQ — Project Presentation";

async function icon(Comp, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Comp, { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
async function aspect(file) {
  const m = await sharp(path.join(A, file)).metadata();
  return m.width / m.height;
}
function T(slide, text, o) {
  slide.addText(text, Object.assign(
    { isTextBox: true, fontFace: BODY, color: C.TEXT, margin: 0, valign: "top" }, o));
}
function header(slide, eyebrow, title, dark = false) {
  T(slide, eyebrow, { x: 0.6, y: 0.34, w: 12.1, h: 0.3, fontSize: 11, bold: true,
    color: dark ? C.TEAL_L : C.TEAL, charSpacing: 2 });
  T(slide, title, { x: 0.6, y: 0.62, w: 12.1, h: 0.72, fontFace: HEAD, fontSize: 30,
    bold: true, color: dark ? "FFFFFF" : C.INK, valign: "middle" });
}
function footer(slide, n, dark = false) {
  const col = dark ? C.DIM : "8A97A6";
  T(slide, "RetainIQ  ·  Prasham Jain (2427030155)  ·  Mentor: Dr. Rishi Gupta  ·  Manipal University Jaipur",
    { x: 0.6, y: 7.1, w: 9.5, h: 0.25, fontSize: 9, color: col });
  T(slide, `${n} / 8`, { x: 11.73, y: 7.1, w: 1.0, h: 0.25, fontSize: 9, color: col, align: "right" });
}
function card(slide, x, y, w, h, fill, extra = {}) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, Object.assign(
    { x, y, w, h, fill: { color: fill }, line: { type: "none" }, rectRadius: 0.08 }, extra));
}
function circleIcon(slide, data, x, y, d, fill) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" } });
  const p = d * 0.25;
  slide.addImage({ data, x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p });
}
const para = (text, opts = {}) => ({ text, options: Object.assign({ breakLine: true }, opts) });

async function main() {
  const I = {
    play: await icon(fa.FaPlay, "FFFFFF"), file: await icon(fa.FaFileAlt, "FFFFFF"),
    filter: await icon(fa.FaFilter, "FFFFFF"), clock: await icon(fa.FaClock, "FFFFFF"),
    brain: await icon(fa.FaBrain, "FFFFFF"), scale: await icon(fa.FaBalanceScale, "FFFFFF"),
    chart: await icon(fa.FaChartLine, "FFFFFF"), target: await icon(fa.FaCrosshairs, "FFFFFF"),
    users: await icon(fa.FaUserCheck, "FFFFFF"), gift: await icon(fa.FaGift, "FFFFFF"),
    coins: await icon(fa.FaCoins, "FFFFFF"), flask: await icon(fa.FaFlask, "FFFFFF"),
    warn: await icon(fa.FaExclamationTriangle, C.CORAL), checkL: await icon(fa.FaCheck, C.TEAL_L),
    vial: await icon(fa.FaVial, "FFFFFF"), branch: await icon(fa.FaCodeBranch, "FFFFFF"),
    shield: await icon(fa.FaShieldAlt, "FFFFFF"), archive: await icon(fa.FaArchive, "FFFFFF"),
    ok: await icon(fa.FaCheckCircle, C.TEAL_L), half: await icon(fa.FaAdjust, C.GOLD),
    no: await icon(fa.FaTimesCircle, C.CORAL_L),
  };

  // ------------------------------------------------------------------ 1. Title
  {
    const s = pres.addSlide(); s.background = { color: C.INK };
    T(s, "PROJECT-BASED LEARNING  ·  B.TECH CSE  ·  V SEMESTER", { x: 0.6, y: 0.55, w: 8, h: 0.3,
      fontSize: 12, bold: true, color: C.TEAL_L, charSpacing: 2 });
    T(s, "RetainIQ", { x: 0.6, y: 0.95, w: 7.8, h: 1.1, fontFace: HEAD, fontSize: 60, bold: true,
      color: "FFFFFF", valign: "middle" });
    T(s, "Deciding who to save: causal retention decisioning for small subscription businesses",
      { x: 0.6, y: 2.1, w: 7.6, h: 0.95, fontSize: 22, color: C.SOFT });
    T(s, [
      para("Prasham Jain  ·  Reg. No. 2427030155", { bold: true, color: "FFFFFF", fontSize: 16 }),
      para("Mentor: Dr. Rishi Gupta", { color: C.SOFT, fontSize: 15 }),
      { text: "Department of Computer Science and Engineering, Manipal University Jaipur",
        options: { color: C.SOFT, fontSize: 15 } },
    ], { x: 0.6, y: 3.35, w: 7.8, h: 1.3, paraSpaceAfter: 6 });

    card(s, 0.6, 5.05, 3.3, 0.64, C.TEAL);
    s.addImage({ data: I.play, x: 0.85, y: 5.23, w: 0.28, h: 0.28 });
    T(s, VIDEO_URL ? [{ text: "Watch the demo video", options: { hyperlink: { url: VIDEO_URL } } }]
                   : "Watch the demo video",
      { x: 1.28, y: 5.05, w: 2.55, h: 0.64, fontSize: 16, bold: true, color: "FFFFFF", valign: "middle" });
    T(s, VIDEO_URL ? [{ text: VIDEO_URL, options: { hyperlink: { url: VIDEO_URL } } }]
                   : "Paste the Google Drive link here",
      { x: 4.1, y: 5.05, w: 4.4, h: 0.64, fontSize: 13, italic: !VIDEO_URL,
        color: VIDEO_URL ? C.SOFT : C.GOLD, valign: "middle" });

    T(s, [
      para("Code: ", { color: C.DIM }),
    ].slice(0, 0).concat([
      { text: "Code  ", options: { color: C.DIM } },
      { text: "github.com/PrashamJ17/PBL-Proj", options: { color: C.SOFT, hyperlink: { url: REPO }, breakLine: true } },
      { text: "DOIs  ", options: { color: C.DIM } },
      { text: "paper 10.5281/zenodo.22009470  ·  software 10.5281/zenodo.22025879  ·  data 10.5281/zenodo.22025123",
        options: { color: C.SOFT } },
    ]), { x: 0.6, y: 6.15, w: 8.2, h: 0.7, fontSize: 11.5, paraSpaceAfter: 4 });

    const tiles = [
      ["0.700", "FFFFFF", "AUC of the churn model on customers it had never seen"],
      ["−22,823", C.CORAL_L, "value lost by giving an offer to that model's top 20%"],
      ["+8,610", C.TEAL_L, "same data: causal targeting that abstains (oracle upper bound)"],
    ];
    tiles.forEach(([v, col, lab], i) => {
      const y = 0.95 + i * 1.72;
      card(s, 8.85, y, 3.9, 1.55, C.INK2);
      T(s, v, { x: 9.15, y: y + 0.18, w: 3.4, h: 0.72, fontFace: HEAD, fontSize: 36, bold: true,
        color: col, valign: "middle" });
      T(s, lab, { x: 9.15, y: y + 0.9, w: 3.45, h: 0.55, fontSize: 12.5, color: C.SOFT });
    });
    T(s, "Simulated subscription business, 3,589 customers; the loss holds on 6 of 6 seeds.",
      { x: 8.85, y: 6.15, w: 3.9, h: 0.55, fontSize: 10.5, color: C.DIM, italic: true });

    s.addNotes(
      "RetainIQ is a retention decision engine for subscription businesses with roughly 200 to 2,000 customers. " +
      "The three numbers on the right are the whole argument of the project in one place. A gradient-boosted churn " +
      "model reaches AUC 0.700 on customers it never saw (make killtest). Giving a retention offer to the top 20% it " +
      "flags loses 22,823 units of value, which is worse than choosing customers at random (-17,035). Using the true " +
      "treatment effects with abstention earns +8,610 on the same budget; that row is an oracle upper bound, not an " +
      "achievable result, and it is labelled that way throughout. Paper DOI 10.5281/zenodo.22009470; software " +
      "10.5281/zenodo.22025879; data 10.5281/zenodo.22025123. Demo video link: see the button.");
  }

  // ------------------------------------------------------- 2. Context & objectives
  {
    const s = pres.addSlide(); s.background = { color: "FFFFFF" };
    header(s, "01  ·  CONTEXT AND OBJECTIVES", "Why churn prediction is the wrong question");

    T(s, "~42%", { x: 0.6, y: 1.45, w: 2.7, h: 0.75, fontFace: HEAD, fontSize: 40, bold: true, color: C.INK, valign: "middle" });
    T(s, "of customers lost in a year at 4.5% monthly voluntary churn, the benchmark SubSim is calibrated to",
      { x: 0.6, y: 2.2, w: 2.95, h: 0.8, fontSize: 12, color: C.MUTED });
    T(s, "30%", { x: 3.85, y: 1.45, w: 2.7, h: 0.75, fontFace: HEAD, fontSize: 40, bold: true, color: C.INK, valign: "middle" });
    T(s, "of all churn is involuntary: failed payments, not a customer's decision",
      { x: 3.85, y: 2.2, w: 2.95, h: 0.8, fontSize: 12, color: C.MUTED });

    T(s, [
      para("What most tools do", { bold: true, fontSize: 15, color: C.INK }),
      para("Score every customer's churn risk, then send the riskiest ones a discount.", { fontSize: 13.5 }),
      para("Why that fails", { bold: true, fontSize: 15, color: C.INK }),
      { text: "Risk is not responsiveness. Some customers leave because they were contacted: the offer reminds a " +
              "dormant payer to cancel (Ascarza, 2018).", options: { fontSize: 13.5 } },
    ], { x: 0.6, y: 3.15, w: 6.25, h: 1.75, paraSpaceAfter: 4 });

    T(s, "Project objectives", { x: 0.6, y: 5.0, w: 6.2, h: 0.32, fontSize: 15, bold: true, color: C.INK });
    const objs = [
      [I.users, "Who to treat", "rank by the offer's effect, not by risk"],
      [I.gift, "Which offer", "the cheapest rung that still pays"],
      [I.coins, "At what cost", "decide in money, with uncertainty"],
      [I.flask, "Did it work", "measure against a randomised holdout"],
    ];
    objs.forEach(([ic, t, d], i) => {
      const x = 0.6 + (i % 2) * 3.2, y = 5.42 + Math.floor(i / 2) * 0.78;
      circleIcon(s, ic, x, y + 0.04, 0.46, C.INK);
      T(s, t, { x: x + 0.6, y, w: 2.5, h: 0.3, fontSize: 13.5, bold: true, color: C.INK });
      T(s, d, { x: x + 0.6, y: y + 0.3, w: 2.55, h: 0.35, fontSize: 11.5, color: C.MUTED });
    });

    // quadrant
    T(s, "If contacted", { x: 8.6, y: 1.42, w: 4.15, h: 0.3, fontSize: 12, bold: true, color: C.MUTED, align: "center" });
    T(s, "stays", { x: 8.6, y: 1.72, w: 2.02, h: 0.28, fontSize: 11.5, color: C.MUTED, align: "center" });
    T(s, "churns", { x: 10.73, y: 1.72, w: 2.02, h: 0.28, fontSize: 11.5, color: C.MUTED, align: "center" });
    T(s, "If left alone", { x: 7.15, y: 1.72, w: 1.35, h: 0.28, fontSize: 12, bold: true, color: C.MUTED, align: "right" });
    T(s, "stays", { x: 7.15, y: 2.05, w: 1.3, h: 1.9, fontSize: 11.5, color: C.MUTED, align: "right", valign: "middle" });
    T(s, "churns", { x: 7.15, y: 4.05, w: 1.3, h: 1.9, fontSize: 11.5, color: C.MUTED, align: "right", valign: "middle" });
    const q = [
      [8.6, 2.05, "E6ECF2", C.INK, "Sure Thing", "Stays either way. The offer is wasted money."],
      [10.73, 2.05, "FBE2D8", C.CORAL, "Sleeping Dog", "Would have stayed; leaves because contacted. The offer destroys value."],
      [8.6, 4.05, "D6F0EB", C.TEAL_D, "Persuadable", "Would have left; stays if contacted. The only customer worth paying for."],
      [10.73, 4.05, "ECEFF2", C.SLATE, "Lost Cause", "Leaves either way. Let them go."],
    ];
    q.forEach(([x, y, fill, col, t, d]) => {
      card(s, x, y, 2.02, 1.9, fill);
      T(s, t, { x: x + 0.18, y: y + 0.18, w: 1.7, h: 0.38, fontFace: HEAD, fontSize: 16, bold: true, color: col });
      T(s, d, { x: x + 0.18, y: y + 0.62, w: 1.7, h: 1.15, fontSize: 12, color: C.TEXT });
    });
    card(s, 7.15, 6.12, 5.6, 0.82, C.MIST);
    s.addImage({ data: I.warn, x: 7.35, y: 6.35, w: 0.34, h: 0.34 });
    T(s, [
      { text: "In the simulated business, Sleeping Dogs are ", options: {} },
      { text: "59.1%", options: { bold: true, color: C.CORAL } },
      { text: " of the churn model's highest-risk decile but only ", options: {} },
      { text: "5.3%", options: { bold: true } },
      { text: " of its lowest.", options: {} },
    ], { x: 7.85, y: 6.12, w: 4.75, h: 0.82, fontSize: 12.5, valign: "middle" });
    footer(s, 2);
    s.addNotes(
      "Why it matters: at 4.5% monthly voluntary churn a business keeps 0.955^12 = 57% of customers after a year, so it " +
      "loses about 42%. Around 30% of churn is involuntary (failed payments). Both are the published SMB-SaaS benchmarks " +
      "the simulator is calibrated to, and the calibration is enforced in CI. " +
      "The quadrant is the core idea. A churn score finds people likely to leave, which mixes Persuadables with Lost " +
      "Causes and Sleeping Dogs. Only Persuadables are worth paying for. Sleeping Dogs are made worse by contact. In " +
      "the simulated business they make up 59.1% of the model's top predicted-risk decile against 5.3% of the bottom " +
      "decile (25.7% overall), which is why risk-ranked targeting loses money. The ineffectiveness of risk targeting " +
      "is prior work (Ascarza, JMR 2018) and is not claimed as new. The objectives are the four questions the system answers.");
  }

  // ------------------------------------------------------------- 3. Data & pipeline
  {
    const s = pres.addSlide(); s.background = { color: "FFFFFF" };
    header(s, "02  ·  DATA AND PIPELINE", "Data and pipeline: from billing export to decision");
    const steps = [
      [I.file, "Ingest", "Stripe or Razorpay CSV export, or the SubSim simulator"],
      [I.filter, "Preflight", "checks units, dates, history; returns BLOCK or READY"],
      [I.clock, "Time-safe data", "features see only what was known at decision time"],
      [I.brain, "Models", "survival hazard and Bayesian causal effect"],
      [I.scale, "Money and policy", "benefit = −Δp·V − c; abstain or pick an offer"],
      [I.chart, "Outputs and proof", "report, dashboard, worklists, holdout ledger"],
    ];
    steps.forEach(([ic, t, d], i) => {
      const x = 0.6 + i * 2.07, y = 1.5;
      card(s, x, y, 1.78, 1.62, C.MIST);
      circleIcon(s, ic, x + 0.14, y + 0.14, 0.44, i === 4 ? C.TEAL : C.INK);
      T(s, String(i + 1), { x: x + 1.3, y: y + 0.16, w: 0.35, h: 0.35, fontFace: HEAD, fontSize: 16, bold: true,
        color: "A9B6C3", align: "right" });
      T(s, t, { x: x + 0.14, y: y + 0.64, w: 1.55, h: 0.32, fontSize: 12.5, bold: true, color: C.INK });
      T(s, d, { x: x + 0.14, y: y + 0.95, w: 1.56, h: 0.62, fontSize: 10, color: C.MUTED });
      if (i < 5) s.addShape(pres.shapes.LINE, { x: x + 1.82, y: y + 0.81, w: 0.21, h: 0,
        line: { color: C.SLATE, width: 1.5, endArrowType: "triangle" } });
    });

    T(s, "Datasets", { x: 0.6, y: 3.3, w: 4, h: 0.3, fontSize: 13, bold: true, color: C.INK });
    const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: C.INK } } });
    const rows = [
      [H("Dataset"), H("Size (rows)"), H("Type"), H("Used for")],
      ["Hillstrom (MineThatData)", "64,000", "RCT · 3 e-mail arms", "correlation test; small-n"],
      ["Criteo-UPLIFT v2.1", "13,979,592", "RCT · advertising", "correlation test"],
      ["Lenta (scikit-uplift)", "687,029", "RCT · retail promotion", "out-of-sample prediction"],
      ["IBM Telco Customer Churn", "7,043 → 7,032", "subscription churn", "survival benchmark"],
      ["GBSG2 (scikit-survival)", "686", "clinical, censored", "negative control"],
      ["SubSim (this project)", "configurable", "simulator, exact effects", "individual ground truth"],
    ].map((r, i) => i === 0 ? r : r.map((c, j) => ({ text: c, options: {
      fill: { color: i % 2 === 0 ? C.MIST : "FFFFFF" }, bold: i === 6 && j === 0, color: C.TEXT } })));
    s.addTable(rows, { x: 0.6, y: 3.63, w: 7.8, colW: [2.3, 1.45, 2.0, 2.05], fontFace: BODY, fontSize: 11,
      rowH: 0.33, valign: "middle", border: { type: "solid", pt: 0.5, color: C.LINE }, margin: [2, 6, 2, 6] });
    T(s, "Preprocessing: temporal splits (train only on months before the decision month); person-month rows split " +
         "by customer, never by row. Telco has no calendar time, so it is split by customer, and TotalCharges is " +
         "dropped as a tenure proxy (r = 0.83). Third-party data is cited, not redistributed; the Zenodo data record " +
         "holds a SHA-256 checksum of each file used.",
      { x: 0.6, y: 6.05, w: 7.8, h: 0.9, fontSize: 10, color: C.MUTED });

    card(s, 8.75, 3.3, 4.0, 3.65, C.MIST);
    T(s, "Tools and libraries", { x: 9.0, y: 3.45, w: 3.5, h: 0.35, fontSize: 14, bold: true, color: C.INK });
    const g = (h, b) => [para(h, { bold: true, color: C.TEAL_D, fontSize: 11.5 }), para(b, { fontSize: 11.5 })];
    T(s, [].concat(
      g("Language and core", "Python 3.11–3.13 · NumPy · pandas · SciPy"),
      g("Machine learning", "scikit-learn (gradient boosting) · lifelines (Cox) · scikit-survival (RSF) · PyTorch (DeepSurv)"),
      g("Engineering", `pytest (${TESTS} tests) · ruff · GitHub Actions CI · headless Chrome and pandoc for reports`),
      [para("Reproducibility", { bold: true, color: C.TEAL_D, fontSize: 11.5 }),
       { text: "Zenodo archives for software, data and paper", options: { fontSize: 11.5 } }],
    ), { x: 9.0, y: 3.85, w: 3.55, h: 3.0, paraSpaceAfter: 3 });
    footer(s, 3);
    s.addNotes(
      "Pipeline: (1) a billing export or the simulator; (2) preflight refuses unsafe files, for example Stripe amounts in " +
      "cents, which would overstate every revenue figure 100x; (3) every fact carries occurred_at and available_at, and " +
      "features only see what was available at decision time; (4) models; (5) the money layer and policy; (6) outputs " +
      "and the holdout ledger. Datasets (Table 1 of the paper): Hillstrom 64,000; Criteo-UPLIFT v2.1 13,979,592; Lenta " +
      "687,029; Telco 7,043 loaded, 7,032 after cleaning; GBSG2 686; SubSim configurable. The four public RCTs have real " +
      "randomised treatment, which is what allows causal evaluation. SubSim exists because no public dataset contains " +
      "individual ground-truth treatment effects. Sources: Hillstrom (2008); Diemert et al. (2018); scikit-uplift; IBM/Kaggle; Schumacher et al. (1994).");
  }

  // -------------------------------------------------------------- 4. Methodology
  {
    const s = pres.addSlide(); s.background = { color: "FFFFFF" };
    header(s, "03  ·  METHODOLOGY AND ARCHITECTURE", "Methodology: three models, one money-based decision");
    const cards = [
      [I.clock, C.INK, "1   Survival: when is a customer likely to leave?",
        "Discrete-time hazard on a person-month table. Voluntary and involuntary churn are separate competing " +
        "risks, customers still subscribed are treated as censored, and features can change each month. " +
        "Benchmarked against Kaplan–Meier, Cox PH, Random Survival Forest and DeepSurv."],
      [I.target, C.INK, "2   Causal effect: would an offer change that?",
        "Hierarchical Bayesian CATE:  logit P(churn) = α + βx + T·(τ₀ + γx).  Shrinkage on γ guards " +
        "against noise at small n. The Laplace posterior is validated against NUTS sampling, and reason codes " +
        "are exact per-feature contributions to τ."],
      [I.scale, C.TEAL, "3   Decision: is it worth the money?",
        "Δp = σ(η₀ + τ) − σ(η₀)   and   benefit = −Δp·V − c.   Treat only if P(benefit > 0) > 1 − α " +
        "(α = 0.30, i.e. 70% confidence); otherwise abstain. The offer ladder picks the rung with the best " +
        "expected value."],
    ];
    cards.forEach(([ic, fill, t, b], i) => {
      const y = 1.45 + i * 1.5;
      card(s, 0.6, y, 7.55, 1.38, C.MIST);
      circleIcon(s, ic, 0.8, y + 0.22, 0.56, fill);
      T(s, t, { x: 1.55, y: y + 0.13, w: 6.45, h: 0.36, fontSize: 15, bold: true, color: C.INK });
      T(s, b, { x: 1.55, y: y + 0.5, w: 6.45, h: 0.84, fontSize: 11.5, color: C.TEXT });
    });

    card(s, 8.45, 1.45, 4.3, 4.38, C.INK);
    T(s, "Training discipline", { x: 8.72, y: 1.62, w: 3.8, h: 0.38, fontSize: 15, bold: true, color: "FFFFFF" });
    const rules = [
      "Temporal splits only: train on months before the decision",
      "Split person-month rows by customer, never by row",
      "Leakage audit: leaky features would show AUC 0.954 against an honest 0.603",
      "Repeated resplits and seeds; report the win rate, not the mean",
      "Predictions pre-registered before fixes; refutations kept",
    ];
    rules.forEach((r, i) => {
      const y = 2.12 + i * 0.73;
      s.addImage({ data: I.checkL, x: 8.72, y: y + 0.05, w: 0.22, h: 0.22 });
      T(s, r, { x: 9.08, y, w: 3.5, h: 0.66, fontSize: 12, color: C.SOFT });
    });

    T(s, "DEVELOPMENT ITERATIONS", { x: 0.6, y: 5.98, w: 4, h: 0.25, fontSize: 10, bold: true, color: C.MUTED, charSpacing: 1.5 });
    s.addShape(pres.shapes.LINE, { x: 0.7, y: 6.36, w: 11.95, h: 0, line: { color: C.LINE, width: 1.5 } });
    const it = [
      ["v0", "churn-score targeting: loses money"], ["v1", "oracle uplift + abstention (upper bound)"],
      ["v2", "Bayesian CATE + abstention"], ["fix", "units bug: log-odds multiplied by money"],
      ["v3", "offer ladder + reason codes"], ["v4", "holdout measurement layer"],
    ];
    it.forEach(([k, t], i) => {
      const x = 0.7 + i * 2.02;
      s.addShape(pres.shapes.OVAL, { x, y: 6.28, w: 0.16, h: 0.16, fill: { color: k === "fix" ? C.CORAL : C.TEAL },
        line: { type: "none" } });
      T(s, [{ text: k + "  ", options: { bold: true, color: k === "fix" ? C.CORAL : C.TEAL_D } },
             { text: t, options: { color: C.TEXT } }],
        { x: x - 0.02, y: 6.5, w: 1.9, h: 0.52, fontSize: 10 });
    });
    footer(s, 4);
    s.addNotes(
      "Model 1: a discrete-time survival model on person-month rows, with voluntary and involuntary churn as competing " +
      "risks (Allison 1982; compared with Cox 1972, Ishwaran et al. 2008, Katzman et al. 2018). Model 2: a hierarchical " +
      "Bayesian conditional average treatment effect, logit P(churn) = alpha + x'beta + T(tau0 + x'gamma), so the effect " +
      "on the log-odds scale is tau0 + x'gamma. The posterior is a Laplace approximation, checked against NUTS (D-053), " +
      "with the shrinkage scale marginalised over a grid (Gelman et al., BDA 2013). Model 3 is the decision: convert the " +
      "log-odds effect to a probability change, then to money, and treat only when the posterior probability of making " +
      "money exceeds 70%. Training discipline is where most churn projects go wrong: a random split lets the model see " +
      "the future. The leakage audit shows the size of that error, AUC 0.954 with leaky features against 0.603 honest " +
      "(Kaufman et al. 2012). The red 'fix' is D-057: the decision rule multiplied a log-odds effect by customer value as " +
      "if it were a probability. All 337 tests passed at the time because every test was a self-consistency check. The " +
      "fix makes the error impossible to express: the rule now accepts money only.");
  }

  // ---------------------------------------------------------- 5. Results I
  {
    const s = pres.addSlide(); s.background = { color: "FFFFFF" };
    header(s, "04  ·  RESULTS I: PREDICTION", "Results I: a sound churn model, judged honestly");
    const H = 2.85, figs = [
      ["roc.png", "ROC curve · held-out month", "3,589 unseen customers; 3.3% churned that month"],
      ["confusion.png", "Confusion matrix · top-20% rule", "threshold = the rule the policy actually uses"],
      ["importance.png", "Churn drivers · permutation importance", "AUC drop when a feature is shuffled (15 repeats)"],
    ];
    const ws = [];
    for (const f of figs) ws.push(H * await aspect(f[0]));
    const gap = (12.13 - ws.reduce((a, b) => a + b, 0)) / 2;
    let x = 0.6;
    figs.forEach(([f, lab, cap], i) => {
      T(s, lab, { x, y: 1.4, w: ws[i] + 0.3, h: 0.32, fontSize: 12.5, bold: true, color: C.INK });
      s.addImage({ path: path.join(A, f), x, y: 1.75, w: ws[i], h: H });
      T(s, cap, { x, y: 4.63, w: ws[i] + 0.3, h: 0.28, fontSize: 10, color: C.MUTED, italic: true });
      x += ws[i] + gap;
    });

    const tiles = [
      ["0.700", "AUC-ROC"], ["44.5%", "recall"], ["7.4%", "precision"],
      ["0.127", "F1 score"], ["79.6%", "accuracy"], ["96.7%", "accuracy of always predicting ‘stays’"],
    ];
    tiles.forEach(([v, l], i) => {
      const tx = 0.6 + (i % 3) * 2.15, ty = 5.02 + Math.floor(i / 3) * 1.0;
      const warn = i === 5;
      card(s, tx, ty, 2.0, 0.9, warn ? "FBE2D8" : C.MIST);
      T(s, v, { x: tx + 0.15, y: ty + 0.06, w: 1.75, h: 0.46, fontFace: HEAD, fontSize: 22, bold: true,
        color: warn ? C.CORAL : C.INK, valign: "middle" });
      T(s, l, { x: tx + 0.15, y: ty + 0.52, w: 1.8, h: 0.34, fontSize: warn ? 9.5 : 11, color: C.MUTED });
    });

    T(s, [
      para("Survival benchmark (Telco, 10 resplits)", { bold: true, fontSize: 12.5, color: C.INK }),
      { text: "Integrated Brier score (lower is better): ties DeepSurv, beats Cox and RSF on 10 of 10 resplits",
        options: { fontSize: 10, color: C.MUTED } },
    ], { x: 7.25, y: 4.97, w: 5.5, h: 0.52 });
    const Hd = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: C.INK } } });
    const srows = [
      [Hd("Model"), Hd("C-index"), Hd("IBS"), Hd("Cal. slope")],
      ["Discrete-time hazard (ours)", "0.865", "0.0824", "1.02"],
      ["DeepSurv", "0.866", "0.0825", "0.98"],
      ["Cox PH", "0.857", "0.0914", "1.18"],
      ["Random Survival Forest", "0.846", "0.0964", "1.18"],
      ["Kaplan–Meier", "—", "0.1823", "—"],
    ].map((r, i) => i === 0 ? r : r.map((c) => ({ text: c, options: {
      bold: i === 1, color: i === 1 ? C.TEAL_D : C.TEXT, fill: { color: i === 1 ? "E3F4F1" : "FFFFFF" } } })));
    s.addTable(srows, { x: 7.25, y: 5.52, w: 5.5, colW: [2.35, 1.0, 1.0, 1.15], fontFace: BODY, fontSize: 10,
      rowH: 0.235, valign: "middle", border: { type: "solid", pt: 0.5, color: C.LINE }, margin: [1, 6, 1, 6] });
    footer(s, 5);
    s.addNotes(
      "All classification metrics are computed from the kill-test model: HistGradientBoosting on 11 observable features, " +
      "trained on 28,283 person-month rows before month 6 and evaluated on the 3,589 customers at month 6, which it never saw. " +
      "AUC 0.700; average precision 0.118 against a 3.3% base rate, a 3.6x lift. At the threshold the policy uses (top 20% " +
      "by predicted risk): TP 53, FP 665, FN 66, TN 2,805; recall 44.5%, precision 7.4%, F1 0.127. Accuracy is 79.6%, which " +
      "is LOWER than the 96.7% you get by predicting that nobody churns. That is why accuracy is not reported as a " +
      "headline metric: with a 3% event rate it rewards doing nothing. The strongest drivers are active seat ratio and " +
      "champion departure. Survival benchmark (paper Table 6): our model's integrated Brier score 0.0824 against " +
      "DeepSurv 0.0825 (a tie, not a win), Cox 0.0914, RSF 0.0964, Kaplan–Meier 0.1823. On GBSG2, the negative control " +
      "with fixed covariates, our model loses, as predicted in advance.");
  }

  // ---------------------------------------------------------- 6. Results II
  {
    const s = pres.addSlide(); s.background = { color: "FFFFFF" };
    header(s, "05  ·  RESULTS II: DECISIONS", "Results II: better prediction does not mean better decisions");

    card(s, 0.6, 1.45, 6.65, 3.95, C.MIST);
    T(s, "Value created by each targeting policy", { x: 0.85, y: 1.57, w: 6.2, h: 0.32, fontSize: 13, bold: true, color: C.INK });
    T(s, "Same 20% budget · 3,589 simulated customers · from  make killtest",
      { x: 0.85, y: 1.88, w: 6.2, h: 0.28, fontSize: 10, color: C.MUTED });
    const bars = [
      ["Do nothing", 0], ["Treat everyone", -89869], ["Random 20%", -17035],
      ["Churn-score top 20%", -22823], ["Oracle uplift top 20% *", 5877], ["Oracle + abstention *", 8610],
    ];
    const CAP = 30000, plotL = 2.95, S = 3.3 / 40000, X0 = plotL + CAP * S;
    s.addShape(pres.shapes.LINE, { x: X0, y: 2.25, w: 0, h: 2.72, line: { color: C.SLATE, width: 1 } });
    bars.forEach(([lab, v], i) => {
      const y = 2.3 + i * 0.44, bh = 0.3;
      T(s, lab, { x: 0.8, y, w: 2.05, h: bh, fontSize: 11, align: "right", valign: "middle",
        bold: lab.startsWith("Churn"), color: lab.startsWith("Churn") ? C.CORAL : C.TEXT });
      if (v < 0) {
        const len = Math.min(-v, CAP) * S;
        s.addShape(pres.shapes.RECTANGLE, { x: X0 - len, y, w: len, h: bh, fill: { color: C.CORAL },
          line: { type: "none" } });
        T(s, (v < -CAP ? "−89,869  (off scale)" : "−" + (-v).toLocaleString("en-US")),
          { x: X0 - len + 0.06, y, w: len - 0.1, h: bh, fontSize: 10.5, bold: true, color: "FFFFFF",
            align: "left", valign: "middle" });
      } else if (v > 0) {
        const len = v * S;
        s.addShape(pres.shapes.RECTANGLE, { x: X0, y, w: len, h: bh, fill: { color: C.TEAL }, line: { type: "none" } });
        T(s, "+" + v.toLocaleString("en-US"), { x: X0 + len + 0.06, y, w: 0.85, h: bh, fontSize: 10.5, bold: true,
          color: C.TEAL_D, valign: "middle" });
      } else {
        T(s, "0", { x: X0 + 0.06, y, w: 0.5, h: bh, fontSize: 10.5, bold: true, color: C.MUTED, valign: "middle" });
      }
    });
    T(s, "* oracle rows use the simulator's true effects: an upper bound, not an achievable result",
      { x: 0.85, y: 5.0, w: 6.25, h: 0.3, fontSize: 9.5, color: C.MUTED, italic: true });

    T(s, [
      para("When does causal (uplift) targeting pay?", { bold: true, fontSize: 13, color: C.INK }),
      { text: "τ = estimated offer effect, π = estimated churn risk", options: { fontSize: 10, color: C.MUTED } },
    ], { x: 7.55, y: 1.45, w: 5.2, h: 0.6 });
    const Hd = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: C.INK } } });
    const cr = [
      ["Hillstrom · men's e-mail", "+0.69", "−5.6%", C.CORAL],
      ["Criteo · advertising", "+0.58", "+0.6%", C.TEXT],
      ["Hillstrom · women's e-mail", "+0.19", "+12.7%", C.TEXT],
      ["Lenta · retail promotion", "+0.17", "+20.3%", C.TEXT],
      ["SubSim · subscription churn", "−0.19", "+106.9%", C.TEAL_D],
    ];
    const crows = [[Hd("Setting"), Hd("corr(τ, π)"), Hd("Uplift advantage")]].concat(cr.map(([a, b, c, col], i) => [
      { text: a, options: { fill: { color: i % 2 ? C.MIST : "FFFFFF" }, bold: i === 4 } },
      { text: b, options: { fill: { color: i % 2 ? C.MIST : "FFFFFF" }, align: "center", bold: i === 4 } },
      { text: c, options: { fill: { color: i % 2 ? C.MIST : "FFFFFF" }, align: "center", bold: true, color: col } },
    ]));
    s.addTable(crows, { x: 7.55, y: 2.1, w: 5.2, colW: [2.3, 1.2, 1.7], fontFace: BODY, fontSize: 11.5, color: C.TEXT,
      rowH: 0.38, valign: "middle", border: { type: "solid", pt: 0.5, color: C.LINE }, margin: [2, 6, 2, 6] });
    T(s, "The lower the correlation between effect and risk, the more causal targeting is worth; retention is the " +
         "adversarial case. Lenta's position was predicted before its data was obtained.",
      { x: 7.55, y: 4.5, w: 5.2, h: 0.8, fontSize: 11, color: C.MUTED });

    const stats = [
      ["75%", "of draws where the best uplift method beats random targeting at n = 500 (real Hillstrom RCT)"],
      ["93%", "of draws where abstaining beats risk ranking; it still does not beat doing nothing"],
      ["58%", "per-customer offer choice vs one well-chosen offer: CI 42–72%, not distinguishable from chance"],
      ["≈119,500", "customers needed to detect the delivered 1.1-point retention lift with a 10% holdout"],
    ];
    stats.forEach(([v, l], i) => {
      const x = 0.6 + i * 3.08;
      card(s, x, 5.58, 2.9, 1.37, i === 3 ? "FBE2D8" : C.MIST);
      T(s, v, { x: x + 0.2, y: 5.66, w: 2.55, h: 0.5, fontFace: HEAD, fontSize: 26, bold: true,
        color: i === 3 ? C.CORAL : C.INK, valign: "middle" });
      T(s, l, { x: x + 0.2, y: 6.18, w: 2.55, h: 0.74, fontSize: 10.5, color: C.TEXT });
    });
    footer(s, 6);
    s.addNotes(
      "Left, from make killtest: with the same 20% budget, targeting by churn score loses 22,823, worse than random " +
      "(-17,035); treating everyone loses 89,869 (bar truncated). The oracle rows use true effects and are upper bounds. " +
      "Right, paper Table 4: across four real randomised trials and the simulator, the gain from uplift modelling rises " +
      "as corr(tau, propensity) falls. When the two rankings agree, the simpler outcome model wins because it estimates " +
      "an easier quantity; the order among the four positive-correlation settings is within noise. Bottom: at n = 500 " +
      "on the real Hillstrom experiment the best uplift method beats random on 75% of draws, which is why win rate is " +
      "reported instead of the mean. The abstention rule beats ranking on 93% of draws but does not beat doing nothing, " +
      "because the break-even effect is four times the delivered effect. The per-customer optimiser wins 58% of draws, " +
      "CI [0.42, 0.72], which is chance. The holdout estimator is unbiased (88–98% interval coverage), but detecting the " +
      "delivered lift of 0.0108 at 80% power needs about 119,500 customers with a 10% holdout (make holdout).");
  }

  // ---------------------------------------------------------- 7. Working system
  {
    const s = pres.addSlide(); s.background = { color: "FFFFFF" };
    header(s, "06  ·  WORKING SYSTEM", "Evidence: the system runs end to end");
    const Hs = 3.45;
    const wd = Hs * await aspect("dash_top.png"), wa = Hs * await aspect("autopsy_top.png");
    s.addImage({ path: path.join(A, "dash_top.png"), x: 0.6, y: 1.45, w: wd, h: Hs,
      line: { color: C.LINE, width: 1 } });
    s.addImage({ path: path.join(A, "autopsy_top.png"), x: 0.6 + wd + 0.2, y: 1.45, w: wa, h: Hs });
    T(s, [para("Retention dashboard", { bold: true, color: C.INK }),
          { text: "make dashboard: contact 142 of 472; the reliability warning always comes first", options: {} }],
      { x: 0.6, y: 5.0, w: wd, h: 0.75, fontSize: 10.5, color: C.MUTED });
    T(s, [para("Churn Autopsy report", { bold: true, color: C.INK }),
          { text: "make sample: losses ranked by money; simulated data is labelled", options: {} }],
      { x: 0.6 + wd + 0.2, y: 5.0, w: wa, h: 0.75, fontSize: 10.5, color: C.MUTED });

    const rx = 0.6 + wd + 0.2 + wa + 0.3, rw = 12.75 - rx;
    card(s, rx, 1.45, rw, 2.45, "0E1B29");
    const L = (t, col) => ({ text: t, options: { color: col || "D6E2EE", breakLine: true } });
    T(s, [
      L("$ python -m retainiq.cli preflight \\", "FFFFFF"),
      L("    --customers customers.csv \\", "FFFFFF"),
      L("    --subscriptions subscriptions.csv", "FFFFFF"),
      L("VERDICT: BLOCKED — do not send a report", C.CORAL_L),
      L("[BLOCK] median MRR 15,312, all integers:", C.GOLD),
      L("        looks like cents (153.12/month)", C.GOLD),
      L("-> re-run with --divide-amounts-by 100"),
      L(" "),
      L("$ python -m retainiq.cli autopsy ... \\", "FFFFFF"),
      L("    --divide-amounts-by 100 --worklists", "FFFFFF"),
      L("VERDICT: READY", C.TEAL_L),
      { text: "wrote report + 2 worklist CSVs", options: { color: "D6E2EE" } },
    ], { x: rx + 0.2, y: 1.58, w: rw - 0.3, h: 2.25, fontFace: MONO, fontSize: 9 });

    card(s, rx, 4.02, rw, 1.73, C.MIST);
    T(s, "retainiq/policy/economics.py  (simplified)", { x: rx + 0.2, y: 4.1, w: rw - 0.3, h: 0.25,
      fontSize: 9.5, bold: true, color: C.MUTED });
    const K = (t, col) => ({ text: t, options: { color: col || C.TEXT, breakLine: true } });
    T(s, [
      K("def benefit_posterior(model, X, value, cost):", C.INK),
      K("    eta0, tau = model.joint_samples(X)  # log-odds"),
      K("    dp = expit(eta0 + tau) - expit(eta0)  # prob."),
      K("    benefit = -dp * value - cost  # money"),
      { text: "    return MoneyPosterior(benefit, dp)", options: { color: C.TEXT } },
    ], { x: rx + 0.2, y: 4.37, w: rw - 0.25, h: 0.85, fontFace: MONO, fontSize: 9 });
    T(s, "After the D-057 fix the decision rule accepts money only, so a log-odds value can never be multiplied by revenue again.",
      { x: rx + 0.2, y: 5.22, w: rw - 0.35, h: 0.5, fontSize: 10, color: C.MUTED, italic: true });

    const chips = [
      [I.vial, `${TESTS} automated tests`, "edge cases, fairness, leakage"],
      [I.branch, "CI on every push", "Python 3.11, 3.12 and 3.13"],
      [I.shield, "4 CI gates", "tests · calibration · leakage · kill test"],
      [I.archive, "Archived releases", "software, data and paper on Zenodo"],
    ];
    chips.forEach(([ic, t, d], i) => {
      const x = 0.6 + i * 3.08;
      card(s, x, 6.0, 2.9, 0.95, C.MIST);
      circleIcon(s, ic, x + 0.16, 6.2, 0.54, i === 2 ? C.TEAL : C.INK);
      T(s, t, { x: x + 0.85, y: 6.13, w: 2.0, h: 0.34, fontSize: 13, bold: true, color: C.INK });
      T(s, d, { x: x + 0.85, y: 6.46, w: 2.0, h: 0.42, fontSize: 10.5, color: C.MUTED });
    });
    footer(s, 7);
    s.addNotes(
      "Screenshots are real outputs, generated by the commands named under them. The dashboard (make dashboard) runs " +
      "the full Phase 5 path on a simulated tenant: a randomised multi-arm pilot, per-offer effect models, a rung per " +
      "customer and a reason for each choice. It recommends contacting 142 of 472 customers and leaving 330 alone, and " +
      "its first element is a warning that the engine beats one good offer on only 58% of tests. The Churn Autopsy " +
      "(make sample) is the report a business receives from its own billing export; the sample is simulated and says so. " +
      "The terminal shows the command-line path on a Stripe-shaped export (make demo-data): preflight blocks the raw " +
      "file because Stripe amounts are cents, which would overstate revenue 100x, and runs once the units are corrected. " +
      "Output is abridged. The code card is the D-057 fix: log-odds become a probability change, then money, in one " +
      "function, and the decision rule accepts nothing else. CI runs four jobs on every push: the test suite on three " +
      "Python versions, the calibration gates, the leakage gate and the kill test.");
  }

  // ------------------------------------------------------------- 8. Conclusion
  {
    const s = pres.addSlide(); s.background = { color: C.INK };
    header(s, "07  ·  CONCLUSION", "Conclusions, readiness and next steps", true);

    card(s, 0.6, 1.45, 3.9, 3.95, C.INK2);
    T(s, "Key takeaways", { x: 0.85, y: 1.6, w: 3.4, h: 0.38, fontSize: 16, bold: true, color: "FFFFFF" });
    const num = { color: C.SOFT, bullet: { type: "number" }, indentLevel: 0 };
    T(s, [
      para("A churn model can be accurate and still lose money: AUC 0.700, yet targeting its top 20% returns −22,823.", num),
      para("One measurable number, corr(τ, π), predicts whether causal targeting pays, confirmed on four real trials.", num),
      { text: "For small businesses, reliability and measurability limit results more than the choice of model.", options: num },
    ], { x: 0.85, y: 2.08, w: 3.45, h: 3.2, fontSize: 12.5, paraSpaceAfter: 10 });

    card(s, 4.72, 1.45, 4.0, 3.95, C.INK2);
    T(s, "Production readiness", { x: 4.97, y: 1.6, w: 3.5, h: 0.38, fontSize: 16, bold: true, color: "FFFFFF" });
    const rd = [
      [I.ok, "Ready", C.TEAL_L, "CLI ingest → preflight → Churn Autopsy; dashboard; tests and 4 CI gates; archived releases"],
      [I.half, "Validated offline only", C.GOLD, "on simulation and public RCTs: survival model; Bayesian CATE with abstention; offer ladder"],
      [I.no, "Not yet shown", C.CORAL_L, "ROI on a real client; beating ‘do nothing’; beating one well-chosen offer"],
    ];
    rd.forEach(([ic, t, col, d], i) => {
      const y = 2.1 + i * 1.08;
      s.addImage({ data: ic, x: 4.97, y: y + 0.03, w: 0.28, h: 0.28 });
      T(s, t, { x: 5.38, y, w: 3.2, h: 0.32, fontSize: 12.5, bold: true, color: col });
      T(s, d, { x: 5.38, y: y + 0.33, w: 3.2, h: 0.68, fontSize: 11, color: C.SOFT });
    });

    card(s, 8.94, 1.45, 3.8, 3.95, C.INK2);
    T(s, "Next steps", { x: 9.19, y: 1.6, w: 3.3, h: 0.38, fontSize: 16, bold: true, color: "FFFFFF" });
    const bul = { color: C.SOFT, bullet: true };
    T(s, [
      para("A first paying Churn Autopsy client (the Phase 2 gate)", bul),
      para("A live pilot with a permanent randomised holdout", bul),
      para("Pool evidence across businesses to get past the measurement floor", bul),
      para("Derive corr(τ, π) analytically, not only measure it", bul),
      { text: "Models for non-contractual (e-commerce) churn", options: bul },
    ], { x: 9.19, y: 2.08, w: 3.35, h: 3.2, fontSize: 12.5, paraSpaceAfter: 8 });

    card(s, 0.6, 5.6, 4.6, 1.35, C.TEAL);
    circleIcon(s, I.play, 0.85, 5.9, 0.72, "0B7A6B");
    T(s, "Demo video", { x: 1.8, y: 5.78, w: 3.2, h: 0.38, fontSize: 17, bold: true, color: "FFFFFF" });
    T(s, VIDEO_URL ? [{ text: VIDEO_URL, options: { hyperlink: { url: VIDEO_URL }, color: "FFFFFF" } }]
                   : "Paste the Google Drive link here",
      { x: 1.8, y: 6.18, w: 3.25, h: 0.6, fontSize: 12, italic: !VIDEO_URL, color: "FFFFFF", underline: !VIDEO_URL });

    card(s, 5.4, 5.6, 7.35, 1.35, C.INK2);
    T(s, "Key references", { x: 5.62, y: 5.68, w: 4, h: 0.28, fontSize: 11, bold: true, color: C.TEAL_L });
    T(s, [
      para("Ascarza (2018) Retention futility, J. Marketing Research  ·  Künzel et al. (2019) Metalearners, PNAS", { color: C.SOFT }),
      para("Cox (1972)  ·  Ishwaran et al. (2008) Random survival forests  ·  Katzman et al. (2018) DeepSurv", { color: C.SOFT }),
      para("Kaufman et al. (2012) Leakage in data mining  ·  Gelman et al. (2013) Bayesian Data Analysis", { color: C.SOFT }),
      { text: "Full reference list: paper, DOI 10.5281/zenodo.22009470  ·  code: github.com/PrashamJ17/PBL-Proj",
        options: { color: C.DIM, hyperlink: { url: REPO } } },
    ], { x: 5.62, y: 5.98, w: 7.0, h: 0.92, fontSize: 9.5, paraSpaceAfter: 1 });
    footer(s, 8, true);
    s.addNotes(
      "Takeaways: prediction quality and decision quality are different things; corr(tau, propensity) tells you in " +
      "advance whether modelling the effect is worth its extra variance; and at small-business scale, reliability and " +
      "measurability are the binding limits. Readiness is stated precisely because the evidence differs by component. " +
      "Ready: the delivery path from a billing export to a report, the dashboard, and the engineering around them " +
      "(tests on three Python versions, four CI gates, archived releases). Validated only on simulation and public " +
      "RCTs: the survival model, the causal model with abstention and the offer ladder. Not yet demonstrated: a real " +
      "client ROI figure, a policy that beats doing nothing, and an optimiser that beats one well-chosen offer. The next " +
      "steps follow directly: a paying client, a live pilot with a permanent holdout, and pooling evidence across " +
      "businesses because no single small business can measure the effect alone.");
  }

  await pres.writeFile({ fileName: OUT });
  console.log("wrote " + OUT);
}
main().catch((e) => { console.error(e); process.exit(1); });
