/**
 * Amazon Lightsail (PaaS-Lite) — Cloud Infrastructure
 * Formal 20-slide deck. Palette derives from the AWS brand (Squid Ink / Smile Orange).
 */
const path = require("path");
const pptxgen = require("pptxgenjs");

const ASSETS = path.join(__dirname, "..", "assets");
const OUTFILE = path.join(__dirname, "..", "Amazon_Lightsail_Presentation.pptx");

const NAVY = "232F3E";
const NAVY_2 = "33475B";
const ORANGE = "FF9900";
const TEAL = "00A1C9";
const GREEN = "5C8001";
const RED = "A8342B";
const INK = "232F3E";
const GREY = "5A6B7B";
const LIGHT = "F4F7F9";
const BORDER = "D5DEE5";
const WHITE = "FFFFFF";

const HEAD = "Cambria";
const BODY = "Calibri";

const W = 13.333;
const H = 7.5;
const M = 0.62; // page margin

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Hridiyansh Shukla";
pres.company = "Reg. No. 2427030591";
pres.title = "Amazon Lightsail (PaaS-Lite) — Cloud Infrastructure";

let slideNo = 0;

/* ----------------------------- helpers ----------------------------- */

function newSlide({ dark = false } = {}) {
  const s = pres.addSlide();
  s.background = { color: dark ? NAVY : WHITE };
  slideNo += 1;
  return s;
}

/** Standard title block: small orange eyebrow above a serif title. */
function titleBlock(slide, kicker, title, { dark = false, subtitle = null } = {}) {
  slide.addText(kicker.toUpperCase(), {
    x: M, y: 0.34, w: W - 2 * M, h: 0.26,
    fontFace: BODY, fontSize: 11, bold: true, charSpacing: 2.2,
    color: ORANGE, align: "left", margin: 0,
  });
  slide.addText(title, {
    x: M, y: 0.62, w: W - 2 * M, h: 0.55,
    fontFace: HEAD, fontSize: 30, bold: true,
    color: dark ? WHITE : INK, align: "left", margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: M, y: 1.16, w: W - 2 * M, h: 0.3,
      fontFace: BODY, fontSize: 13.5, italic: true,
      color: dark ? "B9C6D0" : GREY, align: "left", margin: 0,
    });
  }
}

function footer(slide, { dark = false } = {}) {
  const col = dark ? "6E7F8E" : "9AA9B5";
  slide.addText("Amazon Lightsail (PaaS-Lite)  ·  Hridiyansh Shukla  ·  2427030591", {
    x: M, y: H - 0.46, w: 8.5, h: 0.28,
    fontFace: BODY, fontSize: 9.5, color: col, align: "left", margin: 0,
  });
  slide.addText(String(slideNo), {
    x: W - M - 1.0, y: H - 0.46, w: 1.0, h: 0.28,
    fontFace: BODY, fontSize: 9.5, color: col, align: "right", margin: 0,
  });
}

/** Repeated motif: a filled circle carrying a white glyph. */
function iconCircle(slide, x, y, d, color, icon) {
  slide.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color } });
  const pad = d * 0.26;
  slide.addImage({ path: path.join(ASSETS, `icon-${icon}.png`), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad });
}

function card(slide, x, y, w, h, { fill = LIGHT, line = BORDER, shadow = false } = {}) {
  const opts = { x, y, w, h, fill: { color: fill }, line: { color: line, width: 1 }, rectRadius: 0.09 };
  if (shadow) opts.shadow = { type: "outer", color: "9AA9B5", blur: 8, offset: 2, angle: 90, opacity: 0.25 };
  slide.addShape(pres.ShapeType.roundRect, opts);
}

function styledTable(slide, header, rows, opts) {
  const {
    x, y, w, colW, headSize = 11.5, bodySize = 10.5, rowH = 0.34, headH = 0.4, align = null,
  } = opts;
  const head = header.map((t, i) => ({
    text: t,
    options: {
      fill: { color: NAVY }, color: WHITE, bold: true, fontSize: headSize, fontFace: BODY,
      align: align && align[i] ? align[i] : "left", valign: "middle", margin: [4, 7, 4, 7],
    },
  }));
  const body = rows.map((r, ri) =>
    r.map((cell, i) => {
      const c = typeof cell === "object" ? cell : { text: cell };
      return {
        text: c.text,
        options: {
          fill: { color: ri % 2 ? LIGHT : WHITE },
          color: c.color || INK,
          bold: !!c.bold,
          fontSize: bodySize, fontFace: BODY,
          align: c.align || (align && align[i] ? align[i] : "left"),
          valign: "middle", margin: [3, 7, 3, 7],
        },
      };
    })
  );
  slide.addTable([head, ...body], {
    x, y, w, colW,
    rowH,
    border: { type: "solid", color: BORDER, pt: 0.75 },
    autoPage: false,
  });
  // first row taller
  return y + headH + rows.length * rowH;
}

function bullets(slide, x, y, w, h, items, { size = 13.5, color = INK, gap = 9 } = {}) {
  slide.addText(
    items.map((t, i) => ({
      text: t,
      options: { bullet: { code: "25CF" }, breakLine: i < items.length - 1, paraSpaceAfter: gap },
    })),
    { x, y, w, h, fontFace: BODY, fontSize: size, color, margin: 0, valign: "top", lineSpacingMultiple: 1.05 }
  );
}

