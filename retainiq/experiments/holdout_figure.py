"""Figure 6: the measurement floor.

The single most consequential number Phase 6 produced, drawn so a founder can find their
own customer count on the x-axis and read off whether measuring their retention campaign
is possible at all.

Left panel is the estimator working: measured lift against the simulator's known truth,
with the interval. Right panel is the minimum detectable effect against the effect the
calibrated offer actually delivers -- the two lines do not cross anywhere in the range a
small business occupies, which is the finding.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from retainiq.experiments.holdout_validation import (
    SIZES,
    power_table,
    summarise,
    validate,
)
from retainiq.policy.holdout import required_holdout_size

FIG_DIR = Path(__file__).resolve().parents[2] / "papers" / "figures"


def figure_6(seeds: int = 60, out: Path | None = None) -> Path:
    frame = validate(seeds=seeds)
    summary = summarise(frame)
    delivered = float(frame["true_lift"].mean())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.2, 4.9))

    # --- left: the estimator recovers the truth, with honest intervals ---------
    n = summary["n_customers"].to_numpy(dtype=float)
    ax1.axhline(delivered, color="#2E7D32", lw=2, ls="--",
                label=f"true effect ({delivered:.4f})", zorder=2)
    ax1.errorbar(
        n, summary["measured_lift"], yerr=summary["ci_width"] / 2,
        fmt="o-", color="#1565C0", capsize=4, lw=1.8, ms=6,
        label="measured lift, 95% CI", zorder=3,
    )
    ax1.axhline(0, color="#888", lw=0.8, zorder=1)
    ax1.set_xscale("log")
    ax1.set_xlabel("Customers in the business")
    ax1.set_ylabel("Retention lift")
    ax1.set_title("The estimator is unbiased —\nbut its interval swamps the effect",
                  fontsize=11.5)
    ax1.legend(fontsize=9, loc="upper right", framealpha=0.95)
    ax1.set_xticks(SIZES)
    ax1.set_xticklabels([f"{s:,}" for s in SIZES], fontsize=9)
    for s in ("top", "right"):
        ax1.spines[s].set_visible(False)
    ax1.grid(alpha=0.25, lw=0.6)

    # --- right: the measurement floor -----------------------------------------
    power = power_table()
    pn = power["n_customers"].to_numpy(dtype=float)
    ax2.plot(pn, power["mde"], "o-", color="#C62828", lw=2, ms=6,
             label="minimum detectable effect", zorder=3)
    ax2.axhline(delivered, color="#2E7D32", lw=2, ls="--",
                label=f"effect actually delivered ({delivered:.4f})", zorder=2)
    ax2.fill_between(pn, delivered, power["mde"], color="#C62828", alpha=0.08, zorder=1)
    ax2.set_xscale("log")
    ax2.set_yscale("log")
    ax2.set_xlabel("Customers in the business")
    ax2.set_ylabel("Retention lift (log scale)")
    ax2.set_title("The measurement floor —\nthe shaded gap is what cannot be detected",
                  fontsize=11.5)
    ax2.legend(fontsize=9, loc="upper right", framealpha=0.95)
    ax2.set_xticks(SIZES)
    ax2.set_xticklabels([f"{s:,}" for s in SIZES], fontsize=9)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    ax2.grid(alpha=0.25, lw=0.6, which="both")

    need = required_holdout_size(delivered)
    ax2.annotate(
        f"detecting this effect needs\n≈{need:,} customers",
        xy=(pn[-1], power["mde"].iloc[-1]), xytext=(0.30, 0.16),
        textcoords="axes fraction", fontsize=9.5, color="#C62828",
        arrowprops=dict(arrowstyle="->", color="#C62828", lw=1.2, alpha=0.8),
    )

    fig.suptitle(
        "A holdout measures the campaign honestly, and at small scale it cannot measure it at all",
        fontsize=13, y=1.015,
    )
    fig.tight_layout()

    out = out or (FIG_DIR / "fig06_measurement_floor.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


if __name__ == "__main__":
    print(figure_6())
