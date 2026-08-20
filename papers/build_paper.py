"""Render RESEARCH_PAPER.md to a two-column PDF.

There is no LaTeX on the build machine, so the route is markdown -> HTML -> headless
Chrome. That is not a compromise for this document: the paper is authored in markdown,
the figures are PNGs produced by the experiment modules, and Chrome's print engine
handles CSS multi-column with spanning figures correctly.

Two details carry the layout:

**Wide elements span both columns.** The figures are 13.2 inches wide and several tables
have five or more numeric columns. Squeezed into a 3.4-inch column they become unreadable,
so anything marked wide gets ``column-span: all``. Tables are measured at build time --
column count decides, not a hand-maintained list, so a table that grows a column starts
spanning without anybody remembering to update this file.

**Images are inlined as base64.** Chrome loads a ``file://`` page with restrictions that
vary by version and flags; embedding sidesteps the question entirely and makes the
intermediate HTML a single self-contained artifact worth keeping when a render looks wrong.
"""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "RESEARCH_PAPER.md"
OUTPUT = HERE / "RetainIQ_Research_Paper.pdf"

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

#: A table with at least this many columns is unreadable in a 3.4-inch column.
WIDE_TABLE_COLUMNS = 4

CSS = """
@page { size: A4; margin: 15mm 14mm 16mm 14mm; }

html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }

body {
  font-family: "Times New Roman", Times, serif;
  font-size: 9.2pt;
  line-height: 1.32;
  color: #000;
  margin: 0;
  text-align: justify;
  hyphens: auto;
}

/* ---- title block: full width, above the columns ---------------------------- */
.titleblock { column-span: all; margin-bottom: 9pt; }
.titleblock h1 {
  font-family: Helvetica, Arial, sans-serif;
  font-size: 19pt;
  line-height: 1.16;
  font-weight: 700;
  margin: 0 0 8pt;
  text-align: left;
  hyphens: none;
}
.titleblock p { margin: 2pt 0; text-align: left; font-size: 9.4pt; }
.titleblock em { color: #333; }
.titleblock a { color: #0b4f9e; text-decoration: none; word-break: break-all; }

.rule { column-span: all; border: 0; border-top: 1.6pt solid #000; margin: 7pt 0 9pt; }

/* ---- abstract: full width, set apart -------------------------------------- */
.abstract {
  column-span: all;
  font-size: 9pt;
  line-height: 1.34;
  border-left: 2.5pt solid #0b4f9e;
  padding: 1pt 0 1pt 9pt;
  margin: 0 0 10pt;
}
.abstract h2 {
  font-family: Helvetica, Arial, sans-serif;
  font-size: 9pt; font-weight: 700; letter-spacing: .07em;
  margin: 0 0 4pt; text-transform: uppercase;
}
.abstract p { margin: 0 0 5pt; }
.abstract p:last-child { margin-bottom: 0; }

/* ---- the two-column body --------------------------------------------------- */
.body { column-count: 2; column-gap: 6.5mm; column-fill: balance; }

h2 {
  font-family: Helvetica, Arial, sans-serif;
  font-size: 9.6pt; font-weight: 700; letter-spacing: .04em;
  margin: 11pt 0 4pt; text-transform: uppercase;
  break-after: avoid; text-align: left; hyphens: none;
}
h3 {
  font-family: Helvetica, Arial, sans-serif;
  font-size: 9.2pt; font-weight: 700; font-style: italic;
  margin: 8pt 0 3pt; break-after: avoid; text-align: left; hyphens: none;
}
h4 {
  font-size: 9.2pt; font-weight: 700; font-style: italic;
  margin: 6pt 0 2pt; break-after: avoid; text-align: left;
}
p { margin: 0 0 5pt; orphans: 2; widows: 2; }

ul, ol { margin: 0 0 5pt; padding-left: 13pt; }
li { margin-bottom: 2.5pt; }

code {
  font-family: "SF Mono", Menlo, Consolas, monospace;
  font-size: 8.1pt; background: #f2f2f4; padding: 0 2px; border-radius: 2px;
}
pre {
  background: #f6f6f8; border: .4pt solid #d8d8de; border-radius: 3px;
  padding: 5pt 6pt; font-size: 7.8pt; line-height: 1.3;
  overflow-x: auto; break-inside: avoid; margin: 0 0 6pt;
}
pre code { background: none; padding: 0; font-size: inherit; }

blockquote {
  margin: 0 0 6pt; padding: 3pt 0 3pt 8pt;
  border-left: 2pt solid #b8b8c0; color: #262626; font-size: 8.9pt;
}
blockquote p:last-child { margin-bottom: 0; }

/* ---- tables ---------------------------------------------------------------- */
table {
  border-collapse: collapse; width: 100%;
  font-size: 7.9pt; line-height: 1.24;
  margin: 3pt 0 8pt; break-inside: avoid;
  font-variant-numeric: tabular-nums;
}
thead { display: table-header-group; }
th, td { padding: 2.4pt 4pt; text-align: left; vertical-align: top; hyphens: none; }
th {
  font-family: Helvetica, Arial, sans-serif; font-size: 7.5pt; font-weight: 700;
  border-top: 1.1pt solid #000; border-bottom: .6pt solid #000;
  text-align: left;
}
td { border-bottom: .3pt solid #ccc; }
tbody tr:last-child td { border-bottom: 1.1pt solid #000; }
table code { font-size: 7.3pt; background: none; padding: 0; }

/* ---- figures --------------------------------------------------------------- */
figure { margin: 4pt 0 9pt; break-inside: avoid; text-align: center; }
figure img { max-width: 100%; height: auto; }
figcaption {
  font-size: 8pt; line-height: 1.3; text-align: left;
  margin-top: 3pt; color: #1a1a1a; hyphens: none;
}

/* ---- anything too wide for one column spans both --------------------------- */
.wide { column-span: all; break-inside: avoid; margin: 5pt 0 10pt; }
.tablock { break-inside: avoid; margin: 4pt 0 8pt; }
.wide > p, .tablock > p { margin: 0 0 2pt; font-size: 8.2pt; line-height: 1.28;
  text-align: left; hyphens: none; }
.wide table { font-size: 8.1pt; }
.wide figure { margin: 0; }

/* ---- references ------------------------------------------------------------ */
.refs ol { padding-left: 15pt; }
.refs li { font-size: 8.1pt; line-height: 1.28; margin-bottom: 2.5pt; hyphens: none; }
.refs a { color: #0b4f9e; text-decoration: none; word-break: break-all; }

a { color: #0b4f9e; text-decoration: none; }
strong { font-weight: 700; }
hr { border: 0; border-top: .5pt solid #c8c8ce; margin: 8pt 0; }
"""

