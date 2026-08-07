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

# HuggingFace first: measured ~1.3 MB/s against ~16 KB/s from the Criteo blob
# mirror, i.e. minutes rather than hours for the same 297MB.
CRITEO_URL = (
    "https://huggingface.co/datasets/criteo/criteo-uplift/resolve/main/"
    "criteo-research-uplift-v2.1.csv.gz"
)
CRITEO_MIRROR = (
    "https://criteostorage.blob.core.windows.net/criteo-research-datasets/"
    "criteo-uplift-v2.1.csv.gz"
)
CRITEO_BYTES = 311_422_618

#: Published statistics for the full file, used to check that any subset we read is
#: representative rather than a biased slice.
CRITEO_REFERENCE = {"treatment_rate": 0.85, "visit_rate": 0.047, "conversion_rate": 0.0029}


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


def read_gzip_prefix(path: Path, max_rows: int) -> tuple[pd.DataFrame, bool]:
    """Read up to `max_rows` from a gzipped CSV that may still be downloading.

    gzip is a stream format, so a partially downloaded file decompresses cleanly up
    to the point it was truncated. That makes a 300MB dataset usable long before the
    download finishes -- which matters here, since the full file takes hours on a
    slow link and the experiments only need a few million rows anyway.

    Returns the frame and whether truncation was hit.
    """
    import gzip
    import io

    lines: list[str] = []
    truncated = False

    # Decompress line by line rather than handing the file to pandas. pandas reads
    # in large blocks, so on a truncated file it raises partway through its first
    # block and returns nothing at all -- even when megabytes of valid rows are
    # sitting there. Controlling the decompression ourselves keeps everything up to
    # the truncation point.
    try:
        with gzip.open(path, "rt") as fh:
            for i, line in enumerate(fh):
                if i > max_rows:  # +1 for the header
                    break
                lines.append(line)
    except (EOFError, OSError):
        truncated = True

    if len(lines) < 2:
        raise RuntimeError(
            f"{path.name}: only {len(lines)} lines readable so far. "
            "If a download is still in progress, wait for more data."
        )

    if truncated and not lines[-1].endswith("\n"):
        lines.pop()  # a partial final row

    frame = pd.read_csv(io.StringIO("".join(lines)))
    return frame, truncated


def check_representative(
    frame: pd.DataFrame, reference: dict[str, float], tol: float = 0.20
) -> dict[str, tuple[float, float, bool]]:
    """Compare a subset's headline rates against the full dataset's published ones.

    Reading a *prefix* of a file is only a valid sample if the file is not ordered
    in a way that correlates with treatment or outcome. This cannot be proven from
    the prefix alone, but a prefix whose rates match the published full-file rates
    is strong evidence against a damaging ordering -- and a mismatch is a hard stop.
    """
    observed = {
        "treatment_rate": float(frame["treatment"].mean()),
        "visit_rate": float(frame["visit"].mean()),
        "conversion_rate": float(frame["conversion"].mean()),
    }
    out = {}
    for key, expected in reference.items():
        got = observed[key]
        ok = abs(got - expected) <= tol * expected
        # A degenerate rate is a categorical failure, not a tolerance question.
        # Relative tolerance alone is too permissive here: |1.0 - 0.85| = 0.15 sits
        # inside a 20% band around 0.85, so an all-treated sample -- on which uplift
        # is undefined -- would otherwise pass.
        if key == "treatment_rate" and got in (0.0, 1.0):
            ok = False
        out[key] = (got, expected, ok)
    return out


def load_criteo(
    outcome: str = "visit",
    sample_rows: int | None = 4_000_000,
    path: Path | None = None,
    seed: int = 0,
) -> RCT:
    """Load the Criteo uplift dataset (v2.1) -- a large advertising incrementality
    experiment. Users randomly assigned to see an ad or not; visits and conversions
    recorded.

    **The file is sorted by treatment, and this is a trap.** The first ~250,000 rows
    are 100% treated, with no control group at all. A prefix read -- the obvious way
    to sample a 297MB file, and the way a partial download gives you data -- produces
    a set on which uplift is *undefined* rather than merely noisy. So the whole file
    is always read, and `sample_rows` subsamples **randomly afterwards**. Verified in
    `check_representative`, which refuses a single-arm sample outright.

    Three further differences from Hillstrom, each consequential:

    **Treatment is 85/15, not balanced.** The control arm is small, so uplift
    intervals are much wider for the same total n, and `ClassTransform` would be
    biased without its propensity correction.

    **Outcomes are rare** -- 4.7% visits, 0.29% conversions. At n=500, a conversion
    analysis expects roughly *one* event. `visit` is the only outcome usable for
    small-sample work.

    **There is an `exposure` column, and it is a second trap.** `treatment` is the
    randomised assignment; `exposure` records whether the ad was actually served,
    which happens *after* randomisation and correlates with user behaviour. Using it
    as the treatment indicator, or as a feature, silently converts a clean RCT into
    observational data. It is excluded from covariates, and `treatment` is always
    the assignment.
    """
    path = path or (DATA_DIR / "criteo-uplift-v2.1.csv.gz")
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download it first (297MB, ~4 min):\n"
            f"  curl -L -o {path} {CRITEO_URL}"
        )
    if outcome not in ("visit", "conversion"):
        raise ValueError(f"unknown outcome {outcome!r}; use 'visit' or 'conversion'")

    usecols = [f"f{i}" for i in range(12)] + ["treatment", "visit", "conversion"]
    dtypes = {c: "float32" for c in usecols[:12]}
    dtypes.update({"treatment": "int8", "visit": "int8", "conversion": "int8"})

    raw = pd.read_csv(path, compression="gzip", usecols=usecols, dtype=dtypes)

    checks = check_representative(raw, CRITEO_REFERENCE)
    bad = [k for k, (_, _, ok) in checks.items() if not ok]
    if bad:
        detail = ", ".join(f"{k}={checks[k][0]:.4f} vs {checks[k][1]:.4f}" for k in bad)
        raise RuntimeError(
            f"{path.name}: does not match published statistics on {bad} ({detail}). "
            "The file may be incomplete -- Criteo is sorted by treatment, so a "
            "partial download is not a valid sample."
        )

    if sample_rows is not None and sample_rows < len(raw):
        # Random, never a prefix -- see the docstring.
        raw = raw.sample(n=sample_rows, random_state=seed).reset_index(drop=True)

    return RCT(
        name=f"criteo[{outcome}]" + (f"[n={len(raw):,}]" if sample_rows else ""),
        X=raw[[f"f{i}" for i in range(12)]],
        treatment=raw["treatment"].to_numpy().astype(int),
        outcome=raw[outcome].to_numpy().astype(float),
        outcome_name=outcome,
        spend=None,
    )


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
