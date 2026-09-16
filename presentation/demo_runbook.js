// One-page live-demo runbook for the panel: exact commands, what appears, what to say, and
// what to do when something fails. Durations were measured from a clean checkout, not estimated.
//
//   cd presentation && node demo_runbook.js
const fs = require("node:fs");
const path = require("node:path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, Footer, PageNumber, LevelFormat, PageBreak, VerticalAlign,
} = require("docx");

const OUT = process.env.OUT || path.join(__dirname, "RetainIQ_Live_Demo_Runbook.docx");
const INK = "12263A", TEAL = "0B7A6B", CORAL = "C2410C", MUTED = "5F6F80", MIST = "F2F5F8",
  LINE = "D5DDE5", CODEBG = "0E1B29";
const W = 9638;

const rich = (t, o = {}) => t.split("**").map((p, i) => new TextRun(Object.assign({ text: p, bold: i % 2 === 1 }, o)));
const P = (t, o = {}) => new Paragraph(Object.assign(
  { children: typeof t === "string" ? rich(t) : t, spacing: { after: 90 } }, o));
const H1 = (t) => new Paragraph({ children: [new TextRun(t)], style: "Heading1" });
const H2 = (t) => new Paragraph({ children: [new TextRun(t)], style: "Heading2" });
const bullet = (t) => P(t, { numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 } });
// A command as it is typed, on a dark strip so it is findable at a glance.
const cmd = (t) => new Paragraph({
  children: [new TextRun({ text: t, font: "Courier New", size: 17, color: "D6E2EE" })],
  shading: { type: ShadingType.CLEAR, fill: CODEBG, color: "auto" },
  spacing: { before: 40, after: 40 }, indent: { left: 60, right: 60 },
});
const mono = (t, color = INK) => new Paragraph({
  children: [new TextRun({ text: t, font: "Courier New", size: 16, color })], spacing: { after: 40 },
});

const border = { style: BorderStyle.SINGLE, size: 4, color: LINE };
const borders = { top: border, bottom: border, left: border, right: border };
const cell = (children, width, fill) => new TableCell({
  width: { size: width, type: WidthType.DXA }, borders,
  shading: fill ? { type: ShadingType.CLEAR, fill, color: "auto" } : undefined,
  margins: { top: 70, bottom: 70, left: 100, right: 100 }, verticalAlign: VerticalAlign.TOP,
  children: (Array.isArray(children) ? children : [children]).map((c) =>
    typeof c === "string" ? P(c, { spacing: { after: 0 } }) : c),
});
const table = (widths, rows) => new Table({
  width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
  rows: rows.map((r, i) => new TableRow({
    cantSplit: true, tableHeader: i === 0,
    children: r.map((c, j) => i === 0
      ? cell(P([new TextRun({ text: c, bold: true, color: "FFFFFF", size: 18 })], { spacing: { after: 0 } }), widths[j], INK)
      : cell(c, widths[j], i % 2 === 0 ? MIST : undefined)),
  })),
});

