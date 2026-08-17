#!/usr/bin/env python3
"""Render REPORT.md to a print-ready PDF (and a Word-compatible HTML) via WeasyPrint."""
import pathlib
import re

import markdown
from weasyprint import CSS, HTML

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "REPORT.md"
PDF = ROOT / "REPORT.pdf"

text = SRC.read_text(encoding="utf-8")

# The in-page anchor list is a Markdown convenience; keep it, it becomes a real TOC.
html_body = markdown.markdown(
    text,
    extensions=["tables", "fenced_code", "toc", "attr_list", "sane_lists"],
)

# Start the body of the report (section 1 onward) on a fresh page; let the rest flow.
html_body = html_body.replace('<h2 id="1-introduction">', '<h2 class="newpage" id="1-introduction">', 1)

CSS_TEXT = """
@page {
  size: A4;
  margin: 20mm 18mm 18mm 18mm;
  @bottom-center {
    content: "Amazon Lightsail (PaaS-Lite) — Cloud Infrastructure  ·  Hridiyansh Shukla  ·  2427030591";
    font-family: Calibri, Carlito, sans-serif; font-size: 7.5pt; color: #8A9AA8;
  }
  @bottom-right { content: counter(page); font-family: Calibri, Carlito, sans-serif; font-size: 8pt; color: #8A9AA8; }
}
@page :first { @bottom-center { content: ""; } @bottom-right { content: ""; } }

body { font-family: Calibri, Carlito, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #232F3E; }
h1 { font-family: Cambria, Caladea, serif; font-size: 24pt; color: #232F3E; margin: 0 0 2mm; line-height: 1.15; }
h1 + h3 { font-family: Cambria, Caladea, serif; font-size: 13pt; font-style: italic; color: #FF9900;
          font-weight: normal; margin: 0 0 8mm; }
h2 { font-family: Cambria, Caladea, serif; font-size: 15pt; color: #232F3E;
     margin: 9mm 0 3mm; padding-bottom: 1.5mm; border-bottom: 1.5pt solid #FF9900;
     break-after: avoid; break-inside: avoid; }
h2.newpage { break-before: page; margin-top: 0; }
h3 { font-family: Cambria, Caladea, serif; font-size: 12pt; color: #33475B; margin: 6mm 0 2mm;
     break-after: avoid; break-inside: avoid; }
h4 { font-family: Calibri, Carlito, sans-serif; font-size: 10.5pt; color: #33475B; margin: 4mm 0 1.5mm;
     break-after: avoid; }
p { margin: 0 0 3mm; text-align: justify; }
strong { color: #232F3E; }
a { color: #00718F; text-decoration: none; }

ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
li { margin-bottom: 1.5mm; text-align: justify; }

table { border-collapse: collapse; width: 100%; margin: 3mm 0 5mm; font-size: 9pt; break-inside: avoid; }
th { background: #232F3E; color: #fff; text-align: left; padding: 2mm 2.5mm; font-weight: bold; border: 0.5pt solid #232F3E; }
td { padding: 1.8mm 2.5mm; border: 0.5pt solid #D5DEE5; vertical-align: top; }
tbody tr:nth-child(even) td { background: #F4F7F9; }

img { max-width: 100%; display: block; margin: 4mm auto 1.5mm; break-inside: avoid; }
p.caption { text-align: center; font-size: 8.5pt; font-style: italic; color: #5A6B7B;
            margin-bottom: 5mm; break-before: avoid; }

blockquote { margin: 3mm 0; padding: 2.5mm 4mm; background: #FFF4E2;
             border: 0.75pt solid #FF9900; border-radius: 1.5mm; font-size: 9.5pt; }
blockquote p { margin: 0 0 1.5mm; }
blockquote p:last-child { margin-bottom: 0; }

pre { background: #F4F7F9; border: 0.5pt solid #D5DEE5; border-radius: 1.5mm;
      padding: 3mm; font-family: "Courier New", monospace; font-size: 8pt;
      line-height: 1.35; white-space: pre-wrap; break-inside: avoid; }
code { font-family: "Courier New", monospace; font-size: 9pt; }

hr { border: none; border-top: 0.5pt solid #D5DEE5; margin: 6mm 0; }
"""

HTML(string=f"<html><body>{html_body}</body></html>", base_url=str(ROOT)).write_pdf(
    PDF, stylesheets=[CSS(string=CSS_TEXT)]
)
print(f"wrote {PDF}")

# Also emit a styled HTML file, which LibreOffice converts to an editable .docx.
# Images must be inlined as data URIs, or the .docx merely *links* them and breaks once moved.
import base64


def inline_images(html: str) -> str:
    def repl(m):
        src = m.group(1)
        data = (ROOT / src).read_bytes()
        return 'src="data:image/png;base64,%s"' % base64.b64encode(data).decode()

    return re.sub(r'src="(assets/[^"]+)"', repl, html)


HTML_OUT = ROOT / "src" / "report-for-word.html"
HTML_OUT.write_text(
    "<html><head><meta charset='utf-8'>"
    "<title>Amazon Lightsail (PaaS-Lite) — Cloud Infrastructure</title>"
    f"<style>{CSS_TEXT}</style></head><body>{inline_images(html_body)}</body></html>",
    encoding="utf-8",
)
print(f"wrote {HTML_OUT}")
