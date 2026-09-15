// Record the browser parts of the demo: real pages written by `make sample` and
// `make dashboard`, opened in Chrome, scrolled, clicked and filtered for real. The row
// expansion is the page's own click handler firing; the filter is the page's own <select>.
//
// Annotations (step bar, caption, highlight box, cursor dot) are drawn in a layer attached to
// <html>, outside <body>, so they never change the page's own layout or behaviour.
//
// Run from the repository root after `make sample` and `make dashboard`:
//   node presentation/video/record_browser.mjs
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const OUT = path.join(HERE, "..", "build", "video", "clips");
const SPEC = JSON.parse(fs.readFileSync(path.join(HERE, "steps.json"), "utf8"));
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const N = SPEC.steps.length;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const LAYER_CSS = `
#riq-bar{position:fixed;left:0;top:0;right:0;height:100px;background:#18283A;z-index:2147483646;
  font-family:Helvetica,Arial,sans-serif;box-sizing:border-box;padding:20px 64px 0}
#riq-bar .s{color:#43C6B1;font-weight:700;font-size:20px;letter-spacing:1px;line-height:24px}
#riq-bar .t{color:#fff;font-weight:700;font-size:34px;line-height:44px}
#riq-bar .t span{color:#8296AA;font-weight:400;font-size:24px;margin-left:24px}
#riq-cap{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);max-width:1600px;width:max-content;
  background:#08101A;color:#fff;font:28px/38px Helvetica,Arial,sans-serif;padding:12px 28px;border-radius:14px;
  z-index:2147483646;text-align:center;transition:opacity .25s}
#riq-box{position:fixed;border:4px solid #F2A541;border-radius:12px;z-index:2147483645;pointer-events:none;
  opacity:0;transition:left .35s ease,top .35s ease,width .35s ease,height .35s ease,opacity .25s}
#riq-cursor{position:fixed;left:960px;top:760px;width:28px;height:28px;border-radius:50%;opacity:0;
  background:rgba(255,255,255,.92);border:3px solid #12263A;z-index:2147483647;pointer-events:none;
  transform:translate(-50%,-50%);transition:transform .12s}
`;

async function setup(page, n, step, zoom) {
  await page.evaluate(({ css, n, N, title, subtitle, zoom }) => {
    document.body.style.zoom = String(zoom);
    document.documentElement.style.paddingTop = "100px";
    document.documentElement.style.paddingBottom = "160px";
    const style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
    const layer = document.createElement("div");
    layer.innerHTML = `<div id="riq-bar"><div class="s">STEP ${n} OF ${N}</div>` +
      `<div class="t">${title}<span>${subtitle}</span></div></div>` +
      `<div id="riq-cap" style="opacity:0"></div><div id="riq-box"></div><div id="riq-cursor"></div>`;
    document.documentElement.appendChild(layer);
    window.riq = {
      find(text) {
        const all = [...document.body.querySelectorAll("*")].filter((e) => e.textContent.includes(text));
        all.sort((a, b) => a.textContent.length - b.textContent.length);
        return all[0] || null;
      },
      framed(el, up = 7) {
        let e = el;
        for (let i = 0; i < up && e && e !== document.body; i++) {
          const cs = getComputedStyle(e);
          const border = cs.borderTopStyle !== "none" && parseFloat(cs.borderTopWidth) > 0;
          const bg = cs.backgroundColor !== "rgba(0, 0, 0, 0)" && cs.backgroundColor !== "transparent";
          if (border || bg) return e;
          e = e.parentElement;
        }
        return el;
      },
      row(id) {
        return [...document.querySelectorAll("tr.row")].find((r) => r.cells[0].textContent.trim() === id);
      },
      detail(id) {
        const r = window.riq.row(id);
        return r ? document.getElementById("d" + r.dataset.i) : null;
      },
    };
  }, { css: LAYER_CSS, n, N, title: step.title, subtitle: step.subtitle, zoom });
}

const caption = (page, text) => page.evaluate((t) => {
  const c = document.getElementById("riq-cap");
  c.style.opacity = t ? 1 : 0;
  if (t) c.textContent = t;
}, text);

