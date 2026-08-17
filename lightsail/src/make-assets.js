/**
 * Generates every figure and icon used by the Amazon Lightsail deck and report.
 * SVG is authored here and rasterised with sharp so the deck carries real PNGs.
 */
const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const OUT = path.join(__dirname, "..", "assets");
fs.mkdirSync(OUT, { recursive: true });

// AWS-derived palette (Squid Ink / Smile Orange) — see deck.js
const NAVY = "#232F3E";
const NAVY_2 = "#33475B";
const ORANGE = "#FF9900";
const TEAL = "#00A1C9";
const GREEN = "#7AA116";
const GREY = "#5A6B7B";
const LIGHT = "#EDF1F4";
const PAPER = "#FFFFFF";
const FONT = "DejaVu Sans, Liberation Sans, Arial, Helvetica, sans-serif";

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function svgDoc(w, h, body, bg = PAPER) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
<rect width="${w}" height="${h}" fill="${bg}"/>
<g font-family="${FONT}">${body}</g></svg>`;
}

function text(x, y, str, { size = 22, fill = NAVY, weight = "normal", anchor = "start", spacing = 0 } = {}) {
  return `<text x="${x}" y="${y}" font-size="${size}" fill="${fill}" font-weight="${weight}" text-anchor="${anchor}"${
    spacing ? ` letter-spacing="${spacing}"` : ""
  }>${esc(str)}</text>`;
}

function rect(x, y, w, h, { fill = LIGHT, r = 10, stroke = "none", sw = 0 } = {}) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
}

/** Word-wrap helper: splits into lines of at most `max` characters. */
function wrap(str, max) {
  const words = String(str).split(" ");
  const lines = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length <= max) cur = (cur + " " + w).trim();
    else {
      if (cur) lines.push(cur);
      cur = w;
    }
  }
  if (cur) lines.push(cur);
  return lines;
}

function multiline(x, y, str, max, lh, opts = {}) {
  return wrap(str, max)
    .map((ln, i) => text(x, y + i * lh, ln, opts))
    .join("");
}

async function write(name, svg) {
  await sharp(Buffer.from(svg)).png().toFile(path.join(OUT, name));
  console.log("wrote", name);
}

/* ------------------------------------------------------------------ *
 * FIGURE 1 — Cloud service models: who manages which layer
 * ------------------------------------------------------------------ */
function figServiceModels() {
  const W = 1600,
    H = 940;
  const rows = ["Data", "Application", "Runtime / Middleware", "Operating System", "Virtualisation", "Servers / Compute", "Storage", "Networking"];
  const cols = [
    { name: "On-Premises", sub: "your data centre", plan: ["C", "C", "C", "C", "C", "C", "C", "C"] },
    { name: "IaaS", sub: "Amazon EC2", plan: ["C", "C", "C", "C", "P", "P", "P", "P"] },
    { name: "PaaS-Lite", sub: "Amazon Lightsail", plan: ["C", "C", "S", "S", "P", "P", "P", "P"] },
    { name: "PaaS", sub: "Beanstalk / Heroku", plan: ["C", "C", "P", "P", "P", "P", "P", "P"] },
    { name: "SaaS", sub: "Microsoft 365", plan: ["P", "P", "P", "P", "P", "P", "P", "P"] },
  ];
  const styleOf = { C: [NAVY, "#FFFFFF", "You manage"], S: [TEAL, "#FFFFFF", "Shared"], P: [ORANGE, NAVY, "AWS manages"] };

  const labelW = 300, x0 = 316, gap = 8;
  const colW = (W - x0 - 20 - gap * (cols.length - 1)) / cols.length;
  const headY = 46, headH = 84;
  const yTop = headY + headH + 18, rowGap = 6;
  const rowH = (H - yTop - 110 - rowGap * (rows.length - 1)) / rows.length;

  let b = "";
  // Column headers — the Lightsail column is emphasised.
  cols.forEach((c, i) => {
    const x = x0 + i * (colW + gap);
    const hot = c.name === "PaaS-Lite";
    b += rect(x, headY, colW, headH, { fill: hot ? NAVY : "#DDE4EA", r: 8 });
    b += text(x + colW / 2, headY + 36, c.name, { size: 26, weight: "bold", anchor: "middle", fill: hot ? ORANGE : NAVY });
    b += text(x + colW / 2, headY + 65, c.sub, { size: 18, anchor: "middle", fill: hot ? "#C9D3DC" : GREY });
  });
  // Row labels + cells
  rows.forEach((r, ri) => {
    const y = yTop + ri * (rowH + rowGap);
    b += text(labelW, y + rowH / 2 + 8, r, { size: 22, anchor: "end", fill: NAVY, weight: "bold" });
    cols.forEach((c, ci) => {
      const [bg, fg] = styleOf[c.plan[ri]];
      const x = x0 + ci * (colW + gap);
      b += rect(x, y, colW, rowH, { fill: bg, r: 6 });
      b += text(x + colW / 2, y + rowH / 2 + 8, styleOf[c.plan[ri]][2].split(" ")[0], { size: 21, anchor: "middle", fill: fg, weight: "bold" });
    });
  });
  // Legend
  const ly = H - 62;
  [["You manage", NAVY, 316], ["Shared — pre-built, still yours to change", TEAL, 560], ["AWS manages", ORANGE, 1150]].forEach(([lab, col, lx]) => {
    b += rect(lx, ly, 26, 26, { fill: col, r: 5 });
    b += text(lx + 38, ly + 20, lab, { size: 21, fill: NAVY });
  });
  return svgDoc(W, H, b);
}

/* ------------------------------------------------------------------ *
 * FIGURE 2 — Lightsail architecture: the abstraction over AWS primitives
 * ------------------------------------------------------------------ */
function figArchitecture() {
  const W = 1600, H = 1010;
  let b = "";

  // Layer 1 — access
  b += rect(60, 40, 1480, 96, { fill: LIGHT, r: 12 });
  b += text(84, 96, "ACCESS LAYER", { size: 19, weight: "bold", fill: GREY, spacing: 2 });
  const access = ["Lightsail Console", "AWS CLI  ·  lightsail API", "Browser-based SSH / RDP"];
  access.forEach((a, i) => {
    const x = 400 + i * 380;
    b += rect(x, 58, 350, 60, { fill: PAPER, r: 8, stroke: "#C6D0D8", sw: 2 });
    b += text(x + 175, 96, a, { size: 21, anchor: "middle", fill: NAVY, weight: "bold" });
  });

  // Arrow down
  b += `<path d="M800 136 L800 176" stroke="${ORANGE}" stroke-width="5"/><path d="M786 172 L800 196 L814 172 Z" fill="${ORANGE}"/>`;

  // Layer 2 — Lightsail control plane
  b += rect(60, 204, 1480, 92, { fill: NAVY, r: 12 });
  b += text(800, 244, "AMAZON LIGHTSAIL CONTROL PLANE", { size: 25, anchor: "middle", fill: ORANGE, weight: "bold", spacing: 2 });
  b += text(800, 276, "bundles  ·  blueprints  ·  fixed monthly price  ·  opinionated defaults", { size: 20, anchor: "middle", fill: "#C9D3DC" });

  b += `<path d="M800 296 L800 336" stroke="${ORANGE}" stroke-width="5"/><path d="M786 332 L800 356 L814 332 Z" fill="${ORANGE}"/>`;

  // Layer 3 — resources provisioned, each mapped to the AWS primitive underneath
  const res = [
    ["Instance", "Amazon EC2"],
    ["Block storage", "Amazon EBS"],
    ["Load balancer", "ELB + ACM"],
    ["Managed DB", "Amazon RDS"],
    ["Bucket", "Amazon S3"],
    ["Distribution", "CloudFront"],
    ["DNS zone", "Route 53"],
    ["Snapshot", "EBS snapshot"],
  ];
  b += rect(60, 364, 1480, 250, { fill: "#F4F7F9", r: 12, stroke: "#D5DEE5", sw: 2 });
  b += text(84, 402, "MANAGED RESOURCES  —  what you create", { size: 19, weight: "bold", fill: GREY, spacing: 2 });
  const cw = 168, cg = 14;
  res.forEach((r, i) => {
    const x = 92 + i * (cw + cg);
    b += rect(x, 420, cw, 88, { fill: PAPER, r: 8, stroke: TEAL, sw: 2 });
    b += text(x + cw / 2, 452, r[0], { size: 19, anchor: "middle", fill: NAVY, weight: "bold" });
    b += text(x + cw / 2, 480, "built on", { size: 15, anchor: "middle", fill: GREY });
    b += text(x + cw / 2, 500, r[1], { size: 16, anchor: "middle", fill: TEAL, weight: "bold" });
    b += `<path d="M${x + cw / 2} 508 L${x + cw / 2} 540" stroke="#B9C6D0" stroke-width="3"/>`;
  });
  b += rect(92, 546, 1416, 48, { fill: "#DCE6EC", r: 8 });
  b += text(800, 577, "Lightsail-managed VPC   ·   Region + Availability Zone   ·   built-in instance firewall", {
    size: 20, anchor: "middle", fill: NAVY, weight: "bold",
  });

  // Layer 4 — the wider AWS account, reachable by VPC peering
  b += rect(60, 660, 900, 176, { fill: NAVY_2, r: 12 });
  b += text(90, 704, "VPC PEERING  —  one click", { size: 19, weight: "bold", fill: ORANGE, spacing: 2 });
  b += text(90, 744, "Reach the rest of your AWS account:", { size: 20, fill: "#E4EAEF" });
  b += text(90, 780, "Amazon S3  ·  Amazon RDS  ·  AWS Lambda", { size: 20, fill: "#FFFFFF", weight: "bold" });
  b += text(90, 812, "Amazon CloudWatch  ·  90+ other services", { size: 20, fill: "#FFFFFF", weight: "bold" });

  b += rect(1000, 660, 540, 176, { fill: "#FFF4E2", r: 12, stroke: ORANGE, sw: 3 });
  b += text(1030, 704, "GROWTH PATH", { size: 19, weight: "bold", fill: "#A05C00", spacing: 2 });
  b += text(1030, 744, "Export a snapshot →", { size: 20, fill: NAVY });
  b += text(1030, 778, "AMI + EBS snapshot in EC2", { size: 20, fill: NAVY, weight: "bold" });
  b += text(1030, 812, "No rebuild, no lock-in", { size: 20, fill: GREEN, weight: "bold" });

  // Footnote
  b += text(60, 900, "Every Lightsail resource is a standard AWS primitive with the configuration surface hidden —", { size: 21, fill: GREY });
  b += text(60, 932, "that hiding is the product. You trade knobs for a price you can predict.", { size: 21, fill: NAVY, weight: "bold" });
  return svgDoc(W, H, b);
}

/* ------------------------------------------------------------------ *
 * FIGURE 3 — Deploying a production WordPress site: six steps
 * ------------------------------------------------------------------ */
function figDeployFlow() {
  const W = 1600, H = 640;
  const steps = [
    ["Pick a blueprint", "WordPress, pre-installed and configured", "~10 s"],
    ["Pick a bundle", "e.g. $12/mo — 2 GB, 2 vCPU, 60 GB", "~10 s"],
    ["Create instance", "Boots into a running site", "~60 s"],
    ["Attach static IP", "Free while attached; survives restarts", "~15 s"],
    ["Point the DNS zone", "A record → static IP", "~2 min"],
    ["Enable HTTPS", "Free Let's Encrypt or ACM certificate", "~5 min"],
  ];
  let b = "";
  const cw = 236, gap = 22, x0 = 62;
  steps.forEach((s, i) => {
    const x = x0 + i * (cw + gap);
    b += rect(x, 96, cw, 330, { fill: PAPER, r: 12, stroke: "#D5DEE5", sw: 2 });
    b += `<circle cx="${x + cw / 2}" cy="96" r="34" fill="${NAVY}"/>`;
    b += text(x + cw / 2, 108, String(i + 1), { size: 34, anchor: "middle", fill: ORANGE, weight: "bold" });
    b += multiline(x + cw / 2, 176, s[0], 16, 30, { size: 23, anchor: "middle", fill: NAVY, weight: "bold" });
    b += multiline(x + cw / 2, 260, s[1], 22, 27, { size: 18, anchor: "middle", fill: GREY });
    b += rect(x + 52, 366, cw - 104, 40, { fill: "#E8F4F8", r: 20 });
    b += text(x + cw / 2, 393, s[2], { size: 19, anchor: "middle", fill: TEAL, weight: "bold" });
    if (i < steps.length - 1) {
      const ax = x + cw + 2;
      b += `<path d="M${ax} 261 L${ax + 14} 261" stroke="${ORANGE}" stroke-width="4"/><path d="M${ax + 10} 251 L${ax + 20} 261 L${ax + 10} 271 Z" fill="${ORANGE}"/>`;
    }
  });
  b += rect(62, 470, 1476, 110, { fill: NAVY, r: 12 });
  b += text(800, 518, "Live, HTTPS-secured WordPress site in under 10 minutes", { size: 30, anchor: "middle", fill: "#FFFFFF", weight: "bold" });
  b += text(800, 556, "The same result on raw EC2 needs VPC, subnet, route table, IGW, security group, EBS, Elastic IP and an install script.", {
    size: 20, anchor: "middle", fill: "#B9C6D0",
  });
  return svgDoc(W, H, b);
}

/* ------------------------------------------------------------------ *
 * FIGURE 4 — Networking and security topology
 * ------------------------------------------------------------------ */
function figNetwork() {
  const W = 1600, H = 880;
  let b = "";
  const box = (x, y, w, h, title, sub, color, fill) => {
    let s = rect(x, y, w, h, { fill: fill || PAPER, r: 10, stroke: color, sw: 3 });
    s += text(x + w / 2, y + 42, title, { size: 23, anchor: "middle", fill: NAVY, weight: "bold" });
    if (sub) s += multiline(x + w / 2, y + 74, sub, 26, 24, { size: 17, anchor: "middle", fill: GREY });
    return s;
  };
  const arrow = (x1, y1, x2, y2, col = ORANGE) => {
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy);
    const ux = dx / len, uy = dy / len;
    const hx = x2 - ux * 14, hy = y2 - uy * 14;
    return `<path d="M${x1} ${y1} L${hx} ${hy}" stroke="${col}" stroke-width="4"/><path d="M${x2} ${y2} L${hx - uy * 8} ${hy + ux * 8} L${hx + uy * 8} ${hy - ux * 8} Z" fill="${col}"/>`;
  };

  b += box(620, 30, 360, 96, "Internet users", null, GREY, LIGHT);
  b += arrow(800, 126, 800, 168);

  b += box(560, 172, 480, 106, "DNS zone", "your-domain.com  ·  3M queries/mo included", TEAL);
  b += arrow(800, 278, 800, 320);

  b += box(500, 324, 600, 118, "Load balancer — $18/mo", "HTTPS termination  ·  free, auto-renewed certificate", ORANGE, "#FFF4E2");
  b += arrow(650, 442, 470, 496);
  b += arrow(950, 442, 1130, 496);

  // Two instances behind the LB, each with its own firewall
  [[240, "Instance A", "us-east-1a"], [900, "Instance B", "us-east-1b"]].forEach(([x, name, az]) => {
    b += rect(x, 500, 460, 176, { fill: PAPER, r: 10, stroke: NAVY, sw: 3 });
    b += text(x + 230, 542, name, { size: 23, anchor: "middle", fill: NAVY, weight: "bold" });
    b += rect(x + 30, 560, 400, 44, { fill: "#FDECEC", r: 8 });
    b += text(x + 230, 590, "Instance firewall — default-deny inbound", { size: 17, anchor: "middle", fill: "#A8342B", weight: "bold" });
    b += rect(x + 30, 614, 400, 44, { fill: "#EEF6E4", r: 8 });
    b += text(x + 230, 644, `Static IPv4 (free while attached)  ·  ${az}`, { size: 17, anchor: "middle", fill: "#4A6B0F", weight: "bold" });
  });

  b += arrow(470, 676, 700, 730);
  b += arrow(1130, 676, 900, 730);
  b += box(560, 734, 480, 106, "Managed database — from $15/mo", "automatic backups  ·  optional Multi-AZ standby", TEAL);

  // Side rails: CDN and bucket
  b += rect(1120, 172, 420, 118, { fill: "#F4F7F9", r: 10, stroke: TEAL, sw: 3 });
  b += text(1330, 214, "CDN distribution", { size: 23, anchor: "middle", fill: NAVY, weight: "bold" });
  b += text(1330, 246, "CloudFront edge cache", { size: 17, anchor: "middle", fill: GREY });
  b += text(1330, 272, "50 GB/mo free for 12 months", { size: 17, anchor: "middle", fill: GREEN, weight: "bold" });

  b += rect(60, 172, 420, 118, { fill: "#F4F7F9", r: 10, stroke: TEAL, sw: 3 });
  b += text(270, 214, "Object storage bucket", { size: 23, anchor: "middle", fill: NAVY, weight: "bold" });
  b += text(270, 246, "static assets, media, backups", { size: 17, anchor: "middle", fill: GREY });
  b += text(270, 272, "5 GB from $1/mo", { size: 17, anchor: "middle", fill: GREEN, weight: "bold" });

  return svgDoc(W, H, b);
}

/* ------------------------------------------------------------------ *
 * FIGURE 5 — The graduation path: when Lightsail stops being the answer
 * ------------------------------------------------------------------ */
function figGrowth() {
  const W = 1600, H = 600;
  let b = "";
  b += rect(60, 60, 700, 300, { fill: "#F4F7F9", r: 14, stroke: TEAL, sw: 3 });
  b += text(410, 116, "STAY ON LIGHTSAIL", { size: 26, anchor: "middle", fill: TEAL, weight: "bold", spacing: 2 });
  ["Predictable, bounded traffic", "One to a handful of servers", "Team is small; ops time is scarce", "Cost certainty matters more than tuning"].forEach((t, i) => {
    b += `<circle cx="110" cy="${162 + i * 46}" r="7" fill="${TEAL}"/>`;
    b += text(134, 170 + i * 46, t, { size: 22, fill: NAVY });
  });

  b += rect(840, 60, 700, 300, { fill: "#FFF4E2", r: 14, stroke: ORANGE, sw: 3 });
  b += text(1190, 116, "MOVE TO EC2", { size: 26, anchor: "middle", fill: "#A05C00", weight: "bold", spacing: 2 });
  ["Need auto scaling or spiky traffic", "Need > 64 GB RAM / 16 vCPU on one box", "Need IAM, custom VPC, Reserved Instances", "Need Savings Plans or Spot economics"].forEach((t, i) => {
    b += `<circle cx="890" cy="${162 + i * 46}" r="7" fill="${ORANGE}"/>`;
    b += text(914, 170 + i * 46, t, { size: 22, fill: NAVY });
  });

  // The bridge between them
  b += rect(60, 400, 1480, 150, { fill: NAVY, r: 14 });
  b += text(800, 452, "The exit is built in", { size: 28, anchor: "middle", fill: ORANGE, weight: "bold" });
  b += text(800, 496, "Take a snapshot  →  Export to Amazon EC2  →  AWS creates an AMI + EBS snapshot  →  launch with the Upgrade to EC2 wizard", {
    size: 20, anchor: "middle", fill: "#E4EAEF",
  });
  b += text(800, 528, "Your disk image is standard AWS. Migration is a copy, not a rewrite.", { size: 20, anchor: "middle", fill: "#FFFFFF", weight: "bold" });
  return svgDoc(W, H, b);
}

/* ------------------------------------------------------------------ *
 * FIGURE 7 — Cost model: Lightsail flat bundle vs equivalent EC2 build
 * (matches the native chart on deck slide 11; used by the report)
 * ------------------------------------------------------------------ */
function figCost() {
  const W = 1500, H = 780;
  const bars = [
    ["Lightsail Small", "any egress volume", 12.0, TEAL],
    ["EC2 equivalent", "100 GB egress", 23.63, "#8FA3B3"],
    ["EC2 equivalent", "1 TB egress", 106.79, "#6E8598"],
    ["EC2 equivalent", "3 TB egress", 291.11, "#A8342B"],
  ];
  const x0 = 130, yTop = 60, yBase = 620;
  const plotH = yBase - yTop;
  const max = 320;
  const bw = 180, gap = 108;

  let b = "";
  // Gridlines and value axis
  for (let v = 0; v <= 300; v += 50) {
    const y = yBase - (v / max) * plotH;
    b += `<path d="M${x0} ${y} H${W - 60}" stroke="#E4EAEE" stroke-width="2"/>`;
    b += text(x0 - 16, y + 7, "$" + v, { size: 19, fill: GREY, anchor: "end" });
  }
  b += `<path d="M${x0} ${yBase} H${W - 60}" stroke="#B9C6D0" stroke-width="3"/>`;

  bars.forEach(([l1, l2, v, col], i) => {
    const x = x0 + 40 + i * (bw + gap);
    const h = (v / max) * plotH;
    const y = yBase - h;
    b += rect(x, y, bw, h, { fill: col, r: 4 });
    b += text(x + bw / 2, y - 16, "$" + v.toFixed(2), { size: 24, weight: "bold", fill: NAVY, anchor: "middle" });
    b += text(x + bw / 2, yBase + 34, l1, { size: 20, fill: NAVY, anchor: "middle", weight: "bold" });
    b += text(x + bw / 2, yBase + 60, l2, { size: 18, fill: GREY, anchor: "middle" });
  });

  b += text(x0 - 16, 34, "Monthly cost (USD)", { size: 19, fill: NAVY, weight: "bold" });
  b += text(x0, H - 34, "us-east-1 list prices: t3.small on demand + 60 GB gp3 + one in-use Elastic IP; egress $0.09/GB after the first 100 GB free.", {
    size: 18, fill: GREY,
  });
  return svgDoc(W, H, b);
}

/* ------------------------------------------------------------------ *
 * ICONS — white glyphs, dropped onto coloured circles in the deck
 * ------------------------------------------------------------------ */
const ICONS = {
  server: `<rect x="12" y="14" width="72" height="22" rx="4"/><rect x="12" y="42" width="72" height="22" rx="4"/><rect x="12" y="70" width="72" height="16" rx="4"/>`,
  database: `<ellipse cx="48" cy="22" rx="34" ry="12"/><path d="M14 22 v52 a34 12 0 0 0 68 0 v-52 a34 12 0 0 1 -68 0 z" fill-opacity="0.55"/><ellipse cx="48" cy="48" rx="34" ry="12" fill-opacity="0.9"/>`,
  globe: `<circle cx="48" cy="48" r="36" fill="none" stroke-width="7" stroke="currentStroke"/><ellipse cx="48" cy="48" rx="15" ry="36" fill="none" stroke-width="7" stroke="currentStroke"/><path d="M14 36 H82 M14 60 H82" stroke-width="7" stroke="currentStroke" fill="none"/>`,
  shield: `<path d="M48 8 L82 22 v28 c0 22-14 32-34 40-20-8-34-18-34-40V22 Z"/>`,
  box: `<path d="M48 8 L84 28 v40 L48 88 L12 68 V28 Z" fill-opacity="0.5"/><path d="M48 8 L84 28 L48 48 L12 28 Z"/>`,
  tag: `<path d="M10 10 h40 l38 38 -40 40 -38 -38 Z"/><circle cx="30" cy="30" r="8" fill="#232F3E"/>`,
  gauge: `<path d="M12 66 a36 36 0 1 1 72 0 z" fill-opacity="0.45"/><path d="M48 62 L74 32 l6 6 -26 30 z"/><circle cx="48" cy="66" r="9"/>`,
  cart: `<path d="M8 14 h14 l12 44 h40 l10 -30 H30" fill="none" stroke-width="8" stroke="currentStroke" stroke-linejoin="round"/><circle cx="38" cy="76" r="8"/><circle cx="72" cy="76" r="8"/>`,
  code: `<path d="M32 22 L10 48 L32 74" fill="none" stroke-width="9" stroke="currentStroke" stroke-linecap="round" stroke-linejoin="round"/><path d="M64 22 L86 48 L64 74" fill="none" stroke-width="9" stroke="currentStroke" stroke-linecap="round" stroke-linejoin="round"/><path d="M56 16 L40 80" stroke-width="8" stroke="currentStroke" stroke-linecap="round"/>`,
  cap: `<path d="M48 16 L92 36 L48 56 L4 36 Z"/><path d="M22 46 v20 c0 8 12 14 26 14 s26-6 26-14 V46" fill="none" stroke-width="8" stroke="currentStroke"/>`,
  doc: `<path d="M20 8 h38 l22 22 v58 H20 Z" fill-opacity="0.95"/><path d="M58 8 v22 h22" fill="#232F3E"/><path d="M32 50 h32 M32 64 h32 M32 78 h20" stroke-width="6" stroke="#232F3E" fill="none"/>`,
  scale: `<path d="M48 10 v76" stroke-width="8" stroke="currentStroke"/><path d="M16 26 h64" stroke-width="8" stroke="currentStroke"/><path d="M4 56 L16 26 L28 56 Z"/><path d="M68 56 L80 26 L92 56 Z"/><rect x="30" y="82" width="36" height="8" rx="4"/>`,
  warn: `<path d="M48 8 L92 84 H4 Z"/><rect x="43" y="34" width="10" height="28" rx="5" fill="#232F3E"/><circle cx="48" cy="72" r="6" fill="#232F3E"/>`,
  check: `<circle cx="48" cy="48" r="40"/><path d="M28 50 L42 64 L70 34" fill="none" stroke-width="10" stroke="#232F3E" stroke-linecap="round" stroke-linejoin="round"/>`,
  growth: `<path d="M10 76 L36 48 L54 64 L86 26" fill="none" stroke-width="9" stroke="currentStroke" stroke-linecap="round" stroke-linejoin="round"/><path d="M62 22 h28 v28" fill="none" stroke-width="9" stroke="currentStroke" stroke-linecap="round" stroke-linejoin="round"/>`,
  clock: `<circle cx="48" cy="48" r="38" fill="none" stroke-width="8" stroke="currentStroke"/><path d="M48 24 v26 l18 12" fill="none" stroke-width="8" stroke="currentStroke" stroke-linecap="round"/>`,
  layers: `<path d="M48 8 L88 30 L48 52 L8 30 Z"/><path d="M8 48 L48 70 L88 48" fill="none" stroke-width="8" stroke="currentStroke"/><path d="M8 66 L48 88 L88 66" fill="none" stroke-width="8" stroke="currentStroke"/>`,
  wrench: `<path d="M78 12 a22 22 0 0 0 -28 28 L14 76 a8 8 0 0 0 0 11 l3 3 a8 8 0 0 0 11 0 L64 54 a22 22 0 0 0 28 -28 L76 42 L62 28 Z"/>`,
};

async function icons() {
  for (const [name, body] of Object.entries(ICONS)) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 96 96">
<g fill="#FFFFFF" stroke="none">${body.replace(/currentStroke/g, "#FFFFFF")}</g></svg>`;
    await sharp(Buffer.from(svg)).resize(256, 256).png().toFile(path.join(OUT, `icon-${name}.png`));
  }
  console.log("wrote", Object.keys(ICONS).length, "icons");
}

(async () => {
  await write("fig-service-models.png", figServiceModels());
  await write("fig-architecture.png", figArchitecture());
  await write("fig-deploy-flow.png", figDeployFlow());
  await write("fig-network.png", figNetwork());
  await write("fig-growth.png", figGrowth());
  await write("fig-cost-comparison.png", figCost());
  await icons();
})();
