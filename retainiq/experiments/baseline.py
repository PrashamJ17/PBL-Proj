"""Abstention against Lemmens & Gupta's (2020) target-size rule, on the same pilots.

The abstention rule decides how many customers to treat from a posterior: treat a
customer only when the probability of making money on them clears a bar. Lemmens & Gupta
decide it from held-out data: rank a validation sample, estimate the profit of every
campaign size from the randomised outcomes, and take the best. Theirs is the nearest
published rival and until now it had not been run beside ours (D-068).

**Both rules get the same pilot and nothing else.** Theirs has to cut the pilot into a
part to fit on and a part to choose the size on. Ours fits on all of it. That difference
is the comparison.

The design, the configurations and six predictions were committed before this module
existed (`docs/PREREG-checks-and-baseline.md`). Results are in D-075.

Every policy is scored on customers it never saw, against the simulator's true potential
outcomes, as money relative to doing nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from retainiq.benchmarks.small_n import exact_interval
from retainiq.experiments.abstention import FEATURES, Pilot, _realised, draw_pilot, run_once
from retainiq.models.uplift import HierarchicalCATE
from retainiq.policy.baseline_lg import (
    MIN_ARM,
    FirstStage,
    ProfitLossBoosting,
    choose_fraction,
    top_fraction,
)
from retainiq.policy.economics import benefit_posterior

#: Fixed in the pre-registration.
SIZES = (250, 500, 1000, 2000, 4000)
DRAWS = 100
BUDGET = 0.30
ALPHA = 0.30

OURS = "abstention_money"
RANKING = "top_k_money"


@dataclass(frozen=True)
class Config:
    """One way of running their method."""

    name: str
    estimator: str
    """`profit_loss` (their estimator), `uplift` (their first stage alone), or `bayes`
    (this project's posterior mean, ranked and cut by their rule)."""
    calibration_share: float
    refit: bool
    """Refit on the whole pilot once the size is chosen. Their protocol does not."""
    min_arm: int = MIN_ARM
    """Fewest treated, and fewest control, customers a campaign size must contain on the
    validation sample to be considered."""


PRIMARY = Config("lg_primary", "profit_loss", 0.5, False)
CONFIGS = (
    PRIMARY,
    Config("lg_cutoff_bayes", "bayes", 0.5, False),
    Config("lg_cutoff_uplift", "uplift", 0.5, False),
    Config("lg_best_case", "profit_loss", 2 / 3, True),
)

#: Not pre-registered. Their paper does not say how the boosting step is taken, and the
#: choice changes the ranking among customers the offer helps (see `ProfitLossBoosting`).
#: The primary configuration uses the variant that matches what their paper says the loss
#: does; this runs the other, so the comparison can be shown not to hang on that choice.
#:
#: `lg_no_floor` was added AFTER the pre-registered results were read. The floor of ten
#: customers per arm was fixed in advance as a guard in their favour, and at the smallest
#: pilots it turned out to leave their rule no campaign size it was allowed to choose:
#: with the 30% budget cap, a validation sample under 67 customers cannot hold ten of
#: each arm in its top 30%. So at n = 250 the pre-registered configurations treat nobody
#: by construction. This runs their rule as published, needing one customer in each arm,
#: to show what it does where the floor stops it. It is exploratory and is never the
#: figure quoted as theirs.
SENSITIVITY = (
    Config("lg_newton_step", "profit_loss_newton", 0.5, False),
    Config("lg_no_floor", "profit_loss", 0.5, False, min_arm=1),
)

DESCRIPTION = {
    OURS: "abstention: Bayesian posterior, treat if P(money > 0) clears the bar",
    RANKING: "ranking: same posterior, fill the budget",
    "lg_primary": "L&G as published: profit-based loss, validated size, equal halves",
    "lg_cutoff_bayes": "our estimator with their validated size (isolates the stopping rule)",
    "lg_cutoff_uplift": "their first stage alone with their validated size (isolates their loss)",
    "lg_best_case": "L&G best case: 2:1 split, refitted on the whole pilot",
    "lg_newton_step": "L&G as published, other boosting step (sensitivity, not pre-registered)",
    "lg_no_floor": "L&G with no minimum per arm (added after the results, not pre-registered)",
}


def _scorer(estimator: str, rows: pd.DataFrame, treated: np.ndarray, churned: np.ndarray,
            seed: int) -> Callable[[pd.DataFrame], np.ndarray]:
    """Fit one estimator on pilot rows and return a function that ranks customers.

    Only what a business would hold is read: the features, each customer's value, the
    cost of the offer, who was treated, and the outcome observed for that arm.
    """
    X, value, cost = rows[FEATURES], rows["clv"].to_numpy(), rows["offer_cost"].to_numpy()

    if estimator == "bayes":
        model = HierarchicalCATE().fit(X, treated, churned)
        return lambda f: benefit_posterior(
            model, f[FEATURES], f["clv"].to_numpy(), f["offer_cost"].to_numpy(),
            n_samples=500, seed=seed,
        ).mean

    first = FirstStage.fit(X, treated, churned, seed)
    if estimator == "uplift":
        return lambda f: first.profit_lift(f[FEATURES], f["clv"].to_numpy(),
                                           f["offer_cost"].to_numpy())
    if estimator in ("profit_loss", "profit_loss_newton"):
        second = ProfitLossBoosting(seed=seed, newton=estimator.endswith("newton"))
        second.fit(X, first.profit_lift(X, value, cost))
        return lambda f: second.score(f[FEATURES])
    raise ValueError(f"unknown estimator {estimator!r}")


def validation_size(n_pilot: int, config: Config) -> int:
    """How many pilot customers their rule holds back to choose the campaign size on."""
    return n_pilot - int(round(config.calibration_share * n_pilot))


def can_act(n_pilot: int, config: Config, budget: float = BUDGET) -> bool:
    """Whether any campaign size at all is open to their rule on a pilot of this size.

    The largest campaign the budget allows on the validation sample has to hold the
    minimum number of treated customers and the same number of controls. When it cannot,
    the rule treats nobody whatever the data say, and that outcome is the design's and
    not the method's.
    """
    return int(round(budget * validation_size(n_pilot, config))) >= 2 * config.min_arm


def lg_decision(pilot: Pilot, config: Config, seed: int,
                budget: float = BUDGET) -> tuple[np.ndarray, float]:
    """Their method on one pilot: who to treat among the test customers, and the share.

    Returns a mask over `pilot.test` and the fraction their rule chose. When the
    calibration part cannot support a model at all, the decision is to treat nobody,
    which is what a careful analyst would do with it.
    """
    train, nobody = pilot.train, np.zeros(len(pilot.test), dtype=bool)
    order = np.random.default_rng(990_001 + seed).permutation(len(train))
    cut = len(train) - validation_size(len(train), config)
    cal, val = order[:cut], order[cut:]

    t_cal, y_cal = pilot.treated[cal], pilot.churned[cal]
    if len(np.unique(t_cal)) < 2 or len(np.unique(y_cal)) < 2 or len(val) == 0:
        return nobody, 0.0

    score = _scorer(config.estimator, train.iloc[cal], t_cal, y_cal, seed)
    held = train.iloc[val]
    fraction, _ = choose_fraction(
        score(held), pilot.treated[val], pilot.churned[val],
        held["clv"].to_numpy(), held["offer_cost"].to_numpy(), max_fraction=budget,
        min_arm=config.min_arm,
    )
    if fraction == 0.0:
        return nobody, 0.0
    if config.refit:
        score = _scorer(config.estimator, train, pilot.treated, pilot.churned, seed)
    return top_fraction(score(pilot.test), fraction), fraction


def run_draw(n_customers: int, seed: int) -> list[dict]:
    """One business: this project's two policies and every configuration of theirs."""
    ours = run_once(n_customers, seed, alpha=ALPHA, budget=BUDGET)
    pilot = draw_pilot(n_customers, seed)
    if not ours or pilot is None:
        return []

    rows = [
        {"policy": name, "value": ours[name].realised_value, "n_treated": ours[name].n_treated,
         "can_act": True}
        for name in (OURS, RANKING)
    ]
    for config in (*CONFIGS, *SENSITIVITY):
        mask, _ = lg_decision(pilot, config, seed)
        r = _realised(pilot.test, mask)
        rows.append({"policy": config.name, "value": r.realised_value, "n_treated": r.n_treated,
                     "can_act": can_act(len(pilot.train), config)})
    return [{"n_customers": n_customers, "seed": seed, "n_eligible": len(pilot.test), **r}
            for r in rows]


def _one_thread_draw(job: tuple[int, int]) -> list[dict]:
    """A draw with every numerical library held to one thread.

    scikit-learn sums gradients across threads, and the order of a floating-point sum
    depends on how many threads share it. Holding every draw to one thread makes a draw
    give the same numbers on a laptop and on a server, and whether draws run one after
    another or side by side.
    """
    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=1):
        return run_draw(*job)


