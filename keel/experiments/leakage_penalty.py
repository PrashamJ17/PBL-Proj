"""How much does leakage inflate results?

Phase 1's gate is a working leakage suite. But "we have safeguards" is an assertion.
This experiment measures what they buy, by building the *same* features three ways and
comparing what a model appears to achieve.

Three feature vintages
----------------------
``correct``
    Filter on ``available_at``. What you could genuinely have known.

``occurred_only``
    Filter on ``occurred_at``, ignoring settlement and upload lag. Looks right, and
    is wrong by exactly the availability delay. The subtle bug.

``no_filter``
    No temporal filter -- aggregate the whole dataset regardless of time. The
    catastrophic bug, and an easy one to commit: an analyst writes
    ``df.groupby('customer_id').size()`` and ships it.

The third is worth dwelling on. "Total sessions ever" looks like an innocent activity
feature. But a customer who churned in month 4 has no sessions in months 5-24, so the
feature encodes the outcome almost perfectly. The model appears excellent and has
learned nothing but who stopped generating rows.

The gap between vintages is not an improvement. **It is fiction**, and it is the
number a business would have staked a retention budget on.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from keel.core.features import FEATURE_NAMES, FeatureStore, build_standard
from keel.core.leakage import model_auc
from keel.ingest.subsim_adapter import at_risk_at, month_timestamps, to_canonical
from keel.sim import SimConfig, simulate


@dataclass
class Vintage:
    name: str
    mode: str
    auc: float
    description: str


def _outcome(sim, months: list[int], horizon: int = 3) -> dict:
    """Did each customer churn voluntarily within `horizon` months of each as-of?

    Defined from the simulator's own record rather than from the canonical tables,
    so the label cannot itself be contaminated by the feature pipeline under test.
    """
    cust = sim.customers.set_index("customer_id")
    churn_month = cust["churn_month"]
    kind = cust["churn_kind"]

    labels = {}
    for m in months:
        ids = at_risk_at(sim, m).astype(int)
        cm = churn_month.loc[ids].to_numpy()
        kd = kind.loc[ids].to_numpy()
        labels[m] = ((cm > m) & (cm <= m + horizon) & (kd == "voluntary")).astype(int)
    return labels


def run(
    cfg: SimConfig | None = None,
    months: tuple[int, ...] = (4, 5, 6, 7, 8, 9),
    horizon: int = 3,
    seed: int = 0,
) -> tuple[list[Vintage], pd.DataFrame]:
    """Build features three ways and compare apparent model performance."""
    cfg = cfg or SimConfig(n_customers=2500, n_months=24, seed=7)
    sim = simulate(cfg)
    ds = to_canonical(sim, seed=seed)

    month_list = list(months)
    ts = month_timestamps(month_list)
    customers_at = {t: at_risk_at(sim, m) for t, m in zip(ts, month_list)}

    labels = _outcome(sim, month_list, horizon=horizon)
    y = np.concatenate([labels[m] for m in month_list])

    specs = [
        ("correct", FeatureStore.SAFE,
         "Filters on available_at. What you could genuinely have known."),
        ("occurred_only", FeatureStore.UNSAFE_OCCURRED_ONLY,
         "Ignores settlement and upload lag. Subtly wrong."),
        ("no_filter", FeatureStore.UNSAFE_NO_FILTER,
         "No temporal filter at all. Catastrophically wrong."),
    ]

    vintages, frames = [], {}
    for name, mode, desc in specs:
        store = FeatureStore(ds, mode=mode, strict=(mode == FeatureStore.SAFE))
        X = build_standard(store, ts, customers_at)
        frames[name] = X
        vintages.append(
            Vintage(name, mode, model_auc(X, y, FEATURE_NAMES, seed=seed), desc)
        )

    comparison = pd.DataFrame(
        {
            "vintage": [v.name for v in vintages],
            "apparent_auc": [v.auc for v in vintages],
            "inflation_vs_correct": [v.auc - vintages[0].auc for v in vintages],
        }
    )
    return vintages, comparison


def report(vintages: list[Vintage], comparison: pd.DataFrame) -> str:
    lines = [
        "Leakage penalty",
        "=" * 72,
        f"{'vintage':<16}{'apparent AUC':>14}{'inflation':>12}   description",
        "-" * 72,
    ]
    for v, (_, row) in zip(vintages, comparison.iterrows()):
        lines.append(
            f"{v.name:<16}{v.auc:>14.4f}{row['inflation_vs_correct']:>+12.4f}   {v.description}"
        )
    lines.append("-" * 72)
    worst = comparison["inflation_vs_correct"].max()
    lines.append(
        f"Worst-case inflation: {worst:+.4f} AUC.\n"
        "That gap is not performance. It is the amount by which a backtest would\n"
        "have overstated the model before it reached production."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    v, c = run()
    print(report(v, c))