/* =================================================================== *
 * SLIDE 1 — Title
 * =================================================================== */
{
  const s = newSlide({ dark: true });
  // Subtle depth: a large low-contrast panel behind the fact tiles
  s.addShape(pres.ShapeType.rect, { x: 7.85, y: 0, w: 5.483, h: H, fill: { color: NAVY_2 } });

  s.addText("CLOUD INFRASTRUCTURE  ·  SEMINAR PRESENTATION", {
    x: M, y: 1.28, w: 6.9, h: 0.3, fontFace: BODY, fontSize: 11.5, bold: true, charSpacing: 2.2, color: ORANGE, margin: 0,
  });
  s.addText("Amazon Lightsail", {
    x: M, y: 1.72, w: 6.9, h: 0.95, fontFace: HEAD, fontSize: 48, bold: true, color: WHITE, margin: 0,
  });
  s.addText("Platform-as-a-Service, Lite", {
    x: M, y: 2.66, w: 6.9, h: 0.5, fontFace: HEAD, fontSize: 24, italic: true, color: ORANGE, margin: 0,
  });
  s.addText(
    "How AWS packaged its own building blocks into a fixed-price virtual private server — and what you trade away to get that simplicity.",
    { x: M, y: 3.32, w: 6.75, h: 0.95, fontFace: BODY, fontSize: 14, color: "B9C6D0", margin: 0, lineSpacingMultiple: 1.2 }
  );

  s.addShape(pres.ShapeType.rect, { x: M, y: 4.55, w: 1.5, h: 0.035, fill: { color: ORANGE } });
  s.addText("Presented by", {
    x: M, y: 4.78, w: 6.9, h: 0.26, fontFace: BODY, fontSize: 11, color: "8A9AA8", margin: 0,
  });
  s.addText("Hridiyansh Shukla", {
    x: M, y: 5.04, w: 6.9, h: 0.46, fontFace: HEAD, fontSize: 26, bold: true, color: WHITE, margin: 0,
  });
  s.addText("Registration No. 2427030591", {
    x: M, y: 5.52, w: 6.9, h: 0.32, fontFace: BODY, fontSize: 14, color: ORANGE, margin: 0,
  });

  // Fact tiles
  const facts = [
    ["30 Nov 2016", "Launched at AWS re:Invent", "clock"],
    ["$5 / month", "Entry bundle — compute, SSD and 1 TB of transfer in one price", "tag"],
    ["8 resource types", "Instances, containers, databases, storage, CDN, DNS and more", "layers"],
  ];
  let fy = 1.42;
  facts.forEach(([big, small, ic]) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: 8.35, y: fy, w: 4.48, h: 1.4, fill: { color: NAVY }, line: { color: "4A5D70", width: 1 }, rectRadius: 0.09,
    });
    iconCircle(s, 8.62, fy + 0.42, 0.56, ORANGE, ic);
    s.addText(big, { x: 9.36, y: fy + 0.2, w: 3.3, h: 0.4, fontFace: HEAD, fontSize: 20, bold: true, color: ORANGE, margin: 0 });
    s.addText(small, { x: 9.36, y: fy + 0.62, w: 3.28, h: 0.68, fontFace: BODY, fontSize: 11, color: "C4CFD8", margin: 0, lineSpacingMultiple: 1.1 });
    fy += 1.66;
  });

  s.addText("Amazon Web Services  ·  August 2026", {
    x: 8.35, y: 6.55, w: 4.48, h: 0.3, fontFace: BODY, fontSize: 10.5, color: "8A9AA8", align: "center", margin: 0,
  });
}