#: The source numbers its own captions. Figure captions FOLLOW the image; table captions
#: PRECEDE the table. Both are paired into one unbreakable block below, because a caption
#: stranded in the other column from the thing it names is worse than either alone.
TABLE_CAPTION = re.compile(r"<p><strong>TABLE[^<]*</strong>.*?</p>\s*$", re.S)


def _require(path: str, hint: str) -> None:
    if not Path(path).exists():
        sys.exit(f"missing: {path}\n{hint}")


def _pandoc(md: str) -> str:
    """Markdown to an HTML fragment."""
    if not shutil.which("pandoc"):
        sys.exit("pandoc not found. brew install pandoc")
    return subprocess.run(
        # implicit_figures off: the source writes its own numbered captions, and pandoc's
        # version would duplicate them from the alt text.
        ["pandoc", "--from", "markdown-implicit_figures+pipe_tables+tex_math_dollars",
         "--to", "html5", "--wrap", "none"],
        input=md, capture_output=True, text=True, check=True,
    ).stdout


def _inline_images(html: str) -> str:
    """Base64-embed each figure and absorb its caption paragraph into the same block.

    Pandoc wraps a standalone image in its own ``<p>``, so image and caption are two
    sibling paragraphs. Both are matched as a single unit and replaced together --
    consuming them in one pass, rather than deleting the caption afterwards, is what
    keeps the two from being separated across a column break.
    """
    def repl(m: re.Match) -> str:
        path = (HERE / m.group("src")).resolve()
        if not path.exists():
            sys.exit(f"figure not found: {path}")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        cap = m.group("cap")
        caption = f"<figcaption>{cap}</figcaption>" if cap else ""
        return (f'<div class="wide"><figure>'
                f'<img src="data:image/png;base64,{b64}" alt="{m.group("alt") or ""}">'
                f"{caption}</figure></div>")

    pattern = (
        r'<p><img src="(?P<src>[^"]+)"(?: alt="(?P<alt>[^"]*)")?[^>]*/?></p>'
        r'(?:\s*<p>(?P<cap><strong>FIGURE[^<]*</strong>.*?)</p>)?'
    )
    out, n = re.subn(pattern, repl, html, flags=re.S)
    if n == 0:
        sys.exit("no figures matched -- pandoc's image markup changed; check the pattern")
    leftover = re.search(r'<img src="(?!data:)', out)
    if leftover:
        sys.exit("an image was not inlined; it would render as a broken link in the PDF")
    return out


