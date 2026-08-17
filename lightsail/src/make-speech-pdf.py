#!/usr/bin/env python3
"""Render SPEECH.md to a lectern-ready PDF.

Styled for reading while presenting, not for filing: large body type, prominent
timing marks, and each slide's script held whole on a single page.
"""
import pathlib
import re

import markdown
from weasyprint import CSS, HTML

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "SPEECH.md"
PDF = ROOT / "SPEECH.pdf"

html_body = markdown.markdown(
    SRC.read_text(encoding="utf-8"),
    extensions=["tables", "sane_lists", "toc"],
)

# Start the spoken script on a fresh page.
html_body = html_body.replace('<h2 id="the-script">', '<h2 class="newpage" id="the-script">', 1)

# Tag the timing map (the second table) so the bold total row applies only there.
tables = [m.start() for m in re.finditer(r"<table>", html_body)]
if len(tables) > 1:
    i = tables[1]
    html_body = html_body[:i] + '<table class="timing">' + html_body[i + len("<table>"):]

# Wrap each slide's block so a page break never lands inside one.
html_body = re.sub(
    r'(<h3 id="slide-.*?)(?=<h3 id="slide-|<hr\s*/?>|$)',
    lambda m: f'<section class="slide">{m.group(1)}</section>',
    html_body,
    flags=re.S,
)

CSS_TEXT = """
@page {
  size: A4;
  margin: 16mm 16mm 15mm 16mm;
  @bottom-left {
    content: "Amazon Lightsail (PaaS-Lite)  ·  Hridiyansh Shukla  ·  2427030591";
    font-family: Calibri, Carlito, sans-serif; font-size: 7.5pt; color: #8A9AA8;
  }
  @bottom-right { content: counter(page); font-family: Calibri, Carlito, sans-serif;
                  font-size: 8pt; color: #8A9AA8; }
}
@page :first { @bottom-left { content: ""; } @bottom-right { content: ""; } }

body { font-family: Calibri, Carlito, sans-serif; font-size: 11pt; line-height: 1.5; color: #232F3E; }

h1 { font-family: Cambria, Caladea, serif; font-size: 21pt; color: #232F3E;
     margin: 0 0 4mm; line-height: 1.2; }
h2 { font-family: Cambria, Caladea, serif; font-size: 14pt; color: #232F3E;
     margin: 9mm 0 3mm; padding-bottom: 1.5mm; border-bottom: 1.5pt solid #FF9900;
     break-after: avoid; }
h2.newpage { break-before: page; margin-top: 0; }
h3 { font-family: Cambria, Caladea, serif; font-size: 13pt; color: #232F3E;
     margin: 0 0 2mm; break-after: avoid; }

p { margin: 0 0 3mm; }
a { color: #00718F; text-decoration: none; }

/* Metadata block under the title */
body > p:first-of-type { font-size: 10pt; color: #33475B; margin-bottom: 4mm; }

/* The standing note at the top */
body > blockquote { background: #F4F7F9; border: 0.75pt solid #C6D0D8; border-radius: 1.5mm;
                    padding: 3mm 4mm; font-size: 9.5pt; color: #33475B; margin: 0 0 5mm; }
body > blockquote p { margin: 0 0 1.5mm; }
body > blockquote p:last-child { margin-bottom: 0; }

table { border-collapse: collapse; width: 100%; margin: 3mm 0 5mm; font-size: 9.5pt; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { background: #232F3E; color: #fff; text-align: left; padding: 1.8mm 2.5mm;
     font-weight: bold; border: 0.5pt solid #232F3E; }
td { padding: 1.5mm 2.5mm; border: 0.5pt solid #D5DEE5; }
tbody tr:nth-child(even) td { background: #F4F7F9; }
table.timing tbody tr:last-child td { font-weight: bold; background: #EDF1F4; }

/* ---- One slide of the script ---- */
section.slide {
  break-inside: avoid;
  margin: 0 0 6mm;
  padding: 4mm 4.5mm 3mm;
  border: 0.75pt solid #D5DEE5;
  border-radius: 2mm;
}

/* Timing line: `0:00 - 0:16`  ·  16s · 36 words */
section.slide > p:first-of-type { font-size: 9.5pt; color: #5A6B7B; margin-bottom: 2.5mm; }
section.slide code { font-family: "Courier New", monospace; font-size: 10.5pt;
                     font-weight: bold; color: #232F3E; background: #FFF4E2;
                     border: 0.5pt solid #FF9900; border-radius: 1mm; padding: 0.4mm 1.6mm; }

/* Delivery cue */
section.slide blockquote { margin: 0 0 3mm; padding: 2mm 3mm; background: #F4F7F9;
                           border-left: 2.5pt solid #00A1C9; font-size: 9.5pt; color: #33475B; }
section.slide blockquote p { margin: 0; }
section.slide blockquote strong { color: #00718F; }

/* The words actually spoken — the largest text on the page */
section.slide > p:last-child { font-size: 12.5pt; line-height: 1.62; color: #232F3E; margin: 0; }

hr { border: none; border-top: 0.5pt solid #D5DEE5; margin: 6mm 0; }
strong { color: #232F3E; }
"""

HTML(string=f"<html><body>{html_body}</body></html>", base_url=str(ROOT)).write_pdf(
    PDF, stylesheets=[CSS(string=CSS_TEXT)]
)
print(f"wrote {PDF}")
