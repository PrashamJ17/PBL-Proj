"""Command line: run a Churn Autopsy against a real business's export.

Phase 2's gate is a paying client, and the delivery motion described in D-040 is a
fixed-fee diagnostic: the founder sends CSVs, we send back a report. Until now there was
no command that did that -- the Autopsy was reachable only from Python, against
simulator output. That gap, not the modelling, was what stood between the code and
prospect number one.

Two subcommands, and the order is not optional:

    python -m keel.cli preflight --customers c.csv --subscriptions s.csv
    python -m keel.cli autopsy   --customers c.csv --subscriptions s.csv --name "Acme"

`preflight` refuses to be skipped by `autopsy`: the report command runs the same checks
and stops on a blocker. The reason is in `preflight.py` -- the way this engagement fails
is not a crash, it is a confident report built on a misread file, and the person who
finds that mistake is the prospect.

Deliberately stdlib-only (argparse), so the diagnostic runs anywhere pandas does and
adds no dependency to a project whose Phase 0 rule is numpy/pandas/scipy (invariant 7).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from keel.ingest.csv_ingest import IngestError, load
from keel.ingest.preflight import preflight, render_preflight


def _load(args) -> tuple:
    defaults = {}
    if args.interval:
        defaults["interval"] = args.interval
    assumptions: list[str] = []
    ds = load(
        customers=args.customers,
        subscriptions=args.subscriptions,
        invoices=args.invoices,
        events=args.events,
        tickets=args.tickets,
        defaults=defaults or None,
        assumptions=assumptions,
    )
    if args.divide_amounts_by and args.divide_amounts_by != 1:
        ds.subscriptions["mrr"] = ds.subscriptions["mrr"] / args.divide_amounts_by
        if not ds.invoices.empty:
            ds.invoices["amount"] = ds.invoices["amount"] / args.divide_amounts_by
        assumptions.append(
            f"amounts divided by {args.divide_amounts_by} at your instruction "
            f"(minor units -> major units)"
        )
    return ds, assumptions


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--customers", required=True, help="CSV of customers")
    p.add_argument("--subscriptions", required=True, help="CSV of subscriptions")
    p.add_argument("--invoices", help="CSV of invoices or charges (enables dunning analysis)")
    p.add_argument("--events", help="CSV of product events")
    p.add_argument("--tickets", help="CSV of support tickets")
    p.add_argument("--interval", choices=["day", "week", "month", "year"],
                   help="billing interval, when the export does not carry one. "
                        "Getting this wrong scales every revenue figure.")
    p.add_argument("--divide-amounts-by", type=float, default=1.0, metavar="N",
                   help="convert minor units to major (use 100 for Stripe cents). "
                        "Preflight will tell you if this is needed.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="keel",
        description="Churn Autopsy for subscription businesses.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("preflight", help="check an export is safe to compute from")
    _common(pf)

    ap = sub.add_parser("autopsy", help="produce the Churn Autopsy report")
    _common(ap)
    ap.add_argument("--name", default="Your business", help="business name for the report")
    ap.add_argument("--out", default="churn_autopsy.html", help="output HTML path")
    ap.add_argument("--force", action="store_true",
                    help="generate even if preflight found a blocker. Recorded in the "
                         "output; use only when you know why the check fired.")

    args = parser.parse_args(argv)

    try:
        ds, assumptions = _load(args)
    except (IngestError, FileNotFoundError) as e:
        print(f"could not read the export: {e}", file=sys.stderr)
        return 2

    report = preflight(ds, assumptions)
    print(render_preflight(report))

    if args.cmd == "preflight":
        return 1 if report.blocked else 0

    if report.blocked and not args.force:
        print(
            "\nSTOPPED. Preflight found something that would make the report wrong.\n"
            "Fix it, or re-run with --force if you understand why the check fired.",
            file=sys.stderr,
        )
        return 1

    from keel.report.render import generate

    out = generate(ds, business_name=args.name, out=Path(args.out))
    print(f"\nwrote {out.resolve()}")
    if report.assumptions:
        print("Before sending this, confirm the assumptions listed above with the client.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
