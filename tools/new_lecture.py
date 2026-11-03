#!/usr/bin/env python3
"""Create a lecture project: lectures/<slug>/ = HyperFrames project + local GSAP + Korean font.

usage: python tools/new_lecture.py <slug> [--source sources/file.pdf] [--with-example]
       python tools/new_lecture.py <slug> --restore-assets     # after git pull on another machine

Vendored assets (assets/vendor, assets/fonts) are git-ignored and re-fetched from npm here,
so a fresh clone on the MacBook only needs --restore-assets.
Works on Windows, macOS and Linux (uses npx/npm from PATH).
"""
import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LECTURES = ROOT / "lectures"
EXAMPLE = ROOT / ".claude" / "skills" / "edu-video" / "templates" / "example-lecture"
GSAP = "gsap@3.15.0"
FONT = "pretendard@1.3.9"


def tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        sys.exit(f"{name} not found on PATH (install Node.js 22+)")
    return path


def npm_unpack(spec: str, dest: Path) -> Path:
    out = subprocess.run([tool("npm"), "pack", spec, "--silent"], cwd=dest, capture_output=True, text=True, check=True)
    tgz = dest / out.stdout.strip().splitlines()[-1]
    with tarfile.open(tgz) as t:
        t.extractall(dest / spec.split("@")[0], filter="data")
    return dest / spec.split("@")[0] / "package"


def restore_assets(project: Path) -> None:
    (project / "assets" / "vendor").mkdir(parents=True, exist_ok=True)
    (project / "assets" / "fonts").mkdir(parents=True, exist_ok=True)
    (project / "assets" / "voice").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        gsap = npm_unpack(GSAP, tmp)
        shutil.copy(gsap / "dist" / "gsap.min.js", project / "assets" / "vendor" / "gsap.min.js")
        font = npm_unpack(FONT, tmp)
        for w in ("Regular", "Bold", "Black"):
            shutil.copy(font / "dist" / "web" / "static" / "woff2" / f"Pretendard-{w}.woff2", project / "assets" / "fonts")
    print(f"assets ready: {GSAP}, {FONT}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--source", help="document in sources/ to attach")
    ap.add_argument("--title", default="")
    ap.add_argument("--with-example", action="store_true", help="start from the 45 s reference lecture")
    ap.add_argument("--restore-assets", action="store_true", help="only re-fetch vendored GSAP and fonts")
    a = ap.parse_args()

    project = LECTURES / a.slug
    if a.restore_assets:
        if not project.exists():
            sys.exit(f"{project} does not exist")
        restore_assets(project)
        return
    if project.exists():
        sys.exit(f"{project} already exists")
    LECTURES.mkdir(exist_ok=True)

    subprocess.run([tool("npx"), "--yes", "hyperframes", "init", str(project), "--example=blank",
                    "--non-interactive", "--skip-skills"], check=True)
    for d in ("compositions", "source", "build", "renders"):
        (project / d).mkdir(exist_ok=True)
    restore_assets(project)

    index = project / "index.html"
    if a.with_example:
        shutil.copy(EXAMPLE / "index.html", index)
        for f in (EXAMPLE / "compositions").glob("*.html"):
            shutil.copy(f, project / "compositions" / f.name)
    else:
        text = index.read_text(encoding="utf-8")
        import re
        index.write_text(re.sub(r"https://cdn\.jsdelivr\.net/npm/gsap@[0-9.]+/dist/gsap\.min\.js",
                                "assets/vendor/gsap.min.js", text), encoding="utf-8")

    state = {"slug": a.slug, "title": a.title or a.slug, "source": a.source, "brief": {}, "stages": {}}
    (project / "lecture.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"lecture ready: {project}")


if __name__ == "__main__":
    main()
