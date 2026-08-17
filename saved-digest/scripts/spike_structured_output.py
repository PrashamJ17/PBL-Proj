#!/usr/bin/env python3
"""Settle one open API question, empirically: can `output_config.format` be
combined with the web search tool?

Why this exists. Pass B needs its verdict back as structured JSON *and* needs web
search. Web search always emits citations, and structured outputs are documented
as incompatible with citations — but that documented conflict concerns
`citations: {enabled: true}` on *document* blocks, and the combination Pass B uses
is not addressed either way in the docs. Rather than design around a guess,
`triage/verify.py` supports both channels and probes for the answer at runtime.

This script runs that probe on its own so you can see the answer directly, and
records it in the database so the first real `verify` run does not have to.

    export ANTHROPIC_API_KEY=sk-ant-...
    python3 scripts/spike_structured_output.py

Cost: two tiny requests, at most one web search. Well under a cent.

If it reports UNSUPPORTED, nothing is broken: Pass B uses a `strict` tool call to
carry the verdict instead. The only difference is which channel the JSON arrives
on, and both are tested.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saveddigest.config import Config  # noqa: E402
from saveddigest.store import Store  # noqa: E402
from saveddigest.triage import verify  # noqa: E402


def main() -> int:
    config = Config.from_env()
    if not config.anthropic_api_key:
        print("ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return 2

    try:
        import anthropic
    except ImportError:
        print("pip install anthropic", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    print(f"model: {config.model}")
    print(f"web search tool: {verify.WEB_SEARCH_TOOL_TYPE}")
    print("\n[1/2] probing output_config.format alongside web search ...")

    try:
        supported = verify.probe_structured_output_support(client, config.model)
    except Exception as exc:  # noqa: BLE001 - the point is to report it verbatim
        print(f"\nprobe failed with a non-400 error: {type(exc).__name__}: {exc}")
        print(
            "That is not an answer to the question — it is an auth, network or "
            "model-availability problem. Fix it and re-run; the probe deliberately "
            "refuses to record 'unsupported' on an unrelated failure."
        )
        return 1

    channel = "output_config.format" if supported else "strict tool call"
    print(f"    -> {'SUPPORTED' if supported else 'UNSUPPORTED'}; Pass B will use: {channel}")

    print("\n[2/2] end-to-end verdict on a deliberately stale claim ...")
    print("    claim: 'Django 4.2 is the current LTS release'")

    from saveddigest.store import Item, Platform

    probe_item = Item(
        id=0,
        platform=Platform.YOUTUBE,
        external_id="spike000000",
        url="https://www.youtube.com/watch?v=spike000000",
        source="spike",
        title="Deploying Django (2023)",
        published_at="2023-05-01T00:00:00Z",
    )
    probe_summary = {
        "staleness_class": "version_bound",
        "staleness_reason": "Pinned to a specific Django LTS release.",
        "detailed_summary": (
            "A Django deployment walkthrough that pins Django 4.2 as the current LTS."
        ),
        "tldr": "Deploying Django 4.2.",
        "tools_mentioned": ["Django 4.2"],
        "claims_to_verify": ["Django 4.2 is the current LTS release"],
        "expiry_date": None,
    }

    from datetime import UTC, datetime

    verdict = verify.verify_one_sync(
        client,
        probe_item,
        probe_summary,
        config=config,
        today=datetime.now(UTC).date().isoformat(),
        structured_output=supported,
    )

    print()
    print(json.dumps(verdict, indent=2)[:3000])

    print("\n--- read this ---")
    value = verdict.get("verdict")
    if value == "unverified":
        print(
            "Verdict came back UNVERIFIED. Reason: "
            f"{verdict.get('unverified_reason')}\n"
            "That is the honest failure mode, not a crash. If it says no search was "
            "performed, the model answered from memory and the guard caught it."
        )
    else:
        print(f"Verdict: {value} (confidence {verdict.get('confidence')})")
        print(f"Searches used: {verdict.get('searches_used')}")
        if verdict.get("superseded_by"):
            print(f"Points at: {verdict['superseded_by']}")
        print("Sources:")
        for source in verdict.get("sources") or []:
            print(f"  - {source['url']}")
        print(
            "\nCheck those sources by hand. If the verdict is right and the sources "
            "support it, Pass B is working."
        )

    config.ensure_dirs()
    with Store(config.db_path) as store:
        store.set_meta(
            verify.CAPABILITY_KEY,
            verify.CAPABILITY_SUPPORTED if supported else verify.CAPABILITY_UNSUPPORTED,
        )
    print(f"\nCached the channel choice in {config.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
