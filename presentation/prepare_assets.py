"""Regenerate every figure, screenshot and captured output the presentation uses.

Run from the repository root:

    python presentation/prepare_assets.py            # about 5 minutes, includes make check
    python presentation/prepare_assets.py --skip-check

Everything lands in presentation/build/ (gitignored). Nothing on a slide or in the
storyboard is typed by hand: the charts come from `metrics.py`, the screenshots from the
HTML the project's own commands write, and the terminal frames from captured output.

Requires Google Chrome for the screenshots (override the path with $CHROME).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = HERE / "build"
ASSETS, DEMO = BUILD / "assets", BUILD / "demo"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

#: The dashboard renders its reasoning rows collapsed. This expands the first four so the
#: storyboard can show what a viewer sees after clicking, without editing the product.
EXPAND_ROWS = """<script>window.addEventListener('load',function(){
 var n=0; document.querySelectorAll('tr.hidden').forEach(function(e){
   if(n<4){ e.classList.remove('hidden'); n++; } });
});</script></body>"""


def capture(cmd: list[str], dest: Path, cwd: Path = ROOT, exit_code: bool = False) -> int:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    text = r.stdout + r.stderr
    if exit_code:
        text = text.rstrip("\n") + f"\nexit code: {r.returncode}\n"
    dest.write_text(text)
    return r.returncode


def screenshot(html: Path, png: Path, width: int, height: int) -> None:
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2", f"--window-size={width},{height}",
                    f"--screenshot={png}", html.as_uri()], capture_output=True, check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Regenerate presentation assets.")
    ap.add_argument("--skip-check", action="store_true", help="do not run make check (scene 9)")
    args = ap.parse_args(argv)
    for d in (ASSETS, DEMO):
        d.mkdir(parents=True, exist_ok=True)
    py = sys.executable

    print("1/5 classification metrics and charts")
    subprocess.run([py, str(HERE / "metrics.py")], cwd=ROOT, check=True)

    print("2/5 experiment outputs")
    capture(["make", "killtest"], DEMO / "killtest.txt")
    capture(["make", "holdout"], DEMO / "holdout.txt")
    if not args.skip_check:
        if capture(["make", "check"], DEMO / "make_check.txt") != 0:
            print("make check FAILED -- the storyboard must not show a green run.")
            print("See presentation/build/demo/make_check.txt")
            return 1

    print("3/5 demo export through the CLI")
    make_export = ("from retainiq.experiments.demo_export import write_demo_export as w; "
                   f"w({str(DEMO)!r})")
    subprocess.run([py, "-c", make_export], cwd=ROOT, check=True)
    cli = [py, "-m", "retainiq.cli"]
    files = ["--customers", "demo/customers.csv", "--subscriptions", "demo/subscriptions.csv"]
    capture(cli + ["preflight"] + files, DEMO / "preflight_blocked.txt", cwd=BUILD, exit_code=True)
    capture(cli + ["autopsy"] + files + ["--out", "demo/blocked.html"],
            DEMO / "autopsy_blocked.txt", cwd=BUILD, exit_code=True)
    capture(["ls", "demo/blocked.html"], DEMO / "ls_blocked.txt", cwd=BUILD)
    corrected = ["--divide-amounts-by", "100", "--interval", "month",
                 "--name", "Acme Analytics (demo data)",
                 "--out", "demo/demo_autopsy.html", "--worklists"]
    capture(cli + ["autopsy"] + files + corrected, DEMO / "autopsy_ok.txt", cwd=BUILD,
            exit_code=True)

    print("4/5 dashboard and report screenshots")
    subprocess.run(["make", "dashboard"], cwd=ROOT, check=True, capture_output=True)
    subprocess.run(["make", "sample"], cwd=ROOT, check=True, capture_output=True)
    dash, report = ROOT / "retention_dashboard.html", ROOT / "sample_churn_autopsy.html"
    screenshot(dash, ASSETS / "dashboard_raw.png", 1280, 1500)
    screenshot(report, ASSETS / "autopsy_raw.png", 1100, 1500)
    expanded = ASSETS / "dash_expanded.html"
    page = dash.read_text(encoding="utf-8").replace("</body>", EXPAND_ROWS)
    expanded.write_text(page, encoding="utf-8")
    screenshot(expanded, ASSETS / "dash_expanded_raw.png", 1280, 4200)
    # Crops are in 2x device pixels and track the current page layout.
    crops = [
        ("dashboard_raw.png", (480, 60, 2080, 1690), "dash_top.png"),
        ("autopsy_raw.png", (300, 480, 1900, 2330), "autopsy_top.png"),
        ("dash_expanded_raw.png", (480, 2300, 2080, 5200), "dash_expanded_crop.png"),
    ]
    for raw, box, out in crops:
        Image.open(ASSETS / raw).crop(box).save(ASSETS / out)

    print("5/5 storyboard frames")
    subprocess.run([py, str(HERE / "frames.py")], check=True)
    print(f"done -> {BUILD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