/* =================================================================== *
 * SLIDE 2 — Agenda
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Roadmap", "What this talk covers");
  const items = [
    ["1", "The problem worth solving", "Why AWS built a simpler front door", "wrench"],
    ["2", "Where Lightsail sits", "IaaS, PaaS-Lite, PaaS and SaaS compared", "layers"],
    ["3", "Anatomy of the service", "Blueprints, bundles and the resource catalogue", "server"],
    ["4", "The pricing model in full", "Instances, databases, storage, networking", "tag"],
    ["5", "Lightsail versus the field", "Amazon EC2, DigitalOcean, Heroku, Azure", "scale"],
    ["6", "Hands-on and use cases", "A production site in under ten minutes", "gauge"],
    ["7", "Limits and the exit", "What you give up, and how you leave", "warn"],
    ["8", "Verdict", "When this is the right tool", "check"],
  ];
  const colW = 5.95, rowH = 1.24;
  items.forEach((it, i) => {
    const cx = M + (i % 2) * (colW + 0.45);
    const cy = 1.55 + Math.floor(i / 2) * rowH;
    iconCircle(s, cx, cy + 0.08, 0.62, i % 2 ? TEAL : NAVY, it[3]);
    s.addText(it[1], { x: cx + 0.82, y: cy + 0.06, w: colW - 0.9, h: 0.34, fontFace: HEAD, fontSize: 16, bold: true, color: INK, margin: 0 });
    s.addText(it[2], { x: cx + 0.82, y: cy + 0.44, w: colW - 0.9, h: 0.34, fontFace: BODY, fontSize: 12, color: GREY, margin: 0 });
  });
  footer(s);
}

/* =================================================================== *
 * SLIDE 3 — The problem
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Motivation", "The problem: power arrived with complexity");

  s.addText(
    "Amazon EC2 gives you every knob a data centre has. For a team that only wants a website, a blog or a small application online, most of those knobs are a tax rather than a feature.",
    { x: M, y: 1.55, w: 7.0, h: 0.75, fontFace: BODY, fontSize: 14, color: INK, margin: 0, lineSpacingMultiple: 1.22 }
  );

  const pains = [
    ["Too many decisions", "Before a raw EC2 instance serves traffic you must design a VPC, a subnet, a route table, an internet gateway, a security group, an EBS volume, a key pair and an Elastic IP.", "wrench"],
    ["Unpredictable bills", "Compute, storage, egress and the IP address are four separate meters. A small site cannot forecast next month's invoice.", "tag"],
    ["Skills mismatch", "Students, freelancers and small businesses need a running server, not a cloud architecture certification.", "cap"],
  ];
  let y = 2.42;
  pains.forEach(([h, d, ic]) => {
    iconCircle(s, M, y, 0.58, NAVY, ic);
    s.addText(h, { x: M + 0.78, y: y - 0.03, w: 6.2, h: 0.32, fontFace: HEAD, fontSize: 16, bold: true, color: INK, margin: 0 });
    s.addText(d, { x: M + 0.78, y: y + 0.31, w: 6.2, h: 0.9, fontFace: BODY, fontSize: 12, color: GREY, margin: 0, lineSpacingMultiple: 1.14 });
    y += 1.42;
  });

  // Stat rail
  const stats = [
    ["750+", "Amazon EC2 instance types to choose between"],
    ["8", "Lightsail general-purpose bundles — the whole menu"],
    ["1", "Line on your bill, fixed before you deploy"],
  ];
  let sy = 1.55;
  stats.forEach(([big, lab], i) => {
    card(s, 8.15, sy, 4.55, 1.45, { fill: i === 2 ? NAVY : LIGHT, line: i === 2 ? NAVY : BORDER });
    s.addText(big, {
      x: 8.4, y: sy + 0.11, w: 4.05, h: 0.66, fontFace: HEAD, fontSize: 40, bold: true,
      color: i === 2 ? ORANGE : (i === 0 ? RED : TEAL), margin: 0,
    });
    s.addText(lab, {
      x: 8.4, y: sy + 0.79, w: 4.05, h: 0.56, fontFace: BODY, fontSize: 12,
      color: i === 2 ? "C4CFD8" : GREY, margin: 0, lineSpacingMultiple: 1.1,
    });
    sy += 1.61;
  });
  s.addText("Fewer choices, stated cost, identical AWS hardware.", {
    x: 8.15, y: 6.38, w: 4.55, h: 0.3, fontFace: BODY, fontSize: 11.5, italic: true, color: INK, align: "center", margin: 0,
  });
  footer(s);
}

/* =================================================================== *
 * SLIDE 4 — Service models figure
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Positioning", "Where Lightsail sits in the cloud stack");

  card(s, M, 1.5, 2.95, 5.0, { fill: NAVY, line: NAVY });
  s.addText("Why “PaaS-Lite”?", {
    x: M + 0.24, y: 1.72, w: 2.5, h: 0.4, fontFace: HEAD, fontSize: 17, bold: true, color: ORANGE, margin: 0,
  });
  s.addText(
    "A true PaaS hides the operating system entirely — you push code and never meet a server.\n\n" +
      "Lightsail pre-builds the OS and the runtime for you, then hands you the root password anyway.\n\n" +
      "You get PaaS convenience on day one and IaaS control on day two. That hybrid position is the whole product.",
    { x: M + 0.24, y: 2.22, w: 2.5, h: 4.0, fontFace: BODY, fontSize: 12, color: "C4CFD8", margin: 0, lineSpacingMultiple: 1.16 }
  );

  s.addImage({ path: path.join(ASSETS, "fig-service-models.png"), x: 3.88, y: 1.5, w: 8.83, h: 5.19 });
  s.addText("Figure 1 — Division of management responsibility across cloud service models.", {
    x: 3.88, y: 6.72, w: 8.83, h: 0.26, fontFace: BODY, fontSize: 9.5, italic: true, color: GREY, align: "right", margin: 0,
  });
  footer(s);
}

/* =================================================================== *
 * SLIDE 5 — What is Lightsail
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Definition", "What Amazon Lightsail actually is");

  card(s, M, 1.5, 12.09, 1.28, { fill: LIGHT, line: TEAL });
  s.addText(
    [
      { text: "Amazon Lightsail ", options: { bold: true, color: INK } },
      {
        text: "is AWS's virtual private server offering: pre-configured compute, storage, networking and managed services, sold as fixed-price monthly bundles through a deliberately simplified console.",
        options: { color: INK },
      },
    ],
    { x: M + 0.3, y: 1.66, w: 11.5, h: 0.96, fontFace: BODY, fontSize: 15.5, margin: 0, valign: "middle", lineSpacingMultiple: 1.18 }
  );

  const facts = [
    ["Announced 30 November 2016", "Launched at AWS re:Invent in US East (N. Virginia); expanded to Hong Kong, São Paulo and Spain in June 2026.", "clock", NAVY],
    ["One price, four things", "Every bundle folds vCPU, memory, SSD storage and a monthly data-transfer allowance into a single figure.", "tag", TEAL],
    ["Blueprint, not blank box", "Choose WordPress, LAMP, Node.js or a plain OS; the instance boots with the software already installed.", "doc", NAVY],
    ["Real AWS underneath", "Instances are EC2, disks are EBS, DNS is Route 53. Nothing is a proprietary dead end.", "server", TEAL],
  ];
  const cw = 5.9, ch = 1.72;
  facts.forEach(([h, d, ic, col], i) => {
    const x = M + (i % 2) * (cw + 0.29);
    const y = 3.06 + Math.floor(i / 2) * (ch + 0.28);
    card(s, x, y, cw, ch, { fill: WHITE, line: BORDER, shadow: true });
    iconCircle(s, x + 0.28, y + 0.32, 0.6, col, ic);
    s.addText(h, { x: x + 1.02, y: y + 0.24, w: cw - 1.28, h: 0.34, fontFace: HEAD, fontSize: 15.5, bold: true, color: INK, margin: 0 });
    s.addText(d, { x: x + 1.02, y: y + 0.62, w: cw - 1.28, h: 0.92, fontFace: BODY, fontSize: 11.5, color: GREY, margin: 0, lineSpacingMultiple: 1.14 });
  });
  footer(s);
}

/* =================================================================== *
 * SLIDE 6 — Architecture
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Architecture", "How the abstraction is built");

  card(s, M, 1.5, 3.42, 5.02, { fill: LIGHT, line: BORDER });
  s.addText("The one idea", {
    x: M + 0.26, y: 1.7, w: 2.95, h: 0.34, fontFace: HEAD, fontSize: 16, bold: true, color: TEAL, margin: 0,
  });
  s.addText(
    "Lightsail is not a new infrastructure platform. It is a curated control plane over services AWS already sells.",
    { x: M + 0.26, y: 2.08, w: 2.9, h: 0.95, fontFace: BODY, fontSize: 12.5, color: INK, margin: 0, lineSpacingMultiple: 1.16 }
  );
  bullets(s, M + 0.26, 3.18, 2.9, 2.2, [
    "An instance is an EC2 instance",
    "A disk is an EBS volume",
    "A load balancer is ELB plus a free ACM certificate",
    "A distribution is CloudFront",
    "A DNS zone is Route 53",
  ], { size: 11.5, color: INK, gap: 10 });
  s.addText("Simplicity is the feature; the hardware is unchanged.", {
    x: M + 0.26, y: 5.45, w: 2.9, h: 0.7, fontFace: BODY, fontSize: 12, italic: true, bold: true, color: NAVY, margin: 0, lineSpacingMultiple: 1.12,
  });

  s.addImage({ path: path.join(ASSETS, "fig-architecture.png"), x: 4.35, y: 1.5, w: 8.36, h: 5.28 });
  s.addText("Figure 2 — The Lightsail control plane and the AWS primitives beneath it.", {
    x: 4.35, y: 6.8, w: 8.36, h: 0.24, fontFace: BODY, fontSize: 9.5, italic: true, color: GREY, align: "right", margin: 0,
  });
  footer(s);
}

/* =================================================================== *
 * SLIDE 7 — Resource catalogue
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Anatomy", "The resource catalogue", {
    subtitle: "Ten resource types cover the whole surface of the service.",
  });
  const rows = [
    ["Instance", "Virtual server with a fixed bundle of vCPU, RAM, SSD and transfer", "Amazon EC2"],
    ["Container service", "Runs Docker images behind a managed HTTPS endpoint — no cluster to operate", "ECS / Fargate"],
    ["Managed database", "MySQL or PostgreSQL with automated backups and an optional standby", "Amazon RDS"],
    ["Block storage disk", "Additional SSD volumes attached to a running instance", "Amazon EBS"],
    ["Object storage bucket", "Static assets, media and backups served over HTTPS", "Amazon S3"],
    ["Load balancer", "Spreads traffic across instances; includes a free, auto-renewed certificate", "ELB + ACM"],
    ["CDN distribution", "Edge caching in front of an instance, bucket or load balancer", "Amazon CloudFront"],
    ["DNS zone", "Authoritative DNS with three million queries a month included", "Amazon Route 53"],
    ["Static IP", "A fixed public IPv4 address that survives stop, start and restore", "Elastic IP"],
    ["Snapshot", "Point-in-time backup of an instance or disk; exportable to EC2", "EBS snapshot"],
  ];
  styledTable(s, ["Resource", "What it gives you", "Built on"], rows, {
    x: M, y: 1.62, w: 12.09, colW: [2.35, 6.94, 2.8], rowH: 0.44, headSize: 12, bodySize: 11,
  });
  s.addText(
    "Every row is an AWS service with its configuration surface deliberately reduced — which is exactly why a Lightsail workload can later be lifted onto the full service without a rewrite.",
    { x: M, y: 6.5, w: 12.09, h: 0.42, fontFace: BODY, fontSize: 11.5, italic: true, color: GREY, margin: 0 }
  );
  footer(s);
}

/* =================================================================== *
 * SLIDE 8 — Blueprints and bundles
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Anatomy", "Two choices: the blueprint and the bundle");

  // Left: blueprints
  card(s, M, 1.58, 6.0, 3.55, { fill: WHITE, line: TEAL, shadow: true });
  iconCircle(s, M + 0.3, 1.82, 0.56, TEAL, "doc");
  s.addText("Blueprint — the software", {
    x: M + 1.0, y: 1.84, w: 4.7, h: 0.36, fontFace: HEAD, fontSize: 17, bold: true, color: INK, margin: 0,
  });
  s.addText("What the machine boots into.", {
    x: M + 1.0, y: 2.2, w: 4.7, h: 0.28, fontFace: BODY, fontSize: 11.5, color: GREY, margin: 0,
  });
  s.addText("Operating systems", { x: M + 0.32, y: 2.62, w: 5.4, h: 0.26, fontFace: BODY, fontSize: 11, bold: true, color: TEAL, margin: 0 });
  s.addText("Amazon Linux 2 and 2023  ·  Ubuntu  ·  Debian  ·  AlmaLinux 9  ·  CentOS  ·  FreeBSD  ·  openSUSE  ·  Windows Server 2016 / 2019 / 2022", {
    x: M + 0.32, y: 2.88, w: 5.4, h: 0.62, fontFace: BODY, fontSize: 11, color: INK, margin: 0, lineSpacingMultiple: 1.14,
  });
  s.addText("Application stacks", { x: M + 0.32, y: 3.62, w: 5.4, h: 0.26, fontFace: BODY, fontSize: 11, bold: true, color: TEAL, margin: 0 });
  s.addText("WordPress  ·  WordPress Multisite  ·  LAMP  ·  Nginx (LEMP)  ·  Node.js  ·  Ruby on Rails  ·  Django  ·  Drupal  ·  Joomla  ·  Magento  ·  PrestaShop  ·  Ghost  ·  Redmine  ·  GitLab  ·  cPanel & WHM  ·  Plesk", {
    x: M + 0.32, y: 3.88, w: 5.4, h: 1.1, fontFace: BODY, fontSize: 11, color: INK, margin: 0, lineSpacingMultiple: 1.14,
  });

  // Right: bundles
  card(s, 7.02, 1.58, 5.69, 3.55, { fill: WHITE, line: ORANGE, shadow: true });
  iconCircle(s, 7.32, 1.82, 0.56, ORANGE, "server");
  s.addText("Bundle — the hardware", {
    x: 8.02, y: 1.84, w: 4.4, h: 0.36, fontFace: HEAD, fontSize: 17, bold: true, color: INK, margin: 0,
  });
  s.addText("What it runs on, and what it costs.", {
    x: 8.02, y: 2.2, w: 4.4, h: 0.28, fontFace: BODY, fontSize: 11.5, color: GREY, margin: 0,
  });
  bullets(s, 7.34, 2.66, 5.1, 2.3, [
    "One bundle fixes vCPU, RAM, SSD size and the monthly transfer allowance together",
    "Three families: general purpose, memory optimised (to 512 GB RAM, Feb 2026) and compute optimised (to 72 vCPU, Apr 2026)",
    "Entry tiers use burstable CPU; $24/month and above give dedicated vCPU",
    "Bundles can be resized upward by taking a snapshot and restoring onto a larger plan",
  ], { size: 11.5, gap: 7 });

  // Alert: Bitnami deprecation
  card(s, M, 5.32, 12.09, 1.28, { fill: "FFF4E2", line: ORANGE });
  iconCircle(s, M + 0.26, 5.58, 0.56, ORANGE, "warn");
  s.addText("Currently in transition — worth knowing for any new build", {
    x: M + 0.98, y: 5.48, w: 10.9, h: 0.3, fontFace: HEAD, fontSize: 14.5, bold: true, color: "8A4B00", margin: 0,
  });
  s.addText(
    "AWS stopped shipping newer Bitnami-packaged blueprints on 19 May 2026. WordPress, LAMP, Nginx and Node.js images packaged by Bitnami retire on 19 November 2026; Joomla, Magento, Drupal, Ghost, Django, GitLab, Redmine, MEAN and PrestaShop follow on 19 May 2027. AWS-maintained replacements for Node.js, LAMP and Ruby on Rails shipped in January 2026.",
    { x: M + 0.98, y: 5.8, w: 10.9, h: 0.72, fontFace: BODY, fontSize: 11, color: INK, margin: 0, lineSpacingMultiple: 1.12 }
  );
  footer(s);
}

/* =================================================================== *
 * SLIDE 9 — Instance pricing
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Economics", "Instance bundles — the published price list", {
    subtitle: "Linux/Unix general-purpose bundles with a public IPv4 address. Windows bundles carry a licence premium.",
  });
  const b = (t) => ({ text: t, bold: true });
  const rows = [
    ["Nano", "512 MB", "2", "20 GB", "1 TB", b("$5"), "$9.50"],
    ["Micro", "1 GB", "2", "40 GB", "2 TB", b("$7"), "$14"],
    ["Small", "2 GB", "2", "60 GB", "3 TB", b("$12"), "$22"],
    ["Medium", "4 GB", "2", "80 GB", "4 TB", b("$24"), "—"],
    ["Large", "8 GB", "2", "160 GB", "5 TB", b("$44"), "—"],
    ["XLarge", "16 GB", "4", "320 GB", "6 TB", b("$84"), "—"],
    ["2XLarge", "32 GB", "8", "640 GB", "7 TB", b("$164"), "—"],
    ["4XLarge", "64 GB", "16", "1,280 GB", "8 TB", b("$384"), "—"],
  ];
  styledTable(s, ["Bundle", "Memory", "vCPU", "SSD storage", "Transfer / month", "Linux $/month", "Windows $/month"], rows, {
    x: M, y: 1.82, w: 12.09, colW: [1.66, 1.66, 1.13, 1.86, 2.32, 1.86, 1.6], rowH: 0.42, headSize: 11.5, bodySize: 11.5,
    align: [null, "center", "center", "center", "center", "center", "center"],
  });

  const notes = [
    ["IPv6-only bundles cost about 30% less", "A public IPv4 address is now the premium — the Linux nano tier drops from $5 to $3.50 without one.", TEAL],
    ["Transfer overage is metered", "Exceed the allowance and you pay per GB. Inbound traffic and traffic to other AWS services in-Region are free.", ORANGE],
    ["Three months free", "Selected Linux/Unix IPv6 bundles at $3.50, $5 and $10 carry a three-month introductory credit for new accounts.", GREEN],
  ];
  let nx = M;
  notes.forEach(([h, d, col]) => {
    card(s, nx, 5.68, 3.9, 1.1, { fill: LIGHT, line: BORDER });
    s.addText(h, { x: nx + 0.2, y: 5.8, w: 3.5, h: 0.3, fontFace: BODY, fontSize: 11.5, bold: true, color: col, margin: 0 });
    s.addText(d, { x: nx + 0.2, y: 6.08, w: 3.5, h: 0.62, fontFace: BODY, fontSize: 10, color: GREY, margin: 0, lineSpacingMultiple: 1.1 });
    nx += 4.1;
  });
  footer(s);
}

/* =================================================================== *
 * SLIDE 10 — Everything else
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Economics", "What everything else costs", {
    subtitle: "The rest of the catalogue is priced the same way — a flat monthly figure with an allowance attached.",
  });
  const rows = [
    ["Container service", "Nano node — 0.25 vCPU, 512 MB", "$7 / month per node", "500 GB transfer per service"],
    ["Container service", "XLarge node — 4 vCPU, 8 GB", "$160 / month per node", "Scale = price × node count"],
    ["Managed database", "1 GB RAM, 40 GB SSD (standard)", "$15 / month", "High-availability plans cost double"],
    ["Object storage", "5 GB storage, 25 GB transfer", "$1 / month", "Free for the first 12 months"],
    ["Object storage", "250 GB storage, 500 GB transfer", "$5 / month", "100 GB tier sits at $3"],
    ["Load balancer", "Includes managed TLS certificate", "$18 / month", "Certificate issue and renewal are free"],
    ["CDN distribution", "CloudFront edge caching", "$2.50 / month", "50 GB/month free for 12 months"],
    ["Block storage", "Additional SSD disk", "$0.10 / GB / month", "Attach up to 16 TB per instance"],
    ["Snapshots", "Instance or disk backup", "$0.05 / GB / month", "Manual and automatic both charged"],
    ["Static IP · DNS zone", "IPv4 address · authoritative DNS", "Free", "IP billed only when left unattached"],
  ];
  styledTable(s, ["Resource", "Representative configuration", "Price", "What is included"], rows, {
    x: M, y: 1.82, w: 12.09, colW: [2.5, 3.8, 2.45, 3.34], rowH: 0.4, headSize: 11.5, bodySize: 10.8,
  });
  card(s, M, 6.32, 12.09, 0.6, { fill: NAVY, line: NAVY });
  s.addText(
    "Read the pattern: AWS sells you an allowance, not a meter. That is the entire commercial difference between Lightsail and the rest of AWS.",
    { x: M + 0.25, y: 6.32, w: 11.6, h: 0.6, fontFace: BODY, fontSize: 12.5, bold: true, color: WHITE, margin: 0, valign: "middle" }
  );
  footer(s);
}

/* =================================================================== *
 * SLIDE 11 — Cost chart
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Economics", "Where the fixed price actually pays off");

  s.addChart(
    pres.ChartType.bar,
    [{
      name: "Monthly cost (USD)",
      labels: ["Lightsail Small\n(any volume)", "EC2 equivalent\n100 GB out", "EC2 equivalent\n1 TB out", "EC2 equivalent\n3 TB out"],
      values: [12.0, 23.63, 106.79, 291.11],
    }],
    {
      x: M, y: 1.62, w: 7.85, h: 4.55,
      barDir: "col", barGapWidthPct: 55,
      chartColors: [TEAL, "8FA3B3", "6E8598", RED],
      showTitle: false, showLegend: false,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '"$"#,##0.00',
      dataLabelFontSize: 11, dataLabelFontFace: BODY, dataLabelColor: INK, dataLabelFontBold: true,
      catAxisLabelColor: INK, catAxisLabelFontSize: 10.5, catAxisLabelFontFace: BODY,
      valAxisLabelColor: GREY, valAxisLabelFontSize: 10, valAxisLabelFontFace: BODY,
      valAxisMinVal: 0, valAxisMaxVal: 330, valAxisMajorUnit: 50, valAxisLabelFormatCode: '"$"#,##0',
      valGridLine: { color: "E4EAEE", size: 1 }, catGridLine: { style: "none" },
      catAxisLineShow: true, valAxisLineShow: false,
    }
  );
  s.addText("Figure 3 — Same workload, two billing models.", {
    x: M, y: 6.25, w: 7.85, h: 0.26, fontFace: BODY, fontSize: 9.5, italic: true, color: GREY, margin: 0,
  });

  card(s, 8.8, 1.62, 3.91, 2.5, { fill: LIGHT, line: BORDER });
  s.addText("The assumption behind the bars", {
    x: 9.02, y: 1.78, w: 3.5, h: 0.3, fontFace: HEAD, fontSize: 14, bold: true, color: INK, margin: 0,
  });
  s.addText(
    "A Lightsail Small bundle is $12/month for 2 GB RAM, 2 vCPU, 60 GB SSD and 3 TB of outbound transfer.\n\n" +
      "The comparison builds the same thing on EC2 at us-east-1 list prices: a t3.small on demand, a 60 GB gp3 volume, one Elastic IP, and egress at $0.09/GB after the first 100 GB.",
    { x: 9.02, y: 2.12, w: 3.5, h: 1.9, fontFace: BODY, fontSize: 10.5, color: GREY, margin: 0, lineSpacingMultiple: 1.14 }
  );

  card(s, 8.8, 4.3, 3.91, 1.9, { fill: NAVY, line: NAVY });
  s.addText("Read it honestly", {
    x: 9.02, y: 4.46, w: 3.5, h: 0.3, fontFace: HEAD, fontSize: 14, bold: true, color: ORANGE, margin: 0,
  });
  s.addText(
    "Data transfer, not compute, drives the gap. At low traffic the two are close and EC2 wins back ground with Savings Plans. Lightsail's advantage is bandwidth included in the price — and a number you knew in advance.",
    { x: 9.02, y: 4.8, w: 3.5, h: 1.3, fontFace: BODY, fontSize: 10.5, color: "C4CFD8", margin: 0, lineSpacingMultiple: 1.14 }
  );
  footer(s);
}

/* =================================================================== *
 * SLIDE 12 — Networking and security
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Operations", "Networking and security by default");

  const pts = [
    ["Default-deny firewall", "Every instance ships with its own firewall; only the ports the blueprint needs are open.", "shield"],
    ["Free managed certificates", "A load balancer issues and renews TLS certificates at no charge; instances can use Let's Encrypt.", "globe"],
    ["Static IPv4, free in use", "Attached addresses cost nothing. An unattached one is billed at $0.005/hour to discourage hoarding.", "server"],
    ["Isolation and peering", "Resources live in a Lightsail-managed VPC. One click peers it with your default VPC.", "layers"],
  ];
  let y = 1.62;
  pts.forEach(([h, d, ic]) => {
    iconCircle(s, M, y, 0.56, NAVY, ic);
    s.addText(h, { x: M + 0.76, y: y - 0.04, w: 3.05, h: 0.3, fontFace: HEAD, fontSize: 14.5, bold: true, color: INK, margin: 0 });
    s.addText(d, { x: M + 0.76, y: y + 0.28, w: 3.05, h: 0.95, fontFace: BODY, fontSize: 11, color: GREY, margin: 0, lineSpacingMultiple: 1.14 });
    y += 1.28;
  });

  s.addImage({ path: path.join(ASSETS, "fig-network.png"), x: 4.55, y: 1.68, w: 8.16, h: 4.49 });
  s.addText("Figure 4 — A conventional highly available Lightsail deployment.", {
    x: 4.55, y: 6.24, w: 8.16, h: 0.26, fontFace: BODY, fontSize: 9.5, italic: true, color: GREY, align: "right", margin: 0,
  });
  s.addText(
    "A simpler console does not shrink your security responsibility — patching the OS inside a blueprint is still your job.",
    { x: M, y: 6.58, w: 12.09, h: 0.3, fontFace: BODY, fontSize: 11.5, italic: true, bold: true, color: RED, margin: 0 }
  );
  footer(s);
}

/* =================================================================== *
 * SLIDE 13 — Lightsail vs EC2
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Comparison", "Amazon Lightsail versus Amazon EC2");
  const rows = [
    ["Pricing model", "Fixed monthly bundle, allowance included", "Per-second metering across four separate meters"],
    ["Choice of hardware", "Eight general-purpose bundles plus two specialised families", "More than 750 instance types"],
    ["Maximum single instance", "64 GB / 16 vCPU general purpose; 512 GB memory optimised", "Up to 448 vCPU and 12,288 GB of memory"],
    ["Networking", "Lightsail-managed VPC; peering to the default VPC", "Full VPC design: subnets, route tables, NAT, gateways"],
    ["Automatic scaling", "Not available for instances; containers scale by node count", "EC2 Auto Scaling groups with policies and schedules"],
    ["Discount instruments", "None — the list price is the price", "Reserved Instances, Savings Plans, Spot"],
    ["Access control", "Coarse; Lightsail-level permissions", "Full IAM, resource policies, service control policies"],
    ["Time to first server", "Minutes, from a menu", "Longer; several dependent resources must exist first"],
    ["Best fit", "Predictable small workloads, fast delivery, cost certainty", "Elastic, large or compliance-heavy architectures"],
  ];
  styledTable(s, ["Dimension", "Amazon Lightsail", "Amazon EC2"], rows, {
    x: M, y: 1.6, w: 12.09, colW: [3.05, 4.52, 4.52], rowH: 0.47, headSize: 12, bodySize: 11,
  });
  s.addText(
    "The two are not rivals: Lightsail is the on-ramp, EC2 the motorway, and the snapshot export makes the journey cheap.",
    { x: M, y: 6.46, w: 12.09, h: 0.3, fontFace: BODY, fontSize: 12, italic: true, color: INK, margin: 0 }
  );
  footer(s);
}

/* =================================================================== *
 * SLIDE 14 — Market comparison
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Comparison", "Lightsail against the wider market", {
    subtitle: "Indicative entry pricing, August 2026. Figures are list prices and vary by region.",
  });
  const rows = [
    ["Amazon Lightsail", "$5 / month (nano, dual-stack)", "OS and application", "Generous transfer allowance; a documented path onto full AWS"],
    ["DigitalOcean Droplet", "$4 / month (512 MB); $6 is the practical floor", "OS and application", "Clean developer experience and documentation"],
    ["Linode / Akamai Nanode", "$5 / month (1 GB, 25 GB SSD, 1 TB)", "OS and application", "Strong price-to-memory ratio at the entry tier"],
    ["Heroku dyno", "$5 Eco (sleeps) · $7 Basic", "Application only", "True PaaS — no server to patch, but add-ons are billed separately"],
    ["Azure App Service", "Basic B1 around $55 / month", "Application only", "Deep integration with the Microsoft estate"],
  ];
  styledTable(s, ["Platform", "Entry price", "You still manage", "Distinguishing strength"], rows, {
    x: M, y: 1.9, w: 12.09, colW: [2.72, 3.1, 2.15, 4.12], rowH: 0.62, headSize: 12, bodySize: 11,
  });

  card(s, M, 5.62, 12.09, 1.12, { fill: LIGHT, line: TEAL });
  s.addText("What actually separates them", {
    x: M + 0.26, y: 5.74, w: 5.4, h: 0.3, fontFace: HEAD, fontSize: 14, bold: true, color: TEAL, margin: 0,
  });
  s.addText(
    "On raw price per gigabyte of RAM, Lightsail is competitive rather than cheapest. It wins on two things a price list does not show: the included data-transfer allowance, which is where independent VPS bills usually break, and the fact that the resource underneath is ordinary AWS — so growing out of Lightsail is a migration inside one account rather than a change of vendor.",
    { x: M + 0.26, y: 6.04, w: 11.55, h: 0.62, fontFace: BODY, fontSize: 11.5, color: INK, margin: 0, lineSpacingMultiple: 1.12 }
  );
  footer(s);
}

/* =================================================================== *
 * SLIDE 15 — Hands on
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Demonstration", "From nothing to a live HTTPS site");
  s.addImage({ path: path.join(ASSETS, "fig-deploy-flow.png"), x: M, y: 1.55, w: 12.09, h: 4.84 });
  s.addText("Figure 5 — The complete deployment path for a production WordPress site.", {
    x: M, y: 6.42, w: 5.6, h: 0.26, fontFace: BODY, fontSize: 9.5, italic: true, color: GREY, margin: 0,
  });
  s.addText("Everything above is also a single API call:", {
    x: 6.7, y: 6.4, w: 6.01, h: 0.24, fontFace: BODY, fontSize: 10, color: GREY, align: "right", margin: 0,
  });
  s.addText("aws lightsail create-instances --blueprint-id wordpress --bundle-id small_3_0", {
    x: 5.9, y: 6.64, w: 6.81, h: 0.26, fontFace: "Courier New", fontSize: 9.5, bold: true, color: NAVY, align: "right", margin: 0,
  });
  footer(s);
}

/* =================================================================== *
 * SLIDE 16 — Use cases
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Application", "Where Lightsail earns its place");
  const cases = [
    ["Websites and blogs", "WordPress, Ghost and Drupal on a bundle whose bandwidth allowance covers ordinary traffic.", "doc", NAVY],
    ["Development and test", "Disposable environments that mirror production and are deleted when the sprint ends.", "code", TEAL],
    ["Small business applications", "Line-of-business tools, booking systems and intranets for teams with no operations staff.", "wrench", NAVY],
    ["E-commerce storefronts", "Magento and PrestaShop blueprints with a managed database and a CDN in front.", "cart", TEAL],
    ["Learning and coursework", "A genuine cloud server for the price of a coffee — the fastest route into AWS for a student.", "cap", NAVY],
    ["Research computing", "Lightsail for Research packages CPU and GPU workstations with the same fixed-price model.", "gauge", TEAL],
  ];
  const cw = 3.9, ch = 2.26;
  cases.forEach(([h, d, ic, col], i) => {
    const x = M + (i % 3) * (cw + 0.19);
    const y = 1.62 + Math.floor(i / 3) * (ch + 0.28);
    card(s, x, y, cw, ch, { fill: WHITE, line: BORDER, shadow: true });
    iconCircle(s, x + 0.3, y + 0.3, 0.68, col, ic);
    s.addText(h, { x: x + 0.3, y: y + 1.12, w: cw - 0.6, h: 0.36, fontFace: HEAD, fontSize: 15.5, bold: true, color: INK, margin: 0 });
    s.addText(d, { x: x + 0.3, y: y + 1.5, w: cw - 0.6, h: 0.75, fontFace: BODY, fontSize: 11.5, color: GREY, margin: 0, lineSpacingMultiple: 1.14 });
  });
  s.addText(
    "The common thread is a workload whose ceiling is known in advance. Lightsail is a poor fit the moment demand becomes genuinely unpredictable.",
    { x: M, y: 6.52, w: 12.09, h: 0.32, fontFace: BODY, fontSize: 11.5, italic: true, color: INK, margin: 0 }
  );
  footer(s);
}

/* =================================================================== *
 * SLIDE 17 — Limitations
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Critique", "What you give up for the simplicity");

  card(s, M, 1.58, 5.95, 4.35, { fill: WHITE, line: RED, shadow: true });
  iconCircle(s, M + 0.3, 1.82, 0.56, RED, "warn");
  s.addText("Architectural limits", {
    x: M + 1.0, y: 1.88, w: 4.6, h: 0.34, fontFace: HEAD, fontSize: 17, bold: true, color: INK, margin: 0,
  });
  bullets(s, M + 0.32, 2.6, 5.3, 3.2, [
    "No auto scaling for instances — capacity is a manual decision",
    "No Reserved Instances, Savings Plans or Spot pricing",
    "Coarse IAM; unsuitable where least-privilege access is audited",
    "Integration with the wider AWS estate goes through VPC peering only",
    "Entry bundles run on burstable CPU — sustained load throttles",
  ], { size: 12, gap: 9 });

  card(s, 7.0, 1.58, 5.71, 4.35, { fill: WHITE, line: ORANGE, shadow: true });
  iconCircle(s, 7.3, 1.82, 0.56, ORANGE, "tag");
  s.addText("Operational and commercial limits", {
    x: 8.0, y: 1.88, w: 4.4, h: 0.34, fontFace: HEAD, fontSize: 17, bold: true, color: INK, margin: 0,
  });
  bullets(s, 7.32, 2.6, 5.1, 3.2, [
    "Default quotas: 20 instances, 5 static IPs and 6 DNS zones per account",
    "Exceeding the transfer allowance is billed per gigabyte",
    "Patching the OS and application inside a blueprint remains your job",
    "Bitnami-packaged blueprints are being retired through 2026–2027",
    "Not available in every AWS Region, unlike EC2",
  ], { size: 12, gap: 9 });

  card(s, M, 6.12, 12.09, 0.76, { fill: NAVY, line: NAVY });
  s.addText(
    "None of these is a defect. They are the deliberate cost of a fixed price — and each one is a signal that the workload may have outgrown the service.",
    { x: M + 0.25, y: 6.12, w: 11.6, h: 0.76, fontFace: BODY, fontSize: 12.5, bold: true, color: WHITE, margin: 0, valign: "middle" }
  );
  footer(s);
}

/* =================================================================== *
 * SLIDE 18 — Growth path
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Lifecycle", "Knowing when to leave — and how");
  s.addImage({ path: path.join(ASSETS, "fig-growth.png"), x: M, y: 1.62, w: 12.09, h: 4.53 });
  s.addText("Figure 6 — The decision boundary, and the built-in migration route across it.", {
    x: M, y: 6.24, w: 12.09, h: 0.26, fontFace: BODY, fontSize: 9.5, italic: true, color: GREY, margin: 0,
  });
  s.addText(
    "This is the case for Lightsail over an independent VPS: the exit is a supported AWS workflow, not a rebuild elsewhere.",
    { x: M, y: 6.56, w: 12.09, h: 0.3, fontFace: BODY, fontSize: 12, italic: true, bold: true, color: INK, margin: 0 }
  );
  footer(s);
}

/* =================================================================== *
 * SLIDE 19 — Conclusion
 * =================================================================== */
{
  const s = newSlide({ dark: true });
  titleBlock(s, "Conclusion", "Four things worth remembering", { dark: true });

  const takes = [
    ["Lightsail sells predictability, not power", "The bundle is a price you know before you deploy. Everything else follows from that one commercial decision."],
    ["It is PaaS-Lite, not PaaS", "AWS pre-builds the operating system and runtime, then still gives you root. Convenience on day one, control on day two."],
    ["The saving is in the bandwidth", "Compute is competitively priced; the included data-transfer allowance is where the fixed model genuinely pays."],
    ["Its limits are its exit signs", "No auto scaling, no Savings Plans, coarse IAM. When those start to hurt, snapshot and export to EC2."],
  ];
  let y = 1.62;
  takes.forEach(([h, d], i) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: M, y, w: 12.09, h: 1.18, fill: { color: NAVY_2 }, line: { color: "4A5D70", width: 1 }, rectRadius: 0.08,
    });
    s.addShape(pres.ShapeType.ellipse, { x: M + 0.3, y: y + 0.31, w: 0.56, h: 0.56, fill: { color: ORANGE } });
    s.addText(String(i + 1), {
      x: M + 0.3, y: y + 0.31, w: 0.56, h: 0.56, fontFace: HEAD, fontSize: 19, bold: true, color: NAVY, align: "center", valign: "middle", margin: 0,
    });
    s.addText(h, { x: M + 1.06, y: y + 0.2, w: 10.8, h: 0.36, fontFace: HEAD, fontSize: 17, bold: true, color: WHITE, margin: 0 });
    s.addText(d, { x: M + 1.06, y: y + 0.58, w: 10.8, h: 0.48, fontFace: BODY, fontSize: 12.5, color: "C4CFD8", margin: 0 });
    y += 1.3;
  });
  s.addText("Thank you  ·  Questions welcome", {
    x: M, y: 6.72, w: 12.09, h: 0.4, fontFace: HEAD, fontSize: 18, bold: true, italic: true, color: ORANGE, align: "center", margin: 0,
  });
}

