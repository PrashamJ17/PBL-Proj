# Decisions

Why things are the way they are, especially where the obvious approach is wrong.

---

## D-001 — Two passes, not one

Pass A summarises every item with no tools. Pass B fact-checks only the subset Pass
A flagged, with web search. Both are batches.

The tempting design is one call that summarises *and* checks. It is worse:

- most saves are evergreen and need no search at all, and a search is ~$0.01 plus
  latency plus throttle pressure;
- **you cannot tell which items need checking until you have read them**, so the
  classification has to happen after the read and before the search.

That ordering constraint is the whole reason for two passes. The cost saving is a
consequence, not the motivation.

## D-002 — Web search inside a batch

Contrary to an initial assumption, the Batches API **does** support the web search
tool, priced the same as a regular request. So Pass B keeps the 50% batch discount.

The caveat is real: batch web search is throttled per organisation, so a large
first run can take a long time. That is latency, not failure, and `BatchRunner`'s
timeout message says so explicitly rather than implying the work was lost.

## D-003 — Batch requests are single-shot, which shapes Pass B

There is no second turn in a batch. Two consequences:

- **`pause_turn`** (a long search turn hitting the server-side iteration limit)
  cannot be resumed in-batch. It becomes `unverified` with a "will retry" reason.
  `verify_one_sync` exists for the retry path and *does* handle the continuation
  properly, by echoing the paused assistant message back unchanged.
- **A client-tool call is fine single-shot**, because the verdict travels as the
  tool call's *input*. We read it and never need to answer the call.

## D-004 — Structured output vs web search: probed, not assumed

Pass B needs JSON out and web search in. Web search always emits citations, and
structured outputs are documented as incompatible with citations — but that
documented conflict is about `citations: {enabled: true}` on **document** blocks,
and this combination is not addressed either way.

Rather than pick one and hope, `verify.py` implements **both** channels:

1. `output_config.format` with a `json_schema` (preferred, simpler);
2. a `strict: true` client tool `record_verdict` whose input carries the verdict.

`probe_structured_output_support` asks the API once with a trivial request and
caches the answer in `meta`. A `400` means fall back; **any other error is
re-raised**, because recording "unsupported" on an auth or network failure would
permanently and silently degrade every future verdict.

`tool_choice` is `auto`, not forced: forcing `record_verdict` would make the model
call it immediately, before searching.

## D-005 — A verdict with no search is downgraded, always

`usage.server_tool_use.web_search_requests == 0` means nothing was checked,
regardless of how confident the returned JSON looks. `extract_verdict` downgrades
it to `unverified`.

This matters because of a documented interaction: if the model emits web search and
a client tool in the same parallel group, the API returns `stop_reason: "tool_use"`
and **does not run the search**. In a batch that cannot be continued, so without
this guard a well-formed verdict built on zero evidence would reach the digest
labelled as checked.

The usage counter is the authority rather than the result blocks, because
`response_inclusion: "excluded"` can legitimately remove those blocks from the
response.

## D-006 — A failed search never reads as "still valid"

Web search failures arrive as **HTTP 200** with `web_search_tool_result.content`
being a single error *object* where success is a *list*. No exception is raised.
`web_search_failure` branches on that shape.

Every failure path — refusal, pause, search error, unreadable payload — produces
`unverified` with a stated reason, which the digest renders as "Not checked". A
confident wrong answer is worse than an admitted gap, because the user acts on it
without re-checking.

## D-007 — Results keyed by `custom_id`, never by position

The Batches API makes no ordering guarantee. Zipping results against the request
list silently attaches each summary and verdict to the **wrong saved item** — a
failure that produces plausible-looking output and would be very hard to notice.
`index_results_by_custom_id` is the only path.

## D-008 — Re-sync must not reset progress

`Store.upsert` refreshes title, author and published date on conflict, and keeps
the **earliest** `saved_at`. It deliberately does not touch `status`,
`content_text`, `summary_json`, `verdict_json` or `delivered_at`.

