# Instagram: what works, and the honest limitation

## Capture

There is no API for saved posts. The Graph API's `saved` metric counts saves *of
your own posts*; it cannot enumerate what you have saved. Personal accounts have
essentially no API surface at all.

So capture inverts: **share the reel to a Todoist project** from Instagram's share
sheet instead of tapping the bookmark icon. `sources/todoist.py` reads that
project. No scraping, no ToS exposure, roughly the same effort as saving.

The cost is real and worth stating: anything you bookmark the old way stays
invisible to this tool.

### Share-sheet redirects

Instagram sometimes emits an opaque link with no shortcode in it:

```
https://www.instagram.com/share/reel/_Xk92LmNq
```

Guessing a shortcode from that would attach the wrong summary to the wrong reel,
so these get a namespaced provisional id (`share:_Xk92LmNq`) and are flagged
`needs_resolution`. `enrich` follows the redirect to recover the real shortcode; if
it cannot, the item stays flagged rather than being silently mis-attributed.

## The limitation: caption, not audio

**The default tier reads the post's written caption, not what is spoken in the
video.** `yt-dlp` gives caption, uploader and title for public posts without
cookies, and that is what Pass A summarises.

For a talking-head reel where the substance is spoken, the caption may be a
sentence and three hashtags. The summary will be proportionate and honest about it:
Pass A is told explicitly that it has the caption only and instructed not to infer
what the video showed, and `content_quality` comes back `thin`.

### The opt-in deep tier

Transcribing the audio means downloading the video and running a local Whisper
model:

```bash
pip install 'saved-digest[audio]'
saved-digest enrich --deep
```

Off by default, deliberately:

- it pulls a ~100MB model and is far slower than a caption read;
- for private posts it needs `--cookies-from-browser`, which ties the run to your
  logged-in session and carries ToS and rate-limit exposure that the default tier
  does not.

That is a decision about your account, so it is a flag you turn on rather than
something enabled on your behalf.

## Summary of tiers

| Tier | Gets | Needs | Default |
|---|---|---|---|
| Caption | link, author, caption, date | nothing | **yes** |
| Deep | caption + spoken transcript | `[audio]` extra | no, `--deep` |
| Private | either, for private posts | browser cookies | no |
