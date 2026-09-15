// RetainIQ demo video — production script and storyboard (DOCX, A4 landscape).
// Every number in the narration was captured from the commands listed in this document.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, ImageRun, PageOrientation, Footer, PageNumber, LevelFormat,
  VerticalAlign, PageBreak,
} = require("docx");

const TH = path.join(__dirname, "build", "frames", "thumbs");
const OUT = process.env.OUT || path.join(__dirname, "RetainIQ_Demo_Video_Script_and_Storyboard.docx");
const VIDEO_URL = (process.env.VIDEO_URL || "").trim();

const INK = "12263A", TEAL = "0B7A6B", CORAL = "C2410C", MUTED = "5F6F80", MIST = "F2F5F8", LINE = "D5DDE5";
const W = 15110; // landscape A4 content width in DXA (16838 - 2 x 864)

const run = (text, o = {}) => new TextRun(Object.assign({ text }, o));
const P = (children, o = {}) => new Paragraph(Object.assign({
  children: (Array.isArray(children) ? children : [children]).map((c) => typeof c === "string" ? run(c) : c),
  spacing: { after: 100 },
}, o));
const H1 = (t) => new Paragraph({ children: [run(t)], style: "Heading1" });
const H2 = (t) => new Paragraph({ children: [run(t)], style: "Heading2" });
const bullet = (children) => P(children, { numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 } });
const step = (children) => P(children, { numbering: { reference: "steps", level: 0 }, spacing: { after: 70 } });
const code = (lines) => lines.map((l, i) => new Paragraph({
  children: [run(l, { font: "Courier New", size: 18, color: l.startsWith("#") ? MUTED : INK })],
  shading: { type: ShadingType.CLEAR, fill: MIST, color: "auto" },
  spacing: { before: i === 0 ? 60 : 0, after: i === lines.length - 1 ? 140 : 0 },
  indent: { left: 200, right: 200 },
}));
const border = { style: BorderStyle.SINGLE, size: 4, color: LINE };
const borders = { top: border, bottom: border, left: border, right: border };
function cell(children, width, fill, o = {}) {
  return new TableCell(Object.assign({
    width: { size: width, type: WidthType.DXA }, borders,
    shading: fill ? { type: ShadingType.CLEAR, fill, color: "auto" } : undefined,
    margins: { top: 90, bottom: 90, left: 120, right: 120 },
    children: (Array.isArray(children) ? children : [children]).map((c) => typeof c === "string" ? P(c, { spacing: { after: 0 } }) : c),
  }, o));
}
function table(widths, rows, headerFill = INK) {
  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({
      tableHeader: i === 0, cantSplit: true,
      children: r.map((c, j) => i === 0
        ? cell(P(run(c, { bold: true, color: "FFFFFF", size: 19 }), { spacing: { after: 0 } }), widths[j], headerFill)
        : cell(c, widths[j], i % 2 === 0 ? MIST : undefined)),
    })),
  });
}
function img(file, widthPx) {
  const p = path.join(TH, file);
  if (!fs.existsSync(p)) {
    // Scenes 1 and 10 use rendered slides; see presentation/README.md, step 3.
    return run(`[frame ${file} not built yet]`, { italics: true, color: CORAL });
  }
  const buf = fs.readFileSync(p);
  // thumbs are 1600 x 900
  return new ImageRun({ type: "png", data: buf, transformation: { width: widthPx, height: Math.round(widthPx * 900 / 1600) } });
}
const label = (t) => run(t.toUpperCase() + "   ", { bold: true, color: TEAL, size: 16, characterSpacing: 20 });

