#!/usr/bin/env python3
"""Versioned renders: every render lands in <project>/renders/ with a version, date and source commit.

usage
  render_version.py render [project] [--composition ID] [--note "..."] [--engine auto|remotion|hyperframes] [-- extra render args]
  render_version.py add <file.mp4> [project] --note "..." [--from v003]   register a file made elsewhere (e.g. voice mux)
  render_version.py list [project]
  render_version.py show v003 [project]                                    details + how to restore that source

Files:  renders/v003_2026-11-03_a1b2c3d.mp4   (suffix -dirty when uncommitted changes were rendered)
        renders/manifest.json                 committed; the videos themselves are git-ignored

Revision = git commit of the source. To rebuild an old version: git checkout <commit>, then render again.
Every new version is loudness-normalized to -14 LUFS and checked by qa_render.py (blank/frozen frames,
loudness, read time): renders/<file>.qa.json + a summary under "qa" in the manifest.
Skip with --no-loudnorm / --no-qa. Uses the standard library plus git, npx and ffprobe (numpy for the QA).
"""
import argparse
import datetime as dt
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

GITIGNORE_LINES = ["renders/*.mp4", "renders/*.webm", "renders/*.mov", "!renders/manifest.json"]


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def git_state(project: Path) -> dict:
    if not shutil.which("git") or run(["git", "rev-parse", "--is-inside-work-tree"], project, False).returncode:
        return {"commit": "nogit", "dirty": False, "branch": None, "changed": []}
    commit = run(["git", "rev-parse", "--short=7", "HEAD"], project, False).stdout.strip() or "nocommit"
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], project, False).stdout.strip()
    status = run(["git", "status", "--porcelain", "--untracked-files=normal", "--", ".", ":!renders", ":!lecture.json", ":!.gitignore"], project).stdout
    changed = [line[3:] for line in status.splitlines() if line.strip()]
    return {"commit": commit, "dirty": bool(changed), "branch": branch, "changed": changed[:30]}


def media_info(path: Path) -> dict:
    info = {"bytes": path.stat().st_size}
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    info["sha256"] = h.hexdigest()
    if shutil.which("ffprobe"):
        out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                   "-of", "json", str(path)], path.parent, False).stdout
        try:
            j = json.loads(out)
            info["seconds"] = round(float(j["format"]["duration"]), 2)
            video = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
            if video:
                info["resolution"] = f"{video.get('width')}x{video.get('height')}"
            info["has_audio"] = any(s.get("codec_type") == "audio" for s in j.get("streams", []))
        except (ValueError, KeyError):
            pass
    return info


class Manifest:
    def __init__(self, project: Path):
        self.dir = project / "renders"
        self.path = self.dir / "manifest.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"versions": []}

    def next_version(self) -> str:
        nums = [int(v["version"][1:]) for v in self.data["versions"] if v["version"][1:].isdigit()]
        return f"v{(max(nums) + 1 if nums else 1):03d}"

    def get(self, version: str) -> dict:
        for v in self.data["versions"]:
            if v["version"] == version:
                return v
        sys.exit(f"{version} not in {self.path}")

    def last(self, key: str):
        for v in reversed(self.data["versions"]):
            if v.get(key):
                return v[key]
        return None

    def save(self, entry: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.data["versions"].append(entry)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_gitignore(project: Path) -> None:
    gi = project / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    missing = [line for line in GITIGNORE_LINES if line not in text.splitlines()]
    if missing:
        sep = "" if not text or text.endswith("\n") else "\n"
        gi.write_text(text + sep + "\n# versioned renders (edu-video render_version.py)\n" + "\n".join(missing) + "\n",
                      encoding="utf-8")
        print(f".gitignore: added {', '.join(missing)}")


def detect_engine(project: Path) -> str:
    if (project / "hyperframes.json").exists():
        return "hyperframes"
    pkg = project / "package.json"
    if pkg.exists() and "remotion" in pkg.read_text(encoding="utf-8"):
        return "remotion"
    sys.exit("cannot tell the engine: pass --engine remotion|hyperframes")


def finalize(project: Path, video: Path, a) -> dict:
    """Loudness-normalize, then run the automatic checks. Returns {"qa": summary} for the manifest entry."""
    if getattr(a, "no_qa", False) and getattr(a, "no_loudnorm", False):
        return {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import qa_render
    except ImportError as e:  # numpy missing on this machine: keep the render, say why there is no QA
        print(f"qa skipped: {e}")
        return {}
    if not getattr(a, "no_loudnorm", False):
        n = qa_render.normalize(video)
        print("loudness: " + (f"normalized {n['before_lufs']:.1f} -> {qa_render.TARGET_LUFS:g} LUFS" if n.get("done")
                              else f"unchanged ({n.get('reason')})"))
    if getattr(a, "no_qa", False):
        return {}
    lecture = project if (project / "scenes.json").exists() else None
    qa = qa_render.run_qa(video, lecture)
    (video.parent / (video.name + ".qa.json")).write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n",
                                                           encoding="utf-8")
    for k, c in qa["checks"].items():
        print(f"qa {c['status']:<4} {k:<9} {c['message']}")
    return {"qa": qa_render.summary(qa)}


def file_name(version: str, commit: str, dirty: bool, ext: str = ".mp4") -> str:
    return f"{version}_{dt.date.today().isoformat()}_{commit}{'-dirty' if dirty else ''}{ext}"


def cmd_render(a) -> None:
    project = Path(a.project).resolve()
    m = Manifest(project)
    engine = detect_engine(project) if a.engine == "auto" else a.engine
    git = git_state(project)
    if git["dirty"] and a.require_clean:
        sys.exit("uncommitted changes (commit first, or drop --require-clean):\n  " + "\n  ".join(git["changed"]))
    version = m.next_version()
    out = m.dir / file_name(version, git["commit"], git["dirty"])
    m.dir.mkdir(parents=True, exist_ok=True)
    rel_out = str(out.relative_to(project))

    composition = None
    if engine == "remotion":
        composition = a.composition or m.last("composition")
        if not composition:
            sys.exit("Remotion needs --composition (see: npx remotion compositions)")
        cmd = ["npx", "remotion", "render", composition, rel_out, *a.extra]
    else:
        cmd = ["npx", "hyperframes", "render", "-o", rel_out, *a.extra]

    print(f"{version}: {' '.join(shlex.quote(c) for c in cmd)}")
    started = dt.datetime.now()
    proc = subprocess.run(cmd, cwd=project)
    if proc.returncode or not out.exists():
        sys.exit(f"render failed (exit {proc.returncode}); nothing recorded")
    render_seconds = round((dt.datetime.now() - started).total_seconds(), 1)
    checked = finalize(project, out, a)

    entry = {
        "version": version, "file": out.name, "kind": "render", "engine": engine, "composition": composition,
        "created": started.isoformat(timespec="seconds"),
        "render_seconds": render_seconds,
        "source": git, "command": " ".join(cmd), "note": a.note or "", **media_info(out), **checked,
    }
    m.save(entry)
    ensure_gitignore(project)
    print(f"-> renders/{out.name}  ({entry.get('seconds', '?')} s, {entry['bytes'] / 1e6:.1f} MB)")
    if git["dirty"]:
        print("note: rendered with uncommitted changes; commit them so this version can be rebuilt")


def cmd_add(a) -> None:
    project = Path(a.project).resolve()
    src = Path(a.file).resolve()
    if not src.exists():
        sys.exit(f"{src} not found")
    m = Manifest(project)
    if a.from_version:
        m.get(a.from_version)
    git = git_state(project)
    version = m.next_version()
    out = m.dir / file_name(version, git["commit"], git["dirty"], src.suffix or ".mp4")
    m.dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), out) if a.move else shutil.copy2(src, out)
    checked = finalize(project, out, a)
    entry = {"version": version, "file": out.name, "kind": a.kind, "derived_from": a.from_version,
             "created": dt.datetime.now().isoformat(timespec="seconds"), "source": git,
             "original_path": str(src), "note": a.note or "", **media_info(out), **checked}
    m.save(entry)
    ensure_gitignore(project)
    print(f"{version} -> renders/{out.name}")


