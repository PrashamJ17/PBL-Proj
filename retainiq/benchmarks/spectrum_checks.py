"""The checks the risk-lift correlation owed (D-068).

`spectrum.py` measures one number per setting: the Pearson correlation, on the
probability scale, between a T-learner's estimated effect and an outcome model fitted on
both arms, from one split. Reading it beside Ascarza (2018, Web Appendix A3.4) raised
four questions that one number from one split cannot answer:

1. **Is it the coefficient?** Pearson measures linear association and is moved by a few
   extreme customers. Spearman measures agreement between the two *orderings*, which is
   what targeting uses.
2. **Is it the scale?** If an offer shifts everyone's log-odds by the same amount, the
   shift in probability is largest where the baseline is highest. A positive correlation
   on the probability scale can therefore be produced by arithmetic alone. Ascarza warns
   of this.
3. **Is it the definition of risk?** Her RISK is fitted on control customers only. With a
   T-learner that is the model whose prediction is *subtracted* to form the effect, so
   the two share estimation noise with opposite sign. Fitting the risk on customers the
   effect model never saw removes that.
4. **Is it the split?** One split has no interval.

And a fifth about the figure: the simulator's point compares an oracle with a churn
score. What does a *fitted* uplift model gain there?

The design and five predictions were committed before this module existed, in
`docs/PREREG-checks-and-baseline.md`. The answers are in D-074.

**A follow-up (D-076).** Check 3 moved the figure and could not say why: the independent
version changed who the risk model was fitted on, how much data each model saw, and which
arms the risk model used, all at once. `pooled_half` and `pooled_indep` change those one
at a time. Their design and predictions are in `docs/PREREG-pooled-independent-risk.md`.

**And a diagnostic that nobody planned (D-076).** The follow-up's second prediction failed,
and the reason turned out to be in the instrument: scikit-learn's gradient boosting stops
early by default once it is given more than 10,000 rows. In Hillstrom each arm of the
training half has about 10,650, so the T-learner's two models each stopped when a random
tenth of their own data said so, at different rounds, and the correlation followed the
difference. `--stopping-diagnostic` measures that. It is exploratory and says so in its
output.

**What changed as a result (D-077).** The benchmark classifier now runs its full 150
rounds at every sample size, so every figure in this module is fitted that way. And the
headline figure is `control_indep`: risk fitted on control customers only, on customers
the effect model never saw. That is Ascarza's definition of RISK, and it shares no
estimation noise with the effect. The both-arm figure (`pooled`) is kept beside it. Both
changes were written down before anything was re-run (`docs/PREREG-fixed-stopping.md`).

Nothing here changes what `spectrum.py` prints. That command still shows one split, and
this one shows how far one split can sit from the other twenty-nine. The figure drawn
here (`fig07`) is the one to use: every point on it is a fitted model on a randomised
trial, measured the same way, with the spread across splits drawn on both axes.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from retainiq.benchmarks.datasets import RCT
from retainiq.benchmarks.evaluate import top_k_mask, uplift_of_set
from retainiq.benchmarks.models import TLearner, _clf
from retainiq.benchmarks.run import split
from retainiq.benchmarks.spectrum import OUTCOME_MODELS, UPLIFT_MODELS

#: Splits per setting. Fixed in the pre-registration.
SPLITS = 30

#: Probabilities are clipped to this distance from 0 and 1 before taking logits, so a
#: fitted probability of exactly 0 does not become an infinite log-odds.
CLIP = 1e-4

#: Customers in the trial drawn from the simulator: comparable with Hillstrom.
SIM_CUSTOMERS = 60_000

SCALES = ("prob", "logodds")
RISKS = ("pooled", "control_same", "control_indep")

#: Added by the second pre-registration (D-076), and kept apart from the first three so
#: that it stays visible which figures were designed when.
#:   pooled_half   effect and both-arm risk fitted on the SAME half of the training data
#:   pooled_indep  effect on one half, both-arm risk on the OTHER half
FOLLOW_UP = ("pooled_half", "pooled_indep")
ALL_RISKS = (*RISKS, *FOLLOW_UP)

#: The figure the documents lead with (D-077): Ascarza's RISK, fitted on control customers
#: only, on customers the effect model never saw.
HEADLINE = "control_indep"

#: The gap between the table's figure and the independent control-only one, taken one
#: change at a time. Each is a difference between two correlations on the same split.
STEPS = {
    "step_data": ("pooled_half", "pooled"),              # half the data, customers shared
    "step_sharing": ("pooled_indep", "pooled_half"),     # same data, customers not shared
    "step_definition": ("control_indep", "pooled_indep"),  # both arms -> control only
}
COEFFICIENTS = ("pearson", "spearman")


@dataclass(frozen=True)
class Setting:
    """A randomised experiment and which way its outcome points.

    `benefit_sign` is +1 when the outcome is something the firm wants more of (a visit, a
    purchase) and -1 when it wants less (churn). Every effect is then reported as a
    *benefit*, positive when the treatment helps, which is Ascarza's LIFT. The outcome
    model's score is the propensity for the outcome either way: likeliest to respond, or
    likeliest to churn. That is what a naive policy targets in both cases.
    """

    name: str
    domain: str
    benefit_sign: int = 1


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), CLIP, 1.0 - CLIP)
    return np.log(p / (1.0 - p))


def _constant(x: np.ndarray) -> bool:
    """True when `x` does not vary beyond rounding error.

    An effect that is the same for everyone, computed as a difference of two logits,
    comes out as a constant plus noise in the sixteenth decimal place. Correlating that
    noise with anything returns a number, and the number means nothing.
    """
    return bool(np.ptp(x) <= 1e-9 * max(1.0, float(np.abs(x).max())))


def correlation(a: np.ndarray, b: np.ndarray, coefficient: str) -> float:
    """Pearson or Spearman, and NaN when either input does not vary.

    A constant input has no ordering and no linear association with anything. Returning
    0 would report "uncorrelated", which is a finding; NaN reports that there was
    nothing to correlate.
    """
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.size < 3 or _constant(a) or _constant(b):
        return float("nan")
    if coefficient == "pearson":
        return float(np.corrcoef(a, b)[0, 1])
    if coefficient == "spearman":
        return float(spearmanr(a, b).statistic)
    raise ValueError(f"unknown coefficient {coefficient!r}")


def benefits(p1: np.ndarray, p0: np.ndarray, sign: int) -> dict[str, np.ndarray]:
    """The effect of treatment as a benefit, on each scale."""
    return {"prob": sign * (p1 - p0), "logodds": sign * (logit(p1) - logit(p0))}


def risks_on(scale: str, risk: np.ndarray) -> np.ndarray:
    return risk if scale == "prob" else logit(risk)


def all_correlations(benefit: dict[str, np.ndarray], risk: np.ndarray) -> dict[str, float]:
    """Every coefficient on every scale, for one definition of risk."""
    return {
        f"{coefficient}_{scale}": correlation(benefit[scale], risks_on(scale, risk), coefficient)
        for scale in SCALES for coefficient in COEFFICIENTS
    }


def incremental(scores: np.ndarray, rct: RCT, budget_fraction: float, sign: int) -> float:
    """Extra good outcomes from treating the top of a ranking, estimated from the trial."""
    k = int(round(budget_fraction * len(rct)))
    mask = top_k_mask(scores, k)
    return sign * uplift_of_set(rct.treatment, rct.outcome, mask) * int(mask.sum())


def one_split(rct: RCT, seed: int, benefit_sign: int = 1,
              budget_fraction: float = 0.30) -> dict[str, float]:
    """Everything measured on one split of one experiment."""
    train, test = split(rct, seed=seed)
    X, t, y = train.X, train.treatment, train.outcome

    learner = TLearner(seed=seed).fit(X, t, y)
    p1 = learner.treated.predict_proba(test.X)[:, 1]
    p0 = learner.control.predict_proba(test.X)[:, 1]
    benefit = benefits(p1, p0, benefit_sign)

    row: dict[str, float] = {"seed": seed, "n_test": len(test)}

    # Risk fitted on both arms: what `spectrum.py` does.
    pooled = _clf(seed).fit(X, y.astype(int)).predict_proba(test.X)[:, 1]
    row |= {f"pooled_{k}": v for k, v in all_correlations(benefit, pooled).items()}

    # Risk fitted on control only, by the same model the effect subtracts.
    row |= {f"control_same_{k}": v for k, v in all_correlations(benefit, p0).items()}

    # Risk fitted on control only, on customers the effect model never saw. The training
    # half is cut in two: one part fits the effect, the other fits the risk.
    order = np.random.default_rng(50_000 + seed).permutation(len(train))
    a, b = order[: len(order) // 2], order[len(order) // 2:]
    control_b = b[t[b] == 0]
    usable = (
        len(np.unique(t[a])) == 2 and len(control_b) > 0
        and all(len(np.unique(y[a][t[a] == arm])) == 2 for arm in (0, 1))
        and len(np.unique(y[control_b])) == 2
    )
    if usable:
        effect_a = TLearner(seed=seed).fit(X.iloc[a], t[a], y[a])
        benefit_a = benefits(effect_a.treated.predict_proba(test.X)[:, 1],
                             effect_a.control.predict_proba(test.X)[:, 1], benefit_sign)
        risk_b = (_clf(seed + 2).fit(X.iloc[control_b], y[control_b].astype(int))
                  .predict_proba(test.X)[:, 1])
        found = all_correlations(benefit_a, risk_b)

        # The follow-up (D-076). Both use the effect fitted on part A, so that each
        # differs from its neighbour in one respect only. Risk on both arms of part A
        # shares its customers with the effect; risk on both arms of part B does not.
        pooled_a = _clf(seed).fit(X.iloc[a], y[a].astype(int)).predict_proba(test.X)[:, 1]
        pooled_b = _clf(seed + 2).fit(X.iloc[b], y[b].astype(int)).predict_proba(test.X)[:, 1]
        half, indep = (all_correlations(benefit_a, pooled_a),
                       all_correlations(benefit_a, pooled_b))
    else:
        found = dict.fromkeys(all_correlations(benefit, p0), float("nan"))
        half, indep = dict(found), dict(found)
    row |= {f"control_indep_{k}": v for k, v in found.items()}
    row |= {f"pooled_half_{k}": v for k, v in half.items()}
    row |= {f"pooled_indep_{k}": v for k, v in indep.items()}

    # The advantage of the best uplift model over the best outcome model, as
    # `spectrum.measure` computes it, without the bootstrap.
    def best(classes, sign_scores: int) -> float:
        return max(
            incremental(sign_scores * cls(seed=seed).fit(X, t, y).score(test.X), test,
                        budget_fraction, benefit_sign)
            for cls in classes
        )

    up, out = best(UPLIFT_MODELS, benefit_sign), best(OUTCOME_MODELS, 1)
    row["best_uplift"], row["best_outcome"] = up, out
    row["advantage_pct"] = 100.0 * (up - out) / max(abs(out), 1e-9)
    # Not in the pre-registration: the same gap per thousand customers. The percentage
    # divides by the outcome model's gain, which is small or negative in some settings.
    row["gain_per_1000"] = 1000.0 * (up - out) / len(test)
    row["predicted_negative"] = float((benefit["prob"] < 0).mean())
    return row


def run(rct: RCT, setting: Setting, splits: int = SPLITS) -> pd.DataFrame:
    rows = [one_split(rct, seed, setting.benefit_sign) for seed in range(splits)]
    return pd.DataFrame(rows).assign(setting=setting.name, domain=setting.domain)


# --- the simulator, measured the way the experiments are ----------------------


def subsim_trial(n_customers: int = SIM_CUSTOMERS, seed: int = 7) -> tuple[RCT, pd.DataFrame]:
    """A randomised trial drawn from the simulator, and the truth it was drawn from.

    Treatment is assigned by coin toss and each customer's outcome is observed for the
    arm they were assigned, which is all a real experiment would show. The truth is
    returned beside it and is never given to a model.
    """
    from retainiq.experiments.abstention import FEATURES
    from retainiq.sim import SimConfig, simulate
    from retainiq.sim.counterfactual import potential_outcomes

    sim = simulate(SimConfig(n_customers=n_customers, n_months=24, seed=seed))
    po = potential_outcomes(sim, decision_month=6, horizon=6)
    snap = sim.snapshot(6)[["customer_id", *FEATURES]]
    frame = po.merge(snap, on="customer_id", how="inner").reset_index(drop=True)

    treated = (np.random.default_rng(7_000 + seed).random(len(frame)) < 0.5).astype(int)
    churned = np.where(treated == 1, frame["y1"], frame["y0"]).astype(float)
    rct = RCT(name=f"subsim[{n_customers:,}]", X=frame[FEATURES].astype(float),
              treatment=treated, outcome=churned, outcome_name="churned")
    return rct, frame[["p_churn_control", "p_churn_treated", "tau_true"]]


def true_correlations(truth: pd.DataFrame) -> dict[str, float]:
    """The correlation between true benefit and true untreated risk, on both scales."""
    benefit = benefits(truth["p_churn_treated"].to_numpy(), truth["p_churn_control"].to_numpy(),
                       sign=-1)
    return all_correlations(benefit, truth["p_churn_control"].to_numpy())


# --- summarising ----------------------------------------------------------------


def interval(values: pd.Series) -> tuple[float, float, float]:
    """Mean, and the 2.5th and 97.5th percentiles across splits."""
    v = values.dropna().to_numpy()
    if v.size == 0:
        return float("nan"), float("nan"), float("nan")
    return float(v.mean()), float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def has_follow_up(frame: pd.DataFrame) -> bool:
    """False for splits saved before the follow-up existed."""
    return all(f"{risk}_pearson_prob" in frame for risk in FOLLOW_UP)


def with_steps(frame: pd.DataFrame, suffix: str = "pearson_prob") -> pd.DataFrame:
    """Add the three steps as columns, each a paired difference on the same split.

    They sum, split by split, to `control_indep - pooled`: the movement D-074 reported
    and could not attribute. Returned unchanged when the follow-up was not measured.
    """
    if not has_follow_up(frame):
        return frame
    out = frame.copy()
    for step, (after, before) in STEPS.items():
        out[step] = out[f"{after}_{suffix}"] - out[f"{before}_{suffix}"]
    return out


def summarise(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per setting and measure: mean, split-to-split interval, and spread."""
    measures = [c for c in frame.columns
                if c not in {"seed", "n_test", "setting", "domain"}]
    rows = []
    for name, g in frame.groupby("setting", sort=False):
        for m in measures:
            mean, low, high = interval(g[m])
            seen = g[m].dropna()
            rows.append({"setting": name, "measure": m, "mean": mean, "low": low,
                         "high": high, "splits": int(len(seen)),
                         "sd": float(seen.std()) if len(seen) > 1 else float("nan")})
    return pd.DataFrame(rows)


