"""Render a Churn Autopsy as a self-contained HTML page.

Self-contained on purpose: inline CSS, inline SVG charts, no external requests. The
file can be emailed, opened offline, printed, or dropped behind an unguessable URL
without any of it being a deployment.

Design rules, and each exists because of a way reports like this usually fail:

**Money at the top.** The reader is a founder with half an hour, not an analyst. The
first thing on the page is what churn is costing them per year.

**Every finding says whether it was measured or estimated.** A number computed from
their invoices and a number extrapolated from an industry benchmark are different
kinds of claim, and blurring them is what turns a diagnostic into a sales document.

**Caveats are printed, not omitted.** What could not be computed appears on the page.
A report that hides its own gaps is not worth the trust it is trying to build.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from keel.report.autopsy import Autopsy, _money

CSS = """
/* Theme: LIGHT by default, following the system preference when one is expressed,
   and overridable in both directions by the toggle (which sets data-theme on the
   root). Light is the fallback because this report gets printed and forwarded, and
   an unexpectedly dark page wastes ink and reads badly on paper. */
:root {
  color-scheme: light;
  --bg: #ffffff; --fg: #1a1a1a; --muted: #666; --body: #333;
  --line: #e4e4e4; --rule: #ececec; --panel: #fafafa;
  --accent: #1B5E20; --accent-bg: #f6f8f7; --accent-line: #2E7D32;
  --ok-bg: #E8F5E9; --ok-fg: #1B5E20;
  --warn-bg: #FFF8E1; --warn-fg: #8D6E00; --warn-line: #F9A825;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #16181a; --fg: #e8e8e8; --muted: #9aa0a6; --body: #ccc;
    --line: #2c2f33; --rule: #2c2f33; --panel: #1e2124;
    --accent: #7CC47F; --accent-bg: #17251a; --accent-line: #2E7D32;
    --ok-bg: #1B3A1E; --ok-fg: #A5D6A7;
    --warn-bg: #3A3320; --warn-fg: #FFD54F; --warn-line: #F9A825;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #16181a; --fg: #e8e8e8; --muted: #9aa0a6; --body: #ccc;
  --line: #2c2f33; --rule: #2c2f33; --panel: #1e2124;
  --accent: #7CC47F; --accent-bg: #17251a; --accent-line: #2E7D32;
  --ok-bg: #1B3A1E; --ok-fg: #A5D6A7;
  --warn-bg: #3A3320; --warn-fg: #FFD54F; --warn-line: #F9A825;
}

* { box-sizing: border-box; }
body {
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  max-width: 820px; margin: 0 auto; padding: 40px 24px 80px;
  color: var(--fg); background: var(--bg);
}
h1 { font-size: 30px; margin: 0 0 4px; letter-spacing: -0.02em; }
h2 { font-size: 20px; margin: 44px 0 12px; letter-spacing: -0.01em; }
.sub { color: var(--muted); margin: 0 0 36px; font-size: 15px; }
.headline {
  background: var(--accent-bg); border-left: 4px solid var(--accent-line);
  padding: 22px 26px; border-radius: 4px; margin: 0 0 12px;
}
.headline .num { font-size: 38px; font-weight: 650; color: var(--accent);
  letter-spacing: -0.02em; }
.headline .lbl { color: var(--muted); font-size: 15px; margin-top: 2px; }
.grid { display: grid; gap: 14px; margin: 22px 0;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
.stat { border: 1px solid var(--line); border-radius: 4px; padding: 14px 16px; }
.stat .v { font-size: 22px; font-weight: 600; }
.stat .k { color: var(--muted); font-size: 13px; margin-top: 2px; }
.finding { border: 1px solid var(--line); border-radius: 5px;
  padding: 20px 22px; margin: 0 0 14px; }
.finding .top { display: flex; justify-content: space-between;
  align-items: baseline; gap: 16px; flex-wrap: wrap; }
.finding h3 { font-size: 17px; margin: 0; flex: 1 1 60%; }
.finding .val { font-size: 21px; font-weight: 650; color: var(--accent);
  white-space: nowrap; }
.badge { display: inline-block; font-size: 11.5px; padding: 2px 8px;
  border-radius: 10px; margin-top: 8px; }
.measured { background: var(--ok-bg); color: var(--ok-fg); }
.estimated { background: var(--warn-bg); color: var(--warn-fg); }
.finding p { margin: 10px 0 0; color: var(--body); }
.action { margin-top: 12px; padding: 11px 14px; background: var(--panel);
  border-radius: 4px; font-size: 15px; }
.action b { color: var(--accent); }
table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 15px; }
th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--rule); }
th { font-weight: 600; color: var(--muted); font-size: 13px;
  text-transform: uppercase; letter-spacing: 0.03em; }
td.n { text-align: right; font-variant-numeric: tabular-nums; }
/* Charts inherit `color`, so their axis text and gridlines follow the theme. */
.chart { margin: 18px 0; color: var(--muted); }
.chart svg { max-width: 100%; height: auto; }
.notes { background: var(--warn-bg); border-left: 4px solid var(--warn-line);
  padding: 16px 20px; border-radius: 4px; margin: 24px 0; font-size: 15px;
  color: var(--fg); }
