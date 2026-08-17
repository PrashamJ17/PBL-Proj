"""Command line entry point.

argparse only — no click, no typer. This runs from a cron line on a laptop, and a
dependency that can break an unattended weekly job is not worth the nicer help
text.

Stages are separate subcommands as well as being chained by `run`, because each
one costs something different: `sync` is free, `enrich` is slow, `summarise` and
`verify` cost money. Being able to run them one at a time is what makes it safe
to try this on a large backlog.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saveddigest import __version__
from saveddigest.config import Config
from saveddigest.store import (
    NEEDS_VERIFICATION,
    Item,
    Liveness,
    Platform,
    Status,
    Store,
    utcnow_iso,
)

log = logging.getLogger("saveddigest")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _anthropic_client(config: Config) -> Any:
    """Build an Anthropic client, or exit with an actionable message."""
    try:
        import anthropic
    except ImportError:
        raise SystemExit(
            "The anthropic package is missing. Install it with:\n"
            "    pip install anthropic"
        ) from None
    if not config.anthropic_api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Export it, or put it in your .env:\n"
            "    export ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic(api_key=config.anthropic_api_key)


def _todoist_token(config: Config) -> str:
    if not config.todoist_token:
        raise SystemExit(
            "TODOIST_API_TOKEN is not set. Get one from Todoist Settings -> "
            "Integrations -> Developer, then:\n"
            "    export TODOIST_API_TOKEN=..."
        )
    return config.todoist_token


def _today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


# --------------------------------------------------------------------------
# init-auth
# --------------------------------------------------------------------------
def cmd_init_auth(args: argparse.Namespace, config: Config) -> int:
    from saveddigest.google_auth import AuthError, load_credentials

    config.ensure_dirs()
    try:
        creds = load_credentials(config, allow_interactive=True)
    except AuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    token = config.google_token_path
    mode = oct(token.stat().st_mode & 0o777) if token.exists() else "?"
    print(f"Google credentials stored at {token} (mode {mode})")
    print(f"Refresh token present: {bool(getattr(creds, 'refresh_token', None))}")
    print("\nScopes granted:")
    for scope in getattr(creds, "scopes", []) or []:
        print(f"  - {scope}")
    return EXIT_OK


# --------------------------------------------------------------------------
# sync
# --------------------------------------------------------------------------
def cmd_sync(args: argparse.Namespace, config: Config) -> int:
    config.ensure_dirs()
    collected: list[Item] = []

    if not args.instagram_only:
        collected.extend(_sync_youtube(args, config))
    if not args.youtube_only:
        collected.extend(_sync_todoist(args, config))

    if args.dry_run:
        print(f"\n{len(collected)} item(s) found (dry run, nothing written)")
        for item in collected[:40]:
            print(f"  [{item.platform}] {item.external_id}  {item.title or item.url}")
        if len(collected) > 40:
            print(f"  ... and {len(collected) - 40} more")
        return EXIT_OK

    created = 0
    with Store(config.db_path) as store:
        for item in collected:
            _, was_created = store.upsert(item)
            created += int(was_created)
        counts = store.counts_by_status()

    print(f"\n{len(collected)} item(s) seen, {created} new")
    print(f"pipeline: {counts}")
    return EXIT_OK


def _sync_youtube(args: argparse.Namespace, config: Config) -> list[Item]:
    from saveddigest.google_auth import AuthError, build_service
    from saveddigest.sources.youtube import (
        SOURCE_PLAYLIST,
        YouTubeReader,
        entries_to_items,
    )

    items: list[Item] = []

    if args.import_watch_later:
        items.extend(_import_watch_later(config))

    try:
        service = build_service("youtube", "v3", config)
    except AuthError as exc:
        print(f"skipping YouTube playlist: {exc}", file=sys.stderr)
        return items

    reader = YouTubeReader(service)
    playlist_id = config.youtube_playlist_id or reader.resolve_playlist_id(
        config.youtube_playlist_title
    )
    if not playlist_id:
        print(
            f"No playlist titled {config.youtube_playlist_title!r} found. Create it in "
            "YouTube and save videos into it (Watch Later cannot be read by any API).",
            file=sys.stderr,
        )
        return items

    entries = reader.read_playlist(playlist_id)
    print(f"YouTube playlist {config.youtube_playlist_title!r}: {len(entries)} entry(ies)")
    items.extend(entries_to_items(entries, source=SOURCE_PLAYLIST))
    return items


def _import_watch_later(config: Config) -> list[Item]:
    """One-time Watch Later import using cookies from a logged-in browser."""
    from saveddigest.sources.youtube_wl import import_watch_later

    if not config.cookies_from_browser:
        print(
            "--import-watch-later needs SAVED_DIGEST_COOKIES_BROWSER "
            "(chrome, firefox, edge, brave, safari...)",
            file=sys.stderr,
        )
        return []
    try:
        items = import_watch_later(config.cookies_from_browser)
    except Exception as exc:  # noqa: BLE001 - unofficial path, many failure modes
        print(
            f"Watch Later import failed: {exc}\n"
            "This path is unofficial and breaks when YouTube changes. Your ongoing "
            "saves are unaffected; move the backlog into the playlist by hand.",
            file=sys.stderr,
        )
        return []
    print(f"Watch Later import: {len(items)} entry(ies)")
    return items


def _sync_todoist(args: argparse.Namespace, config: Config) -> list[Item]:
    from saveddigest.sources.todoist import TodoistClient, items_from_tasks

    try:
        token = _todoist_token(config)
    except SystemExit as exc:
        print(f"skipping Instagram/Todoist: {exc}", file=sys.stderr)
        return []

    client = TodoistClient(token)
    project_id = client.find_project_id(config.todoist_project_name)
    if not project_id:
        print(
            f"No Todoist project named {config.todoist_project_name!r}. Create it and "
            "share posts to it from Instagram.",
            file=sys.stderr,
        )
        return []

    raw = client.tasks_in_project(project_id)
    items, consumed = items_from_tasks(raw)
    print(f"Todoist {config.todoist_project_name!r}: {len(items)} item(s) from {len(raw)} task(s)")

    if consumed and not args.dry_run:
        marked = client.mark_ingested(consumed)
        log.info("labelled %d task(s) as ingested", marked)
    return items


# --------------------------------------------------------------------------
# enrich
# --------------------------------------------------------------------------
def cmd_enrich(args: argparse.Namespace, config: Config) -> int:
    from saveddigest.enrich.media import (
        ContentKind,
        fetch_instagram_content,
        fetch_youtube_content,
        resolve_share_redirect,
    )
    from saveddigest.sources.urls import is_unresolved_share, parse_url

    limit = args.limit or config.stage_limit
    with Store(config.db_path) as store:
        queue = store.by_status(Status.NEW, limit=limit)
        if not queue:
            print("nothing to enrich")
            return EXIT_OK

        print(f"enriching {len(queue)} item(s)")
        for item in queue:
            assert item.id is not None
            try:
                if item.liveness is Liveness.DEAD:
                    # Already known gone from the playlist tombstone; no fetch.
                    store.advance(item.id, Status.ENRICHED, content_kind=ContentKind.METADATA_ONLY)
                    print(f"  - {item.external_id}: already deleted, skipped fetch")
                    continue

                url = item.url
                if is_unresolved_share(item.external_id):
                    resolved = resolve_share_redirect(url)
                    parsed = parse_url(resolved) if resolved else None
                    if parsed and not parsed.needs_resolution:
                        url = parsed.canonical_url
                        print(f"  - resolved share link to {parsed.external_id}")
                    else:
                        store.record_failure(item.id, "could not resolve share redirect")
                        store.update(item.id, liveness=Liveness.UNVERIFIABLE)
                        print(f"  ! {item.external_id}: share link unresolved")
                        continue

                if item.platform is Platform.YOUTUBE:
                    fetched = fetch_youtube_content(item.external_id)
                else:
                    fetched = fetch_instagram_content(
                        url,
                        cookies_from_browser=(
                            config.cookies_from_browser if args.deep else None
                        ),
                    )

                store.advance(
                    item.id,
                    Status.ENRICHED,
                    content_text=fetched.text,
                    content_kind=fetched.kind,
                    title=item.title or fetched.title,
                    author=item.author or fetched.author,
                    published_at=item.published_at or fetched.published_at,
                    liveness=Liveness.ALIVE if fetched.is_usable else item.liveness,
                    error=None,
                )
                label = "ok" if fetched.is_usable else "no content"
                print(f"  - {item.external_id}: {label} ({fetched.kind})")

            except Exception as exc:  # noqa: BLE001 - one bad item must not stop the run
                store.record_failure(item.id, str(exc))
                print(f"  ! {item.external_id}: {exc}", file=sys.stderr)

        print(f"pipeline: {store.counts_by_status()}")
    return EXIT_OK


# --------------------------------------------------------------------------
# summarise (Pass A)
# --------------------------------------------------------------------------
def cmd_summarise(args: argparse.Namespace, config: Config) -> int:
    from saveddigest.triage import summarize
    from saveddigest.triage.batch import BatchRunner

    limit = args.limit or config.stage_limit
    client = _anthropic_client(config)

    with Store(config.db_path) as store:
        queue = store.by_status(Status.ENRICHED, limit=limit)
        if not queue:
            print("nothing to summarise")
            return EXIT_OK

        requests = [
            summarize.build_request(item, model=config.model, effort=config.effort)
            for item in queue
        ]
        print(f"submitting {len(requests)} item(s) to Pass A (batch, 50% rate)")

        outcomes = BatchRunner(client).run(requests)
        advanced = 0
        for item in queue:
            outcome = outcomes.get(summarize.custom_id_for(item))
            if outcome is None:
                store.record_failure(item.id, "no batch result returned")
                continue
            if summarize.apply_outcome(store, item, outcome):
                advanced += 1

        print(f"summarised {advanced}/{len(queue)}")
        print(f"pipeline: {store.counts_by_status()}")
    return EXIT_OK


# --------------------------------------------------------------------------
# verify (Pass B)
# --------------------------------------------------------------------------
def cmd_verify(args: argparse.Namespace, config: Config) -> int:
    from saveddigest.triage import verify
    from saveddigest.triage.batch import BatchRunner
    from saveddigest.triage.schemas import not_applicable_verdict

    limit = args.limit or config.stage_limit
    client = _anthropic_client(config)
    today = _today_iso()

    with Store(config.db_path) as store:
        queue = store.by_status(Status.SUMMARISED, limit=limit)
        if not queue:
            print("nothing to verify")
            return EXIT_OK

        # Evergreen items skip the web search entirely — the cost saving.
        needs_check: list[Item] = []
        skipped = 0
        for item in queue:
            if item.staleness in NEEDS_VERIFICATION:
                needs_check.append(item)
            else:
                verify.record_skipped(store, item, not_applicable_verdict())
                skipped += 1

        print(f"{skipped} evergreen item(s) skipped, {len(needs_check)} to fact-check")
        if not needs_check:
            print(f"pipeline: {store.counts_by_status()}")
            return EXIT_OK

        structured = verify.resolve_structured_output(store, client, config.model)
        channel = "output_config.format" if structured else "strict tool call"
        print(f"structured output channel: {channel}")

        requests = [
            verify.build_request(
                item,
                item.summary or {},
                model=config.model,
                today=today,
                structured_output=structured,
                effort=config.effort,
                max_searches=config.max_searches_per_item,
            )
            for item in needs_check
        ]
        estimated = len(requests) * config.max_searches_per_item
        print(
            f"submitting {len(requests)} item(s) to Pass B "
            f"(up to {estimated} searches, ~${estimated * 0.01:.2f})"
        )

        outcomes = BatchRunner(client).run(requests)
        tally: dict[str, int] = {}
        for item in needs_check:
            outcome = outcomes.get(verify.custom_id_for(item))
            if outcome is None:
                store.record_failure(item.id, "no batch result returned")
                continue
            if verify.apply_outcome(store, item, outcome, structured_output=structured):
                refreshed = store.get(item.id)
                value = (refreshed.verdict or {}).get("verdict", "?")
                tally[value] = tally.get(value, 0) + 1

        print(f"verdicts: {tally}")
        print(f"pipeline: {store.counts_by_status()}")
    return EXIT_OK


# --------------------------------------------------------------------------
# digest
# --------------------------------------------------------------------------
def cmd_digest(args: argparse.Namespace, config: Config) -> int:
    from saveddigest.deliver.html import render_html, render_text
    from saveddigest.deliver.rank import build_digest, subject_line, summarise_counts

    limit = args.limit or config.digest_item_limit
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    with Store(config.db_path) as store:
        items = store.by_status(Status.VERIFIED, limit=None, max_attempts=99)
        digest = build_digest(items, limit=limit, generated_at=generated)
        counts = summarise_counts(digest)

        print(f"subject: {subject_line(digest)}")
        print(f"counts:  {counts}")

        if args.html_out:
            path = Path(args.html_out)
            path.write_text(render_html(digest), encoding="utf-8")
            print(f"html:    {path}")

        if args.dry_run:
            print()
            print(render_text(digest))
            return EXIT_OK

        if digest.is_empty:
            print("nothing to send")
            return EXIT_OK

        from saveddigest.deliver.email import send_digest
        from saveddigest.google_auth import AuthError

        try:
            message_id = send_digest(digest, config, to=args.to)
        except AuthError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        print(f"sent:    gmail message {message_id}")

        if not args.no_tasks and config.todoist_token:
            from saveddigest.deliver.tasks import (
                TodoistTaskWriter,
                plan_task,
                select_actionable,
            )

            chosen = select_actionable(digest)
            if chosen:
                writer = TodoistTaskWriter(config.todoist_token)
                created = writer.create_all([plan_task(e) for e in chosen])
                print(f"tasks:   created {len(created)}")

        stamp = utcnow_iso()
        for entry in digest.entries:
            store.advance(entry.item.id, Status.DELIVERED, delivered_at=stamp)
        for bucket in (digest.gone, digest.expired, digest.no_content):
            for entry in bucket:
                store.advance(entry.item.id, Status.DELIVERED, delivered_at=stamp)

        print(f"pipeline: {store.counts_by_status()}")
    return EXIT_OK


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------
def cmd_status(args: argparse.Namespace, config: Config) -> int:
    with Store(config.db_path) as store:
        counts = store.counts_by_status()
        items = store.all_items()

    print(f"database: {config.db_path}")
    print(f"items:    {len(items)}")
    for stage in Status:
        if counts.get(stage.value):
            print(f"  {stage.value:<12} {counts[stage.value]}")

    stale = [i for i in items if i.attempts >= 3]
    if stale:
        print(f"\n{len(stale)} item(s) stuck after 3 failed attempts:")
        for item in stale[:10]:
            print(f"  {item.external_id}: {item.error}")

    by_verdict: dict[str, int] = {}
    for item in items:
        value = (item.verdict or {}).get("verdict")
        if value:
            by_verdict[value] = by_verdict.get(value, 0) + 1
    if by_verdict:
        print(f"\nverdicts: {by_verdict}")
    return EXIT_OK


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace, config: Config) -> int:
    """The cron entry point: every stage, in order, stopping on a hard error."""
    for name, handler in (
        ("sync", cmd_sync),
        ("enrich", cmd_enrich),
        ("summarise", cmd_summarise),
        ("verify", cmd_verify),
        ("digest", cmd_digest),
    ):
        print(f"\n=== {name} ===")
        code = handler(args, config)
        if code != EXIT_OK:
            print(f"stopping: {name} exited {code}", file=sys.stderr)
            return code
    return EXIT_OK


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saved-digest",
        description=(
            "Resurface, filter and fact-check the things you saved on YouTube and "
            "Instagram and never went back to."
        ),
    )
    parser.add_argument("--version", action="version", version=f"saved-digest {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-auth", help="grant Google access once (opens a browser)")

    p_sync = sub.add_parser("sync", help="capture new saves (free)")
    p_sync.add_argument("--dry-run", action="store_true", help="show what would be stored")
    p_sync.add_argument(
        "--import-watch-later",
        action="store_true",
        help="one-time backlog import via browser cookies (unofficial)",
    )
    p_sync.add_argument("--youtube-only", action="store_true")
    p_sync.add_argument("--instagram-only", action="store_true")

    p_enrich = sub.add_parser("enrich", help="fetch transcripts and captions (slow)")
    p_enrich.add_argument("--limit", type=int, help="max items this run")
    p_enrich.add_argument(
        "--deep",
        action="store_true",
        help="use browser cookies for private Instagram posts (see docs/INSTAGRAM.md)",
    )

    p_sum = sub.add_parser("summarise", aliases=["summarize"], help="Pass A: summarise + triage")
    p_sum.add_argument("--limit", type=int, help="max items this run")

    p_ver = sub.add_parser("verify", help="Pass B: fact-check against the web")
    p_ver.add_argument("--limit", type=int, help="max items this run")

    p_dig = sub.add_parser("digest", help="build and send the digest")
    p_dig.add_argument("--dry-run", action="store_true", help="print instead of sending")
    p_dig.add_argument("--html-out", help="also write the HTML to this path")
    p_dig.add_argument("--to", help="override the recipient")
    p_dig.add_argument("--limit", type=int, help="max entries in the body")
    p_dig.add_argument("--no-tasks", action="store_true", help="skip Todoist tasks")

    sub.add_parser("status", help="what is in the database")

    p_run = sub.add_parser("run", help="every stage in order (the cron entry point)")
    p_run.add_argument("--limit", type=int, help="max items per stage")
    p_run.add_argument("--dry-run", action="store_true", help="do not send or write")
    p_run.add_argument("--html-out", help="also write the HTML to this path")
    p_run.add_argument("--to", help="override the recipient")
    p_run.add_argument("--no-tasks", action="store_true")
    p_run.add_argument("--deep", action="store_true")
    p_run.add_argument("--import-watch-later", action="store_true")
    p_run.add_argument("--youtube-only", action="store_true")
    p_run.add_argument("--instagram-only", action="store_true")

    return parser


_HANDLERS = {
    "init-auth": cmd_init_auth,
    "sync": cmd_sync,
    "enrich": cmd_enrich,
    "summarise": cmd_summarise,
    "summarize": cmd_summarise,
    "verify": cmd_verify,
    "digest": cmd_digest,
    "status": cmd_status,
    "run": cmd_run,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # Quiet the Google discovery client's routine chatter.
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)

    config = Config.from_env()
    handler = _HANDLERS[args.command]

    # Defaults for flags that only some subcommands define, so shared handlers
    # can read them unconditionally.
    for flag, default in (
        ("dry_run", False),
        ("limit", None),
        ("html_out", None),
        ("to", None),
        ("no_tasks", False),
        ("deep", False),
        ("import_watch_later", False),
        ("youtube_only", False),
        ("instagram_only", False),
    ):
        if not hasattr(args, flag):
            setattr(args, flag, default)

    try:
        return handler(args, config)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return EXIT_ERROR
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(f"error: {exc.code}", file=sys.stderr)
            return EXIT_CONFIG
        return int(exc.code or EXIT_OK)


if __name__ == "__main__":
    raise SystemExit(main())