def _pair_tables_with_captions(html: str) -> str:
    """Bind each table to the caption above it, and span wide ones across both columns."""
    out, pos = [], 0
    for m in re.finditer(r"<table>.*?</table>", html, flags=re.S):
        table = m.group(0)
        head = table.split("</thead>")[0]
        n_cols = len(re.findall(r"<th[ >]", head)) or max(
            (len(re.findall(r"<td[ >]", row))
             for row in re.findall(r"<tr>.*?</tr>", table, flags=re.S)), default=0)

        before = html[pos:m.start()]
        cap = TABLE_CAPTION.search(before)
        caption = ""
        if cap:
            caption = cap.group(0)
            before = before[:cap.start()]

        cls = "wide" if n_cols >= WIDE_TABLE_COLUMNS else "tablock"
        out.append(before)
        out.append(f'<div class="{cls}">{caption}{table}</div>')
        pos = m.end()
    out.append(html[pos:])
    return "".join(out)


def _split_sections(html: str) -> tuple[str, str, str]:
    """Return (title block, abstract, body).

    The title block is everything before the first <hr>; the abstract runs from the
    ABSTRACT heading to the <hr> that follows it. Both are set full width above the
    columns, which is what makes the page read as a paper rather than a printout.
    """
    parts = html.split("<hr />")
    if len(parts) < 3:
        return "", "", html
    title = parts[0]
    abstract = parts[1]
    body = "<hr />".join(parts[2:])
    return title, abstract, body


