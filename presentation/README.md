# Presentation and demo-video storyboard

| File | What it is |
|---|---|
| `RetainIQ_Presentation.pptx` | 8-slide project presentation (16:9), speaker notes on every slide |
| `RetainIQ_Demo_Video_Script_and_Storyboard.docx` | Production script and storyboard for a 7 min 55 s demo video (A4 landscape) |

Both are generated. Nothing on a slide or in the storyboard is typed by hand: charts come
from `metrics.py`, screenshots from the HTML the project's own commands write, and terminal
frames from captured command output. Each slide's speaker notes name the command behind
its numbers.

## Adding the demo video link

After uploading the video to Google Drive (Share → "Anyone with the link" → Viewer):

- **In PowerPoint:** on slide 1 select "Paste the Google Drive link here", press ⌘K (Ctrl+K),
  paste the link. Repeat on slide 8 in the Demo video card. Also link the "Watch the demo
  video" button text on slide 1.
- **Or rebuild:** `VIDEO_URL="https://drive.google.com/..." node build_deck.js` (step 2) writes
  the link into both slides as a working hyperlink. The storyboard's cover accepts the same
  variable.

## Rebuilding

Requires Python with the project installed, Node 18+, and Google Chrome (for screenshots).
Run from the repository root.

```bash
# 1. regenerate every chart, screenshot and captured output into presentation/build/
python presentation/prepare_assets.py            # add --skip-check to skip make check

# 2. build the deck
cd presentation && npm install && TESTS=466 node build_deck.js && cd ..

# 3. scenes 1 and 10 of the storyboard are slides 2 and 8: render the deck to PDF
#    (PowerPoint → File → Export → PDF, saved as presentation/build/RetainIQ_Presentation.pdf)
python presentation/frames.py --slide-thumbs presentation/build/RetainIQ_Presentation.pdf

# 4. build the storyboard
cd presentation && node storyboard.js
```

`TESTS` should equal the count `pytest --collect-only -q` reports; the deck states it.

## What the deck does and does not claim

The classification metrics on slide 5 are computed from the kill-test churn model
(`metrics.py`): AUC 0.700, recall 44.5%, precision 7.4%, F1 0.127. Accuracy (79.6%) is shown
next to the 96.7% scored by predicting that nobody churns, because with a 3.3% event rate
accuracy rewards doing nothing.

Slide 8 states production readiness per component rather than for the whole system: the
delivery path (CLI, preflight, report, dashboard, tests, CI) is ready; the decision models
are validated on simulated and public data only; a real-client ROI has not been shown. See
`docs/DECISIONS.md` D-067.
