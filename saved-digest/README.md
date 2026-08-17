# saved-digest

You save things on YouTube and Instagram and never go back. This collects them,
**filters out what is no longer worth your time**, **checks against the live web
whether the rest is still applicable**, and emails you a detailed summary of what
survives.

```
CAPTURE          →  ENRICH        →  PASS A (batch)    →  PASS B (batch)     →  FILTER + DELIVER
"To Watch" (API)    transcript       detailed summary     web-search verify     drop dead/expired
Watch Later (1×)    caption          + staleness class    only time-sensitive   rank by age + value
Todoist (Insta)     liveness         + claims to check    verdict + citations   Gmail + Todoist
```

---

## Read this first: both platforms are closed

The two things you would expect to connect to cannot be connected to. Not a scope
problem, not a quota problem:

- **YouTube Watch Later is permanently closed to the API.** `channels.list` →
  `contentDetails.relatedPlaylists` returns the literal constants `HL` and `WL`
  even for your own authorised channel, and those playlists are system-managed and
  reject reads and writes. By design.
- **Instagram saved posts exist in no API at all.** The Graph API's "saves" is a
  metric on *your own* posts, never a reader's collection. Personal accounts have
  essentially no API surface.

So capture comes in sideways:

| Platform | How saves are captured | Official? |
|---|---|---|
| YouTube, ongoing | You save into an ordinary playlist (`To Watch`); read via Data API v3 | Yes, and it never breaks |
| YouTube, backlog | One-time Watch Later import via `yt-dlp` + browser cookies | No — see [docs/WATCH-LATER.md](docs/WATCH-LATER.md) |
| Instagram | Share sheet → Todoist project; this reads that project | Yes, no scraping |

---

## It has to run on your machine

Not a preference. YouTube blocks known cloud-provider IP ranges for caption
fetches, so `enrich` returns `RequestBlocked` / `IpBlocked` from AWS, GCP, Azure
and CI runners while working fine on a laptop. The Watch Later import additionally
needs a browser profile on the same machine.

The Claude calls (including web search) run on Anthropic's servers and are
IP-agnostic — only `yt-dlp` needs a residential connection.

---

## Setup

### 1. Install

