"""Draw the paper's Figures 1, 3 and 4 with plain labels.

    python papers/draw_paper_figures.py                       # Figures 1 and 3, about two minutes
    python papers/draw_paper_figures.py --from-splits FILE    # and Figure 4, from saved splits

The repository's own figures carry a headline and the project's names for things. A figure
in a journal carries neither: its caption says what it shows. Each figure here is drawn by
the function that draws the repository's version, so the data and the marks are the same.
Only the wording is changed, just before the file is written, and a label that is no longer
found stops the run rather than being skipped.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.text import Text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retainiq.benchmarks.spectrum_checks import figure as correlation_figure  # noqa: E402
from retainiq.experiments.figures import figure_1  # noqa: E402
from retainiq.experiments.holdout_figure import figure_6  # noqa: E402

OUT = Path(__file__).resolve().parent / "figures" / "paper"

#: New wording for a label: the text itself, or a function of the old text where the
#: label carries a number that the figure code computed.
Wording = dict[str, "str | Callable[[str], str]"]


@contextmanager
def edited(edit: Callable[[Figure], None]) -> Iterator[None]:
    """Apply `edit` to every figure saved inside the block, just before it is written."""
    original = Figure.savefig

    def savefig(fig: Figure, *args, **kwargs):
        edit(fig)
        return original(fig, *args, **kwargs)

    Figure.savefig = savefig
    try:
        yield
    finally:
        Figure.savefig = original


def reword(fig: Figure, wording: Wording) -> None:
    """Replace every label whose text starts with a key of `wording`. The longest key wins."""
    missing = set(wording)
    for artist in fig.findobj(Text):
        text = artist.get_text()
        keys = [k for k in wording if text.startswith(k)]
        if not keys:
            continue
        key = max(keys, key=len)
        new = wording[key]
        artist.set_text(new(text) if callable(new) else new)
        missing.discard(key)
    if missing:
        raise SystemExit(f"labels not found, the figure code has changed: {sorted(missing)}")


def policy_value(fig: Figure) -> None:
    fig.suptitle("")
    reword(fig, {
        "Churn-score targeting destroys value":
            "Expected value against the share of customers treated\n"
            "(mean of six simulated businesses; bands: one standard deviation)",
        "Why: the customers a churn model ranks highest":
            "Make-up of each tenth of predicted churn risk\n(one simulated business)",
        "Retention budget (% of customer base treated)":
            "Share of eligible customers treated (%)",
        "Oracle uplift (upper bound)": "By true effect (upper bound)",
        "Random targeting": "At random",
        "Churn-score targeting": "By churn score",
        "Persuadable (worth paying for)": "Persuadable",
        "Sure Thing (wasted spend)": "Sure thing",
        "Lost Cause (unreachable)": "Lost cause",
        "Sleeping Dog (harmed by contact)": "Sleeping dog",
    })


def measurement_floor(fig: Figure) -> None:
    fig.suptitle("")
    _, right = fig.axes
    right.set_xlabel("Customers eligible for the offer")
    reword(fig, {
        "The estimator is unbiased": "Measured lift with its 95% interval, against the true effect",
        "The measurement floor": "Minimum detectable effect, against the effect delivered",
        "effect actually delivered": lambda text: text.replace("actually ", ""),
        "detecting this effect needs":
            lambda text: (text.replace("this effect", "the effect delivered")
                          .replace("customers", "eligible customers")),
    })


def correlation(fig: Figure) -> None:
    fig.suptitle("")
    reword(fig, {
        "Each point is the mean over": "",
        "Hillstrom (mens)": "Hillstrom, men's e-mail",
        "Hillstrom (womens)": "Hillstrom, women's e-mail",
        "Criteo": "Criteo (advertising)",
        "Lenta": "Lenta (retail promotion)",
        "SubSim (fitted)": "Simulated retention trial",
    })


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from-splits", type=Path, metavar="CSV",
                    help="splits saved by `python -m retainiq.benchmarks.spectrum_checks --save`; "
                         "without it Figure 4 is not drawn")
    args = ap.parse_args(argv)

    with edited(policy_value):
        print(figure_1(out=OUT / "fig1_policy_value.png"))
    with edited(measurement_floor):
        print(figure_6(out=OUT / "fig3_measurement_floor.png"))
    if args.from_splits:
        with edited(correlation):
            print(correlation_figure(pd.read_csv(args.from_splits),
                                     out=OUT / "fig4_correlation.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