def _cell(summary: pd.DataFrame, setting: str, measure: str, fmt: str = "+.2f") -> str:
    r = summary[(summary["setting"] == setting) & (summary["measure"] == measure)]
    if r.empty or np.isnan(r["mean"].iloc[0]):
        return "n/a"
    mean, low, high = (r[c].iloc[0] for c in ("mean", "low", "high"))
    return f"{mean:{fmt}} [{low:{fmt}}, {high:{fmt}}]"


def report(frame: pd.DataFrame, truth: dict[str, float] | None = None,
           oracle_note: str | None = None, source: str | None = None) -> str:
    """The tables. `source` names a saved file when the splits were re-read, not re-run."""
    s = summarise(with_steps(frame))
    settings = list(dict.fromkeys(frame["setting"]))
    splits = int(frame.groupby("setting").size().max())
    width = 118
    out = [
        "THE RISK-LIFT CORRELATION, CHECKED (D-068, D-074)",
        f"mean over {splits} splits, with the 2.5th and 97.5th percentiles across splits",
    ]
    if source:
        # Named as re-read so that a table printed from a saved file is never mistaken
        # for the experiment having been run again (invariant 14).
        out.append(f"RE-READ from {source}, not re-run")
    out.append("=" * width)

    def table(title: str, columns: list[tuple[str, str]], fmt: str = "+.2f",
              col: int = 31) -> None:
        out.extend(["", title, "-" * width,
                    f"{'setting':<24}" + "".join(f"{h:>{col}}" for h, _ in columns)])
        for name in settings:
            out.append(f"{name:<24}" + "".join(f"{_cell(s, name, m, fmt):>{col}}"
                                               for _, m in columns))

    def spread(name: str, measure: str) -> str:
        r = s[(s["setting"] == name) & (s["measure"] == measure)]
        return "n/a" if r.empty or np.isnan(r["sd"].iloc[0]) else f"{r['sd'].iloc[0]:.3f}"

    lead = HEADLINE
    table("HEADLINE: risk fitted on control customers the effect model never saw (D-077)",
          [("Pearson, probability", f"{lead}_pearson_prob"),
           ("Pearson, log-odds", f"{lead}_pearson_logodds"),
           ("Spearman, probability", f"{lead}_spearman_prob")])
    table("1. THE COEFFICIENT (probability scale, pooled risk)",
          [("Pearson", "pooled_pearson_prob"), ("Spearman", "pooled_spearman_prob")])
    table("2. THE SCALE (Pearson, pooled risk)",
          [("probability", "pooled_pearson_prob"), ("log-odds", "pooled_pearson_logodds")])
    table("   THE SCALE (Spearman, pooled risk)",
          [("probability", "pooled_spearman_prob"), ("log-odds", "pooled_spearman_logodds")])
    table("3. THE DEFINITION OF RISK (Pearson, probability scale)",
          [("pooled", "pooled_pearson_prob"), ("control, same data", "control_same_pearson_prob"),
           ("control, independent", "control_indep_pearson_prob")])
    if has_follow_up(frame):
        four = [("pooled", "pooled_pearson_prob"), ("pooled, half", "pooled_half_pearson_prob"),
                ("pooled, indep.", "pooled_indep_pearson_prob"),
                ("control, indep.", "control_indep_pearson_prob")]
        table("3b. WHY IT MOVES: one change at a time (Pearson, probability scale; D-076)",
              four, col=23)
        table("    THE THREE STEPS, each a difference on the same split",
              [("half the data", "step_data"), ("customers not shared", "step_sharing"),
               ("control only", "step_definition")])
        out.extend(["", "    SPREAD ACROSS SPLITS (standard deviation of the correlation)",
                    "-" * width,
                    f"{'setting':<24}" + "".join(f"{h:>23}" for h, _ in four)])
        for name in settings:
            out.append(f"{name:<24}" + "".join(f"{spread(name, m):>23}" for _, m in four))

    table("4. WHAT THE UPLIFT MODEL GAINS over the best outcome model",
          [("advantage, %", "advantage_pct"), ("per 1,000 customers", "gain_per_1000")],
          fmt="+.1f")

    if truth is not None:
        out += ["", "5. THE SIMULATOR'S TRUTH (true benefit against true untreated risk)",
                "-" * width,
                "  " + "   ".join(f"{k.replace('_', ', ')}: {v:+.2f}" for k, v in truth.items())]
    if oracle_note:
        out += ["", oracle_note]
    out += [
        "", "-" * width,
        "Benefit is positive when treatment helps. Risk is the propensity for the outcome a",
        "naive policy targets: likeliest to respond, or likeliest to churn.",
        "control, same data  = risk from the model the effect subtracts: shares its noise.",
        "control, independent = risk and effect fitted on different customers.",
    ]
    if has_follow_up(frame):
        out += [
            "pooled, half   = effect and both-arm risk fitted on the same half of the data.",
            "pooled, indep. = effect on one half, both-arm risk on the other.",
            "The three steps add up to (control, independent) minus (pooled).",
        ]
    return "\n".join(out)