.notes ul { margin: 8px 0 0; padding-left: 20px; }
footer { margin-top: 56px; padding-top: 20px; border-top: 1px solid var(--rule);
  color: var(--muted); font-size: 13.5px; }
#theme {
  position: fixed; top: 14px; right: 14px; z-index: 10;
  font: inherit; font-size: 13px; padding: 6px 12px; cursor: pointer;
  background: var(--panel); color: var(--muted);
  border: 1px solid var(--line); border-radius: 999px;
}
#theme:hover { color: var(--fg); }
/* Printing always uses the light palette: an unexpectedly dark page wastes ink. */
@media print {
  :root { color-scheme: light;
    --bg: #fff; --fg: #000; --muted: #444; --body: #222;
    --line: #ccc; --rule: #ddd; --panel: #f6f6f6;
    --accent: #1B5E20; --accent-bg: #f4f7f4; }
  #theme { display: none; }
  body { padding: 0; max-width: none; }
  .finding { break-inside: avoid; }
}
"""


#: Sentinel colours written into the SVG by matplotlib, then swapped for
#: `currentColor` so the charts follow the page theme. Without this the axis text is
#: baked to a fixed colour at render time and becomes invisible in dark mode -- which
#: is exactly what happened on the first version of this report.
_TEXT_SENTINEL = "#abcdef"
_AXIS_SENTINEL = "#123456"

_CHART_RC = {
    "text.color": _TEXT_SENTINEL,
    "axes.labelcolor": _TEXT_SENTINEL,
    "xtick.color": _TEXT_SENTINEL,
    "ytick.color": _TEXT_SENTINEL,
    "axes.edgecolor": _AXIS_SENTINEL,
    "grid.color": _AXIS_SENTINEL,
}


THEME_TOGGLE = """<button id="theme">Dark mode</button>
<script>
(function () {
  var root = document.documentElement;
  var btn = document.getElementById("theme");
  function label() {
    var dark = root.getAttribute("data-theme") === "dark" ||
      (!root.hasAttribute("data-theme") &&
       window.matchMedia("(prefers-color-scheme: dark)").matches);
    btn.textContent = dark ? "Light mode" : "Dark mode";
  }
  btn.addEventListener("click", function () {
    var dark = root.getAttribute("data-theme") === "dark" ||
      (!root.hasAttribute("data-theme") &&
       window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.setAttribute("data-theme", dark ? "light" : "dark");
    label();
  });
  label();
})();
</script>"""


def _svg(fig) -> str:
    """Render a figure to inline SVG whose text and axes inherit the page colour."""
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    svg = buf.getvalue()
    svg = svg[svg.index("<svg") :]
    # Data colours (the green line, the red bars) are deliberately left alone; only
    # chrome inherits.
    return svg.replace(_TEXT_SENTINEL, "currentColor").replace(_AXIS_SENTINEL, "currentColor")


def _retention_chart(a: Autopsy) -> str:
    curve = a.retention_curve
    with plt.rc_context(_CHART_RC):
        fig, ax = plt.subplots(figsize=(7.2, 3.0))
        ax.plot(curve["month"], curve["retention"] * 100, color="#2E7D32", lw=2.4)
        ax.fill_between(curve["month"], 0, curve["retention"] * 100,
                        color="#2E7D32", alpha=0.10)
        ax.set_xlabel("Months since signup", fontsize=9)
        ax.set_ylabel("Still subscribed (%)", fontsize=9)
        ax.set_ylim(0, 100)
        ax.grid(alpha=0.28, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=8.5)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        return _svg(fig)


def _decline_chart(a: Autopsy) -> str:
    mix = a.decline_mix
    if mix.empty:
        return ""
    with plt.rc_context(_CHART_RC):
        fig, ax = plt.subplots(figsize=(7.2, max(2.0, 0.5 * len(mix) + 1.0)))
        y = range(len(mix))
        ax.barh(list(y), mix["amount"], color="#C62828", alpha=0.88)
        ax.set_yticks(list(y))
        ax.set_yticklabels(mix["code"], fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("Value of failed payments (observed window)", fontsize=9)
        ax.grid(alpha=0.28, axis="x", lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=8.5)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        return _svg(fig)


#: Printed at the very top of a sample report, before anything else on the page.
#:
#: A report that *looks* like a real business's numbers must say that it is not, in the
#: first thing the reader sees. Two reasons, and the second is the one that costs money
#: if ignored: a prospect who mistakes a demo for a real client's data learns that we
#: circulate client data, which is precisely the fear the engagement has to overcome.
DEMO_BANNER = """
  <div class="demobanner">
    <h2>This is a sample, not a real business</h2>
    <p>Every figure on this page comes from a <strong>simulated</strong> subscription
       business. No real company's data appears here, and none ever will in a sample —
       your report would be built from your own export and shown to nobody else.</p>
    <p>It is here so you can see the <em>shape</em> of the output before deciding whether
       to send anything.</p>
  </div>"""

DEMO_CSS = """
.demobanner { border: 2px solid var(--warn, #b45309); border-radius: 8px;
  padding: 1rem 1.2rem; margin: 0 0 1.6rem; background: var(--warnbg, #fffbeb); }
.demobanner h2 { margin: 0 0 .4rem; font-size: 1.05rem; color: var(--warn, #b45309);
  border: none; padding: 0; }
.demobanner p { margin: .35rem 0; }
:root { --warn: #b45309; --warnbg: #fffbeb; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --warn: #fbbf24; --warnbg: #2a2005; }
}
:root[data-theme="dark"] { --warn: #fbbf24; --warnbg: #2a2005; }
"""


def render(
    a: Autopsy,
    business_name: str = "Your business",
    out: Path | None = None,
    demo: bool = False,
) -> Path:
    """Write the report and return its path.

    `demo=True` marks the page as built from simulated data. It is a parameter rather
    than something the caller remembers to write into `business_name`, so a sample can
    never be produced without saying so.
    """
    findings = a.findings()

    stats = "".join(
        f'<div class="stat"><div class="v">{v}</div><div class="k">{k}</div></div>'
        for v, k in [
            (f"{a.n_active:,}", "active customers"),
            (_money(a.mrr_active), "monthly recurring revenue"),
            (f"{a.monthly_logo_churn:.1%}", "monthly customer churn"),
            (f"{a.monthly_revenue_churn:.1%}", "monthly revenue churn"),
            (f"{a.recovery_rate:.0%}", "failed payments recovered"),
            (f"{a.involuntary_share:.0%}", "churn that is involuntary"),
        ]
    )

    finding_html = ""
    for f in findings:
        cls = "measured" if f.measured else "estimated"
        finding_html += f"""
        <div class="finding">
          <div class="top">
            <h3>{f.title}</h3>
            <div class="val">{_money(f.annual_value)}<span
               style="font-size:13px;font-weight:400">/yr</span></div>
          </div>
          <span class="badge {cls}">{f.confidence}</span>
          <p>{f.detail}</p>
          <div class="action"><b>What to do:</b> {f.action}</div>
        </div>"""

    decline_rows = "".join(
        f"<tr><td>{r['code']}</td><td class='n'>{int(r['n'])}</td>"
        f"<td class='n'>{_money(r['amount'])}</td>"
        f"<td class='n'>{r['recovery_rate']:.0%}</td></tr>"
        for _, r in a.decline_mix.iterrows()
    )
    decline_section = (
        f"""<h2>Why payments failed</h2>
        <div class="chart">{_decline_chart(a)}</div>
        <table>
          <tr><th>Decline reason</th><th style="text-align:right">Count</th>
              <th style="text-align:right">Value</th>
              <th style="text-align:right">Recovered</th></tr>
          {decline_rows}
        </table>"""
        if not a.decline_mix.empty else ""
    )

    notes_section = (
        '<div class="notes"><b>What we could not determine from this export</b><ul>'
        + "".join(f"<li>{n}</li>" for n in a.notes)
        + "</ul></div>"
        if a.notes else ""
    )

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Churn Autopsy{" (sample)" if demo else ""} — {business_name}</title>
<style>{CSS}{DEMO_CSS if demo else ""}</style></head>
<body>
  {THEME_TOGGLE}
{DEMO_BANNER if demo else ""}
  <h1>Churn Autopsy{" &mdash; sample" if demo else ""}</h1>
  <p class="sub">{business_name} &middot; {date.today():%d %B %Y} &middot;
     based on {a.n_customers:,} customers over {a.window_days/30.44:.0f} months
     of billing history</p>

  <div class="headline">
    <div class="num">{_money(a.annual_churn_cost)}</div>
    <div class="lbl">is what churn costs you per year at your current rate</div>
  </div>

  <div class="grid">{stats}</div>

  <h2>What we found</h2>
  <p class="sub" style="margin-bottom:18px">Ranked by money at stake. Green means measured
     directly from your data; amber means estimated using published industry benchmarks.</p>
  {finding_html}

  <h2>How long customers stay</h2>
  <div class="chart">{_retention_chart(a)}</div>
  <p style="color:#666;font-size:14.5px">Share of customers still subscribed after each month.
     A curve that flattens is healthy — it means the fragile customers leave early and the rest
     stay. A curve that keeps falling means you are still losing established customers.</p>

  {decline_section}
  {notes_section}

  <footer>
    Prepared from your billing export. Recovery is inferred by matching a failed invoice to a
    payment from the same customer within {30} days, because billing exports rarely link a retry
    to the attempt it retried.<br><br>
    This report describes what <em>has</em> happened. It deliberately does not recommend which
    individual customers to contact — doing that reliably requires a record of past
    interventions and their outcomes, which no billing export contains.
  </footer>
</body></html>"""

    out = out or Path("churn_autopsy.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def generate(
    data,
    business_name: str = "Your business",
    out: Path | None = None,
    demo: bool = False,
) -> Path:
    """Analyse a canonical Dataset and write the report. The whole pipeline."""
    from keel.report.autopsy import analyse

    return render(analyse(data), business_name=business_name, out=out, demo=demo)