```bash
git clone <this repo> && cd saved-digest
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

### 2. Google (one consent, two scopes)

`youtube.readonly` to read the playlist, `gmail.send` to send the digest — one
OAuth client, one token file.

1. In the [Google Cloud console](https://console.cloud.google.com/), create a
   project.
2. Enable **YouTube Data API v3** and the **Gmail API**.
3. Credentials → Create credentials → **OAuth client ID** → **Desktop app**.
4. Download the JSON to `~/.config/saved-digest/google_client_secret.json`.
5. Add your own address as a test user on the OAuth consent screen.

```bash
saved-digest init-auth      # opens a browser once
```

> **Refresh tokens expire after 7 days while your app is in "testing" status.**
> For an unattended weekly job, publish the consent screen (it stays private to
> your test users) or expect to re-run `init-auth` weekly.

### 3. Create the YouTube playlist

Make a playlist called **To Watch**. From now on, tap **Save → To Watch** instead
of the Watch Later clock icon. Same number of taps, and it is readable forever.

### 4. Instagram → Todoist

Get a token from Todoist **Settings → Integrations → Developer**, then create a
project called **Saved from Instagram**. When you find a reel, use Instagram's
share sheet → Todoist instead of the bookmark icon.

### 5. Environment

```bash
cp .env.example .env    # then edit
set -a; source .env; set +a
```

### 6. Settle the one open API question

```bash
python3 scripts/spike_structured_output.py
```

Pass B needs structured JSON *and* web search. Whether those two combine is not
documented either way, so the code supports both channels and probes at runtime.
This runs the probe explicitly, shows you a real verdict on a deliberately stale
claim, and caches the answer. See [docs/DECISIONS.md](docs/DECISIONS.md).

---

## Use

```bash
saved-digest sync --dry-run          # what would be captured (free)
saved-digest sync                    # capture
saved-digest enrich --limit 5        # fetch transcripts (slow, local IP required)
saved-digest summarise --limit 5     # Pass A: detailed summary + staleness triage
saved-digest verify --limit 5        # Pass B: fact-check the time-sensitive ones
saved-digest digest --dry-run        # print the digest without sending
saved-digest digest                  # send it
saved-digest status                  # what is in the database
saved-digest run                     # every stage, in order — the cron entry point
```

Stages are separate because they cost different things. `sync` is free, `enrich`
is slow, `summarise` and `verify` cost money. **On a large backlog, run them one at
a time with `--limit` first.**

### First run on a big backlog

`sync` imports everything; the other stages take `--limit` (default 50) and the
digest shows 12 entries per send. So a 400-item backlog drains over several weekly
runs instead of producing one $10 batch and one unreadable email.

### Schedule it

```cron
# Sundays at 9am. Note `run` needs your login keychain for browser cookies,
# so a user cron (not root) is correct.
0 9 * * 0  cd /path/to/saved-digest && .venv/bin/saved-digest run >> ~/.local/share/saved-digest/cron.log 2>&1
```

macOS: prefer a launchd agent — cron there lacks the keychain access `--deep` wants.

---

## What "still applicable" actually means

Four separate questions. Only one needs the web, which is why classification and
verification are separate passes:

| Check | How | Cost |
|---|---|---|
| **Dead** — deleted or private | `videos.list` omits the id; playlist shows a "Deleted video" tombstone | free |
| **Expired** — deadline passed | date named in the content vs today | free |
| **Superseded** — newer version exists, tool shut down | **web search** | ~$0.01/item |
| **Evergreen** — techniques, maths, mental models | Pass A classification; skips Pass B | free |

Most saves are evergreen and skip the search entirely. That skip is where the cost
control lives — and you can only tell which ones qualify after reading the content,
which fixes the ordering of the two passes.

### The digest filter

| Class | Treatment |
|---|---|
| Dead | One footer line. **Reported, never silently dropped.** |
| Expired | One footer line each, with the date |
| Superseded | Full entry, badged, **with a link to the current version** |
| Partly outdated | Full entry with the specific caveat |
| Still valid / evergreen | Full entry |
| Unverified | Full entry, **explicitly labelled "Not checked"** with the reason |

### Cost

A 30-minute transcript is roughly 5k tokens. Twenty items a week:

| | |
|---|---|
| Pass A (all items, batched) | ~$0.13 |
| Pass B (~40% of items, ≤4 searches each) | ~$0.24 |
| **Weekly total** | **~$0.40** |

The one-time backlog is the real spend, which is what `--limit` is for.

---

## Trust boundaries — read before acting on a verdict

- **Verdicts are a language model plus web search, not ground truth.** Every
  verdict ships with its citations so you can check it. Do not treat
  `still_valid` on a niche topic as authoritative.
- **A failed check reads `unverified`, never `still_valid`.** If no search
  actually ran, the guard in `triage/verify.py` downgrades the verdict regardless
  of how confident the output looked. A confident wrong answer is worse than an
  admitted gap, because you would act on it without re-checking.
- **Instagram is the weak leg.** The default tier reads the *caption*, not the
  spoken audio. See [docs/INSTAGRAM.md](docs/INSTAGRAM.md).
- **Auto-captions mishear technical terms**, and summaries built from them are
  labelled accordingly.

---

## Development

```bash
pytest                  # 465 tests, all offline
pytest -m network       # the few that need egress (skipped by default)
ruff check .
python3 scripts/sample_digest.py /tmp/d.html   # eyeball the layout, no API calls
```

The default suite runs with no network and no API key. Network-dependent code is
split so the decision logic is pure and tested: `enrich/vtt.py` (rolling-caption
flattening), `sources/urls.py` (dedup keys), `triage/batch.py` (`custom_id`
mapping, web-search error shape, `pause_turn`), `deliver/rank.py` (the filter).

`tests/test_todoist_source.py` runs against a payload **recorded from the live
API** — which is how the `addedAt` vs `created_at` field-naming difference between
Todoist's API versions was caught.

### Layout

```
saveddigest/
  cli.py               argparse entry point
  config.py            env + XDG paths
  store.py             SQLite; (platform, external_id) is the dedup key
  google_auth.py       one OAuth credential, two scopes
  sources/
    urls.py            canonicalisation → external_id
    youtube.py         playlist read via Data API v3
    youtube_wl.py      one-time Watch Later import (quarantined)
    todoist.py         Instagram capture
  enrich/
    vtt.py             WebVTT → prose, rolling-window dedup
    media.py           yt-dlp wrappers + track selection
  triage/
    schemas.py         JSON schemas + defensive coercion
    batch.py           Batches plumbing
    summarize.py       Pass A
    verify.py          Pass B
  deliver/
    rank.py            filter + ranking
    html.py            HTML + text render
    email.py           Gmail API
    tasks.py           Todoist tasks
```

See [docs/DECISIONS.md](docs/DECISIONS.md) for why things are the way they are.
