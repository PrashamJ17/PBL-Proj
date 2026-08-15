"""The retention dashboard: a self-contained HTML page an owner can act from.

The last Phase 5 deliverable. Same shape as the Churn Autopsy (`render.py`) and for the
same reasons -- inline CSS, inline SVG, no external requests, no server. It can be
emailed, opened offline, printed, or dropped behind an unguessable URL, and none of that
is a deployment. D-040 orders the go-to-market by *trust required*, and a file someone
opens asks for less trust than a login.

It also keeps the core on numpy/pandas/scipy (invariant 7). A Streamlit or Next.js
dashboard would add a runtime, a build step and a hosting bill to a project whose gate is
still "does this make money", and the plan was explicit that Streamlit would not survive
a real launch anyway.

The one design decision that matters
------------------------------------
**The reliability banner is the first thing on the page, above the recommendations.**

The conventional retention dashboard leads with a large red number -- "92.4% churn risk,
SAVE NOW" -- and hides the model's accuracy in a methodology tab, if it reports it at
all. We measured a sibling product doing exactly this on top of a model with ROC-AUC
0.543 (D-060). The failure is not that the number is wrong; it is that the page is
designed so nobody asks.

D-058 measured this optimiser beating a single well-chosen offer on **58% of tests, CI
[0.42, 0.72]** -- better than guessing, not proven. A page that renders per-customer
recommendations without that sentence in the reader's eye is claiming more than five
phases of work support. So it goes at the top, in the same weight as the headline
number, and `render_dashboard` has no argument to turn it off.

Everything else follows from "what would let someone act, and what would let them stop":
what we recommend, why each person, why we are leaving most people alone, and what this
cannot tell you.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from html import escape
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from retainiq.report.reasons import Reason
from retainiq.report.render import _CHART_RC, CSS, THEME_TOGGLE, _svg

__all__ = ["render_dashboard"]

#: Appended to the report stylesheet. Only what the dashboard adds: the banner, the
#: action table and its expandable rows.
EXTRA_CSS = """
.banner {
  border: 2px solid var(--warn, #b45309); border-radius: 8px;
  padding: 1rem 1.2rem; margin: 1.5rem 0; background: var(--warnbg, #fffbeb);
}
.banner h2 { margin: 0 0 .4rem; font-size: 1.05rem; color: var(--warn, #b45309); }
.banner p { margin: .3rem 0; }
:root { --warn: #b45309; --warnbg: #fffbeb; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --warn: #fbbf24; --warnbg: #2a2005; }
}
:root[data-theme="dark"] { --warn: #fbbf24; --warnbg: #2a2005; }

table.actions { width: 100%; border-collapse: collapse; margin: 1rem 0; }
table.actions th, table.actions td {
  text-align: left; padding: .5rem .6rem; border-bottom: 1px solid var(--rule, #e5e5e5);
  vertical-align: top;
}
table.actions th { font-size: .82rem; text-transform: uppercase; letter-spacing: .04em;
  color: var(--muted); }
table.actions td.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.detail td { background: var(--detailbg, #fafafa); font-size: .92rem; }
tr.detail.hidden { display: none; }
:root { --rule: #e5e5e5; --detailbg: #fafafa; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --rule: #333; --detailbg: #1c1c1c; }
}
:root[data-theme="dark"] { --rule: #333; --detailbg: #1c1c1c; }
tr.row { cursor: pointer; }
tr.row:hover { background: var(--detailbg, #fafafa); }
.badge { display: inline-block; padding: .12rem .5rem; border-radius: 999px;
  font-size: .78rem; border: 1px solid var(--rule); }
.reason { margin: .25rem 0; }
.reason .k { color: var(--muted); display: inline-block; min-width: 8.5rem; }
.caution { color: var(--warn); }
.overflow { overflow-x: auto; }
"""

#: Row expansion. Vanilla, because a dependency for a disclosure triangle would be
#: absurd on a page whose whole premise is that it needs no runtime.
TABLE_JS = """<script>
(function () {
  document.querySelectorAll("tr.row").forEach(function (r) {
    r.addEventListener("click", function () {
      var d = document.getElementById("d" + r.dataset.i);
      if (d) { d.classList.toggle("hidden"); }
    });
  });
  var f = document.getElementById("filter");
  if (f) {
    f.addEventListener("change", function () {
      var want = f.value;
      document.querySelectorAll("tr.row").forEach(function (r) {
        var show = (want === "all" || r.dataset.rung === want);
        r.style.display = show ? "" : "none";
        var d = document.getElementById("d" + r.dataset.i);
        if (d && !show) { d.classList.add("hidden"); }
      });
    });
  }
})();
</script>"""


def _money(x: float) -> str:
    return f"{x:,.0f}"


def _rung_chart(counts: Counter, names: list[str]) -> str:
    """What we are recommending, including the abstentions.

    Abstentions are drawn on the same axis as the offers rather than relegated to a
    footnote, because "leave them alone" is a decision this system makes far more often
    than it makes any other, and a chart that omitted it would misrepresent the policy.
    """
    labels, values = [], []
    for k, nm in enumerate(names):
        if counts.get(k):
            labels.append(nm.replace("_", " "))
            values.append(counts[k])
    labels.append("no offer")
    values.append(counts.get("abstain", 0))

    with plt.rc_context(_CHART_RC):
        fig, ax = plt.subplots(figsize=(7.2, max(2.0, 0.42 * len(labels) + 0.8)))
        colours = ["#2563eb"] * (len(labels) - 1) + ["#9ca3af"]
        ax.barh(labels, values, color=colours)
        ax.invert_yaxis()
        ax.set_xlabel("customers")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for i, v in enumerate(values):
            ax.text(v, i, f" {v:,}", va="center", fontsize=9)
        ax.margins(x=0.12)
    return _svg(fig)


def _reason_block(r: Reason) -> str:
    parts = []
    if r.economics:
        parts.append(f'<div class="reason"><span class="k">why it pays</span>'
                     f'{escape(r.economics)}</div>')
    for d in r.drivers:
        parts.append(f'<div class="reason"><span class="k">why them</span>'
                     f'{escape(d)}</div>')
    if r.runner_up:
        parts.append(f'<div class="reason"><span class="k">why this offer</span>'
                     f'{escape(r.runner_up)}</div>')
    if r.caveat:
        parts.append(f'<div class="reason caution"><span class="k">caution</span>'
                     f'{escape(r.caveat)}</div>')
    return "".join(parts) or "<em>no further detail</em>"


def render_dashboard(
    reasons: list[Reason],
    offer_names: list[str],
    business_name: str = "Your business",
    out: Path | None = None,
    ids: list | None = None,
    reliability: str = (
        "This engine chose better than a single well-chosen offer on <strong>58% of "
        "tests</strong> (95% confidence: 42%&ndash;72%). That is better than guessing, "
        "and it is <strong>not</strong> statistically distinguishable from a coin flip."
    ),
    limit: int = 100,
) -> Path:
    """Write the dashboard and return the path.

    `reasons` comes from `retainiq.report.reasons.explain`. `ids` is optional and only
    changes what each row is labelled; if omitted, rows are numbered.
    """
    if not reasons:
        raise ValueError(
            "no reasons to render; the optimiser produced no recommendations at all, "
            "which is itself the finding and should be reported rather than drawn."
        )

    acts = sorted([r for r in reasons if r.is_action], key=lambda r: -r.expected_value)
    skips = [r for r in reasons if not r.is_action]
    trimmed = [r for r in skips if "budget" in r.economics]
    unprofitable = [r for r in skips if "budget" not in r.economics]

    counts: Counter = Counter()
    name_to_k = {nm: k for k, nm in enumerate(offer_names)}
    for r in acts:
        counts[name_to_k.get(r.action, -1)] += 1
    counts["abstain"] = len(skips)

    total = sum(r.expected_value for r in acts)
    thin = [r for r in acts if r.confidence < 0.6]

    rows = []
    for n, r in enumerate(acts[:limit]):
        who = escape(str(ids[r.index])) if ids is not None else f"#{r.index}"
        k = name_to_k.get(r.action, -1)
        # A recommendation below 60% is closer to a coin flip than to advice, and
        # sorting by money puts exactly those rows near the top when the upside is
        # large. Marking it only inside the collapsed detail would put the uncertainty
        # one click further away than the number it qualifies -- the arrangement this
        # project criticises other dashboards for.
        weak = r.confidence < 0.6
        conf = (f'<td class="num caution">{r.confidence:.0%} &#9888;</td>' if weak
                else f'<td class="num">{r.confidence:.0%}</td>')
        rows.append(
            f'<tr class="row" data-i="{n}" data-rung="{k}">'
            f"<td>{who}</td>"
            f'<td><span class="badge">{escape(r.action.replace("_", " "))}</span></td>'
            f'<td class="num">{_money(r.expected_value)}</td>'
            f"{conf}"
            f'<td class="num">&#9662;</td></tr>'
            f'<tr class="detail hidden" id="d{n}"><td colspan="5">'
            f"{_reason_block(r)}</td></tr>"
        )

    options = "".join(
        f'<option value="{k}">{escape(nm.replace("_", " "))}</option>'
        for k, nm in enumerate(offer_names) if counts.get(k)
    )
    more = (f"<p class='sub'>Showing the {limit} largest of {len(acts):,} "
            f"recommendations.</p>" if len(acts) > limit else "")

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Retention recommendations &mdash; {escape(business_name)}</title>
<style>{CSS}{EXTRA_CSS}</style></head>
<body>
  {THEME_TOGGLE}

  <h1>Retention recommendations</h1>
  <p class="sub">{escape(business_name)} &middot; {date.today():%d %B %Y} &middot;
     {len(reasons):,} customers assessed</p>

  <div class="banner">
    <h2>Read this before you act on anything below</h2>
    <p>{reliability}</p>
    <p>Every recommendation on this page is a suggestion with a number attached, not a
       finding. The most useful thing here is probably not the individual names &mdash;
       it is <strong>which offer</strong> to make, and to <strong>how few people</strong>.</p>
  </div>

  <div class="headline">
    <div class="num">{len(acts):,}</div>
    <div class="lbl">customers to contact, out of {len(reasons):,}.
      We recommend leaving <strong>{len(skips):,}</strong> alone.</div>
  </div>

  <h2>What we recommend</h2>
  {_rung_chart(counts, offer_names)}
  <p>If these were all acted on and each performed as estimated, the total gain would be
     about <strong>{_money(total)}</strong>. Treat that as the middle of a wide range,
     not a forecast: {len(thin):,} of the {len(acts):,} recommendations have less than a
     60% chance of making money on their own.</p>

  <h2>Who to contact</h2>
  <p class="sub">Click any row for the reasoning behind it.</p>
  <p><label for="filter">Show: </label>
     <select id="filter"><option value="all">all offers</option>{options}</select></p>
  {more}
  <div class="overflow">
  <table class="actions">
    <thead><tr><th>customer</th><th>offer</th><th>expected gain</th>
      <th>chance it pays</th><th></th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  </div>

  <h2>Why we are leaving {len(skips):,} customers alone</h2>
  <p><strong>{len(unprofitable):,}</strong> because no offer we can measure pays for
     itself on them &mdash; the expected gain does not cover the cost of the offer. This
     is a verdict about those customers, and more budget would not change it.</p>
  <p><strong>{len(trimmed):,}</strong> because the budget ran out. These were worth
     treating, just not first. This is a verdict about the budget, and raising it would
     change the answer.</p>

  <h2>What this cannot tell you</h2>
  <ul>
    <li>Whether a customer will leave. This page is about whether <em>contacting</em>
        them pays, which is a different and harder question.</li>
    <li>Anything about offers you have never tried. Effects are estimated per offer from
        your own randomised pilot; an offer with no pilot data is never recommended.</li>
    <li>Whether the estimated gains are right. They are posterior means over small
        samples, and the confidence column is the honest width of that.</li>
  </ul>
  <p class="sub">Generated by RetainIQ. The randomised holdout that produced these estimates
     must stay in place &mdash; it is the only thing that can tell you afterwards
     whether any of this worked.</p>

  {TABLE_JS}
</body></html>"""

    out = Path(out) if out else Path("retention_dashboard.html")
    out.write_text(html, encoding="utf-8")
    return out
