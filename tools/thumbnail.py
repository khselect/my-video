#!/usr/bin/env python3
"""YouTube thumbnail helpers for Lecture Studio stage 7 (publish).

    thumbnail.py frames <video> <out_dir> [--n 6]     # evenly spaced 1280x720 stills from a render, f1.jpg ...
    thumbnail.py capture <html> [<html> ...]          # each page -> <name>.png (1280x720) next to it
    thumbnail.py final <png> <out.jpg>                # YouTube upload file: 1280x720 JPG under 2 MB

capture uses a local Chrome/Chromium in headless mode with a throwaway profile (never the user's running
browser). Set $CHROME to pick a binary. ffmpeg/ffprobe do the rest. Nothing leaves this machine except
web fonts the page itself asks for.
"""
import argparse
import glob
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

W, H = 1280, 720
YT_MAX = 2 * 1024 * 1024


def find_chrome() -> str:
    cands = [os.environ.get("CHROME", ""),
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "/Applications/Chromium.app/Contents/MacOS/Chromium",
             "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
             *(shutil.which(n) or "" for n in ("google-chrome", "chromium", "chromium-browser", "chrome")),
             *sorted(glob.glob(str(Path.home() / "Library/Caches/ms-playwright/chromium-*/chrome-mac*/*.app/Contents/MacOS/*")),
                     reverse=True)]
    for c in cands:
        if c and Path(c).is_file():
            return c
    sys.exit("Chrome/Chromium 을 찾지 못했습니다 — Google Chrome 을 설치하거나 CHROME 환경변수로 경로를 지정하세요")


def png_size(p: Path) -> tuple[int, int]:
    with p.open("rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def capture(pages: list[Path]) -> None:
    chrome = find_chrome()
    for page in pages:
        out = page.with_suffix(".png")
        prof = tempfile.mkdtemp(prefix="thumb-chrome-")
        try:
            # a bit taller window: some Chrome builds subtract browser chrome from the window height
            cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                   "--no-default-browser-check", f"--user-data-dir={prof}", "--force-device-scale-factor=1",
                   f"--window-size={W},{H}", "--virtual-time-budget=5000", "--run-all-compositor-stages-before-draw",
                   f"--screenshot={out}", page.resolve().as_uri()]
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
        finally:
            shutil.rmtree(prof, ignore_errors=True)
        if not out.exists():
            print(r.stdout[-2000:])
            sys.exit(f"캡처 실패: {page.name}")
        w, h = png_size(out)
        if (w, h) != (W, H):   # normalise whatever the browser produced to exactly 1280x720
            tmp = out.with_suffix(".tmp.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-vf",
                            f"crop=min(iw\\,{W}):min(ih\\,{H}):0:0,scale={W}:{H}", str(tmp)], check=True)
            tmp.replace(out)
        print(f"captured {out.name} ({out.stat().st_size // 1024} KB)")


def frames(video: Path, out_dir: Path, n: int) -> None:
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
                           capture_output=True, text=True, check=True)
    dur = float(json.loads(probe.stdout)["format"]["duration"])
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("f*.jpg"):
        old.unlink()
    for i in range(n):   # skip the first/last 8 % (titles fading in, end card)
        t = dur * (0.08 + 0.84 * (i + 0.5) / n)
        dst = out_dir / f"f{i + 1}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "-q:v", "3", str(dst)],
                       check=True)
        print(f"{dst.name} @ {t:.1f}s")


def final(png: Path, out: Path) -> None:
    for q in (2, 3, 5, 8, 12):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(png), "-vf", f"scale={W}:{H}", "-q:v", str(q), str(out)],
                       check=True)
        if out.stat().st_size <= YT_MAX:
            print(f"{out.name} {out.stat().st_size // 1024} KB (q={q})")
            return
    sys.exit("2MB 이하로 줄이지 못했습니다")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("frames"); f.add_argument("video", type=Path); f.add_argument("out_dir", type=Path)
    f.add_argument("--n", type=int, default=6)
    c = sub.add_parser("capture"); c.add_argument("pages", type=Path, nargs="+")
    z = sub.add_parser("final"); z.add_argument("png", type=Path); z.add_argument("out", type=Path)
    a = ap.parse_args()
    if a.cmd == "frames":
        frames(a.video, a.out_dir, a.n)
    elif a.cmd == "capture":
        capture(a.pages)
    else:
        final(a.png, a.out)


if __name__ == "__main__":
    main()
