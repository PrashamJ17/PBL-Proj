# Why Watch Later cannot be read, and what to do instead

## The constraint

`channels.list(part="contentDetails", mine=True)` returns:

```json
{"relatedPlaylists": {"likes": "LL...", "uploads": "UU...",
                      "watchHistory": "HL", "watchLater": "WL"}}
```

`HL` and `WL` are **literal constants**, not playlist ids — the API returns those
exact two-character strings for every authorised user. And even given the string,
those playlists are system-managed and reject read and modify requests.

There is no scope that changes this. `youtube.readonly`, `youtube.force-ssl`, full
`youtube` — all return the same constants. This has been the behaviour since 2016
and is documented as intentional.

The **Liked videos** playlist (`LL...`) *is* readable, if you use "like" as a save
signal. Watch history (`HL`) is not.

## What this project does instead

An ordinary playlist. Create one called `To Watch`, and tap **Save → To Watch**
rather than the clock icon. Ordinary playlists are fully readable through
`playlistItems.list`, indefinitely, with no unofficial dependency.

Two facts that read gives us for free, both load-bearing:

- `snippet.publishedAt` on a playlist *item* is when it was **added to the
  playlist** — that is when you saved it, and it drives the digest's ageing.
- `contentDetails.videoPublishedAt` is when the **video** was published, which is
  what Pass A uses to judge whether the content is likely stale.

## The backlog

For whatever is already sitting in Watch Later:

```bash
export SAVED_DIGEST_COOKIES_BROWSER=chrome
saved-digest sync --import-watch-later
```

This uses `yt-dlp` with cookies from your logged-in browser. It is **unofficial**
and quarantined in `sources/youtube_wl.py` for that reason:

- it breaks whenever YouTube changes its internals;
- it needs a browser profile on the same machine, not locked by a running browser;
- a flat playlist listing carries **no add-date**, so imported items have no
  `saved_at` and are ordered by import time instead. Correct — we genuinely do not
  know which was saved first.

It runs **once**, for the backlog. If it fails, the message says so and ongoing
capture is unaffected; move the backlog across by hand and nothing else changes.

## Tombstones

Deleted and private videos are *not* removed from playlists. They remain as
entries titled `Deleted video` or `Private video`. `sources/youtube.py` detects
those exactly (so a real video called "Deleted video recovery: how I got my footage
back" is not misclassified) and records them as `liveness=dead`.

They are then reported in the digest footer as "3 saved items no longer exist"
rather than dropped. A save that silently disappears is indistinguishable from a
bug.
