"""Figure 5 -- what the discrete-time hazard actually buys.

Deliberately NOT a bar chart of concordance. The Phase 3 argument is not "our model
scores higher"; on rank it is a tie with the strongest baseline. It is that the model
returns **probabilities you can multiply by money**, and that it can see covariates
move. So the two panels are:

**Left -- calibration on Telco.** Predicted survival against Kaplan-Meier survival, in
bins of predicted risk, at the reference horizon. The diagonal is perfect. Cox and RSF
sit visibly off it; the discrete model and DeepSurv sit on it. This is the panel that
justifies the CLV layer, because CLV is a functional of the absolute level.

**Right -- when seeing covariates move starts to pay.** Share of simulated businesses
on which the time-varying model beats the same model restricted to signup-time
covariates. Win rate over seeds rather than a mean, per D-023: a business gets one
draw. Reported next to the n=250 result, which is the honest one -- below a few
hundred customers, it does not reliably beat anything.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from keel.benchmarks.survival_data import load_telco, split_by_unit
from keel.experiments.survival_benchmark import run_landmark_small_n
from keel.models.survival.baselines import available_baselines
from keel.models.survival.discrete import DiscreteTimeHazard
from keel.models.survival.metrics import calibration_at_horizon

FIG_DIR = Path(__file__).resolve().parents[2] / "papers" / "figures"

COLOURS = {
    "discrete_logistic": "#1565C0",
    "deepsurv": "#6A1B9A",
    "cox_ph": "#C62828",
    "rsf": "#EF6C00",
}
LABELS = {
    "discrete_logistic": "discrete-time hazard (ours)",
    "deepsurv": "DeepSurv",
    "cox_ph": "Cox PH",
    "rsf": "Random Survival Forest",
}


def _telco_calibration(seed: int = 0) -> tuple[dict, float]:
    data = load_telco()
    train, test, _ = split_by_unit(data, 0.3, seed)
    train.name = test.name = data.name
    ref = float(np.median(train.duration))
    event = (test.event > 0).astype(int)

    curves = {}
    ours = DiscreteTimeHazard("logistic", pool_after=24, seed=seed).fit_data(train)
    curves["discrete_logistic"] = calibration_at_horizon(
        test.duration, event, ours.survival_at(test.X, np.array([ref]))[:, 0], ref
    )
    for baseline in available_baselines():
        if baseline.name not in COLOURS:
            continue
        baseline.fit(train)
        curves[baseline.name] = calibration_at_horizon(
            test.duration, event, baseline.survival_at(test.X, np.array([ref]))[:, 0], ref
        )
    return curves, ref


def figure_5(out: Path | None = None, seeds: int = 12) -> Path:
    curves, ref = _telco_calibration()
    sweep = run_landmark_small_n(seeds=seeds)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.2))

    lo = min(min(c["predicted"].min(), c["observed"].min()) for c in curves.values())
    hi = max(max(c["predicted"].max(), c["observed"].max()) for c in curves.values())
    pad = 0.03 * (hi - lo)
    ax1.plot([lo - pad, hi + pad], [lo - pad, hi + pad], color="#9E9E9E", lw=1,
             ls="--", zorder=1, label="perfect calibration")
    for name in ("cox_ph", "rsf", "deepsurv", "discrete_logistic"):
        if name not in curves:
            continue
        c = curves[name]
        ax1.plot(c["predicted"], c["observed"], marker="o", ms=5,
                 color=COLOURS[name], lw=2 if name == "discrete_logistic" else 1.4,
                 alpha=1.0 if name == "discrete_logistic" else 0.75,
                 label=f"{LABELS[name]}  (slope {c['slope']:.2f})", zorder=3)
    ax1.set_xlabel(f"Predicted survival at month {ref:.0f}")
    ax1.set_ylabel("Observed (Kaplan-Meier) survival")
    ax1.set_title(
        "Telco: does the predicted probability mean\nwhat it says?", fontsize=12, pad=10
    )
    ax1.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax1.grid(alpha=0.25)
    ax1.set_axisbelow(True)

    x = np.arange(len(sweep))
    ax2.bar(x - 0.2, sweep["beats_baseline_on_c"] * 100, width=0.4,
            color="#1565C0", label="vs. signup-time covariates only")
    ax2.bar(x + 0.2, sweep["beats_cox_on_c"] * 100, width=0.4,
            color="#90A4AE", label="vs. Cox refitted at each landmark")
    ax2.axhline(50, color="#C62828", lw=1, ls="--")
    ax2.text(len(x) - 0.55, 52, "coin flip", color="#C62828", fontsize=8.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{int(n):,}" for n in sweep["n_customers"]])
    ax2.set_xlabel("Customers in the business")
    ax2.set_ylabel("Share of simulated businesses where\ntime-varying model ranks better (%)")
    ax2.set_ylim(0, 105)
    ax2.set_title(
        "Seeing covariates move beats a signup snapshot --\nbut not below a few hundred"
        " customers",
        fontsize=12, pad=10,
    )
    ax2.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax2.grid(alpha=0.25, axis="y")
    ax2.set_axisbelow(True)

    fig.suptitle(
        "The discrete-time hazard is a tie on ranking and a win on meaning",
        fontsize=13.5, y=1.02,
    )
    fig.tight_layout()

    out = out or (FIG_DIR / "fig05_survival_calibration.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


if __name__ == "__main__":
    print(figure_5())