def sweep(sizes: tuple[int, ...] = SIZES, draws: int = DRAWS, jobs: int = 1,
          resume: Path | None = None) -> pd.DataFrame:
    """Every draw at every size.

    `jobs` runs draws side by side; it changes how long the sweep takes and nothing
    else. `resume` names a CSV that each finished draw is appended to, and whose draws
    are skipped when the sweep is started again. It is only meaningful if the code has
    not changed since the file was begun, and nothing here can check that.
    """
    todo = [(n, 1000 + s) for n in sizes for s in range(draws)]
    done = pd.DataFrame()
    if resume is not None and resume.exists() and resume.stat().st_size:
        done = pd.read_csv(resume)
        seen = set(zip(done["n_customers"], done["seed"], strict=True))
        todo = [job for job in todo if job not in seen]

    rows: list[dict] = []

    def keep(result: list[dict]) -> None:
        rows.extend(result)
        if resume is not None and result:
            resume.parent.mkdir(parents=True, exist_ok=True)
            fresh = not resume.exists() or not resume.stat().st_size
            pd.DataFrame(result).to_csv(resume, mode="a", header=fresh, index=False)

    if jobs > 1 and len(todo) > 1:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor

        # Fresh interpreters on every platform. Forking a process that has already used
        # a threaded numerical library can leave the child waiting on a lock it copied.
        fresh = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=jobs, mp_context=fresh) as pool:
            for result in pool.map(_one_thread_draw, todo):
                keep(result)
    else:
        for job in todo:
            keep(_one_thread_draw(job))

    frame = pd.concat([done, pd.DataFrame(rows)], ignore_index=True)
    if frame.empty:
        return frame
    wanted = {n: i for i, n in enumerate(sizes)}
    frame = frame[frame["n_customers"].isin(wanted) & (frame["seed"] < 1000 + draws)]
    return frame.sort_values(["n_customers", "seed"], kind="stable").reset_index(drop=True)