function scene(s) {
  const left = [
    P([run(`Scene ${s.n}`, { bold: true, color: INK, size: 26, font: "Cambria" })], { spacing: { after: 20 } }),
    P([run(`${s.start} – ${s.end}  ·  ${s.dur}`, { color: MUTED, size: 18 })], { spacing: { after: 120 } }),
    ...s.frames.map((f) => P([img(f, 424)], { spacing: { after: 80 } })),
    P([run(s.frameNote, { italics: true, color: MUTED, size: 16 })], { spacing: { after: 0 } }),
  ];
  const block = (lab, content, o = {}) => P([label(lab), ...(Array.isArray(content) ? content : [run(content, o)])],
    { spacing: { after: 110 } });
  const right = [
    P([run(s.title, { bold: true, color: INK, size: 26, font: "Cambria" })], { spacing: { after: 120 } }),
    block("On screen", s.onScreen),
    block("Action", s.action.map((a, i) => run((i ? "   ·   " : "") + a, { font: a.startsWith("$") ? "Courier New" : "Calibri", size: a.startsWith("$") ? 18 : 21 }))),
    P([label("Narration (verbatim)")], { spacing: { after: 40 } }),
    P([run("“" + s.vo + "”", { size: 22, color: "1B2733" })], {
      shading: { type: ShadingType.CLEAR, fill: "E8F4F1", color: "auto" }, indent: { left: 120, right: 120 },
      spacing: { after: 120 } }),
    block("On-screen text", s.lower, { italics: true }),
    block("Visual cues", s.cues),
    block("Transition", s.transition),
  ];
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: [6600, W - 6600],
    rows: [new TableRow({ cantSplit: true, children: [
      cell(left, 6600, MIST, { verticalAlign: VerticalAlign.TOP }), cell(right, W - 6600, undefined),
    ] })],
  });
}