A weekly sync sees every playlist entry again. Without this, every run would
re-summarise and re-email the entire library at full cost. `Store.advance` refuses
backwards transitions for the same reason.

Keeping the earliest `saved_at` matters separately: age is the digest's primary
signal, and a re-sync must not make an eight-month-old save look new.

## D-009 — Local execution is a constraint, not a preference

YouTube blocks known cloud-provider IP ranges for caption fetches. The same
`yt-dlp` call that works on a laptop returns `RequestBlocked` / `IpBlocked` from
AWS, GCP, Azure or a CI runner. Confirmed while building this: the development
sandbox's egress policy blocked `www.youtube.com` outright.

Anthropic API calls, including web search, are unaffected — they run on Anthropic's
servers. Only `enrich` needs a residential IP.

## D-010 — Watch Later import is quarantined

Isolated in `sources/youtube_wl.py`, behind an explicit flag, with a failure
message that says ongoing capture is unaffected. It is unofficial, needs browser
cookies, and breaks when YouTube changes. It runs once, for the backlog. See
[WATCH-LATER.md](WATCH-LATER.md).

## D-011 — Instagram share redirects are flagged, not guessed

`instagram.com/share/reel/_Xk92LmNq` contains no shortcode. Inventing one would
attach the wrong summary to the wrong reel. These get a namespaced provisional id
(`share:` prefix) and are resolved by following the redirect, or stay flagged.

## D-012 — Rolling-window caption dedup

YouTube auto-captions are a rolling two-line window: each cue repeats the previous
cue's last line. Naive concatenation roughly **doubles** the transcript, which pays
twice per word and measurably degrades the summary. `enrich/vtt.py` collapses
consecutive duplicate lines — only consecutive ones, since a phrase legitimately
repeated later in the video is content.

## D-013 — Dead items are reported, not dropped

Deleted, expired and unreadable items go to a digest footer as one line each. They
are never silently removed: "3 saved items no longer exist" is information, and a
save that quietly vanishes is indistinguishable from a bug.

Footer counts are **not** subject to the body's `--limit`, so the count of what
vanished never depends on how many entries happened to fit.

## D-014 — Ranking is not purely by age, and the copy says so

`relevance_score` is `age_factor * verdict_weight * quality_weight +
actionability`. A still-valid save outranks a superseded one of the same vintage,
and a promotional roundup sinks regardless of age. Age saturates at one year so an
ancient item cannot monopolise the digest for ever.

`unverified` deliberately outranks `superseded`: "we could not check this" is more
likely to still be worth your attention than "this has been replaced".

An earlier version printed "Oldest saves first" above this list, which was simply
untrue of the list underneath it. Caught by reading the rendered output rather than
the tests, and now pinned by
`test_digest_does_not_claim_to_be_ordered_purely_by_age`.

## D-015 — `expiry_date` is validated strictly

Only a well-formed `YYYY-MM-DD` is accepted; anything else becomes `None`. A
malformed date silently compared against today would push **live** items into the
expired bucket, where they get one footer line instead of a full summary.

## D-016 — Unknown enum values fail towards being checked

An unrecognised `staleness_class` (from a future revision, or a model slip) coerces
to `time_sensitive`, not `evergreen`. The failure mode of guessing wrong should be
a wasted search, not an unchecked stale item presented as fine.

## D-017 — argparse, and a small dependency set

No click, no typer, no Streamlit. This runs from a cron line on a laptop; a
dependency that can break an unattended weekly job is not worth nicer help text.
Nothing in the base install compiles. `faster-whisper` is an extra precisely
because it is heavy and most items do not need it.

## D-018 — Everything model-generated is escaped

Titles come from YouTube and every summary field comes from a language model. All
of it is untrusted markup being pasted into an HTML email, so it all goes through
`html.escape`. Tested with `<script>`, `<img onerror>` and attribute-breakout
payloads.

## D-019 — Transcripts are capped, and the truncation is disclosed

120k characters (~30k tokens). A three-hour podcast would otherwise cost real money
for one saved video. The prompt is told when content was truncated rather than
having it hidden, so the summary does not silently claim to cover the whole thing.