# --- a diagnostic: the classifier's early stopping ---------------------------------------

#: The two ways the benchmark classifier is fitted in the diagnostic. "automatic" is the
#: library default: on when a model is given more than 10,000 rows, off otherwise. Every
#: figure in D-074 and D-076 was made with it. "off" is the project's setting since D-077,
#: and so what every other figure in this module is made with now.
STOPPING = {"automatic": "auto", "off": False}

#: Settings in which some model crosses the 10,000-row line somewhere in the design, so
#: that the fitting changes along with whatever else was meant to change. In Criteo and
#: Lenta every model is far above the line at every step, and fitting them without early
#: stopping thirty times over would take hours.
STOPPING_SETTINGS = ("Hillstrom (mens)", "Hillstrom (womens)", "SubSim (fitted)")


@contextmanager
def fitting(early_stopping):
    """Fit every benchmark classifier with early stopping forced to one setting.

    The classifier is built in one place, `models._clf`, and used by every model in the
    benchmark. Swapping that factory for the duration reaches all of them without
    copying a single hyperparameter. `False` reproduces the project's own setting
    exactly; `"auto"` is the library default it replaced.
    """
    from retainiq.benchmarks import models

    original = models._clf

    def factory(seed: int):
        return original(seed).set_params(early_stopping=early_stopping)

    here = globals()
    models._clf, here["_clf"] = factory, factory
    try:
        yield
    finally:
        models._clf, here["_clf"] = original, original