# --- summarising ----------------------------------------------------------------


def compare(frame: pd.DataFrame, a: str, b: str) -> dict[str, float]:
    """`a` against `b` on the same draws: wins, ties and losses, counted separately.

    A draw on which both treat nobody is a tie. Counting it for either side would invent
    a result, so the win rate is taken over the draws on which the two differ.
    """
    wide = frame.pivot(index=["n_customers", "seed"], columns="policy", values="value")
    if a not in wide or b not in wide:
        return {"wins": 0, "ties": 0, "losses": 0, "rate": float("nan"),
                "low": float("nan"), "high": float("nan"), "mean_gap": float("nan")}
    d = (wide[a] - wide[b]).dropna()
    wins, losses, ties = int((d > 0).sum()), int((d < 0).sum()), int((d == 0).sum())
    decided = wins + losses
    low, high = exact_interval(wins, decided) if decided else (float("nan"), float("nan"))
    return {"wins": wins, "ties": ties, "losses": losses,
            "rate": wins / decided if decided else float("nan"),
            "low": low, "high": high, "mean_gap": float(d.mean()) if len(d) else float("nan")}


def by_policy(frame: pd.DataFrame) -> pd.DataFrame:
    """Per size and policy: mean money, how often nobody is treated, how often it pays."""
    rows = []
    for (n, policy), g in frame.groupby(["n_customers", "policy"], sort=True):
        beat = int((g["value"] > 0).sum())
        low, high = exact_interval(beat, len(g))
        rows.append({
            "n_customers": n, "policy": policy, "draws": len(g),
            "mean_value": g["value"].mean(), "mean_treated": g["n_treated"].mean(),
            "treats_nobody": (g["n_treated"] == 0).mean(),
            "could_act": g["can_act"].astype(bool).mean() if "can_act" in g else 1.0,
            "beats_nothing": beat / len(g), "beats_low": low, "beats_high": high,
        })
    return pd.DataFrame(rows)