// step: [command, seconds, what appears, what to say]
const STEPS = [
  ["make demo-data", "0.7 s",
    "wrote demo/customers.csv and demo/subscriptions.csv",
    "“A real engagement starts from a billing export, so here is one, shaped exactly like Stripe's.”"],
  ["head -3 demo/subscriptions.csv", "instant",
    "Stripe column names; first row Plan Amount **18922**",
    "“Stripe exports money in cents. 18922 is 189 dollars and 22 cents. Watch what the system does with that.”"],
  ["python -m retainiq.cli preflight --customers demo/customers.csv --subscriptions demo/subscriptions.csv", "0.4 s",
    "**VERDICT: BLOCKED**, median MRR 15,312 looks like cents, plus the billing-interval assumption",
    "“It refuses the file. A report built from this would state every revenue figure a hundred times too high. It does not guess — it asks the business.”"],
  ["echo $?", "instant", "**1**",
    "“And it exits non-zero, so an automated pipeline stops here rather than carrying on.”"],
  ["python -m retainiq.cli autopsy --customers demo/customers.csv --subscriptions demo/subscriptions.csv --out demo/blocked.html", "0.5 s",
    "**STOPPED.** Preflight found something that would make the report wrong",
    "“If I ask for the report anyway, it still refuses.”  (optional, but it lands well)"],
  ["ls demo/blocked.html", "instant", "No such file or directory",
    "“And nothing was written.”"],
  ["python -m retainiq.cli autopsy --customers demo/customers.csv --subscriptions demo/subscriptions.csv --divide-amounts-by 100 --interval month --name \"Acme Analytics (demo)\" --out demo/demo_autopsy.html --worklists", "1.3 s",
    "**VERDICT: READY**, median 153.12; writes the report and two worklists",
    "“Once I confirm the units, the same command runs, and the assumption is recorded in the output.”"],
  ["make killtest", "1.4 s",
    "AUC 0.700 and the six-policy table",
    "“This is the experiment the project is built on: a churn model with AUC 0.700, and targeting its top 20% loses 22,823 — worse than random at −17,035.”"],
  ["make sample && open sample_churn_autopsy.html", "1.2 s",
    "The Churn Autopsy report in the browser",
    "“This is what a business receives. Simulated data, and the page says so first. Losses ranked by money; green is measured, amber is estimated from benchmarks.”"],
  ["make dashboard && open retention_dashboard.html", "1.8 s",
    "The decision dashboard",
    "“Contact 142 of 472, leave 330 alone. The warning at the top cannot be switched off. Click a row for the reasons; row 1212 is flagged at a 47% chance of paying.”"],
  ["make holdout", "8.5 s",
    "Estimator validation, then the minimum-detectable-effect table",
    "“Unbiased, 88 to 98% interval coverage — and every size says the effect cannot be detected. You would need about 119,500 customers.”"],
];

const children = [];
children.push(
  P([new TextRun({ text: "RetainIQ — live demo runbook", font: "Cambria", size: 44, bold: true, color: INK })], { spacing: { after: 40 } }),
  P([new TextRun({ text: "Exact commands to run in front of the panel. Durations measured from a clean checkout on 16 September 2026.", size: 21, color: MUTED })], { spacing: { after: 180 } }),
);

children.push(H1("0. Before the panel walks in"));
children.push(P("The whole demo is **under seven seconds of computation**. Everything else is you talking, so nothing needs to be rushed. Do this ten minutes early:"));
children.push(cmd("cd ~/Desktop/pbl-proj && git pull"));
children.push(cmd("make check          # 2 min 20 s — run it NOW, not in front of them"));
children.push(cmd("make sample && make dashboard && rm -rf demo   # warm the caches, then clear the demo folder"));
[
  "`make check` must end with **467 passed** and **RESULT: ALL TARGETS MET** twice. Now you can quote it, and the Python caches are warm so the live commands are instant.",
  "`rm -rf demo` matters: the refusal in step 3 only happens if the export is regenerated live.",
  "Terminal: full screen, font **18–20 pt**, dark theme, `clear` the scrollback.",
  "Browser: close every tab except one blank one. The pages are self-contained files, so no server and no internet is needed.",
  "Have the demo video open in a paused player on another desktop, as the fallback.",
  "Optional, for a clean prompt: `export PS1=\"PBL-Proj $ \"`",
].forEach((t) => children.push(bullet(t)));

children.push(H1("1. The 60-second version"));
children.push(P("If the panel says “just show us that it runs”:"));
children.push(cmd("make killtest"));
children.push(P("Then open the dashboard, point at the banner and at “142 of 472”, and expand one row. Two commands, one page, done."));

children.push(H1("2. The full demo — eleven commands, about four minutes"));
children.push(P("The order matters: the refusal (steps 3–6) is the part panels remember, because it is the opposite of what software usually does."));
children.push(table([3500, 800, 2400, W - 6700], [
  ["Type this", "Takes", "What appears", "What to say"],
  ...STEPS.map(([c, s, appears, say]) => [mono(c, "1B2733"), s, P(appears, { spacing: { after: 0 } }), P(say, { spacing: { after: 0 } })]),
]));
children.push(P("**Stop after `make holdout`.** That is the strongest note to end on: the system measures honestly enough to tell you when it cannot measure at all.", { spacing: { before: 120 } }));

