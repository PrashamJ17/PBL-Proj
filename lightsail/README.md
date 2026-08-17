# Amazon Lightsail (PaaS-Lite) — Cloud Infrastructure

Presentation, speech and technical report.

**Hridiyansh Shukla · Registration No. 2427030591 · August 2026**

---

## Deliverables

| File | What it is |
|---|---|
| `Amazon_Lightsail_Presentation.pptx` | The deck — 20 slides, formal, with figures, tables and a native chart. Speaker notes are embedded on every slide. |
| `Amazon_Lightsail_Presentation.pdf` | The same deck as PDF, for handout or as a projector fallback. |
| `SPEECH.pdf` | The spoken script, print-ready — large type, timing marks, one card per slide that never splits across a page. **Print this one for the lectern.** |
| `SPEECH.md` | Source of the spoken script — 1,528 words, **11 min 22 s** at 134 wpm, with a per-slide timing map, delivery cues and anticipated questions. |
| `REPORT.pdf` | The technical report, 23 pages, print-ready A4. |
| `REPORT.docx` | The same report in Word format, images embedded, for editing or submission. |
| `REPORT.md` | The report source. |
| `assets/` | All figures (PNG) and icons used by the deck and the report. |
| `src/` | Generator scripts — see below. |

## How the pieces stay in sync

`src/script.js` is the **single source of truth for everything spoken**. `src/deck.js`
embeds it as PowerPoint speaker notes, and `src/make-speech.js` renders `SPEECH.md`
from the same array — so the script on the lectern and the notes in PowerPoint cannot
drift apart. Every figure quoted aloud also appears on the slide being shown.

## Timing

The talk is written for the 10–12 minute brief with margin at both ends:

| Delivery pace | Runtime |
|---|---|
| 125 wpm (deliberate) | 12.2 min |
| 134 wpm (target) | 11.4 min |
| 145 wpm (brisk) | 10.5 min |

Checkpoints while presenting: **slide 9 by 4:28**, **slide 15 by 8:07**.

## Rebuilding

```bash
cd src
npm install                  # pptxgenjs + sharp
node make-assets.js          # regenerate figures and icons into ../assets
node deck.js                 # build the .pptx
node make-speech.js          # build ../SPEECH.md from script.js
python3 make-report-pdf.py   # build ../REPORT.pdf and the Word-conversion HTML
python3 make-speech-pdf.py   # build ../SPEECH.pdf
```

To regenerate `REPORT.docx` after editing `REPORT.md`:

```bash
python3 make-report-pdf.py
soffice --headless --convert-to docx:"MS Word 2007 XML" --outdir .. src/report-for-word.html
mv ../report-for-word.docx ../REPORT.docx
```

## Sourcing

All pricing and feature claims were verified in August 2026 against the AWS Lightsail
pricing pages, the Lightsail User Guide and the 2026 AWS service announcements; full
references are in Section 14 of the report and on slide 20.

The cost model in Section 6.3 (and slide 11) is computed rather than quoted — it uses
us-east-1 list prices for a t3.small on demand, a 60 GB gp3 volume, one in-use Elastic IP
and egress at $0.09/GB after the first 100 GB free. The arithmetic is shown in full in the
report so it can be checked.