/* =================================================================== *
 * SLIDE 20 — References
 * =================================================================== */
{
  const s = newSlide();
  titleBlock(s, "Sources", "References", {
    subtitle: "All pricing and feature claims verified against these sources in August 2026.",
  });
  const refs = [
    "Amazon Web Services. Amazon Lightsail — Pricing. aws.amazon.com/lightsail/pricing",
    "Amazon Web Services. Amazon Lightsail User Guide: instance bundles, blueprints, buckets, container services, and account quotas. docs.aws.amazon.com/lightsail",
    "Amazon Web Services. “Announcing memory-optimized instance bundles for Amazon Lightsail”, What's New, 2 February 2026.",
    "Amazon Web Services. “Announcing compute-optimized instance bundles for Amazon Lightsail”, What's New, April 2026.",
    "Amazon Web Services. “Amazon Lightsail expands blueprint selection with updated support for Node.js, LAMP and Ruby on Rails blueprints”, What's New, January 2026.",
    "Amazon Web Services. “Amazon Lightsail is now available in three additional AWS Regions”, What's New, June 2026.",
    "Amazon Web Services. Lightsail documentation: “Blueprints packaged by Bitnami” — deprecation schedule, 2026–2027.",
    "Amazon Web Services. Lightsail documentation: “Export Lightsail snapshots to Amazon EC2” and the Upgrade to EC2 wizard.",
    "AWS re:Post. “Compare Amazon EC2 and Amazon Lightsail”, AWS Knowledge Center.",
    "Amazon Web Services. Amazon EC2 On-Demand Pricing and Amazon EBS Pricing, us-east-1 (used for the Figure 3 cost model).",
    "DigitalOcean, Akamai (Linode), Heroku and Microsoft Azure published price lists, consulted August 2026 for Slide 14.",
  ];
  s.addText(
    refs.map((r, i) => ({ text: r, options: { bullet: { type: "number" }, breakLine: i < refs.length - 1, paraSpaceAfter: 6 } })),
    { x: M, y: 1.9, w: 12.09, h: 4.6, fontFace: BODY, fontSize: 11.5, color: INK, margin: 0, lineSpacingMultiple: 1.06 }
  );
  s.addText("Prepared by Hridiyansh Shukla  ·  Registration No. 2427030591  ·  August 2026", {
    x: M, y: 6.62, w: 12.09, h: 0.32, fontFace: BODY, fontSize: 11.5, italic: true, color: GREY, align: "center", margin: 0,
  });
  footer(s);
}

/* ------------------------- speaker notes --------------------------- */
const NOTES = require("./notes.js");
pres.slides.forEach((s, i) => {
  if (NOTES[i]) s.addNotes(NOTES[i]);
});

pres.writeFile({ fileName: OUTFILE }).then(() => console.log("wrote", OUTFILE));