def _pct(x: float) -> str:
    return "  n/a" if np.isnan(x) else f"{x:.0%}"


def report(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No usable draws."
    table = by_policy(frame)
    order = [OURS, RANKING, *[c.name for c in (*CONFIGS, *SENSITIVITY)]]
    width = 112
    out = [
        "ABSTENTION AGAINST LEMMENS & GUPTA (2020) -- same pilots, scored on unseen customers",
        "realised money relative to doing nothing; ground truth withheld from every policy",
        "=" * width,
    ]
    for name in order:
        out.append(f"  {name:<18} {DESCRIPTION[name]}")

    for n in sorted(table["n_customers"].unique()):
        at = table[table["n_customers"] == n].set_index("policy")
        out += ["", f"n = {int(n):,}   ({int(at['draws'].max())} draws)",
                f"  {'policy':<18}{'mean money':>12}{'treated':>10}{'treats nobody':>16}"
                f"{'beats doing nothing':>32}",
                "  " + "-" * (width - 2)]
        for name in order:
            if name not in at.index:
                continue
            r = at.loc[name]
            barred = r.could_act == 0
            out.append(
                f"  {name:<18}{r.mean_value:>12,.0f}{r.mean_treated:>10.1f}"
                f"{f'{r.treats_nobody:.0%}':>16}"
                f"{f'{r.beats_nothing:.0%} [{r.beats_low:.0%}, {r.beats_high:.0%}]':>32}"
                + ("   could not act *" if barred else "")
            )

    out += ["", "ABSTENTION AGAINST EACH, draw by draw",
            f"  {'against':<18}{'size':>8}{'ahead':>8}{'tied':>7}{'behind':>8}"
            f"{'ahead, of those that differ':>34}{'mean gap':>12}",
            "  " + "-" * (width - 2)]
    for name in order[1:]:
        for label, part in [("all", frame), *[(f"{int(n):,}", frame[frame.n_customers == n])
                                              for n in sorted(frame["n_customers"].unique())]]:
            c = compare(part, OURS, name)
            rate = ("n/a" if np.isnan(c["rate"]) else
                    f"{c['rate']:.0%} [{c['low']:.0%}, {c['high']:.0%}]")
            out.append(f"  {name if label == 'all' else '':<18}{label:>8}{c['wins']:>8}"
                       f"{c['ties']:>7}{c['losses']:>8}{rate:>34}{c['mean_gap']:>12,.0f}")

    c = compare(frame, "lg_primary", "lg_cutoff_uplift")
    out += ["", "THEIR LOSS AGAINST THEIR FIRST STAGE ALONE (both with the validated size)",
            f"  profit-based loss ahead on {c['wins']}, tied {c['ties']}, behind {c['losses']}; "
            f"ahead on {_pct(c['rate'])} of those that differ "
            f"[{_pct(c['low'])}, {_pct(c['high'])}]",
            "", "-" * width,
            "treats nobody = share of draws on which the policy contacted no one.",
            "* could not act: the pilot was too small for the budget's largest campaign to hold",
            f"  {MIN_ARM} treated and {MIN_ARM} control customers on the validation sample, so no",
            "  campaign size was open to the rule. It treats nobody there by construction, not by",
            "  choice.",
            "A tie is a draw on which the two policies earned exactly the same, almost always",
            "because both treated nobody. Intervals are exact 95% intervals."]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--draws", type=int, default=DRAWS,
                    help=f"draws per size (default {DRAWS}, as pre-registered)")
    ap.add_argument("--jobs", type=int, default=1,
                    help="draws to run side by side; changes the time taken, not the numbers")
    ap.add_argument("--save", type=Path, metavar="CSV", help="also write every draw's rows")
    ap.add_argument("--resume", type=Path, metavar="CSV",
                    help="append each finished draw to CSV and skip the draws already in it")
    ap.add_argument("--from-draws", type=Path, metavar="CSV",
                    help="print the report for draws saved earlier, without running anything")
    args = ap.parse_args(argv)

    if args.from_draws:
        print(report(pd.read_csv(args.from_draws)))
        return 0
    frame = sweep(draws=args.draws, jobs=args.jobs, resume=args.resume)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.save, index=False)
    print(report(frame))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