// Highlight whatever `locate` returns (a string evaluated in the page), padded.
const highlight = (page, locate, pad = 10, color = "#F2A541") => page.evaluate(({ locate, pad, color }) => {
  const b = document.getElementById("riq-box");
  const el = locate ? eval(locate) : null; // eslint-disable-line no-eval
  if (!el) { b.style.opacity = 0; return false; }
  const r = el.getBoundingClientRect();
  Object.assign(b.style, { left: `${r.left - pad}px`, top: `${r.top - pad}px`, width: `${r.width + 2 * pad}px`,
    height: `${r.height + 2 * pad}px`, borderColor: color, opacity: 1 });
  return true;
}, { locate, pad, color });

async function scrollToEl(page, locate, offset = 170, ms = 1500) {
  const [y0, y1] = await page.evaluate(({ locate, offset }) => {
    const el = eval(locate); // eslint-disable-line no-eval
    const target = el ? window.scrollY + el.getBoundingClientRect().top - offset : window.scrollY;
    return [window.scrollY, Math.max(0, target)];
  }, { locate, offset });
  await scrollY(page, y0, y1, ms);
}
async function scrollY(page, y0, y1, ms) {
  const steps = Math.max(1, Math.round(ms / 16));
  for (let i = 1; i <= steps; i++) {
    const p = i / steps;
    const e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
    await page.evaluate((v) => window.scrollTo(0, v), y0 + (y1 - y0) * e);
    await sleep(16);
  }
}

async function clickEl(page, locate) {
  const pt = await page.evaluate((locate) => {
    const r = eval(locate).getBoundingClientRect(); // eslint-disable-line no-eval
    return [r.left + Math.min(120, r.width / 2), r.top + r.height / 2];
  }, locate);
  const from = await page.evaluate(() => {
    const c = document.getElementById("riq-cursor");
    c.style.opacity = 1;
    return [parseFloat(c.style.left), parseFloat(c.style.top)];
  });
  const steps = 30;
  for (let i = 1; i <= steps; i++) {
    const p = i / steps, e = 1 - Math.pow(1 - p, 3);
    const x = from[0] + (pt[0] - from[0]) * e, y = from[1] + (pt[1] - from[1]) * e;
    await page.mouse.move(x, y);
    await page.evaluate(([x, y]) => Object.assign(document.getElementById("riq-cursor").style,
      { left: `${x}px`, top: `${y}px` }), [x, y]);
    await sleep(16);
  }
  await page.evaluate(() => { document.getElementById("riq-cursor").style.transform = "translate(-50%,-50%) scale(.7)"; });
  await page.mouse.click(pt[0], pt[1]);
  await sleep(140);
  await page.evaluate(() => { document.getElementById("riq-cursor").style.transform = "translate(-50%,-50%) scale(1)"; });
}

async function record(browser, name, n, step, zoom, url, script) {
  const page = await browser.newPage();
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "dark" }]);
  await page.goto(url, { waitUntil: "load" });
  await setup(page, n, step, zoom);
  await sleep(300);
  const file = path.join(OUT, `${name}.webm`);
  const rec = await page.screencast({ path: file });
  await script(page);
  await rec.stop();
  await page.close();
  console.log("recorded", file);
}

const idx = (id) => SPEC.steps.findIndex((s) => s.id === id);
const url = (f) => pathToFileURL(path.join(ROOT, f)).href;

fs.mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true,
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 } });