def cmd_list(a) -> None:
    m = Manifest(Path(a.project).resolve())
    if not m.data["versions"]:
        print("no versions yet")
        return
    print(f"{'ver':<6}{'date':<12}{'commit':<15}{'kind':<8}{'sec':>7}{'MB':>7}  note")
    for v in m.data["versions"]:
        commit = v["source"]["commit"] + ("*" if v["source"]["dirty"] else "")
        print(f"{v['version']:<6}{v['created'][:10]:<12}{commit:<15}{v['kind']:<8}"
              f"{v.get('seconds', 0):>7}{v['bytes'] / 1e6:>7.1f}  {v.get('note', '')}")
    print("* = rendered with uncommitted changes")


def cmd_show(a) -> None:
    project = Path(a.project).resolve()
    v = Manifest(project).get(a.version)
    print(json.dumps(v, ensure_ascii=False, indent=2))
    f = project / "renders" / v["file"]
    print(f"\nfile: {f}" + ("" if f.exists() else "  (missing on this machine)"))
    c = v["source"]["commit"]
    if c not in ("nogit", "nocommit"):
        print(f"rebuild: git stash -u && git checkout {c}  ->  render again  ->  git checkout {v['source']['branch']} && git stash pop")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("render", help="render a new version")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--engine", default="auto", choices=["auto", "remotion", "hyperframes"])
    p.add_argument("--composition", help="Remotion composition id (remembered from the last version)")
    p.add_argument("--note", help="what changed in this version")
    p.add_argument("--require-clean", action="store_true", help="refuse to render uncommitted changes")
    p.add_argument("--no-loudnorm", action="store_true", help="keep the audio level as rendered")
    p.add_argument("--no-qa", action="store_true", help="skip the automatic checks")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("add", help="register an existing video as a new version")
    p.add_argument("file")
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--note")
    p.add_argument("--from", dest="from_version", help="the version this one was made from")
    p.add_argument("--kind", default="derived", help="e.g. voiced, music, final")
    p.add_argument("--move", action="store_true", help="move instead of copy")
    p.add_argument("--no-loudnorm", action="store_true", help="keep the audio level as it is")
    p.add_argument("--no-qa", action="store_true", help="skip the automatic checks")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("list", help="list versions")
    p.add_argument("project", nargs="?", default=".")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("show", help="details of one version")
    p.add_argument("version")
    p.add_argument("project", nargs="?", default=".")
    p.set_defaults(fn=cmd_show)

    argv = sys.argv[1:]
    extra = []
    if "--" in argv:  # everything after -- goes to the render command untouched
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    a = ap.parse_args(argv)
    a.extra = extra
    a.fn(a)


if __name__ == "__main__":
    main()
