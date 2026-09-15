"""Storyboard frames and thumbnails, rendered from real captured command output.

Called by `prepare_assets.py`, which captures the output first. Terminal frames are drawn
from those text captures rather than typed in, so a frame cannot show a number the
command did not print.

Two storyboard frames are slides from the presentation itself, and the presentation has to
be rendered before they exist:

    python presentation/frames.py --slide-thumbs presentation/build/RetainIQ_Presentation.pdf
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BUILD = Path(__file__).resolve().parent / "build"
DEMO, FRAMES, ASSETS = BUILD / "demo", BUILD / "frames", BUILD / "assets"
THUMBS = FRAMES / "thumbs"

BG, FG, DIM = (14, 27, 41), (214, 226, 238), (130, 150, 170)
TEAL, CORAL, WHITE = (67, 198, 177), (255, 138, 102), (255, 255, 255)


def _mono() -> str:
    for p in ("/System/Library/Fonts/Menlo.ttc", "/Library/Fonts/Courier New.ttf"):
        if Path(p).exists():
            return p
    from matplotlib import font_manager
    return font_manager.findfont("DejaVu Sans Mono")


MONO = _mono()


def _colour(line: str) -> tuple[int, int, int]:
    s = line.strip()
    if line.startswith("$"):
        return WHITE
    if "BLOCKED" in line or "[ BLOCK]" in line or line.startswith("STOPPED") or s.endswith(" no"):
        return CORAL
    if "READY" in line or "[  ok  ]" in line or "[PASS]" in line or "ALL TARGETS MET" in line:
        return TEAL
    if s and set(s) <= set("-="):
        return DIM
    return FG


def frame(name: str, title: str, lines: list[str], size: int = 26, width: int = 96) -> Path:
    """A 1920x1080 terminal window. The font shrinks until every line fits."""
    wrapped: list[str] = []
    for line in lines:
        wrapped += textwrap.wrap(line, width, subsequent_indent="          ",
                                 drop_whitespace=False) or [""]
    img = Image.new("RGB", (1920, 1080), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1920, 64], fill=(24, 40, 58))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([28 + i * 34, 22, 48 + i * 34, 42], fill=c)
    d.text((140, 18), title, font=ImageFont.truetype(MONO, 22), fill=DIM)
    while True:
        f = ImageFont.truetype(MONO, size)
        lh, cw = int(size * 1.38), f.getlength("M")
        longest = max((len(x) for x in wrapped), default=0)
        if len(wrapped) * lh <= 1080 - 120 and longest * cw <= 1920 - 120:
            break
        size -= 1
    y = 92
    for line in wrapped:
        d.text((60, y), line, font=f, fill=_colour(line))
        y += lh
    out = FRAMES / f"{name}.png"
    img.save(out)
    return out


def thumb(src: Path, dst: str, crop_top: bool = False) -> None:
    """Fit any image to 1600x900. Tall screenshots are cropped from the top, so the part a
    viewer reads first is the part that survives."""
    im = Image.open(src).convert("RGB")
    w, h = im.size
    target = 9 / 16
    if h / w > target + 0.01:
        if crop_top:
            im = im.crop((0, 0, w, int(w * target)))
        else:
            nw = int(h / target)
            canvas = Image.new("RGB", (nw, h), BG)
            canvas.paste(im, ((nw - w) // 2, 0))
            im = canvas
    elif h / w < target - 0.01:
        nh = int(w * target)
        canvas = Image.new("RGB", (w, nh), BG)
        canvas.paste(im, (0, (nh - h) // 2))
        im = canvas
    im.resize((1600, 900), Image.LANCZOS).save(THUMBS / dst)


def _read(name: str) -> list[str]:
    return (DEMO / name).read_text().rstrip("\n").splitlines()


def terminal_frames() -> None:
    frame("f02_killtest", "make killtest",
          ["$ make killtest", ""] + _read("killtest.txt"), 56, width=60)
    frame("f03_export", "demo/subscriptions.csv",
          ["$ make demo-data", "wrote demo/customers.csv", "wrote demo/subscriptions.csv", "",
           "$ head -6 demo/subscriptions.csv"] + _read("subscriptions.csv")[:6], 26)

    blocked = [x for x in _read("preflight_blocked.txt") if not x.startswith("exit code")]
    frame("f04_preflight_blocked", "python -m retainiq.cli preflight",
          ["$ python -m retainiq.cli preflight --customers demo/customers.csv \\",
           "      --subscriptions demo/subscriptions.csv", ""]
          + blocked + ["", "$ echo $?", "1"], 24)

    refused = _read("autopsy_blocked.txt")
    code = [x for x in refused if x.startswith("exit code")][0].split(": ")[1]
    frame("f04b_autopsy_refused", "python -m retainiq.cli autopsy (on the blocked file)",
          ["$ python -m retainiq.cli autopsy --customers demo/customers.csv \\",
           "      --subscriptions demo/subscriptions.csv --out demo/blocked.html", ""]
          + [x for x in refused if x.startswith(("STOPPED", "Fix it"))]
          + ["", "PREFLIGHT — is this export safe to compute from?"]
          + [x for x in refused if "VERDICT" in x] + [""]
          + [x for x in refused if x.startswith("[ BLOCK]")][:1]
          + ["", "  (assumptions and footer as in the preflight output)", "", "$ echo $?", code, "",
             "$ ls demo/blocked.html"] + _read("ls_blocked.txt"), 26)

    ready = [x for x in _read("autopsy_ok.txt") if not x.startswith("exit code")]
    frame("f05_autopsy_ready", "python -m retainiq.cli autopsy",
          ["$ python -m retainiq.cli autopsy --customers demo/customers.csv \\",
           "      --subscriptions demo/subscriptions.csv --divide-amounts-by 100 \\",
           "      --interval month --name \"Acme Analytics (demo data)\""
           " --out demo/demo_autopsy.html --worklists",
           ""] + ready, 24)

    holdout = _read("holdout.txt")
    start = next(i for i, x in enumerate(holdout) if x.startswith("MINIMUM DETECTABLE"))
    frame("f10_holdout", "make holdout", ["$ make holdout", "..."] + holdout[start:], 26)

    if (DEMO / "make_check.txt").exists():
        frame("f09_make_check", "make check", ["$ make check"] + _read("make_check.txt"), 26)
    else:
        print("  (no make_check.txt: run prepare_assets.py without --skip-check for scene 9)")


def terminal_thumbs() -> None:
    for name, src, top in [
        ("s02.png", FRAMES / "f02_killtest.png", False),
        ("s03.png", FRAMES / "f03_export.png", False),
        ("s04.png", FRAMES / "f04_preflight_blocked.png", False),
        ("s04b.png", FRAMES / "f04b_autopsy_refused.png", False),
        ("s05a.png", FRAMES / "f05_autopsy_ready.png", False),
        ("s05b.png", ASSETS / "autopsy_raw.png", True), ("s06.png", ASSETS / "dash_top.png", True),
        ("s07.png", ASSETS / "dash_expanded_crop.png", True),
        ("s08.png", FRAMES / "f10_holdout.png", False),
        ("s09.png", FRAMES / "f09_make_check.png", False),
    ]:
        if src.exists():
            thumb(src, name, top)


def slide_thumbs(deck_pdf: Path) -> None:
    """Scenes 1 and 10 open and close on slides 2 and 8 of the presentation."""
    import pymupdf
    doc = pymupdf.open(deck_pdf)
    for page_no, name in [(2, "s01.png"), (8, "s10.png")]:
        png = FRAMES / f"slide-{page_no}.png"
        doc[page_no - 1].get_pixmap(dpi=110).save(png)
        thumb(png, name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--slide-thumbs", type=Path, metavar="DECK_PDF",
                    help="only build the two slide thumbnails from a rendered deck PDF")
    args = ap.parse_args(argv)
    THUMBS.mkdir(parents=True, exist_ok=True)
    if args.slide_thumbs:
        slide_thumbs(args.slide_thumbs)
    else:
        terminal_frames()
        terminal_thumbs()
    print("thumbnails:", ", ".join(sorted(p.name for p in THUMBS.glob("*.png"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