const SCENES = [
  { n: 1, start: "0:00", end: "0:40", dur: "40 s", title: "Cold open: the wrong question",
    frames: ["s01.png"], frameNote: "Presentation slide 2 (quadrant), full screen.",
    onScreen: "Presentation slide 2. Start on the title, then reveal the four-quadrant diagram.",
    action: ["Screen-record the slide in presenter view off; advance once at “Some customers are persuadable”."],
    vo: "Subscription businesses lose customers every month, and the usual answer is a churn model: score everyone's risk, then send the riskiest customers a discount. RetainIQ starts from a different question. Not “who is likely to leave?”, but “whose decision will an offer actually change, and is it worth the money?” Some customers are persuadable. Some would stay anyway. And some, the sleeping dogs, leave because you contacted them. In the next eight minutes I'll run the system end to end, from a raw billing export to a list of actions, and show where it refuses to guess.",
    lower: "RetainIQ · Prasham Jain · Reg. No. 2427030155 · Mentor: Dr. Rishi Gupta · Manipal University Jaipur",
    cues: "Hold the title 3 s. Soft zoom (110%) on the Sleeping Dog quadrant while it is named.",
    transition: "Cross-dissolve (0.5 s) to the terminal." },
  { n: 2, start: "0:40", end: "1:25", dur: "45 s", title: "The founding experiment: a good model that loses money",
    frames: ["s02.png"], frameNote: "Real output of make killtest.",
    onScreen: "Terminal, dark theme, font 20 pt or larger, repository root.",
    action: ["$ make killtest", "Wait for the table; do not cut the wait if under 10 s."],
    vo: "First, the experiment the project is built on. This trains a gradient-boosted churn model on a simulated subscription business of 3,589 customers, using only information available before the decision month. The model is respectable: an AUC of 0.700 on customers it has never seen. Now watch what happens when we act on it. Giving an offer to its top 20% loses 22,823, worse than picking customers at random, which loses 17,035. The last two rows use the simulator's true effects, so they are an upper bound: targeting by effect, and abstaining when unsure, earns 8,610 on the same budget.",
    lower: "make killtest · simulated business · oracle rows = upper bound",
    cues: "Highlight box on “AUC 0.700”, then on churn_score_top20pct (−22,823) in coral, then on the two oracle rows with the label “upper bound”.",
    transition: "Hard cut." },
  { n: 3, start: "1:25", end: "2:00", dur: "35 s", title: "Raw input: a Stripe-shaped billing export",
    frames: ["s03.png"], frameNote: "Real output of make demo-data and head.",
    onScreen: "Terminal.",
    action: ["$ make demo-data", "$ head -6 demo/subscriptions.csv"],
    vo: "Real engagements start from a billing export, so here is one, shaped exactly like Stripe's: its own column names, timestamps marked UTC, and plan amounts in cents. These rows are randomly generated, so the figures they produce say nothing about retention; they are here to exercise the delivery path. Notice the Plan Amount column: 18,922 means 189 dollars and 22 cents. That detail matters in the next step.",
    lower: "Input: customers.csv + subscriptions.csv (Stripe column names, amounts in cents)",
    cues: "Underline the “Plan Amount” header and the value 18922.",
    transition: "Hard cut." },
  { n: 4, start: "2:00", end: "2:55", dur: "55 s", title: "Preflight: refusing a file that would mislead",
    frames: ["s04.png", "s04b.png"], frameNote: "Real output: preflight blocks (top); autopsy refuses the same file (bottom).",
    onScreen: "Terminal.",
    action: ["$ python -m retainiq.cli preflight --customers demo/customers.csv --subscriptions demo/subscriptions.csv",
      "$ echo $?",
      "$ python -m retainiq.cli autopsy --customers demo/customers.csv --subscriptions demo/subscriptions.csv --out demo/blocked.html",
      "$ ls demo/blocked.html"],
    vo: "Before any report is produced, preflight checks whether the file means what it looks like it means. It blocks this one. The median plan amount is 15,312 and every value is a whole number, which is what cents look like. A report built from it would overstate every revenue figure a hundred times. It does not silently convert; it tells you to confirm with the business. It also flags an assumption: there is no billing-interval column, so every plan would be treated as monthly. The command exits with status 1, and if you ask for the report anyway, it refuses and writes nothing.",
    lower: "Preflight · VERDICT: BLOCKED · exit code 1 · no report written",
    cues: "Coral highlight on “VERDICT: BLOCKED”; gold highlight on the BILLING INTERVAL assumption; zoom on “1” after echo $?; show the “No such file” line from ls.",
    transition: "Hard cut." },
  { n: 5, start: "2:55", end: "4:05", dur: "70 s", title: "Units confirmed: the Churn Autopsy report",
    frames: ["s05a.png", "s05b.png"], frameNote: "Real output: READY run (top); sample report from make sample (bottom).",
    onScreen: "Terminal, then browser showing sample_churn_autopsy.html (built by make sample).",
    action: ["$ python -m retainiq.cli autopsy --customers demo/customers.csv --subscriptions demo/subscriptions.csv --divide-amounts-by 100 --interval month --name \"Acme Analytics (demo data)\" --out demo/demo_autopsy.html --worklists",
      "$ open sample_churn_autopsy.html", "Scroll slowly to the first two findings."],
    vo: "With the units confirmed, the same command runs with divide-amounts-by 100. Preflight now reads a median of 153 a month, which is plausible, and the verdict is READY. It writes the report and two worklist files. Because these demo rows are random, that report's figures mean nothing, so to show how to read a report I'll open the sample built from a realistic simulated business of 900 customers; the yellow banner says it is simulated. Churn costs about 2.6 lakh rupees a year, and 31% of churn is failed payments. Each finding is ranked by money and tagged: green is measured from the data, amber is estimated from benchmarks. The first actions are mechanical: fix involuntary churn, and move payment retries onto payday.",
    lower: "Churn Autopsy · green = measured from data · amber = estimated from benchmarks",
    cues: "Teal highlight on “VERDICT: READY” and the three “wrote” lines. In the browser, point to the simulated-data banner, the ₹2.6 lakh headline, the 31% tile and the ‘What to do’ box.",
    transition: "Cross-dissolve (0.5 s)." },
  { n: 6, start: "4:05", end: "5:10", dur: "65 s", title: "From diagnosis to decisions: the dashboard",
    frames: ["s06.png"], frameNote: "Real output of make dashboard (simulated tenant).",
    onScreen: "Browser showing retention_dashboard.html.",
    action: ["$ make dashboard", "$ open retention_dashboard.html", "Pause on the banner, then on 142, then on the offer chart."],
    vo: "A report describes the problem. Deciding whom to contact needs evidence about how customers respond to offers, and a billing export does not contain that. So the dashboard runs on a simulated business of 1,500 customers, where a randomised pilot assigned offers at random to half of the eligible customers. The first thing on the page is a warning that cannot be turned off: this engine beat one well-chosen offer on 58% of tests, with a 95% interval of 42 to 72%, which is not distinguishable from a coin flip. Then the decision: contact 142 of the 472 customers assessed, and leave 330 alone. Leaving customers alone is a result, not a failure. Most recommendations are downgrade offers, which cost little; only 10 are discounts.",
    lower: "Dashboard · simulated business · 142 to contact, 330 left alone",
    cues: "Gold outline on the banner. Count-up animation on “142”. Highlight the “no offer” bar (330).",
    transition: "Hard cut (same page, scroll)." },
  { n: 7, start: "5:10", end: "6:10", dur: "60 s", title: "Explaining a recommendation, and flagging a weak one",
    frames: ["s07.png"], frameNote: "Real output: rows expanded in the dashboard.",
    onScreen: "Same dashboard, scrolled to “Who to contact”.",
    action: ["Click row 379.", "Click row 146.", "Scroll to and click row 1212 (47%)."],
    vo: "Click any customer to see the reasoning. Customer 379 is worth 9,733 if kept, has a 56% risk of leaving without contact, and this offer moves that risk by 33 points at a cost of 1,422. The expected gain is 1,705, with a 62% chance of paying off. “Why them” lists the features that make the offer more or less likely to work, computed exactly from the model rather than approximated. “Why this offer” names the next-best offer and how much less it is worth. Now the edge case. Customer 1212 has only a 47% chance of making money. It is listed on expected value, but flagged in amber as thin evidence, to be treated as a suggestion, not a finding.",
    lower: "Every recommendation: expected gain · chance it pays · why · caution",
    cues: "Box each label as it is read (why it pays, why them, why this offer). Amber pulse on “47%” and on the caution line.",
    transition: "Cross-dissolve (0.5 s) to the terminal." },
  { n: 8, start: "6:10", end: "6:55", dur: "45 s", title: "Did it work? The measurement floor",
    frames: ["s08.png"], frameNote: "Real output of make holdout (minimum detectable effect table).",
    onScreen: "Terminal.",
    action: ["$ make holdout", "Scroll to the MINIMUM DETECTABLE EFFECT table."],
    vo: "Last question: did it work? RetainIQ assigns a permanent random holdout and measures the difference. Checked against the simulator's known effect, the estimator is unbiased, with intervals that contain the truth 88 to 98% of the time. But look at the minimum detectable effect. The offer really improves retention by about 1.1 points. Even at 10,000 customers, the smallest effect a 10% holdout can detect is 3.7 points. Detecting this one needs about 119,500 customers. A small business cannot measure its own retention campaign alone, which is why pooling evidence across businesses is the next step.",
    lower: "make holdout · 10% holdout · 80% power · α = 0.05",
    cues: "Coral highlight on the “no” column; zoom on “119,501 customers”.",
    transition: "Hard cut." },
  { n: 9, start: "6:55", end: "7:25", dur: "30 s", title: "Quality and reproducibility",
    frames: ["s09.png"], frameNote: "Real output of make check (pre-recorded, sped up).",
    onScreen: "Terminal; optional 3 s of the repository's GitHub Actions page.",
    action: ["$ make check  (record in advance; play at 8x with a “sped up” label)"],
    vo: "Everything shown is reproducible. make check runs the linter, all 467 tests and the simulator's calibration gates. On GitHub, every push re-runs the test suite on Python 3.11, 3.12 and 3.13, plus the calibration gates, a leakage gate and the kill test. The code, the data and the paper are archived on Zenodo.",
    lower: "467 tests · 4 CI gates · github.com/PrashamJ17/PBL-Proj",
    cues: "Label “sped up 8x”. Highlight “467 passed” and both “RESULT: ALL TARGETS MET”.",
    transition: "Cross-dissolve (0.8 s) to the closing slide." },
  { n: 10, start: "7:25", end: "7:55", dur: "30 s", title: "Close: the full workflow and its honest limits",
    frames: ["s10.png"], frameNote: "Presentation slide 8.",
    onScreen: "Presentation slide 8, then a 3 s end card with the repository and DOIs.",
    action: ["Show slide 8; hold on “Production readiness” while it is read."],
    vo: "To recap the flow: a billing export goes through preflight, becomes a report, and, with pilot evidence, becomes a short list of customers to contact, each with a reason and a confidence, while most are deliberately left alone. What is ready is the delivery path and its engineering. What is not yet shown is a real client's return on investment. That is the next step. Thank you.",
    lower: "Code: github.com/PrashamJ17/PBL-Proj · Paper DOI 10.5281/zenodo.22009470",
    cues: "Build the three readiness rows in sequence (green, gold, coral).",
    transition: "Fade to black (1 s)." },
];

