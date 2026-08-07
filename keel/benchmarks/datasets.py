"""Public randomised-experiment datasets.

Everything proven so far lives inside our own simulator. That is not evidence a
referee will accept, and it should not be evidence we accept either: the headline
result could be an artifact of a correlation we built in ourselves.

These datasets are real randomised controlled trials. Because treatment was assigned
at random, the untreated group is a valid counterfactual for the treated group *in
aggregate*, which is enough to evaluate a targeting **policy** even though it is not
enough to score an individual treatment-effect estimate. That distinction is what
makes this the right external check for our central claim.

Hillstrom (MineThatData, 2008)
------------------------------
64,000 customers who last purchased within twelve months, randomly assigned to one of
three arms: a men's-merchandise email, a women's-merchandise email, or no email.
Outcomes recorded over the following two weeks.

The `mens` and `womens` columns are *purchase-history flags*, not customer gender, and
`segment` is which campaign arm they landed in. Confusing the two is an easy mistake
that quietly turns a clean RCT into a muddle.
"""

from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

HILLSTROM_URL = (
    "http://www.minethatdata.com/"
    "Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv"
)
HILLSTROM_ROWS = 64_000


@dataclass
class RCT:
    """A randomised controlled trial, in the shape every downstream tool expects."""

    name: str
    X: pd.DataFrame
    """Pre-treatment covariates only. Anything measured after assignment is excluded."""
    treatment: np.ndarray
    """1 if treated, 0 if control."""
    outcome: np.ndarray
    """The outcome being optimised."""
    outcome_name: str
    spend: np.ndarray | None = None
    """Continuous revenue outcome where the dataset provides one."""

    def __len__(self) -> int:
        return len(self.treatment)

    def summary(self) -> str:
        t, c = self.treatment == 1, self.treatment == 0
        yt, yc = self.outcome[t].mean(), self.outcome[c].mean()
        return (
            f"{self.name}: n={len(self):,}  treated={t.sum():,} ({t.mean():.1%})\n"
            f"  outcome '{self.outcome_name}': treated {yt:.4f} vs control {yc:.4f}  "
            f"(ATE {yt - yc:+.4f}, lift {yt / yc - 1:+.1%})"
        )

    def subsample(self, n: int, seed: int = 0) -> RCT:
        """A stratified random subsample, preserving the treated/control balance.

        The point of this project is behaviour at small n, and every public uplift
        dataset is far larger than the businesses we care about. Subsampling is how
        we get a realistic regime out of them.
        """
        rng = np.random.default_rng(seed)
        idx = []
        for arm in (0, 1):
            pool = np.flatnonzero(self.treatment == arm)
            take = int(round(n * len(pool) / len(self)))
            idx.append(rng.choice(pool, size=min(take, len(pool)), replace=False))
        keep = np.sort(np.concatenate(idx))
        return RCT(
            name=f"{self.name}[n={len(keep)}]",
            X=self.X.iloc[keep].reset_index(drop=True),
            treatment=self.treatment[keep],
            outcome=self.outcome[keep],
            outcome_name=self.outcome_name,
            spend=None if self.spend is None else self.spend[keep],
        )


def _download(url: str, dest: Path, expect_rows: int | None = None) -> Path:
    """Fetch and cache a dataset, verifying it arrived whole.

    Partial downloads are the failure mode here: a truncated CSV parses fine and
    silently changes every result. Row count is checked rather than trusted.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if expect_rows is None or sum(1 for _ in dest.open()) - 1 == expect_rows:
            return dest
        dest.unlink()  # truncated from an earlier attempt

    tmp = dest.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)  # noqa: S310 - fixed, documented URL
    rows = sum(1 for _ in tmp.open()) - 1
    if expect_rows is not None and rows != expect_rows:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name}: expected {expect_rows} rows, got {rows}")
    tmp.rename(dest)
    return dest


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_hillstrom(
    treatment_arm: str = "womens",
    outcome: str = "visit",
    path: Path | None = None,
) -> RCT:
    """Load the Hillstrom email experiment.

    Parameters
    ----------
    treatment_arm:
        ``womens`` (default) or ``mens`` compares that campaign against no email --
        a clean single-treatment RCT. ``any`` pools both campaigns, which yields
        more data but mixes two genuinely different treatments; heterogeneity then
        partly reflects the experimental design rather than the customers, and any
        "negative uplift" it produces may be an artifact of sending the wrong
        catalogue rather than a real do-not-disturb effect. Default is the clean
        comparison for that reason.
    outcome:
        ``visit`` (~15% base rate), ``conversion`` (~0.9%, very sparse), or
        ``spend``.
    """
    path = path or _download(HILLSTROM_URL, DATA_DIR / "hillstrom.csv", HILLSTROM_ROWS)
    raw = pd.read_csv(path)

    arms = {
        "womens": "Womens E-Mail",
        "mens": "Mens E-Mail",
    }
    if treatment_arm == "any":
        keep = raw
        treat = (raw["segment"] != "No E-Mail").to_numpy().astype(int)
    elif treatment_arm in arms:
        keep = raw[raw["segment"].isin([arms[treatment_arm], "No E-Mail"])].reset_index(drop=True)
        treat = (keep["segment"] == arms[treatment_arm]).to_numpy().astype(int)
    else:
        raise ValueError(f"unknown treatment_arm {treatment_arm!r}")

    if outcome not in ("visit", "conversion", "spend"):
        raise ValueError(f"unknown outcome {outcome!r}")

    # Pre-treatment covariates only. `visit`, `conversion` and `spend` are all
    # measured after assignment and must never enter X.
    X = pd.DataFrame({
        "recency": keep["recency"].astype(float),
        "history": keep["history"].astype(float),
        "log_history": np.log1p(keep["history"].astype(float)),
        "mens_history": keep["mens"].astype(float),
        "womens_history": keep["womens"].astype(float),
        "newbie": keep["newbie"].astype(float),
        "zip_surburban": (keep["zip_code"] == "Surburban").astype(float),
        "zip_urban": (keep["zip_code"] == "Urban").astype(float),
        "channel_web": (keep["channel"] == "Web").astype(float),
        "channel_phone": (keep["channel"] == "Phone").astype(float),
        "channel_multi": (keep["channel"] == "Multichannel").astype(float),
    })

    return RCT(
        name=f"hillstrom[{treatment_arm}/{outcome}]",
        X=X,
        treatment=treat,
        outcome=keep[outcome].to_numpy().astype(float),
        outcome_name=outcome,
        spend=keep["spend"].to_numpy().astype(float),
    )