def boosting_rounds(rct: RCT, seed: int) -> dict[str, int]:
    """How many boosting rounds each of the three models behind the table's figure ran,
    and how many customers each arm gave its model."""
    train, _ = split(rct, seed=seed)
    X, t, y = train.X, train.treatment, train.outcome
    learner = TLearner(seed=seed).fit(X, t, y)
    pooled = _clf(seed).fit(X, y.astype(int))
    return {
        "train_treated": int((t == 1).sum()), "train_control": int((t == 0).sum()),
        "rounds_treated": int(learner.treated.n_iter_),
        "rounds_control": int(learner.control.n_iter_),
        "rounds_pooled": int(pooled.n_iter_),
    }


def stopping_diagnostic(rct: RCT, setting: Setting, splits: int = SPLITS) -> pd.DataFrame:
    """Every split measured twice: with the default stopping, and with it switched off."""
    rows = []
    for label, value in STOPPING.items():
        with fitting(value):
            for seed in range(splits):
                rows.append(one_split(rct, seed, setting.benefit_sign)
                            | boosting_rounds(rct, seed) | {"stopping": label})
    return pd.DataFrame(rows).assign(setting=setting.name, domain=setting.domain)


def report_stopping(frame: pd.DataFrame) -> str:
    settings = list(dict.fromkeys(frame["setting"]))
    splits = int(frame.groupby(["setting", "stopping"]).size().max())
    width = 118
    auto = frame[frame["stopping"] == "automatic"]
    part = {label: summarise(with_steps(frame[frame["stopping"] == label]
                                        .drop(columns="stopping")))
            for label in STOPPING}

    def cell(label: str, name: str, measure: str, fmt: str = "+.2f") -> str:
        s = part[label]
        r = s[(s["setting"] == name) & (s["measure"] == measure)]
        if r.empty or np.isnan(r["mean"].iloc[0]):
            return "n/a"
        mean, low, high, sd = (r[c].iloc[0] for c in ("mean", "low", "high", "sd"))
        return f"{mean:{fmt}} [{low:{fmt}}, {high:{fmt}}] sd {sd:.3f}"

    out = [
        "THE CLASSIFIER'S EARLY STOPPING, AND WHAT IT DOES TO THE CORRELATION (D-076)",
        "EXPLORATORY: not pre-registered. Added after a pre-registered prediction failed.",
        f"mean over {splits} splits, with the 2.5th and 97.5th percentiles and the standard "
        "deviation",
        "=" * width,
        "",
        "A. HOW LONG EACH MODEL WAS FITTED under the library's automatic stopping",
        "   boosting rounds, fewest / median / most, of a possible 150",
        "-" * width,
        f"{'setting':<22}{'customers per arm':>20}{'treated model':>17}{'control model':>17}"
        f"{'both-arm model':>17}{'corr. with round gap':>23}",
    ]
    for name in settings:
        g = auto[auto["setting"] == name]

        def spell(column: str, g=g) -> str:
            v = g[column]
            return f"{int(v.min())} / {int(v.median())} / {int(v.max())}"

        gap = g["rounds_treated"] - g["rounds_control"]
        link = correlation(g["pooled_pearson_prob"].to_numpy(), gap.to_numpy(), "pearson")
        arms = f"{int(g['train_treated'].median()):,} / {int(g['train_control'].median()):,}"
        out.append(f"{name:<22}{arms:>20}{spell('rounds_treated'):>17}"
                   f"{spell('rounds_control'):>17}{spell('rounds_pooled'):>17}"
                   f"{'n/a' if np.isnan(link) else f'{link:+.2f}':>23}")
    out += ["   round gap = rounds the treated model ran minus rounds the control model ran;",
            "   the last column is its correlation, across splits, with that split's figure."]

    def block(title: str, columns: list[tuple[str, str]], label: str, fmt: str = "+.2f",
              col: int = 31) -> None:
        out.extend(["", title, "-" * width,
                    f"{'setting':<22}" + "".join(f"{h:>{col}}" for h, _ in columns)])
        for name in settings:
            out.append(f"{name:<22}" + "".join(f"{cell(label, name, m, fmt):>{col}}"
                                               for _, m in columns))

    two = f"{'setting':<22}{'automatic stopping':>40}{'stopping off':>40}"
    out.extend(["", "B. THE TABLE'S FIGURE (both-arm risk, same customers; Pearson, probability "
                "scale)", "-" * width, two])
    for name in settings:
        out.append(f"{name:<22}{cell('automatic', name, 'pooled_pearson_prob'):>40}"
                   f"{cell('off', name, 'pooled_pearson_prob'):>40}")

    four = [("pooled", "pooled_pearson_prob"), ("pooled, half", "pooled_half_pearson_prob"),
            ("pooled, indep.", "pooled_indep_pearson_prob"),
            ("control, indep.", "control_indep_pearson_prob")]
    steps = [("half the data", "step_data"), ("customers not shared", "step_sharing"),
             ("control only", "step_definition")]

    def plain(label: str, name: str, measure: str) -> str:
        return cell(label, name, measure).split(" sd ")[0]

    for label in ("off", "automatic"):
        out.extend(["", "C. ONE CHANGE AT A TIME, stopping off (as in the main tables)"
                    if label == "off" else
                    "   THE SAME, automatic stopping (the library default)", "-" * width,
                    f"{'setting':<22}" + "".join(f"{h:>24}" for h, _ in four)])
        for name in settings:
            out.append(f"{name:<22}" + "".join(f"{plain(label, name, m):>24}" for _, m in four))
        out.append(f"{'  steps':<22}" + "".join(f"{h:>32}" for h, _ in steps))
        for name in settings:
            out.append(f"{'  ' + name:<22}"
                       + "".join(f"{plain(label, name, m):>32}" for _, m in steps))

    out.extend(["", "D. WHAT THE UPLIFT MODEL GAINS, extra outcomes per 1,000 customers",
                "-" * width, two])
    for name in settings:
        out.append(f"{name:<22}{cell('automatic', name, 'gain_per_1000', '+.1f'):>40}"
                   f"{cell('off', name, 'gain_per_1000', '+.1f'):>40}")
    out += [
        "", "-" * width,
        "The library stops a model early, by default, when it has more than 10,000 rows: it holds",
        "back a random tenth and stops when that tenth stops improving. Each arm's model stops at",
        "its own round. Below 10,000 rows nothing stops early and the two columns must agree.",
        "Since D-077 the benchmark classifier is fitted with stopping off; the 'automatic'",
        "columns show what the library default would give.",
    ]
    return "\n".join(out)