children.push(P([new PageBreak()]));
children.push(H1("3. If they ask for more"));
children.push(table([3800, W - 3800], [
  ["Command", "What it shows"],
  [mono("python -m retainiq.experiments.leakage_penalty"), "The cost of data leakage, in 3 s: **0.606** filtered correctly, 0.615 ignoring availability lag, "
    + "**0.954** with no filter at all — 0.35 AUC of pure fiction. Use this if they ask about leakage."],
  [mono("make abstention"), "The Phase 4 gate: abstention against ranking, in money."],
  [mono("make ladder"), "The Phase 5 gate: per-customer offer choice, 58% with CI 42–72%."],
  [mono("make sensitivity"), "Why that gate could not be passed: break-even 0.040 against a delivered 0.010."],
  [mono("make survival"), "Cox, Random Survival Forest and DeepSurv head-to-head. **Needs `make install-survival` first** — do not run this cold."],
  [mono("make check"), "Lint, 467 tests, calibration gates. 2 min 20 s: offer it, say it has already been run."],
  [mono("make help"), "Every command the project exposes."],
  [mono("open docs/DECISIONS.md"), "67 logged decisions with their reasoning, including the two bugs found in our own code."],
]));

children.push(H1("4. If something goes wrong"));
children.push(table([3200, W - 3200], [
  ["Symptom", "Do this"],
  ["Any command throws an error", "**Do not debug in the room.** Say “I'll show you the trace afterwards”, switch to the demo video, and carry on. The video covers the same eight steps."],
  ["`make: command not found`", "You are on a machine without make. Run the underlying commands: `python -m retainiq.experiments.kill_test`, `python -m retainiq.cli preflight ...`"],
  ["`ModuleNotFoundError` / wrong Python", "`source .venv/bin/activate`, then `make install`. This is why you run `make check` before they arrive."],
  ["Preflight says READY when you wanted BLOCKED", "The demo folder was left over from an earlier run with corrected units. `rm -rf demo && make demo-data`, then retry."],
  ["Browser does not open the file", "The HTML is self-contained: drag `retention_dashboard.html` onto the browser window, or use the tab you pre-opened."],
  ["Dashboard rows will not expand", "Click directly on the row, not on the offer chip. If it still fails, the expanded view is in the video and in the storyboard."],
  ["No internet in the room", "Nothing here needs it. Say so — it is a point in your favour."],
  ["Laptop will not connect to the projector", "Present from the exported PDF of the deck on their machine, and play the MP4. Keep both on a USB drive."],
]));

children.push(H1("5. Running it on a machine that has never seen it"));
children.push(P("Do this **the day before**, never in the room: the install needs the internet and a few minutes."));
children.push(cmd("git clone https://github.com/PrashamJ17/PBL-Proj.git"));
children.push(cmd("cd PBL-Proj && python3 -m venv .venv && source .venv/bin/activate"));
children.push(cmd("make install        # needs Python 3.11 or newer"));
children.push(cmd("make check          # expect 467 passed, RESULT: ALL TARGETS MET twice"));
children.push(P("Then run section 0 to warm the caches. If the machine is Windows without make, every target is a plain Python command — `make help` lists them and the Makefile shows each one."));

children.push(H1("6. The three things to say while your hands are busy"));
[
  "While preflight blocks the file: **“The most valuable thing this does is refuse to produce a confident wrong number.”**",
  "While the dashboard loads: **“It recommends contacting 142 of 472 customers and leaving 330 alone. Abstaining is a result, not a failure.”**",
  "While the holdout table prints: **“This is the finding I did not expect: at this scale, the business cannot measure its own campaign.”**",
].forEach((t) => children.push(bullet(t)));

const doc = new Document({
  creator: "Prasham Jain", title: "RetainIQ — live demo runbook",
  styles: {
    default: { document: { run: { font: "Calibri", size: 21, color: "1B2733" } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Cambria", size: 30, bold: true, color: INK },
        paragraph: { spacing: { before: 260, after: 120 }, outlineLevel: 0, keepNext: true } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Calibri", size: 24, bold: true, color: TEAL },
        paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 1, keepNext: true } },
    ],
  },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 340, hanging: 230 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1000, right: 1000, bottom: 1000, left: 1000 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
      new TextRun({ text: "RetainIQ · live demo runbook · page ", size: 16, color: "8A97A6" }),
      new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "8A97A6" }),
    ] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("wrote " + OUT); });
