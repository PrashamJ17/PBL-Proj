"""Classification metrics and charts for slide 5, computed from the kill-test churn model.

Nothing here is invented or tuned for the slide. It rebuilds the model exactly as
`retainiq.experiments.kill_test` does -- same simulator seed, same 11 observable features,
same temporal split (train on months before 6, score month 6) -- and evaluates it at the
threshold the policy actually uses: the top 20% by predicted risk.

Accuracy is reported next to the accuracy of predicting that nobody churns, because with a
3% event rate accuracy on its own rewards doing nothing (D-067).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

from retainiq.experiments.kill_test import FEATURES, run  # noqa: E402
from retainiq.sim import SimConfig, simulate  # noqa: E402

OUT = Path(__file__).resolve().parent / "build" / "assets"
INK, TEAL, CORAL, GREY = "#12263A", "#0F9D8A", "#E4572E", "#8A97A6"
DECISION_MONTH = 6
BUDGET = 0.20

NICE = {
    "tenure_months": "Tenure (months)", "mrr": "Monthly revenue",
    "sessions_30d": "Sessions, last 30d", "engagement_trend": "Engagement trend",
    "features_used": "Features used", "support_tickets_90d": "Support tickets, 90d",
    "unresolved_pain": "Unresolved issues", "payment_failures_ltd": "Payment failures",
    "seats_active_ratio": "Active seat ratio", "champion_departed": "Champion departed",
    "price_to_median": "Price vs median",
}


def evaluate() -> tuple[dict, dict]:
    sim = simulate(SimConfig(6000, 24, 7))
    panel = sim.panel
    train = panel[panel["month"] < DECISION_MONTH]
    hold = panel[panel["month"] == DECISION_MONTH]

    model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, max_depth=4,
                                           random_state=0)
    model.fit(train[FEATURES], train["churn_voluntary"])
    y = hold["churn_voluntary"].to_numpy()
    p = model.predict_proba(hold[FEATURES])[:, 1]

    threshold = np.quantile(p, 1 - BUDGET)
    yhat = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, yhat).ravel()

    res = {
        "train_rows": int(len(train)), "holdout_rows": int(len(hold)),
        "base_rate": float(y.mean()), "auc": float(roc_auc_score(y, p)),
        "avg_precision": float(average_precision_score(y, p)), "threshold": float(threshold),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "accuracy": float(accuracy_score(y, yhat)), "majority_accuracy": float(1 - y.mean()),
        "precision": float(precision_score(y, yhat)), "recall": float(recall_score(y, yhat)),
        "f1": float(f1_score(y, yhat)),
    }

    pi = permutation_importance(model, hold[FEATURES], y, scoring="roc_auc", n_repeats=15,
                                random_state=0)
    imp = pd.Series(pi.importances_mean, index=FEATURES)
    res["importance"] = {k: float(v) for k, v in imp.sort_values(ascending=False).items()}

    results, _, auc = run(sim, decision_month=DECISION_MONTH, budget_fraction=BUDGET)
    res["kill_test_auc"] = float(auc)
    res["policies"] = {
        r.name: {"treated": int(r.n_treated), "value": float(r.expected_value),
                 "harmed": int(r.customers_harmed), "saved": int(r.customers_saved)}
        for r in results
    }
    curves = {"y": y, "p": p, "importance_mean": imp, "importance_std": pi.importances_std}
    return res, curves


def plot(res: dict, curves: dict) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False,
                         "axes.spines.right": False, "axes.edgecolor": "#B8C2CC",
                         "font.size": 8})
    y, p = curves["y"], curves["p"]
    tn, fp, fn, tp = res["tn"], res["fp"], res["fn"], res["tp"]

    fpr, tpr, _ = roc_curve(y, p)
    fig, ax = plt.subplots(figsize=(3.4, 3.05), dpi=300)
    ax.plot([0, 1], [0, 1], ls="--", color=GREY, lw=1.2, label="random (AUC 0.50)")
    ax.plot(fpr, tpr, color=INK, lw=2.4, label=f"GBM churn model (AUC {res['auc']:.3f})")
    point = (fp / (fp + tn), tp / (tp + fn))
    ax.scatter(*point, s=60, color=CORAL, zorder=5)
    ax.annotate("top-20% policy\noperating point", point, xytext=(0.40, 0.22), fontsize=7.5,
                color=CORAL, arrowprops={"arrowstyle": "->", "color": CORAL})
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.legend(loc="lower right", fontsize=7, frameon=False)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "roc.png", facecolor="white")
    plt.close(fig)

    cm = np.array([[tn, fp], [fn, tp]])
    labels = [["True negative", "False positive"], ["False negative", "True positive"]]
    fig, ax = plt.subplots(figsize=(3.3, 3.05), dpi=300)
    ax.imshow(cm, cmap="Blues", vmin=0, vmax=cm.max() * 1.15)
    for i in range(2):
        for j in range(2):
            dark = cm[i, j] > cm.max() * 0.55
            ax.text(j, i, f"{cm[i, j]:,}\n{labels[i][j]}", ha="center", va="center",
                    fontsize=8.5, color="white" if dark else INK, fontweight="bold")
    ax.set_xticks([0, 1], ["Not targeted", "Targeted (top 20%)"], fontsize=7.5)
    ax.set_yticks([0, 1], ["Stayed", "Churned"], fontsize=7.5)
    ax.set_xlabel("Model decision", fontsize=8)
    ax.set_ylabel("Actual outcome (month 6)", fontsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "confusion.png", facecolor="white")
    plt.close(fig)

    imp = curves["importance_mean"].sort_values()
    std = curves["importance_std"][[FEATURES.index(k) for k in imp.index]]
    fig, ax = plt.subplots(figsize=(3.8, 3.05), dpi=300)
    ax.barh([NICE[k] for k in imp.index], imp.values, xerr=std, ecolor=GREY, capsize=2,
            color=[TEAL if v == imp.max() else "#5B7A99" for v in imp.values])
    ax.set_xlabel("Drop in holdout AUC when shuffled", fontsize=7.5)
    ax.tick_params(labelsize=7.2)
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "importance.png", facecolor="white")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res, curves = evaluate()
    (OUT / "metrics.json").write_text(json.dumps(res, indent=2))
    plot(res, curves)
    headline = ("auc", "avg_precision", "base_rate", "recall", "precision", "f1", "accuracy",
                "majority_accuracy")
    print(json.dumps({k: round(res[k], 4) for k in headline}, indent=2))
    print("figures written to", OUT)


if __name__ == "__main__":
    main()