# --- the figure ---------------------------------------------------------------------

#: One marker per setting, so the two Hillstrom campaigns can be told apart.
MARKERS = {"Hillstrom (mens)": "o", "Hillstrom (womens)": "s", "Criteo": "D", "Lenta": "^",
           "SubSim (fitted)": "P"}

PANELS = ((f"{HEADLINE}_pearson_prob", "probability scale"),
          (f"{HEADLINE}_pearson_logodds", "log-odds scale"))


def figure(frame: pd.DataFrame, out: Path | None = None) -> Path:
    """What the uplift model gains, against the correlation on each scale.

    Two panels with the same vertical axis. Only the scale the correlation is taken on
    differs between them, so a pattern present in one and absent in the other belongs to
    the scale. Every point is the mean over the splits, with the spread across splits
    drawn on both axes; no point is an oracle.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from retainiq.benchmarks.spectrum import COLOURS, FIG_DIR

    s = summarise(frame).set_index(["setting", "measure"])
    settings = list(dict.fromkeys(frame["setting"]))
    domain = frame.drop_duplicates("setting").set_index("setting")["domain"]
    splits = int(frame.groupby("setting").size().max())

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 6.6), sharey=True)
    for ax, (measure, scale) in zip(axes, PANELS, strict=True):
        ax.axhline(0, color="#263238", lw=1.3, zorder=2)
        ax.axvline(0, color="#90A4AE", lw=1.0, ls=":", zorder=1)
        for name in settings:
            x, y = s.loc[(name, measure)], s.loc[(name, "gain_per_1000")]
            colour = COLOURS.get(domain[name], "#455A64")
            ax.errorbar(
                x["mean"], y["mean"],
                xerr=[[x["mean"] - x["low"]], [x["high"] - x["mean"]]],
                yerr=[[y["mean"] - y["low"]], [y["high"] - y["mean"]]],
                fmt=MARKERS.get(name, "o"), ms=9, color=colour, ecolor=colour,
                elinewidth=1.3, capsize=3, markeredgecolor="white", markeredgewidth=0.8,
                zorder=5, label=name,
            )
        ax.set_xlim(-0.9, 0.9)
        ax.set_title(f"correlation taken on the {scale}", fontsize=11.5)
        ax.set_xlabel("corr( estimated benefit , estimated risk if left alone ),  Pearson",
                      fontsize=10)
        ax.grid(alpha=0.25, lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Extra good outcomes per 1,000 customers from ranking\n"
                       "by uplift instead of by the outcome model (top 30%)", fontsize=10)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=len(settings), frameon=False,
               fontsize=10, bbox_to_anchor=(0.5, 0.925))
    fig.suptitle("What an uplift model gains over an outcome model, against the "
                 "risk\u2013lift correlation", fontsize=13, y=0.985)
    fig.text(
        0.5, 0.012,
        f"Each point is the mean over {splits} random splits of one randomised trial; bars "
        "run from the 2.5th to the 97.5th percentile across splits.\n"
        "All points are fitted models, measured the same way. Left and right show the same "
        "gains; only the scale of the correlation differs,\n"
        "so a pattern on one side and not the other belongs to the scale. SubSim is a trial "
        f"of {SIM_CUSTOMERS:,} simulated customers whose negative\n"
        "correlation is configured, not observed. The correlation is the one varied in "
        "Ascarza (2018, Web Appendix A3.4).\n"
        "Risk is fitted on control customers only, on customers the effect model never saw; "
        "each model sees half the training data or less (D-077).",
        ha="center", va="bottom", fontsize=8.8, color="#455A64", linespacing=1.45,
    )
    fig.tight_layout(rect=(0, 0.155, 1, 0.9))
    out = out or (FIG_DIR / "fig07_correlation_checked.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


SIM = Setting("SubSim (fitted)", "subscription retention", benefit_sign=-1)

ORACLE_NOTE = (
    "Row 'SubSim (fitted)' is what fitted models gain, in outcomes, on a trial drawn from the\n"
    "simulator. `python -m retainiq.benchmarks.spectrum` prints what an oracle gains there, in\n"
    "money net of the offer. The two are in different units and their percentages are not to\n"
    "be compared (D-074)."
)


def _loaders() -> list:
    """Each public experiment and how to load it. The simulator is handled apart."""
    from retainiq.benchmarks.datasets import load_criteo, load_hillstrom, load_lenta

    return [
        (Setting("Hillstrom (mens)", "promotional email"), lambda: load_hillstrom("mens")),
        (Setting("Criteo", "advertising"), lambda: load_criteo(sample_rows=1_500_000, seed=0)),
        (Setting("Hillstrom (womens)", "promotional email"), lambda: load_hillstrom("womens")),
        (Setting("Lenta", "retail promotion"), load_lenta),
    ]


def collect(splits: int = SPLITS, include: tuple[str, ...] = ()) -> tuple[pd.DataFrame, dict]:
    """Every setting. Loads the public datasets; the simulator needs none."""
    frames = [run(load(), setting, splits) for setting, load in _loaders()
              if not include or setting.name in include]

    truth: dict[str, float] = {}
    if not include or SIM.name in include:
        rct, facts = subsim_trial()
        frames.append(run(rct, SIM, splits))
        truth = true_correlations(facts)
    return pd.concat(frames, ignore_index=True), truth


def collect_stopping(splits: int = SPLITS,
                     include: tuple[str, ...] = STOPPING_SETTINGS) -> pd.DataFrame:
    """The diagnostic, on the settings where a model crosses the 10,000-row line."""
    frames = [stopping_diagnostic(load(), setting, splits) for setting, load in _loaders()
              if setting.name in include]
    if SIM.name in include:
        frames.append(stopping_diagnostic(subsim_trial()[0], SIM, splits))
    return pd.concat(frames, ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--splits", type=int, default=SPLITS)
    ap.add_argument("--only", action="append", default=[], metavar="SETTING",
                    help="run one setting by name; repeat for several")
    ap.add_argument("--save", type=Path, metavar="CSV", help="also write every split's row")
    ap.add_argument("--from-splits", type=Path, metavar="CSV",
                    help="print and draw from a file written by --save instead of running. "
                         "The output says it was re-read, not re-run.")
    ap.add_argument("--no-figure", action="store_true",
                    help="print the tables only; do not redraw the figure")
    ap.add_argument("--stopping-diagnostic", action="store_true",
                    help="exploratory (D-076): measure each split with the classifier's "
                         "early stopping automatic and off, on the settings where a model "
                         "crosses 10,000 rows. About ten minutes. Draws no figure.")
    args = ap.parse_args(argv)

    if args.stopping_diagnostic:
        frame = collect_stopping(args.splits, tuple(args.only) or STOPPING_SETTINGS)
        if args.save:
            args.save.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(args.save, index=False)
        print(report_stopping(frame))
        return 0

    source = None
    if args.from_splits:
        frame = pd.read_csv(args.from_splits)
        source = args.from_splits.name
        # The truth is not in the file. It is a property of the simulator, not of any
        # split, and it is recomputed rather than trusted from a saved copy.
        has_sim = (frame["setting"] == SIM.name).any()
        truth = true_correlations(subsim_trial()[1]) if has_sim else {}
    else:
        frame, truth = collect(args.splits, tuple(args.only))
        if args.save:
            args.save.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(args.save, index=False)
    print(report(frame, truth or None, ORACLE_NOTE if truth else None, source))

    if args.no_figure:
        return 0
    if args.only:
        print("\nFigure not drawn: it shows every setting, and only some were run.")
        return 0
    # Drawn from the same splits that printed the tables, so the two cannot disagree.
    print()
    print(figure(frame))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