await record(browser, "report", idx("report") + 1, SPEC.steps[idx("report")], 1.3,
  url("sample_churn_autopsy.html"), async (page) => {
    await sleep(600);
    await caption(page, "The report opens by stating that this business is simulated.");
    await highlight(page, "riq.framed(riq.find('This is a sample, not a real business'))");
    await sleep(4500);
    await caption(page, "Headline: what churn costs this business per year, computed from its billing data.");
    await highlight(page, "riq.framed(riq.find('is what churn costs you per year'))");
    await sleep(4500);
    await highlight(page, null);
    await scrollToEl(page, "riq.find('is what churn costs you per year')", 190, 1200);
    await caption(page, "Customer and revenue churn, failed-payment recovery, and the share of churn that is involuntary.");
    await highlight(page, "riq.framed(riq.find('churn that is involuntary'))");
    await sleep(4500);
    await highlight(page, null);
    await scrollToEl(page, "riq.find('What we found')");
    await caption(page, "Findings are ranked by money at stake and tagged: measured from the data, or estimated from benchmarks.");
    await highlight(page, "riq.framed(riq.find('What churn costs you annually'))");
    await sleep(5500);
    await caption(page, "Each finding ends with a concrete next action.");
    await highlight(page, "riq.framed(riq.find('Fix the involuntary share first'))");
    await sleep(4000);
    await highlight(page, null);
    await scrollToEl(page, "riq.find('is your biggest single decline reason')");
    await caption(page, "Failed payments: the largest decline reason, and when retries should run.");
    await highlight(page, "riq.framed(riq.find('Move retries onto the next salary date'))");
    await sleep(5000);
    await highlight(page, null);
    await caption(page, "The remaining findings follow the same pattern.");
    const [y0, y1] = await page.evaluate(() => [window.scrollY, document.documentElement.scrollHeight - innerHeight]);
    await scrollY(page, y0, y1, 7000);
    await sleep(1500);
  });

await record(browser, "dashboard", idx("dashboard") + 1, SPEC.steps[idx("dashboard")], 1.25,
  url("retention_dashboard.html"), async (page) => {
    await sleep(600);
    await caption(page, "First, how far to trust it: better than one well-chosen offer on 58% of tests (95% CI 42–72%), not distinguishable from chance.");
    await highlight(page, "riq.framed(riq.find('Read this before you act on anything below'))");
    await sleep(7000);
    await caption(page, "The decision: contact 142 of the 472 customers assessed, and deliberately leave 330 alone.");
    await highlight(page, "riq.framed(riq.find('customers to contact, out of'))");
    await sleep(5500);
    await highlight(page, null);
    await scrollToEl(page, "riq.find('What we recommend')");
    await caption(page, "The offer mix: mostly low-cost downgrade offers, 10 discounts and 1 pause.");
    await highlight(page, "(() => { const h = [...document.querySelectorAll('h2,h3')].find(e => e.textContent.includes('What we recommend')); return h && h.nextElementSibling; })()");
    await sleep(5500);
    await highlight(page, null);
    await scrollToEl(page, "riq.find('Who to contact')", 150);
    await caption(page, "Each row shows the offer, the expected gain, and the chance it pays.");
    await sleep(3500);
    await clickEl(page, "riq.row('379')");
    await sleep(400);
    await caption(page, "Clicking a customer shows why: value if kept, risk without contact, the offer's effect and cost, and the next-best offer.");
    await highlight(page, "riq.detail('379')", 8, "#43C6B1");
    await sleep(8000);
    await highlight(page, null);
    await scrollToEl(page, "riq.row('1212')", 320);
    await clickEl(page, "riq.row('1212')");
    await sleep(400);
    await caption(page, "Flagged: only a 47% chance this offer makes money, so it is marked as thin evidence, a suggestion rather than a finding.");
    await highlight(page, "riq.detail('1212')", 8);
    await sleep(8000);
    await highlight(page, null);
    await scrollToEl(page, "document.getElementById('filter')", 260);
    await caption(page, "Recommendations can be filtered by offer.");
    await highlight(page, "document.getElementById('filter')", 8);
    await sleep(2200);
    const value = await page.evaluate(() => {
      const o = [...document.querySelectorAll("#filter option")].find((x) => x.textContent.toLowerCase().includes("downgrade"));
      return o ? o.value : null;
    });
    if (value !== null) {
      await page.select("#filter", value);
      await caption(page, "Showing downgrade offers only.");
      await sleep(4000);
      await page.select("#filter", "all");
    }
    await highlight(page, null);
    await caption(page, "");
    const y0 = await page.evaluate(() => window.scrollY);
    await scrollY(page, y0, 0, 2200);
    await sleep(1500);
  });

await browser.close();
