"""Record the demo's terminal sessions live, with real timing.

Each step in steps.json runs as one bash script inside a pseudo-terminal sized like the
video's terminal, so programs see a real TTY: pytest prints its progress dots as tests
finish, colours are on, and output arrives when the program writes it. Every read from the
terminal is stored with its timestamp. Commands are separated by an ASCII record-separator
byte printed between them, which the renderer uses to know where to show the next typed
command; the byte itself is never displayed.

`echo $?` is run as `echo $rc`, where rc holds the previous command's exit status, because
the separator `printf` in between would otherwise reset `$?` to 0.

Run from the repository root:  python presentation/video/record_terminal.py [step-id ...]
"""

from __future__ import annotations

import base64
import fcntl
import json
import os
import pty
import select
import struct
import sys
import termios
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE.parent / "build" / "video" / "recordings"
STEPS = json.loads((HERE / "steps.json").read_text())["steps"]

COLS, ROWS = 112, 30
SEP = b"\x1e"


def script_for(step: dict) -> str:
    parts = []
    for c in step["commands"]:
        parts.append(c.get("shell", c["cmd"]) + "; rc=$?; printf '\\036'")
    return "\n".join(parts)


def record(step: dict) -> dict:
    env = dict(
        os.environ,
        TERM="xterm-256color",
        COLUMNS=str(COLS),
        LINES=str(ROWS),
        PYTHONUNBUFFERED="1",
        FORCE_COLOR="1",
        CLICOLOR_FORCE="1",
    )
    pid, fd = pty.fork()
    if pid == 0:  # child: become the shell running the step's commands
        os.chdir(ROOT)
        os.execvpe("bash", ["bash", "--noprofile", "--norc", "-c", script_for(step)], env)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))

    t0 = time.monotonic()
    chunks: list[tuple[float, bytes]] = []
    while True:
        r, _, _ = select.select([fd], [], [], 0.25)
        if r:
            try:
                data = os.read(fd, 65536)
            except OSError:  # EIO once the child has exited and the slave side closed
                break
            if not data:
                break
            chunks.append((time.monotonic() - t0, data))
        else:
            done, _ = os.waitpid(pid, os.WNOHANG)
            if done:
                break
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    os.close(fd)

    # Split the byte stream into one output per command at the separator bytes.
    outputs: list[list[tuple[float, str]]] = [[]]
    for t, data in chunks:
        pieces = data.split(SEP)
        for k, piece in enumerate(pieces):
            if piece:
                outputs[-1].append((t, base64.b64encode(piece).decode()))
            if k < len(pieces) - 1:
                outputs[-1].append((t, ""))  # marks the moment this command finished
                outputs.append([])
    outputs = outputs[: len(step["commands"])]
    return {
        "id": step["id"],
        "cols": COLS,
        "rows": ROWS,
        "duration": time.monotonic() - t0,
        "outputs": outputs,
    }


def main(argv: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = set(argv) or {s["id"] for s in STEPS}
    for step in STEPS:
        if step["id"] not in wanted:
            continue
        print(f"recording {step['id']} ...", flush=True)
        rec = record(step)
        (OUT / f"{step['id']}.json").write_text(json.dumps(rec))
        n = [len(o) for o in rec["outputs"]]
        print(f"  {rec['duration']:.1f}s, output chunks per command: {n}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
