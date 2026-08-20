"""Build the Zenodo data release.

Two things go into the archive, and the distinction matters.

**SubSim reference datasets — ours to publish, and the novel artifact.** No public dataset
carries individual-level ground-truth treatment effects, which is the whole reason the
simulator exists. Releasing a fixed, seeded draw lets anyone score a CATE estimator
against per-customer truth without re-running our code, and lets a reviewer check our
numbers against the same rows we used.

**A manifest for the third-party datasets — cited, never redistributed.** Hillstrom,
Criteo-UPLIFT, Lenta, Telco and GBSG2 belong to other people and carry their own terms.
Re-hosting them under our DOI would risk breaching those terms and would confuse
provenance: a reader could no longer tell whose dataset they had. The manifest instead
records the canonical source, the exact size, and a SHA-256 of the file we used, so
anybody can fetch the original and verify byte-for-byte that they have what we had.

That is the stronger reproducibility guarantee anyway. A copy proves what we uploaded; a
checksum against the canonical source proves what we *used*.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from retainiq.sim import SimConfig, simulate
from retainiq.sim.counterfactual import LADDER, potential_outcomes

#: Sizes released. Chosen to span the range the paper analyses: the small-business
#: regime where the reliability and measurement results bite, and one larger draw for
#: estimator development.
RELEASE_SIZES = (500, 2_000, 10_000)
RELEASE_SEED = 20260815
N_MONTHS = 24

#: Canonical sources for datasets we cite but do not redistribute.
THIRD_PARTY = [
    {
        "name": "Hillstrom MineThatData E-Mail Analytics Challenge",
        "file": "hillstrom.csv",
        "rows": 64_000,
        "source": "https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html",
        "role": "Correlation criterion (Table 4); small-n reliability (Table 5)",
        "redistribute": False,
        "note": "Randomised 3-arm e-mail experiment. Cited, not redistributed.",
    },
    {
        "name": "Criteo-UPLIFT v2.1",
        "file": "criteo-uplift-v2.1.csv.gz",
        "rows": 13_979_592,
        "source": "https://ailab.criteo.com/criteo-uplift-prediction-dataset/",
        "role": "Correlation criterion, high-correlation end (Table 4)",
        "redistribute": False,
        "note": "Criteo AI Lab terms apply. Cited, not redistributed.",
    },
    {
        "name": "Lenta",
        "file": "lenta_dataset.csv.gz",
        "rows": 687_029,
        "source": "https://www.uplift-modeling.com/en/latest/api/datasets/fetch_lenta.html",
        "role": "Out-of-sample prediction test (Table 4)",
        "redistribute": False,
        "note": "Distributed with scikit-uplift. Cited, not redistributed.",
    },
    {
        "name": "Telco Customer Churn",
        "file": "telco_churn.csv",
        "rows": 7_043,
        "source": "https://www.kaggle.com/datasets/blastchar/telco-customer-churn",
        "role": "Survival benchmark (Table 6)",
        "redistribute": False,
        "note": "IBM sample data via Kaggle; Kaggle terms apply. Cited, not redistributed.",
    },
    {
        "name": "GBSG2",
        "file": "(bundled with scikit-survival)",
        "rows": 686,
        "source": "https://scikit-survival.readthedocs.io/en/stable/api/generated/sksurv.datasets.load_gbsg2.html",
        "role": "Survival benchmark, negative control (Table 7)",
        "redistribute": False,
        "note": "Loaded from scikit-survival at runtime; no local copy is kept.",
    },
]


@dataclass
class FileRecord:
    filename: str
    rows: int
    columns: int
    bytes: int
    sha256: str
    description: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write(frame: pd.DataFrame, path: Path, description: str) -> FileRecord:
    frame.to_csv(path, index=False)
    return FileRecord(
        filename=path.name,
        rows=len(frame),
        columns=frame.shape[1],
        bytes=path.stat().st_size,
        sha256=_sha256(path),
        description=description,
    )


def build(outdir: Path | str = "zenodo_release") -> Path:
    """Generate the SubSim reference datasets and the manifest."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    records: list[FileRecord] = []

    for n in RELEASE_SIZES:
        sim = simulate(SimConfig(n_customers=n, n_months=N_MONTHS, seed=RELEASE_SEED))

        records.append(_write(
            sim.panel, out / f"subsim_panel_n{n}.csv",
            "Person-period panel: one row per customer per month at risk. Observable "
            "covariates only — latent state is deliberately excluded, and a CI test "
            "enforces that exclusion.",
        ))
        records.append(_write(
            sim.customers, out / f"subsim_customers_n{n}.csv",
            "One row per customer: MRR, signup month, churn month (-1 if retained), "
            "and cause of churn.",
        ))

        # The artifact that does not exist anywhere else.
        po = potential_outcomes(sim, decision_month=6, horizon=6)
        records.append(_write(
            po, out / f"subsim_counterfactuals_n{n}.csv",
            "GROUND TRUTH. Per-customer potential outcomes under common random numbers: "
            "p_churn_control, p_churn_treated, tau_true (negative = the offer helps), "
            "realised y0 and y1, true quadrant, CLV, offer cost, and value_of_treating. "
            "This is what no public dataset contains and what the simulator exists to "
            "provide.",
        ))

    # Per-rung counterfactuals at one size, for offer-ladder work.
    sim = simulate(SimConfig(n_customers=2_000, n_months=N_MONTHS, seed=RELEASE_SEED))
    ladder = []
    for k, offer in enumerate(LADDER):
        po = potential_outcomes(sim, decision_month=6, horizon=6, offer=offer)
        po = po[["customer_id", "tau_true", "y0", "y1", "clv", "offer_cost",
                 "value_of_treating"]].copy()
        po.insert(1, "offer", offer.name)
        po.insert(2, "rung", offer.rung)
        ladder.append(po)
    records.append(_write(
        pd.concat(ladder, ignore_index=True), out / "subsim_offer_ladder_n2000.csv",
        "Ground-truth effects for all six offer-ladder rungs on the same 2,000 customers "
        "under common random numbers, so rungs are directly comparable per person.",
    ))

    manifest = {
        "title": "RetainIQ: SubSim reference datasets with ground-truth counterfactuals",
        "related_software_doi": "https://doi.org/10.5281/zenodo.22009471",
        "repository": "https://github.com/PrashamJ17/PBL-Proj",
        "generator": {
            "module": "retainiq.experiments.zenodo_release",
            "command": "python -m retainiq.experiments.zenodo_release",
            "seed": RELEASE_SEED,
            "n_months": N_MONTHS,
            "sizes": list(RELEASE_SIZES),
            "note": "Regenerating with this seed reproduces these files byte-for-byte.",
        },
        "license": "CC BY 4.0 (simulator output, generated by this work)",
        "files": [asdict(r) for r in records],
        "third_party_datasets_cited_not_redistributed": THIRD_PARTY,
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    d = build()
    print(f"wrote {d.resolve()}")
    for f in sorted(d.iterdir()):
        print(f"  {f.name:44} {f.stat().st_size/1048576:8.2f} MB")