async function main() {
  const children = [];

  // ---------------------------------------------------------------- cover
  children.push(
    P([run("RetainIQ — Demo Video", { font: "Cambria", size: 56, bold: true, color: INK })], { spacing: { after: 40 } }),
    P([run("Production script and storyboard", { font: "Cambria", size: 36, color: TEAL })], { spacing: { after: 120 } }),
    P([run("A shooting guide for a working demonstration of the system, written for academic evaluators and technical reviewers who have not seen the code.", { size: 23, color: MUTED })], { spacing: { after: 240 } }),
    table([3300, W - 3300], [
      ["Item", "Detail"],
      [P(run("Project", { bold: true })), "RetainIQ: causal retention decisioning for small subscription businesses"],
      [P(run("Presenter", { bold: true })), "Prasham Jain (Reg. No. 2427030155) · Mentor: Dr. Rishi Gupta · Department of Computer Science and Engineering, Manipal University Jaipur"],
      [P(run("Target runtime", { bold: true })), "7 min 55 s across 10 scenes. Hard ceiling: 9 minutes."],
      [P(run("Delivery format", { bold: true })), "1920 × 1080, 30 fps, H.264 MP4 with AAC audio; SRT captions recommended"],
      [P(run("File name", { bold: true })), "RetainIQ_Demo_PrashamJain_2427030155.mp4"],
      [P(run("Video link", { bold: true })), VIDEO_URL ? VIDEO_URL : P(run("Paste the Google Drive link here after upload, and add the same link to slides 1 and 8 of the presentation.", { italics: true, color: CORAL }))],
      [P(run("Source of every number", { bold: true })), "Captured from the commands in this guide on 15–16 September 2026. Re-run them before recording. If a number on screen differs from the script, say the number on screen."],
    ]),
    P([new PageBreak()]),
  );

  // ------------------------------------------------------------ 1. purpose
  children.push(H1("1. What the video must demonstrate"));
  [
    [run("The complete flow runs, ", { bold: true }), run("from a raw billing export to a list of actions a business can take.")],
    [run("It refuses unsafe input: ", { bold: true }), run("a file in the wrong units is blocked, not silently converted.")],
    [run("Recommendations carry money, confidence and reasons, ", { bold: true }), run("including customers deliberately left alone and a flagged low-confidence case.")],
    [run("Results are measured honestly, ", { bold: true }), run("including the limit on what a small business can measure.")],
    [run("Scope is stated precisely: ", { bold: true }), run("the delivery path is ready; the decision engine is validated on simulated and public data, not yet on a real client.")],
  ].forEach((r) => children.push(bullet(r)));

  // ------------------------------------------------------ 2. pre-production
  children.push(H1("2. Pre-production"));
  children.push(H2("2.1 Environment (macOS or Linux, Python 3.11 or later)"));
  children.push(...code([
    "git clone https://github.com/PrashamJ17/PBL-Proj.git",
    "cd PBL-Proj",
    "python3 -m venv .venv && source .venv/bin/activate",
    "make install",
    "make check        # expect: 467 passed, and RESULT: ALL TARGETS MET twice",
  ]));
  children.push(H2("2.2 Generate every output once before recording"));
  children.push(table([4200, 5400, W - 9600], [
    ["Command", "Writes or prints", "Used in"],
    [P(run("make demo-data", { font: "Courier New", size: 19 })), "demo/customers.csv, demo/subscriptions.csv", "Scenes 3–5"],
    [P(run("make killtest", { font: "Courier New", size: 19 })), "policy value table (AUC 0.700, −22,823)", "Scene 2"],
    [P(run("make sample", { font: "Courier New", size: 19 })), "sample_churn_autopsy.html and two sample worklists", "Scene 5"],
    [P(run("make dashboard", { font: "Courier New", size: 19 })), "retention_dashboard.html", "Scenes 6–7"],
    [P(run("make holdout", { font: "Courier New", size: 19 })), "estimator validation and minimum detectable effect tables", "Scene 8"],
    [P(run("make check", { font: "Courier New", size: 19 })), "lint, 467 tests, calibration gates", "Scene 9 (pre-recorded)"],
  ]));
  children.push(H2("2.3 Screen and audio"));
  [
    "Display at 1920 × 1080. Hide desktop icons, turn on Do Not Disturb, quit chat and mail apps.",
    "Terminal: dark theme, 20 pt monospace font or larger, window maximised, prompt shortened to “$ ”.",
    "Browser: zoom 125%, bookmarks bar hidden, one tab per page, dashboard pre-loaded.",
    "Record screen with QuickTime (File → New Screen Recording) or OBS at 30 fps.",
    "Record narration separately with an external or headset microphone in a quiet room, then lay it over the screen recording. Read the script at about 150 words per minute.",
  ].forEach((t) => children.push(bullet(t)));
  children.push(H2("2.4 Reset between takes"));
  children.push(...code(["rm -rf demo && make demo-data     # restores the raw export exactly (fixed seed)"]));

  // ------------------------------------------------------------ 3. run of show
  children.push(P([new PageBreak()]));
  children.push(H1("3. Run of show"));
  children.push(table([700, 5200, 1100, 1100, 1200, W - 9300], [
    ["#", "Scene", "Start", "End", "Length", "What it proves"],
    ...SCENES.map((s) => [String(s.n), s.title, s.start, s.end, s.dur, ({
      1: "The problem is a decision, not a prediction",
      2: "A sound churn model can still lose money",
      3: "The system starts from real-world input",
      4: "Unsafe input is refused (edge cases)",
      5: "Input becomes a readable, ranked report",
      6: "Recommendations include abstention and a reliability warning",
      7: "Every recommendation is explained; weak ones are flagged",
      8: "Measurement is honest about its limits",
      9: "Results are tested and reproducible",
      10: "End-to-end recap and precise scope",
    })[s.n]]),
    ["", P(run("Total", { bold: true })), "", "", P(run("7:55", { bold: true })), ""],
  ]));

  // ------------------------------------------------------------ 4. scenes
  children.push(P([new PageBreak()]));
  children.push(H1("4. Scene-by-scene script and storyboard"));
  children.push(P([run("Frames are real outputs from the commands shown. Commands prefixed with $ are typed on screen; everything under Narration is read word for word.", { color: MUTED })]));
  // One scene per page: each page is a complete shooting card for that scene.
  SCENES.forEach((s, i) => {
    if (i > 0) children.push(P([new PageBreak()], { spacing: { after: 0 } }));
    children.push(scene(s));
  });

  // ----------------------------------------------------------- 5. edge cases
  children.push(P([new PageBreak()]));
  children.push(H1("5. Edge cases shown, and how each is triggered"));
  children.push(table([3300, 3900, W - 8700 - 1500, 1500], [
    ["Edge case", "How it is triggered", "Expected behaviour (verified)", "Scene"],
    ["Amounts exported in cents", "Raw demo export, unmodified", "Preflight BLOCKED; exit code 1", "4"],
    ["No billing-interval column", "The demo export has none", "Listed as an assumption: every plan treated as monthly", "4"],
    ["Report requested on a blocked file", "autopsy without --divide-amounts-by", "Refuses; exit code 1; no report file is written", "4"],
    ["Units confirmed by the operator", "--divide-amounts-by 100", "READY; the division is recorded as an assumption", "5"],
    ["Customers not worth contacting", "Dashboard decision", "330 of 472 customers left alone", "6"],
    ["Engine reliability not proven", "Dashboard banner", "Always shown first: 58% of tests, 95% CI 42–72%", "6"],
    ["Low-confidence recommendation", "Dashboard row 1212", "47% shown in amber with a “thin evidence” caution", "7"],
    ["Effect too small to measure", "make holdout", "Every size fails to detect it; about 119,500 customers needed", "8"],
    ["Razorpay epoch timestamps and paise", "Automated tests (not on screen)", "Timestamps parsed as seconds; paise blocked like cents", "9 (mention only)"],
  ]));

  // ---------------------------------------------------- 6. interpretation
  children.push(H1("6. How to read the outputs"));
  children.push(table([3000, W - 3000 - 5600, 5600], [
    ["Output", "What it tells you", "Action it informs"],
    ["Preflight verdict", "Whether any figure computed from the file can be trusted; each check is ok or BLOCK, and each assumption is listed.", "BLOCKED: confirm units, dates or columns with the business before any report. Every assumption becomes a question for the client."],
    ["Churn Autopsy report", "What churn costs per year, and each loss ranked by money; green is measured from the data, amber is estimated from benchmarks.", "Fix the largest measured leak first, usually failed-payment recovery, before spending on voluntary churn."],
    ["Worklists (CSV)", "Unrecovered failed payments and recent departures, listed descriptively.", "Operational follow-up lists. They contain no risk scores or predictions, by design."],
    ["Dashboard banner and headline", "How reliable the engine is, and how many customers are worth contacting.", "Treat recommendations as suggestions; the offer mix is more trustworthy than individual names."],
    ["Recommendation row", "Expected gain and chance it pays for one customer, with why it pays, why them, why this offer, and any caution.", "Contact rows with a high chance of paying; treat amber rows (below 60%) as optional; do not contact customers marked “no offer”."],
    ["Minimum detectable effect table", "Whether the business is large enough to measure a campaign with a holdout.", "Keep a permanent holdout. Below the required size, report an interval, not a point estimate, and pool evidence."],
  ]));

  // ------------------------------------------------------ 7. guardrails
  children.push(H1("7. Accuracy guardrails for narration and captions"));
  children.push(P([run("These claims are false or overstated. The evidence for each correction is in the paper and the commands above.", { color: MUTED })]));
  children.push(table([4300, 6200, W - 10500], [
    ["Do not say", "Say instead", "Why"],
    ["“The model predicts churn with 80% accuracy.”", "“The churn model's AUC is 0.700.”", "Accuracy is 79.6%, below the 96.7% scored by predicting that nobody churns."],
    ["“RetainIQ is production-ready and increases revenue.”", "“The delivery path runs end to end and is tested; the decision engine is validated on simulated and public data.”", "No real client ROI has been measured yet."],
    ["“+8,610 is what RetainIQ earns.”", "“+8,610 uses the simulator's true effects, so it is an upper bound.”", "It is the oracle row of the kill test."],
    ["“The engine beats a single offer.”", "“It beat one well-chosen offer on 58% of tests, which is not distinguishable from chance.”", "95% CI 42–72% (D-058)."],
    ["“Abstaining beats doing nothing.”", "“Abstaining beats risk ranking on 93% of draws; it does not beat doing nothing.”", "Paper, Section VI-G."],
    ["“This is a real business.”", "“This is a simulated business.” / “These demo rows are random.”", "The dashboard, the sample report and the demo export are all synthetic."],
  ]));

  // ------------------------------------------------ 8. post-production
  children.push(H1("8. Post-production and upload"));
  [
    "Assemble scenes in order. Trim dead air; keep typing visible. Speed up any wait longer than 10 seconds and label it “sped up”.",
    "Add the on-screen text for each scene as a lower third (bottom-left, 3–5 s).",
    "Add the highlights and zooms listed under Visual cues.",
    "Generate captions automatically, then correct every number and technical term (AUC, preflight, CATE, holdout). Export an SRT file.",
    "Normalise audio to about −16 LUFS and remove background noise.",
    "Export 1920 × 1080, 30 fps, H.264 at 8–12 Mbps. Play the exported file through once.",
    "Watch it against Section 7. Re-record any line that breaks a guardrail.",
    "Upload to Google Drive. Share → General access → “Anyone with the link”, role Viewer → Copy link.",
    "Open the link in a private browser window while signed out, to confirm it plays.",
    "Paste the link into the presentation on slide 1 (the text next to the “Watch the demo video” button) and slide 8 (the Demo video card): select the text, press ⌘K (Ctrl+K on Windows), paste, OK. Paste it on this document's cover as well.",
  ].forEach((t) => children.push(step(t)));

  // ------------------------------------------------------- appendix
  children.push(H1("Appendix A. Command sheet, in recording order"));
  children.push(...code([
    "# Scene 2", "make killtest",
    "# Scene 3", "make demo-data", "head -6 demo/subscriptions.csv",
    "# Scene 4", "python -m retainiq.cli preflight --customers demo/customers.csv --subscriptions demo/subscriptions.csv", "echo $?",
    "python -m retainiq.cli autopsy --customers demo/customers.csv --subscriptions demo/subscriptions.csv --out demo/blocked.html", "ls demo/blocked.html",
    "# Scene 5", "python -m retainiq.cli autopsy --customers demo/customers.csv --subscriptions demo/subscriptions.csv \\",
    "    --divide-amounts-by 100 --interval month --name \"Acme Analytics (demo data)\" --out demo/demo_autopsy.html --worklists",
    "open sample_churn_autopsy.html",
    "# Scenes 6-7", "make dashboard", "open retention_dashboard.html",
    "# Scene 8", "make holdout",
    "# Scene 9 (pre-recorded)", "make check",
  ]));

  const doc = new Document({
    creator: "Prasham Jain", title: "RetainIQ demo video: script and storyboard",
    styles: {
      default: { document: { run: { font: "Calibri", size: 21, color: "1B2733" } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: "Cambria", size: 34, bold: true, color: INK },
          paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 0, keepNext: true } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: "Calibri", size: 24, bold: true, color: TEAL },
          paragraph: { spacing: { before: 200, after: 90 }, outlineLevel: 1, keepNext: true } },
      ],
    },
    numbering: { config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 400, hanging: 260 } } } }] },
      { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 440, hanging: 340 } } } }] },
    ] },
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838, orientation: PageOrientation.LANDSCAPE },
        margin: { top: 864, right: 864, bottom: 864, left: 864 } } },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
        run("RetainIQ demo video · script and storyboard · page ", { size: 16, color: "8A97A6" }),
        new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "8A97A6" }),
      ] })] }) },
      children,
    }],
  });
  fs.writeFileSync(OUT, await Packer.toBuffer(doc));
  console.log("wrote " + OUT);
}
main().catch((e) => { console.error(e); process.exit(1); });
