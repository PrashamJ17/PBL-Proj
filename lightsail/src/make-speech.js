/** Renders SPEECH.md from script.js — the same text embedded as speaker notes in the deck. */
const fs = require("fs");
const path = require("path");
const script = require("./script.js");

const words = (t) => t.trim().split(/\s+/).length;
const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

const totalWords = script.reduce((a, s) => a + words(s.text), 0);
const totalSecs = script.reduce((a, s) => a + s.seconds, 0);

let cum = 0;
const marks = script.map((s) => {
  const start = cum;
  cum += s.seconds;
  return { ...s, start, end: cum, words: words(s.text) };
});

const L = [];
L.push("# Presentation Speech — Amazon Lightsail (PaaS-Lite): Cloud Infrastructure");
L.push("");
L.push("**Speaker:** Hridiyansh Shukla  ");
L.push("**Registration No.:** 2427030591  ");
L.push("**Deck:** `Amazon_Lightsail_Presentation.pptx` (20 slides)  ");
L.push(`**Length:** ${totalWords} words · **${mmss(totalSecs)}** at a measured 134 words per minute`);
L.push("");
L.push("> This script is the single source of the speaker notes embedded in the `.pptx`.");
L.push("> Every figure spoken aloud appears on the slide in front of you, so the two cannot contradict each other.");
L.push("");
L.push("## How to hit the time");
L.push("");
L.push("| If you speak at | The talk runs |");
L.push("|---|---|");
L.push(`| 125 wpm (deliberate) | ${(totalWords / 125).toFixed(1)} min |`);
L.push(`| 134 wpm (target) | ${(totalWords / 134).toFixed(1)} min |`);
L.push(`| 145 wpm (brisk) | ${(totalWords / 145).toFixed(1)} min |`);
L.push("");
L.push("The whole range sits inside the 10–12 minute brief. Two checkpoints while presenting:");
L.push(`**slide 9 by ${mmss(marks[8].start)}** and **slide 15 by ${mmss(marks[14].start)}**. `);
L.push("If you are running late at slide 15, compress slides 16 and 17 — they are the most cuttable.");
L.push("");
L.push("If you must lose a minute, drop slide 14 (the market comparison) and slide 16 (use cases); ");
L.push("the argument still holds without them. Never cut slides 4, 11 or 19 — they carry the thesis.");
L.push("");
L.push("---");
L.push("");
L.push("## Timing map");
L.push("");
L.push("| Slide | Title | Enter at | Budget | Words |");
L.push("|---:|---|---:|---:|---:|");
marks.forEach((m) => {
  L.push(`| ${m.n} | ${m.title} | ${mmss(m.start)} | ${m.seconds}s | ${m.words} |`);
});
L.push(`| | **Total** | | **${mmss(totalSecs)}** | **${totalWords}** |`);
L.push("");
L.push("---");
L.push("");
L.push("## The script");
L.push("");
marks.forEach((m) => {
  L.push(`### Slide ${m.n} — ${m.title}`);
  L.push("");
  L.push(`\`${mmss(m.start)} – ${mmss(m.end)}\`  ·  *${m.seconds}s · ${m.words} words*`);
  L.push("");
  L.push(`> **Delivery:** ${m.cue}`);
  L.push("");
  L.push(m.text);
  L.push("");
});
L.push("---");
L.push("");
L.push("## Anticipated questions");
L.push("");
const qa = [
  [
    "Is Lightsail just a rebranded EC2 instance?",
    "The compute underneath is EC2, yes — but the product is the packaging: a fixed bundle, a data-transfer allowance, " +
      "a blueprint that boots ready to serve, and a console with most of the configuration removed. " +
      "You are buying a pricing model and a set of defaults, not new hardware.",
  ],
  [
    "Why is it cheaper if it runs on the same hardware?",
    "For compute alone it largely is not — a t3.small is close to the equivalent bundle. The difference is data transfer. " +
      "EC2 bills egress per gigabyte after the first 100 GB; Lightsail includes terabytes in the bundle price. " +
      "AWS is betting most small workloads never use their allowance.",
  ],
  [
    "Can I use IAM roles and other AWS services with it?",
    "Partly. Lightsail permissions are coarse compared with full IAM, which rules it out where least-privilege access is audited. " +
      "You reach the rest of your account through VPC peering — one click connects the Lightsail VPC to your default VPC, " +
      "after which S3, RDS, Lambda and the rest are reachable.",
  ],
  [
    "What happens if I exceed the data-transfer allowance?",
    "You are billed per gigabyte for the overage; the instance is not throttled or stopped. " +
      "Inbound traffic and traffic to other AWS services in the same Region do not count against the allowance.",
  ],
  [
    "Is there vendor lock-in?",
    "Less than with an independent VPS, which is the strategic argument for it. Snapshot export produces a standard AMI " +
      "and EBS snapshot in EC2, so moving up is a supported workflow inside the same account rather than a rebuild elsewhere.",
  ],
  [
    "Should I start a new project on a Bitnami blueprint today?",
    "No. AWS stopped shipping newer Bitnami-packaged images in May 2026, and the WordPress, LAMP, Nginx and Node.js ones " +
      "retire in November 2026. Choose an AWS-maintained blueprint, or a plain OS image and install the stack yourself.",
  ],
];
qa.forEach(([q, a], i) => {
  L.push(`**Q${i + 1}. ${q}**`);
  L.push("");
  L.push(a);
  L.push("");
});

fs.writeFileSync(path.join(__dirname, "..", "SPEECH.md"), L.join("\n"));
console.log(`wrote SPEECH.md — ${totalWords} words, ${mmss(totalSecs)}`);
