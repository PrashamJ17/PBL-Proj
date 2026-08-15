"""Figure 4: more dunning is not better dunning.

The intuitive response to failed payments is to try harder -- retry more often, email
more insistently. On this simulation that is **strictly dominated**: `aggressive` uses
2.5x the retries and 3.9x the emails of a code-aware schedule and recovers *no more*.
It loses on value and does not even win on the vendor's own headline metric.

What does work is knowing *which* failure you are looking at. `insufficient_funds` is a
timing problem and waits for payday; `expired_card` cannot be fixed by retrying at all.
The processor already tells you which is which, and the default schedule ignores it.

Where a metric disagreement does remain, it is between the top two: recovery rate
prefers `code_aware`, net value prefers `code_aware_quiet` -- the same schedule
emailing a third less. That gap is entirely contact fatigue, which is the Phase 0
salience mechanism arriving through the billing path (D-032).

The right panel is a sensitivity sweep rather than a single number, because the
conclusion depends on how much a dunning email actually costs in goodwill — a quantity
we assumed rather than measured. The honest presentation is to show where the ranking
flips instead of asserting the assumption.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from retainiq.experiments.dunning import DunningResult, run
from retainiq.policy.dunning import AGGRESSIVE, QUIET_CODE_AWARE
from retainiq.sim.dunning import DunningConfig

FIG_DIR = Path(__file__).resolve().parents[2] / "papers" / "figures"

ORDER = [
    "processor_default", "fixed_smart", "code_aware", "code_aware_quiet", "aggressive",
]
LABELS = {
    "processor_default": "Processor\ndefault",
    "fixed_smart": "Fixed\nsmart",
    "code_aware": "Code-\naware",
    "code_aware_quiet": "Code-aware\n+ quiet",
    "aggressive": "Aggressive",
}


def fatigue_sweep(
    fatigue_values: np.ndarray, n_failures: int = 20_000, seed: int = 0
) -> dict[str, np.ndarray]:
    """Net value of the two contenders as the cost of a dunning email varies."""
    quiet, aggressive = [], []
    for f in fatigue_values:
        cfg = replace(DunningConfig(), contact_fatigue_per_email=float(f))
        res = run(
            n_failures=n_failures, cfg=cfg,
            policies=[QUIET_CODE_AWARE, AGGRESSIVE], seed=seed,
        )
        by = {r.name: r.net_value for r in res}
        quiet.append(by["code_aware_quiet"])
        aggressive.append(by["aggressive"])
    return {"quiet": np.array(quiet), "aggressive": np.array(aggressive)}


def figure_4(
    results: list[DunningResult] | None = None,
    n_failures: int = 40_000,
    out: Path | None = None,
) -> Path:
    results = results or run(n_failures=n_failures)
    by = {r.name: r for r in results if r.name in ORDER}
    names = [n for n in ORDER if n in by]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.6))
    x = np.arange(len(names))

    # --- left: the two metrics disagree --------------------------------------
    recovery = np.array([by[n].recovery_rate * 100 for n in names])
    net = np.array([by[n].net_value / 1e6 for n in names])

    best_recovery = int(np.argmax(recovery))
    best_net = int(np.argmax(net))

    ax1.bar(x - 0.2, recovery, width=0.38, color="#90A4AE", label="Recovery rate (%)")
    ax1b = ax1.twinx()
    ax1b.bar(x + 0.2, net, width=0.38, color="#2E7D32", label="Net value (millions)")

    ax1.set_xticks(x)
    ax1.set_xticklabels([LABELS[n] for n in names], fontsize=9)
    ax1.set_ylabel("Recovery rate (%)", color="#546E7A")
    ax1b.set_ylabel("Net value (millions)", color="#2E7D32")
    ax1.set_ylim(0, max(recovery) * 1.35)
    ax1b.set_ylim(0, max(net) * 1.35)

    ax1.annotate(
        "best\nrecovery", xy=(best_recovery - 0.2, recovery[best_recovery]),
        xytext=(0, 10), textcoords="offset points", ha="center", va="bottom",
        fontsize=9, color="#546E7A", weight="bold",
    )
    ax1b.annotate(
        "best\nVALUE", xy=(best_net + 0.2, net[best_net]),
        xytext=(0, 10), textcoords="offset points", ha="center", va="bottom",
        fontsize=9, color="#2E7D32", weight="bold",
    )
    # Make the disagreement explicit rather than leaving it to be spotted.
    ax1.annotate(
        "2.5x the contact,\nno more recovered",
        xy=(len(names) - 1 + 0.2, net[-1] / max(net) * max(recovery) * 1.0),
        xytext=(-4, -46), textcoords="offset points", ha="center",
        fontsize=8.5, color="#C62828", style="italic",
    )
    ax1.set_title(
        "Trying harder is strictly dominated:\n2.5x the retries, no more recovered",
        fontsize=12, pad=10,
    )
    ax1.grid(alpha=0.2, axis="y", lw=0.6)
    ax1.set_axisbelow(True)

    # --- right: where the conclusion holds ------------------------------------
    fatigue = np.linspace(0.0, 0.14, 15)
    sweep = fatigue_sweep(fatigue)

    ax2.plot(fatigue, sweep["quiet"] / 1e6, color="#2E7D32", lw=2.4,
             marker="o", ms=4, label="Code-aware + quiet")
    ax2.plot(fatigue, sweep["aggressive"] / 1e6, color="#C62828", lw=2.4,
             marker="o", ms=4, label="Aggressive")

    diff = sweep["aggressive"] - sweep["quiet"]
    crossings = np.where(np.diff(np.sign(diff)))[0]
    if len(crossings):
        i = crossings[0]
        # Linear interpolation to the crossing point.
        f0, f1 = fatigue[i], fatigue[i + 1]
        d0, d1 = diff[i], diff[i + 1]
        cross = f0 + (f1 - f0) * (0 - d0) / (d1 - d0) if d1 != d0 else f0
        ax2.axvline(cross, color="#37474F", ls=":", lw=1.4)
        ax2.annotate(
            f"ranking flips at {cross:.3f}",
            xy=(cross, ax2.get_ylim()[0]), xytext=(-6, 18), textcoords="offset points",
            fontsize=9, color="#37474F", ha="right",
        )

    ax2.axvline(0.055, color="#F9A825", lw=1.6)
    ax2.annotate(
        "our assumption\n(0.055)", xy=(0.055, ax2.get_ylim()[1]),
        xytext=(6, -34), textcoords="offset points", fontsize=9, color="#8D6E00",
    )
    ax2.set_xlabel("Cost of one dunning email\n(added to monthly churn hazard, logit scale)")
    ax2.set_ylabel("Net value (millions)")
    ax2.set_title(
        "Where that conclusion holds\n(the fatigue cost is assumed, not measured)",
        fontsize=12, pad=10,
    )
    ax2.legend(frameon=False, fontsize=9.5, loc="upper right")
    ax2.grid(alpha=0.25, lw=0.6)
    ax2.set_axisbelow(True)

    fig.suptitle(
        "Dunning: knowing WHICH payment failed beats trying harder",
        fontsize=13.5, y=1.02,
    )
    fig.tight_layout()

    out = out or (FIG_DIR / "fig04_dunning_value.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


if __name__ == "__main__":
    print(figure_4())
