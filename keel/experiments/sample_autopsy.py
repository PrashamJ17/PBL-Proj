"""Build the sample Churn Autopsy used in outreach.

`make sample`. A prospect deciding whether to send you their billing data reasonably
wants to see what comes back first. This produces that artefact: a complete report on a
**simulated** business, structurally identical to what they would receive.

Two rules govern it, and both exist for the same reason.

**It must never be mistakable for a real business.** `render(demo=True)` puts a banner
above everything else on the page saying the figures are simulated. That is a parameter
rather than a convention so a sample cannot be produced without it. A prospect who thinks
they are looking at another client's real numbers has learned that we circulate client
data, which is exactly the fear the engagement exists to overcome.

**It must not be flattered.** The temptation with a sales artefact is to pick the seed
that produces the most alarming churn number. The simulator is used at its calibrated
defaults, and the seed is fixed at the top of this file rather than searched. If the
sample looks unimpressive, that is information about the pitch, not a reason to re-roll.
"""

from __future__ import annotations

from pathlib import Path

from keel.ingest.subsim_adapter import to_canonical
from keel.report.autopsy import analyse
from keel.report.render import render
from keel.report.worklist import write_worklists
from keel.sim import SimConfig, simulate

#: Fixed, not searched. Changing it to find a more alarming number would make the sample
#: a selected result, which is the thing this project spends its time refusing to do.
SEED = 11

#: Deliberately mid-range for the target market (200-2,000 customers), so the sample
#: resembles the reader's own business rather than an enterprise.
N_CUSTOMERS = 900
N_MONTHS = 24

BUSINESS_NAME = "Northwind Software (simulated)"

#: The simulator prices in abstract units (median ~55/month), and the report formats
#: money as rupees. Rendered unscaled, the sample described 900 customers paying about
#: Rs 15 each and losing Rs 5,752 a year to churn -- figures a founder dismisses on
#: sight, and rightly.
#:
#: Scaling is safe and is not a thumb on the scale. The hazard depends on
#: `price_pressure`, which is each customer's price *relative to the median*, so
#: multiplying every amount by a constant leaves churn rates, the involuntary share and
#: the decline mix exactly unchanged; only the currency figures move. What it fixes is a
#: units mismatch between the simulator and the renderer -- the same class of error as
#: D-057 and D-062, caught the same way, by looking at the output.
TARGET_MEDIAN_MRR = 2_400.0
"""Median monthly price of the simulated business, in rupees. Chosen as typical for
Indian SMB B2B SaaS so the sample resembles the reader's own business."""


def _rescale_money(data, target_median: float):
    """Put the simulated business on a realistic price point.

    Applied to the canonical tables rather than the simulator config, because changing
    `SimConfig` would move the calibration the whole project is pinned to.
    """
    median = float(data.subscriptions["mrr"].median())
    if median <= 0:
        return data
    k = target_median / median
    data.subscriptions["mrr"] = data.subscriptions["mrr"] * k
    if not data.invoices.empty:
        data.invoices["amount"] = data.invoices["amount"] * k
    return data


#: Honest caveats about *this* data, added so the sample also demonstrates the section
#: a real report uses to say what it could not compute. Simulated data is complete, so
#: without these the "what we could not determine" block would be absent from the sample
#: -- and that block is one of the reasons to trust the report at all. Inventing a
#: limitation would be worse than omitting one; these two are real.
SAMPLE_NOTES = [
    "Every simulated customer signed up in the same month, so the retention curve here "
    "is a single cohort. A real export has staggered signups and the report splits them.",
    "Every figure here is computed from billing data alone -- subscriptions and "
    "invoices. Product usage and support history are not used, even where an export "
    "contains them, so nothing on this page depends on them.",
]


def build(out: Path | None = None, n_customers: int = N_CUSTOMERS, seed: int = SEED) -> Path:
    sim = simulate(SimConfig(n_customers=n_customers, n_months=N_MONTHS, seed=seed))
    data = _rescale_money(to_canonical(sim, seed=seed), TARGET_MEDIAN_MRR)
    autopsy = analyse(data)
    autopsy.notes.extend(SAMPLE_NOTES)
    path = render(
        autopsy,
        business_name=BUSINESS_NAME,
        out=out or Path("sample_churn_autopsy.html"),
        demo=True,
    )
    # The worklists ship with the sample so a prospect sees both halves: the argument,
    # and the rows they would actually work through on Monday.
    write_worklists(data, outdir=path.parent, prefix="sample_")
    return path


if __name__ == "__main__":
    p = build()
    print(f"wrote {p.resolve()}")
    for extra in sorted(p.parent.glob("sample_*.csv")):
        print(f"wrote {extra.resolve()}")
