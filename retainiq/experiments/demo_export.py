"""Write a Stripe-shaped billing export for demonstrations.

`make demo-data`. The demo video walks the delivery path a real engagement follows --
preflight, then the Churn Autopsy -- and that path starts from a billing export, not from
the simulator. This writes one: two CSVs with Stripe's own column names, timestamps
carrying the "(UTC)" suffix, and amounts in **cents**, exactly as Stripe exports them.

The cents are the point. Run preflight on these files unmodified and it blocks, because a
report computed from them would state every revenue figure 100x too high (D-062). That is
the first thing the demo shows, deliberately: the most valuable behaviour of the delivery
path is refusing to produce a confident wrong number.

**The rows are random, not drawn from SubSim's churn model.** They exercise ingestion,
preflight and the report. They say nothing about retention behaviour, and a demo must not
present the report's figures as if they did.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

#: Fixed so the video can be re-recorded and show the same numbers.
SEED = 0
N_CUSTOMERS = 400
CHURN_SHARE = 0.35
SIGNUP_WINDOW_DAYS = 700


def demo_frames(
    n: int = N_CUSTOMERS, seed: int = SEED
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Customers and subscriptions, shaped like a Stripe dashboard export."""
    rng = np.random.default_rng(seed)
    created = pd.to_datetime("2023-06-01") + pd.to_timedelta(
        rng.integers(0, SIGNUP_WINDOW_DAYS, n), "D"
    )
    customers = pd.DataFrame({
        "id": [f"cus_{i:05d}" for i in range(n)],
        "Email": [f"u{i}@example.com" for i in range(n)],
        "Created (UTC)": created,
    })
    churned = rng.random(n) < CHURN_SHARE
    subscriptions = pd.DataFrame({
        "id": [f"sub_{i:05d}" for i in range(n)],
        "Customer ID": customers["id"],
        "Status": np.where(churned, "canceled", "active"),
        "Created (UTC)": created,
        "Canceled At (UTC)": [
            (c + pd.Timedelta(days=int(rng.integers(30, 500)))) if k else ""
            for c, k in zip(created, churned, strict=True)
        ],
        # Minor units, as Stripe exports them: 2900 means 29.00.
        "Plan Amount": rng.integers(900, 29_900, n),
        "Plan Currency": "usd",
    })
    return customers, subscriptions


def write_demo_export(outdir: Path | str = "demo") -> tuple[Path, Path]:
    """Write `customers.csv` and `subscriptions.csv`; return their paths."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    customers, subscriptions = demo_frames()
    c, s = out / "customers.csv", out / "subscriptions.csv"
    customers.to_csv(c, index=False)
    subscriptions.to_csv(s, index=False)
    return c, s


if __name__ == "__main__":
    c, s = write_demo_export()
    print(f"wrote {c}\nwrote {s}")
    print("\nNext, and expect it to BLOCK (amounts are in cents):")
    print(f"  python -m retainiq.cli preflight --customers {c} --subscriptions {s}")