def build(out: Path = OUTPUT, keep_html: bool = False) -> Path:
    _require(CHROME, "Google Chrome is required to render the PDF.")
    md = SOURCE.read_text(encoding="utf-8")

    html = _pandoc(md)
    html = _inline_images(html)
    html = _pair_tables_with_captions(html)
    title, abstract, body = _split_sections(html)

    # The references list is the last <ol>; give it its own class for tighter setting.
    body = re.sub(r'(<h2[^>]*>REFERENCES</h2>)', r'<div class="refs">\1', body, count=1)
    if '<div class="refs">' in body:
        body = re.sub(r'(<h2[^>]*>AUTHOR BIOGRAPHIES</h2>)', r'</div>\1', body, count=1)

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>When Does Uplift Modelling Pay?</title>
<style>{CSS}</style></head>
<body>
<div class="titleblock">{title}</div>
<hr class="rule">
<div class="abstract">{abstract}</div>
<div class="body">{body}</div>
</body></html>"""

    tmp = Path(tempfile.mkdtemp(prefix="retainiq-paper-")) / "paper.html"
    tmp.write_text(page, encoding="utf-8")

    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         "--virtual-time-budget=20000",
         f"--print-to-pdf={out}", tmp.as_uri()],
        check=True, capture_output=True,
    )
    if keep_html:
        print(f"intermediate HTML: {tmp}")
    return out


def _reference_docx(dest: Path) -> Path:
    """Build a Word reference document: Times New Roman body, Arial headings, ruled tables.

    Pandoc's default reference is Aptos at 12pt with borderless tables, which reads as an
    office memo rather than a manuscript. Rather than commit a binary nobody can diff, the
    default is fetched from pandoc and patched here, so every change is visible in code.

    Single column deliberately. The PDF is the typeset artifact; a DOCX exists to be
    edited and submitted, and journals typeset from the manuscript themselves -- handing
    them a two-column Word file makes their job harder, not easier.
    """
    import zipfile

    base = dest.parent / "_pandoc_default.docx"
    base.write_bytes(subprocess.run(
        ["pandoc", "--print-default-data-file", "reference.docx"],
        capture_output=True, check=True,
    ).stdout)

    work = dest.parent / "_ref"
    with zipfile.ZipFile(base) as z:
        z.extractall(work)

    theme = work / "word/theme/theme1.xml"
    t = theme.read_text(encoding="utf-8")
    t = re.sub(r'(<a:majorFont>\s*<a:latin typeface=")[^"]*', r"\1Arial", t, count=1)
    t = re.sub(r'(<a:minorFont>\s*<a:latin typeface=")[^"]*', r"\1Times New Roman", t,
               count=1)
    theme.write_text(t, encoding="utf-8")

    styles = work / "word/styles.xml"
    s = styles.read_text(encoding="utf-8")
    # 11pt body (w:sz is in half-points).
    s = s.replace('<w:sz w:val="24" />\n        <w:szCs w:val="24" />',
                  '<w:sz w:val="22" />\n        <w:szCs w:val="22" />')
    # Ruled tables: rules above and below the block, hairlines between rows.
    s = s.replace(
        '<w:tblPr>\n      <w:tblInd w:w="0" w:type="dxa" />',
        '<w:tblPr>\n      <w:tblBorders>'
        '<w:top w:val="single" w:sz="8" w:color="000000"/>'
        '<w:bottom w:val="single" w:sz="8" w:color="000000"/>'
        '<w:insideH w:val="single" w:sz="2" w:color="BFBFBF"/>'
        '</w:tblBorders>\n      <w:tblInd w:w="0" w:type="dxa" />', 1)
    styles.write_text(s, encoding="utf-8")

    # A4 with 1-inch margins, which is what most journals ask for.
    doc = work / "word/document.xml"
    d = doc.read_text(encoding="utf-8")
    d = re.sub(r'<w:pgSz[^/]*/>', '<w:pgSz w:w="11906" w:h="16838"/>', d, count=1)
    d = re.sub(r'<w:pgMar[^/]*/>',
               '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
               'w:header="720" w:footer="720" w:gutter="0"/>', d, count=1)
    doc.write_text(d, encoding="utf-8")

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(work.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(work).as_posix())

    base.unlink()
    shutil.rmtree(work)
    return dest


def build_docx(out: Path | None = None) -> Path:
    """Render the paper to a Word document."""
    out = out or (HERE / "RetainIQ_Research_Paper.docx")
    tmpdir = Path(tempfile.mkdtemp(prefix="retainiq-docx-"))
    ref = _reference_docx(tmpdir / "reference.docx")

    subprocess.run(
        # implicit_figures off for the same reason as the PDF: the source writes its own
        # numbered captions, and pandoc would add a second one from the alt text.
        ["pandoc", str(SOURCE),
         "--from", "markdown-implicit_figures+pipe_tables+tex_math_dollars",
         "--to", "docx", "--reference-doc", str(ref),
         "--resource-path", str(HERE), "-o", str(out)],
        check=True, capture_output=True,
    )
    shutil.rmtree(tmpdir, ignore_errors=True)
    return out


if __name__ == "__main__":
    if "--docx" in sys.argv:
        doc = build_docx()
        print(f"wrote {doc}  ({doc.stat().st_size / 1024:,.0f} KB)")
    else:
        pdf = build(keep_html="--keep-html" in sys.argv)
        print(f"wrote {pdf}  ({pdf.stat().st_size / 1024:,.0f} KB)")
