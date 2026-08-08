"""Survival datasets for the Phase 3 benchmark.

Three sources, chosen to answer three different questions.

**Telco (IBM, 7,043 customers)** -- the one that matters. Real, public, and a
*contractual subscription* business, which is the vertical. Tenure in months plus a
churn flag is exactly a right-censored duration. Small enough (7k rows, 26.5% churn)
to be in the regime this project cares about rather than the industrial regime the
uplift literature lives in.

**GBSG2 (686 breast-cancer patients)** -- the canonical survival benchmark, used in
the RSF and DeepSurv papers themselves. Included precisely because it is the
baselines' home turf: continuous time, no time-varying covariates, moderate n. If a
discrete-time model has to be discretised onto a monthly grid to run there at all,
that cost should be visible rather than avoided by not running it.

**SubSim** -- ours, and the only one of the three with covariates that move. No public
survival dataset carries a monthly behavioural panel with the outcome attached, which
is the same argument D-020 made for the simulator on the causal side: the mechanism of
interest does not exist in public data, so it had to be built.

The Telco leak that everyone ships
----------------------------------
`TotalCharges` is cumulative billing to date. It correlates with `tenure` at **r =
0.83** -- it is very nearly `MonthlyCharges * tenure`. As a fixed covariate in a
survival model it is a direct encoding of the duration being predicted, so it must be
excluded. Every published Telco survival analysis that feeds the raw column set into
a Cox model has this, and it flatters the results. `EXCLUDED_FROM_TELCO` names it and
a test pins the exclusion.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from keel.benchmarks.datasets import DATA_DIR
from keel.models.survival.discrete import PERIOD, UNIT, SurvivalData

TELCO_URL = (
    "https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/"
    "master/data/Telco-Customer-Churn.csv"
)
TELCO_ROWS = 7_043

#: Excluded from Telco covariates, with the reason. Kept as data rather than a
#: comment so a test can assert on it.
EXCLUDED_FROM_TELCO = {
    "customerID": "identifier",
    "tenure": "this is the duration being modelled",
    "Churn": "this is the outcome",
    "TotalCharges": "cumulative billing -- r=0.83 with tenure, i.e. a duration proxy",
}

_TELCO_BINARY = {
    "gender": "Female",
    "Partner": "Yes",
    "Dependents": "Yes",
    "PhoneService": "Yes",
    "PaperlessBilling": "Yes",
}
_TELCO_CATEGORICAL = [
    "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup",
    "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies",
    "Contract", "PaymentMethod",
]


def load_telco(path: Path | None = None) -> SurvivalData:
    """IBM Telco customer churn, as a right-censored duration dataset.

    `tenure` is months as a customer and `Churn` is whether they left, so a churner
    with tenure 5 failed in period 5 and a non-churner with tenure 5 is censored
    there. That is the standard survival reading of this dataset.

    **11 customers have tenure 0** -- signed up but never completed a billing period.
    They contribute no period at risk and are dropped explicitly. Coercing them to
    tenure 1 would invent a month of survival for the customers least likely to have
    had one.
    """
    path = path or (DATA_DIR / "telco_churn.csv")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(TELCO_URL, tmp)  # noqa: S310 - fixed, documented URL
        rows = sum(1 for _ in tmp.open()) - 1
        if rows != TELCO_ROWS:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"telco: expected {TELCO_ROWS} rows, got {rows}")
        tmp.rename(path)

    raw = pd.read_csv(path)
    raw = raw[raw["tenure"] >= 1].reset_index(drop=True)

    X = pd.DataFrame(index=raw.index)
    X["senior_citizen"] = raw["SeniorCitizen"].astype(float)
    X["monthly_charges"] = raw["MonthlyCharges"].astype(float)
    for col, positive in _TELCO_BINARY.items():
        X[col.lower()] = (raw[col] == positive).astype(float)
    for col in _TELCO_CATEGORICAL:
        dummies = pd.get_dummies(raw[col], prefix=col.lower(), drop_first=True)
        X[dummies.columns] = dummies.astype(float)

    return SurvivalData(
        name="telco",
        X=X.reset_index(drop=True),
        duration=raw["tenure"].to_numpy().astype(int),
        event=(raw["Churn"] == "Yes").to_numpy().astype(int),
        cause_names={1: "churn"},
    )


def load_gbsg2(months_per_period: float = 30.44) -> SurvivalData:
    """GBSG2 breast-cancer trial, discretised onto a monthly grid.

    Requires `scikit-survival` (a Phase 3 extra) for the bundled copy.

    **The discretisation is a real cost and is not hidden.** Times are recorded in
    days over seven years; binning them into months throws away resolution that Cox,
    RSF and DeepSurv all keep. That is the correct handicap to accept: this dataset
    is here to check the implementation against the methods' own benchmark, not to
    win on it. Subscription billing genuinely is monthly, which is why the
    handicap does not apply where it counts.
    """
    from sksurv.datasets import load_gbsg2 as _load

    X_raw, y = _load()
    X = pd.DataFrame(index=X_raw.index)
    for col in X_raw.columns:
        if str(X_raw[col].dtype) == "category":
            dummies = pd.get_dummies(X_raw[col], prefix=col, drop_first=True)
            X[dummies.columns] = dummies.astype(float)
        else:
            X[col] = X_raw[col].astype(float)

    period = np.maximum(1, np.ceil(y["time"] / months_per_period)).astype(int)
    return SurvivalData(
        name="gbsg2",
        X=X.reset_index(drop=True),
        duration=period,
        event=y["cens"].astype(int),
        cause_names={1: "recurrence_or_death"},
    )


# --- SubSim -----------------------------------------------------------------

#: Panel columns usable as covariates. `tenure_months` is excluded because in SubSim
#: it is *exactly* period - 1, so it would duplicate the baseline-hazard term and
#: give the fixed-covariate baselines a free copy of the time axis they are not
#: otherwise entitled to. The churn columns are outcomes.
SUBSIM_FEATURES = [
    "mrr", "sessions_30d", "engagement_trend", "features_used",
    "support_tickets_90d", "unresolved_pain", "payment_failures_ltd",
    "seats_active_ratio", "champion_departed", "price_to_median",
]

SUBSIM_CAUSES = {1: "voluntary", 2: "involuntary"}


def subsim_survival(result) -> SurvivalData:
    """SubSim as a competing-risks duration dataset with **baseline** covariates.

    Duration is the number of months the customer was at risk; the event code is 1
    for voluntary churn, 2 for involuntary, 0 for still active at the end of the
    window (right-censored -- these are not negatives).

    Covariates are the month-0 snapshot. This is what a fixed-covariate survival
    model can consume, and the fact that it is *all* they can consume is the point
    being measured, not a limitation of this adapter.
    """
    panel = result.panel
    duration = panel.groupby("customer_id").size()

    last = panel.sort_values(["customer_id", "month"]).groupby("customer_id").last()
    event = np.where(
        last["churn_voluntary"] == 1, 1, np.where(last["churn_involuntary"] == 1, 2, 0)
    )

    baseline = (
        panel[panel["month"] == panel.groupby("customer_id")["month"].transform("min")]
        .set_index("customer_id")
        .loc[duration.index]
    )

    return SurvivalData(
        name="subsim",
        X=baseline[SUBSIM_FEATURES].reset_index(drop=True).astype(float),
        duration=duration.to_numpy().astype(int),
        event=event.astype(int),
        cause_names=dict(SUBSIM_CAUSES),
    )


def subsim_person_period(result, cause: int = 1) -> pd.DataFrame:
    """SubSim as a person-period frame with the covariates **as they moved**.

    This is the representation only the discrete-time model can use. Each row is one
    customer-month with that month's observed features and a flag for whether they
    failed from `cause` in it -- the same shape the Phase 1 feature store produces,
    one point-in-time build per row.
    """
    panel = result.panel.sort_values(["customer_id", "month"]).reset_index(drop=True)
    out = panel[SUBSIM_FEATURES].copy()
    out.insert(0, UNIT, panel["customer_id"].to_numpy())
    out.insert(1, PERIOD, panel["month"].to_numpy() + 1)
    col = "churn_voluntary" if cause == 1 else "churn_involuntary"
    out["event"] = panel[col].to_numpy().astype(int)
    return out


def split_by_unit(
    data: SurvivalData, test_fraction: float = 0.3, seed: int = 0
) -> tuple[SurvivalData, SurvivalData, np.ndarray]:
    """Random split **by subject**, returning `(train, test, test_index)`.

    Invariant 1 requires temporal splits, and this is not one -- deliberately, and
    the exception is worth naming rather than glossing. Telco and GBSG2 carry no
    calendar time at all: there is only tenure, which is the outcome. There is no
    "train on months < T" to perform, so a random subject-level split is the only
    honest option, and it is the one the survival literature uses for these sets.

    Where calendar time *does* exist -- SubSim, and any real tenant -- the temporal
    split applies unchanged and is used instead.
    """
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(data))
    n_test = int(round(test_fraction * len(data)))
    test_idx, train_idx = np.sort(idx[:n_test]), np.sort(idx[n_test:])
    return data.subset(train_idx), data.subset(test_idx), test_idx
