"""Render the silent demo video from the live recordings.

Inputs, all produced by the other scripts in this directory:
  build/video/recordings/<step>.json   live terminal sessions (record_terminal.py)
  build/video/clips/<step>.webm        Chrome screencasts (record_browser.mjs)

Terminal sessions are replayed through a real terminal emulator (pyte), so what appears
on screen is exactly the byte stream the programs wrote, at the time they wrote it. Only
two things are added: the typing of each command, and time compression for runs longer
than six seconds, which is always shown on screen with its factor.

Output: build/video/RetainIQ_Demo.mp4 (1920x1080, 30 fps, H.264, no audio).
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import pyte
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent / "build" / "video"
REC, CLIPS, SEG = BUILD / "recordings", BUILD / "clips", BUILD / "segments"
OUT = BUILD / "RetainIQ_Demo.mp4"
SPEC = json.loads((HERE / "steps.json").read_text())
STEPS = SPEC["steps"]
N = len(STEPS)

W, H, FPS = 1920, 1080, 30
X264 = [
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "20",
    "-pix_fmt",
    "yuv420p",
    "-r",
    str(FPS),
    "-g",
    "60",
    "-movflags",
    "+faststart",
]

BG, STRIP, PANEL, PANEL_STRIP = (11, 21, 33), (24, 40, 58), (14, 27, 41), (22, 36, 52)
INK, DIM, TEAL, GOLD, WHITE = (
    (214, 226, 238),
    (130, 150, 170),
    (67, 198, 177),
    (242, 165, 65),
    (255, 255, 255),
)
PROMPT = "\x1b[36mPBL-Proj\x1b[0m \x1b[90m$\x1b[0m "

MAX_REAL = 6.0  # runs longer than this are compressed...
KEEP = 0.10  # ...keeping 10% of the time beyond it


def _face(path: str, style: str, size: int) -> ImageFont.FreeTypeFont:
    for i in range(12):
        try:
            f = ImageFont.truetype(path, size, index=i)
        except OSError:
            break
        if f.getname()[1].lower() == style:
            return f
    return ImageFont.truetype(path, size)


HELV, MENLO = "/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Menlo.ttc"
F = {
    "step": _face(HELV, "bold", 20),
    "title": _face(HELV, "bold", 34),
    "sub": _face(HELV, "regular", 24),
    "cap": _face(HELV, "regular", 28),
    "badge": _face(HELV, "bold", 22),
    "strip": _face(MENLO, "regular", 18),
    "mono": _face(MENLO, "regular", 22),
    "monob": _face(MENLO, "bold", 22),
}
CW = F["mono"].getlength("M")
LH = 26

NAMED = {
    "black": (110, 120, 135),
    "red": (255, 110, 100),
    "green": (95, 210, 135),
    "brown": (242, 190, 80),
    "yellow": (242, 190, 80),
    "blue": (110, 165, 255),
    "magenta": (205, 140, 255),
    "cyan": (67, 198, 177),
    "white": (235, 240, 245),
}


def colour(name: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if name == "default":
        return default
    base = name[6:] if name.startswith("bright") else name
    if base in NAMED:
        return NAMED[base]
    if len(name) == 6:
        try:
            return tuple(int(name[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return default


class Encoder:
    """Pipes frames to ffmpeg, re-sending the previous frame when nothing changed."""

    def __init__(self, path: Path):
        self.proc = subprocess.Popen(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{W}x{H}",
                "-r",
                str(FPS),
                "-i",
                "-",
                *X264,
                str(path),
            ],
            stdin=subprocess.PIPE,
        )
        self.key, self.buf, self.frames = None, None, 0

    def put(self, key, draw) -> None:
        if key != self.key or self.buf is None:
            self.buf, self.key = draw().tobytes(), key
        self.proc.stdin.write(self.buf)
        self.frames += 1

    def close(self) -> None:
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError("ffmpeg failed")


def fade(img: Image.Image, i: int, total: int, n: int = 12) -> Image.Image:
    a = min(1.0, (i + 1) / n, (total - i) / n)
    return img if a >= 1 else Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), img, max(0.0, a))


def fade_bucket(i: int, total: int, n: int = 12) -> int:
    return i if i < n else (i - total if i >= total - n else 0)


def wrap_px(text: str, font, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if font.getlength(trial) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def draw_header(d: ImageDraw.ImageDraw, n: int, step: dict) -> None:
    d.rectangle([0, 0, W, 100], fill=STRIP)
    d.text((64, 20), f"STEP {n} OF {N}", font=F["step"], fill=TEAL)
    d.text((64, 46), step["title"], font=F["title"], fill=WHITE)
    x = 64 + F["title"].getlength(step["title"]) + 24
    d.text((x, 56), step["subtitle"], font=F["sub"], fill=DIM)


def draw_caption(d: ImageDraw.ImageDraw, text: str) -> None:
    if not text:
        return
    lines = wrap_px(text, F["cap"], 1600)
    widest = max(F["cap"].getlength(x) for x in lines)
    h = 24 + 38 * len(lines)
    y0 = H - 16 - h
    d.rounded_rectangle(
        [(W - widest) / 2 - 28, y0, (W + widest) / 2 + 28, y0 + h], radius=14, fill=(8, 16, 26)
    )
    for i, line in enumerate(lines):
        d.text(
            ((W - F["cap"].getlength(line)) / 2, y0 + 12 + 38 * i), line, font=F["cap"], fill=WHITE
        )


# --------------------------------------------------------------------------- cards
def card(path: Path, lines: list[tuple[str, str, tuple]], seconds: float) -> None:
    enc = Encoder(path)
    total = int(seconds * FPS)
    fonts = {
        "h": _face(HELV, "bold", 110),
        "s": _face(HELV, "regular", 40),
        "p": _face(HELV, "bold", 30),
        "q": _face(HELV, "regular", 28),
        "n": _face(HELV, "regular", 22),
    }

    def base() -> Image.Image:
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        y = 300
        for kind, text, col in lines:
            f = fonts[kind]
            for part in wrap_px(text, f, 1500):
                d.text(((W - f.getlength(part)) / 2, y), part, font=f, fill=col)
                y += {"h": 140, "s": 64, "p": 52, "q": 46, "n": 34}[kind]
            y += 18
        return img

    frame = base()
    for i in range(total):
        enc.put(fade_bucket(i, total), lambda i=i: fade(frame, i, total))
    enc.close()


# ------------------------------------------------------------------------ terminal
def terminal_segment(path: Path, n: int, step: dict, rec: dict) -> float:
    cols, rows = rec["cols"], rec["rows"]
    screen = pyte.Screen(cols, rows)
    stream = pyte.ByteStream(screen)
    stream.feed(PROMPT.encode())

    # Build a timeline: typed commands, output chunks at their (possibly compressed) times.
    events: list[tuple[float, int, str, object]] = []  # (time, order, kind, payload)
    typing: list[tuple[float, float, str]] = []  # (start, chars/s, text)
    captions: list[tuple[float, float, str]] = []
    badges: list[tuple[float, float, float]] = []
    t, prev_real, order = 0.8, 0.0, 0
    for i, cmd in enumerate(step["commands"]):
        text = cmd["cmd"]
        cps = max(45.0, len(text) / 2.0)
        typing.append((t, cps, text))
        start = t
        t += len(text) / cps + 0.35
        events.append((t, order, "enter", None))
        order += 1
        outs = rec["outputs"][i] if i < len(rec["outputs"]) else []
        end_real = outs[-1][0] if outs else prev_real
        dur = max(0.0, end_real - prev_real)
        shown = dur if dur <= MAX_REAL else MAX_REAL + (dur - MAX_REAL) * KEEP
        factor = dur / shown if shown > 0 else 1.0
        n_lines = 0
        for rt, b64 in outs:
            if b64:
                data = base64.b64decode(b64)
                n_lines += data.count(b"\n")
                events.append((t + (rt - prev_real) / factor, order, "out", data))
                order += 1
        if factor > 1.2:
            badges.append((t, t + shown, factor))
        t += shown + 0.15
        events.append((t, order, "prompt", None))
        order += 1
        # No narration, so output stays up long enough to read: longer output, longer hold.
        hold = min(14.0, 4.5 + 0.2 * n_lines)
        if i == len(step["commands"]) - 1:
            hold += 1.5
        captions.append((start, t + hold, cmd["caption"]))
        t += hold
        prev_real = end_real
    total_t = t + 0.6
    events.sort(key=lambda e: (e[0], e[1]))

    enc = Encoder(path)
    total = int(total_t * FPS)
    ev_i, typed = 0, [0] * len(typing)
    fed = 0
    x_text = (W - cols * CW) / 2
    y_text = 172

    for f in range(total):
        now = f / FPS
        for k, (st, cps, text) in enumerate(typing):
            want = min(len(text), max(0, int((now - st) * cps)))
            if want > typed[k]:
                stream.feed(text[typed[k] : want].encode())
                fed += want - typed[k]
                typed[k] = want
        while ev_i < len(events) and events[ev_i][0] <= now:
            _, _, kind, payload = events[ev_i]
            if kind == "enter":
                stream.feed(b"\r\n")
            elif kind == "out":
                stream.feed(payload)
            elif kind == "prompt":
                stream.feed(PROMPT.encode())
            fed += 1
            ev_i += 1
        cap = next((c for c in captions if c[0] <= now < c[1]), None)
        badge = next((b for b in badges if b[0] <= now < b[1]), None)
        cursor_on = int(now * 2) % 2 == 0
        key = (
            fed,
            sum(typed),
            cursor_on,
            cap[2] if cap else "",
            badge[2] if badge else 0,
            fade_bucket(f, total),
        )

        def draw(f=f, cap=cap, badge=badge, cursor_on=cursor_on):
            img = Image.new("RGB", (W, H), BG)
            d = ImageDraw.Draw(img)
            draw_header(d, n, step)
            px0, px1 = x_text - 36, x_text + cols * CW + 36
            d.rounded_rectangle([px0, 116, px1, 172 + rows * LH + 16], radius=16, fill=PANEL)
            d.rounded_rectangle([px0, 116, px1, 152], radius=16, fill=PANEL_STRIP)
            d.rectangle([px0, 140, px1, 152], fill=PANEL_STRIP)
            for j, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
                d.ellipse([px0 + 22 + j * 26, 127, px0 + 36 + j * 26, 141], fill=c)
            label = f"PBL-Proj — bash — {cols}×{rows}"
            d.text(
                ((px0 + px1 - F["strip"].getlength(label)) / 2, 124),
                label,
                font=F["strip"],
                fill=DIM,
            )
            for y in range(rows):
                row = screen.buffer[y]
                x = 0
                while x < cols:
                    ch = row[x]
                    style = (ch.fg, ch.bold)
                    start = x
                    s = []
                    while x < cols and (row[x].fg, row[x].bold) == style:
                        s.append(row[x].data)
                        x += 1
                    run = "".join(s)
                    if run.strip():
                        d.text(
                            (x_text + start * CW, y_text + y * LH),
                            run,
                            font=F["monob"] if style[1] else F["mono"],
                            fill=colour(style[0], INK),
                        )
            if cursor_on:
                cx, cy = screen.cursor.x, screen.cursor.y
                d.rectangle(
                    [
                        x_text + cx * CW,
                        y_text + cy * LH + 2,
                        x_text + (cx + 1) * CW - 1,
                        y_text + cy * LH + LH - 2,
                    ],
                    fill=(150, 170, 190),
                )
            if badge:
                label = (
                    f"sped up {badge[2]:.0f}×  (live run: {badge[2] * (badge[1] - badge[0]):.0f} s)"
                )
                bw = F["badge"].getlength(label)
                d.rounded_rectangle([px1 - bw - 44, 160, px1 - 16, 196], radius=10, fill=GOLD)
                d.text((px1 - bw - 30, 166), label, font=F["badge"], fill=(20, 24, 30))
            draw_caption(d, cap[2] if cap else "")
            return fade(img, f, total)

        enc.put(key, draw)
    enc.close()
    return total_t


# ------------------------------------------------------------------------- browser
def browser_segment(path: Path, clip: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(clip),
            "-vf",
            f"fps={FPS},scale={W}:{H},format=yuv420p,fade=t=in:st=0:d=0.4",
            "-an",
            *X264,
            str(path),
        ],
        check=True,
    )


def duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    ).stdout
    return float(out.strip() or 0)


def main() -> int:
    SEG.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    t = SPEC["title"]
    segments.append(SEG / "00_title.mp4")
    card(
        segments[-1],
        [
            ("h", t["heading"], WHITE),
            ("s", t["subheading"], TEAL),
            ("p", t["people"], INK),
            ("q", t["place"], DIM),
            ("n", t["note"], DIM),
        ],
        6.5,
    )
    for n, step in enumerate(STEPS, 1):
        rec = json.loads((REC / f"{step['id']}.json").read_text())
        p = SEG / f"{n:02d}_{step['id']}_terminal.mp4"
        secs = terminal_segment(p, n, step, rec)
        segments.append(p)
        print(f"step {n} {step['id']}: terminal {secs:.1f}s", flush=True)
        if step["kind"] == "browser":
            p = SEG / f"{n:02d}_{step['id']}_browser.mp4"
            browser_segment(p, CLIPS / f"{step['id']}.webm")
            segments.append(p)
            print(f"step {n} {step['id']}: browser {duration(p):.1f}s", flush=True)
    e = SPEC["end"]
    segments.append(SEG / "99_end.mp4")
    card(
        segments[-1],
        [("h", e["heading"], WHITE)]
        + [("q", x, INK) for x in e["lines"]]
        + [("n", e["note"], DIM)],
        8.0,
    )

    listing = SEG / "concat.txt"
    listing.write_text("".join(f"file '{s.name}'\n" for s in segments))
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(OUT),
        ],
        check=True,
    )
    print(f"wrote {OUT}  ({duration(OUT) / 60:.2f} min, {OUT.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
