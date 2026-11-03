#!/usr/bin/env python3
"""Lecture Studio — a local human-in-the-loop app for the edu-video pipeline.

    python studio/app.py            # http://127.0.0.1:8765
    python studio/app.py --port 9000

Each lecture walks seven gates; nothing moves on until you approve it:
  1 source     pick the document, check the extracted text
  2 brief      one idea, audience, emphasis, length, voice
  3 script     Claude drafts scenes.json, you edit and approve
  4 narration  narrate.py per scene, you listen, redo single scenes, approve
  5 visuals    Claude builds HyperFrames scenes to the narration timing, you review snapshots and give feedback
  6 render     versioned render into renders/, you watch and approve
  7 publish    checklist (AI voice disclosure, licences, facts) before posting

Editing an earlier stage marks every later approval stale.
Standard library only; long steps run as background jobs with a live log.
Binds to 127.0.0.1 only.
"""
import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
LECTURES = ROOT / "lectures"
SOURCES = ROOT / "sources"
TOOLS = ROOT / "tools"
STUDIO = ROOT / "studio"
CONFIG = STUDIO / "config.local.json"   # per machine, git-ignored

STAGES = ["source", "brief", "script", "narration", "visuals", "render", "publish"]
PUBLISH_CHECKS = [
    "AI 합성 음성/영상 표시를 업로드 화면에서 체크했다",
    "화면의 숫자·사실을 원문과 대조했다",
    "도구 라이선스를 확인했다 (Remotion: 4인 이상 회사는 유료)",
    "클론한 목소리는 본인 목소리다 (타인은 서면 동의)",
    "제목·설명·썸네일(0초 프레임)을 확인했다",
]
DEFAULT_CONFIG = {
    "qwen_python": sys.executable,       # e.g. C:\\Developments\\qwen-tts-env\\Scripts\\python.exe
    "narrate_backend": "customvoice",    # customvoice | clone | silent
    "speaker": "sohee",
    "voice": "me",
    "claude_cmd": "claude",
}
SLUG_RE = re.compile(r"^[A-Za-z0-9가-힣._-]{1,80}$")


# ---------------- config / state ----------------

def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lecture_dir(slug: str) -> Path:
    if not SLUG_RE.match(slug or ""):
        raise ValueError("bad lecture name")
    d = LECTURES / slug
    if not d.is_dir():
        raise FileNotFoundError(slug)
    return d


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_state(slug: str) -> dict:
    d = lecture_dir(slug)
    st = read_json(d / "lecture.json", {"slug": slug, "title": slug, "brief": {}, "stages": {}})
    st.setdefault("stages", {})
    st.setdefault("brief", {})
    return st


def save_state(slug: str, st: dict) -> None:
    write_json(lecture_dir(slug) / "lecture.json", st)


def mark_changed(st: dict, stage: str) -> None:
    """Editing a stage un-approves it and marks every later approval stale."""
    i = STAGES.index(stage)
    for s in STAGES[i:]:
        rec = st["stages"].get(s)
        if rec and rec.get("status") == "approved":
            rec["status"] = "stale" if s != stage else "editing"
            rec["stale_since"] = time.strftime("%Y-%m-%dT%H:%M:%S")


def approve(st: dict, stage: str, note: str = "") -> None:
    i = STAGES.index(stage)
    for prev in STAGES[:i]:
        if st["stages"].get(prev, {}).get("status") != "approved":
            raise ValueError(f"'{prev}' 단계를 먼저 승인하세요")
    st["stages"][stage] = {"status": "approved", "approved_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "note": note}


# ---------------- background jobs ----------------

JOBS: dict[str, dict] = {}
JOB_LOCK = threading.Lock()


def run_job(slug: str, kind: str, cmd: list[str], cwd: Path, after=None) -> str:
    with JOB_LOCK:
        for j in JOBS.values():
            if j["slug"] == slug and j["status"] == "running":
                raise ValueError(f"'{j['kind']}' 작업이 진행 중입니다")
        job_id = uuid.uuid4().hex[:8]
        log = lecture_dir(slug) / "build" / "logs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        JOBS[job_id] = {"id": job_id, "slug": slug, "kind": kind, "status": "running", "log": str(log),
                        "cmd": cmd, "started": time.time(), "returncode": None}

    def worker():
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        with open(log, "w", encoding="utf-8", errors="replace") as f:
            f.write("$ " + " ".join(cmd) + "\n\n")
            f.flush()
            try:
                p = subprocess.Popen(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, env=env)
                rc = p.wait()
            except FileNotFoundError as e:
                f.write(f"\n실행 파일을 찾을 수 없습니다: {e}\n")
                rc = 127
        JOBS[job_id]["returncode"] = rc
        if rc == 0 and after:
            try:
                after()
            except Exception as e:  # noqa: BLE001
                with open(log, "a", encoding="utf-8") as f:
                    f.write(f"\n후처리 실패: {e}\n")
                rc = 1
        JOBS[job_id]["status"] = "done" if rc == 0 else "failed"
        JOBS[job_id]["ended"] = time.time()

    threading.Thread(target=worker, daemon=True).start()
    return job_id


def job_view(job: dict) -> dict:
    text = Path(job["log"]).read_text(encoding="utf-8", errors="replace") if Path(job["log"]).exists() else ""
    return {k: job[k] for k in ("id", "slug", "kind", "status", "returncode")} | {"log": text[-12000:]}


# ---------------- prompts for Claude Code ----------------

def prompt_script(slug: str, st: dict) -> str:
    b = st.get("brief", {})
    return f"""edu-video 스킬(.claude/skills/edu-video/SKILL.md)과 WORKFLOW.md 3장을 따른다.
lectures/{slug}/source/source.md 를 끝까지 읽고, 장면 대본 lectures/{slug}/scenes.json 을 scenes.example.json 형식으로 작성하라.
- 핵심 아이디어 하나: {b.get('one_idea', '(원문에서 정하라)')}
- 대상: {b.get('audience', '일반 학습자')}
- 강조할 관점: {b.get('emphasis', '없음')}
- 목표 길이: 약 {b.get('target_seconds', 60)}초 (장면당 4~9초, 내레이션 40~55자)
- language "korean", speaker "{b.get('speaker', 'sohee')}", voice "{b.get('voice', 'me')}" 를 최상위에 넣는다.
- 장면 id 는 s01, s02 ... ; shape 는 style-guide 의 7가지 중 장면마다 다르게.
- 원문에 없는 숫자는 쓰지 않는다. 영어 고유명사는 내레이션에서 한글 발음으로 적는다.
scenes.json 파일만 쓰고 끝낸다."""


def prompt_visuals(slug: str, feedback: dict | None = None) -> str:
    base = f"""edu-video 스킬과 HyperFrames 스킬(/hyperframes:hyperframes)의 Contract 를 따른다.
작업 폴더: lectures/{slug} (HyperFrames 프로젝트)
- 장면 내용: scenes.json (on_screen, visual, shape)
- 타이밍: build/audio/manifest.json 의 장면별 start/duration 을 그대로 쓴다. 각 요소는 내레이션이 그것을 말하는 순간 등장.
- 내레이션: assets/voice/narration.wav 를 루트 index.html 에 <audio id="vo" src="assets/voice/narration.wav" data-start="0" data-volume="1"> 로 넣는다.
- 루트 data-duration = manifest total_duration. 장면 하나 = compositions/<id>.html.
- 스타일: .claude/skills/edu-video/references/style-guide.md, 기준 구현 templates/example-lecture.
- 끝나면 lectures/{slug} 에서 npx hyperframes check --json 을 실행해 error 를 0개로 만든다."""
    if feedback:
        lines = "\n".join(f"- {sid}: {txt}" for sid, txt in feedback.items() if txt.strip())
        base += f"\n\n이미 만든 장면을 아래 피드백대로만 고친다(다른 장면은 건드리지 않는다):\n{lines}"
    return base


def claude_cmd(cfg: dict, prompt: str) -> list[str]:
    exe = shutil.which(cfg.get("claude_cmd", "claude")) or cfg.get("claude_cmd", "claude")
    return [exe, "-p", prompt, "--permission-mode", "acceptEdits",
            "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash(npx hyperframes:*),Bash(npx --yes hyperframes:*)"]


# ---------------- actions ----------------

def list_lectures() -> list[dict]:
    out = []
    if LECTURES.exists():
        for d in sorted(LECTURES.iterdir()):
            if d.is_dir() and (d / "lecture.json").exists():
                st = read_json(d / "lecture.json", {})
                done = [s for s in STAGES if st.get("stages", {}).get(s, {}).get("status") == "approved"]
                out.append({"slug": d.name, "title": st.get("title", d.name), "approved": len(done)})
    return out


def lecture_view(slug: str) -> dict:
    d = lecture_dir(slug)
    st = load_state(slug)
    src = d / "source" / "source.md"
    manifest = read_json(d / "build" / "audio" / "manifest.json")
    renders = read_json(d / "renders" / "manifest.json", {"versions": []})
    snaps = sorted((d / "build" / "snapshots").glob("*.jpg")) + sorted((d / "build" / "snapshots").glob("*.png"))
    running = [job_view(j) for j in JOBS.values() if j["slug"] == slug and j["status"] == "running"]
    return {
        "state": st, "stages": STAGES, "publish_checks": PUBLISH_CHECKS,
        "sources": sorted(p.name for p in SOURCES.glob("*") if p.is_file() and not p.name.startswith(".")),
        "source_preview": src.read_text(encoding="utf-8")[:6000] if src.exists() else "",
        "scenes": read_json(d / "scenes.json"),
        "audio": manifest,
        "snapshots": [p.relative_to(d).as_posix() for p in snaps],
        "renders": renders["versions"],
        "prompts": {"script": prompt_script(slug, st), "visuals": prompt_visuals(slug)},
        "running": running[0] if running else None,
    }


def do_action(slug: str, action: str, body: dict) -> dict:
    cfg = load_config()
    d = lecture_dir(slug)
    st = load_state(slug)
    py = sys.executable

    if action == "set_source":
        name = Path(body["file"]).name
        src = SOURCES / name
        if not src.exists():
            raise FileNotFoundError(name)
        st["source"] = f"sources/{name}"
        mark_changed(st, "source")
        save_state(slug, st)
        return {"job": run_job(slug, "extract", [py, str(TOOLS / "extract_source.py"), str(src), str(d)], ROOT)}

    if action == "save_brief":
        st["brief"] = {k: body.get(k, "") for k in ("one_idea", "audience", "emphasis", "target_seconds", "speaker", "voice")}
        st["title"] = body.get("title") or st.get("title", slug)
        mark_changed(st, "brief")
        save_state(slug, st)
        return {"ok": True}

    if action == "draft_script":
        return {"job": run_job(slug, "claude-script", claude_cmd(cfg, prompt_script(slug, st)), ROOT)}

    if action == "save_scenes":
        scenes = body["scenes"]
        ids = [s["id"] for s in scenes["scenes"]]
        if len(ids) != len(set(ids)) or not all(re.match(r"^[A-Za-z0-9_-]+$", i) for i in ids):
            raise ValueError("장면 id 가 비었거나 중복됩니다")
        write_json(d / "scenes.json", scenes)
        mark_changed(st, "script")
        save_state(slug, st)
        return {"ok": True}

    if action == "narrate":
        b = st.get("brief", {})
        backend = body.get("backend") or cfg["narrate_backend"]
        cmd = [cfg["qwen_python"] if backend != "silent" else py, str(TOOLS / "narrate.py"), str(d / "scenes.json"),
               "--out", str(d / "build" / "audio"), "--backend", backend,
               "--speaker", b.get("speaker") or cfg["speaker"], "--voice", b.get("voice") or cfg["voice"]]
        if body.get("force") is not None:
            cmd += ["--force", *body["force"]]
        st["stages"].setdefault("narration", {})
        mark_changed(st, "narration")
        save_state(slug, st)

        def copy_track():
            (d / "assets" / "voice").mkdir(parents=True, exist_ok=True)
            shutil.copy(d / "build" / "audio" / "narration.wav", d / "assets" / "voice" / "narration.wav")
        return {"job": run_job(slug, "narrate", cmd, ROOT, after=copy_track)}

    if action == "build_visuals":
        fb = body.get("feedback") or None
        st.setdefault("feedback", []).append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "items": fb}) if fb else None
        mark_changed(st, "visuals")
        save_state(slug, st)
        return {"job": run_job(slug, "claude-visuals", claude_cmd(cfg, prompt_visuals(slug, fb)), ROOT)}

    if action == "snapshot":
        out = d / "build" / "snapshots"
        if out.exists():
            shutil.rmtree(out)
        npx = shutil.which("npx") or "npx"
        return {"job": run_job(slug, "snapshot", [npx, "hyperframes", "snapshot", "--review", "-o", str(out)], d)}

    if action == "check":
        npx = shutil.which("npx") or "npx"
        return {"job": run_job(slug, "check", [npx, "hyperframes", "check"], d)}

    if action == "render":
        note = body.get("note", "")
        return {"job": run_job(slug, "render", [py, str(TOOLS / "render_version.py"), "render", str(d), "--note", note], ROOT)}

    if action == "approve":
        stage = body["stage"]
        if stage == "publish":
            checks = body.get("checks", [])
            if len(checks) != len(PUBLISH_CHECKS) or not all(checks):
                raise ValueError("게시 체크리스트를 모두 확인하세요")
            st["publish"] = {"version": body.get("version"), "url": body.get("url", ""),
                             "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if stage == "narration":
            st["narration_review"] = body.get("review", {})
        approve(st, stage, body.get("note", ""))
        save_state(slug, st)
        return {"ok": True}

    raise ValueError(f"unknown action {action}")


def new_lecture(body: dict) -> dict:
    slug = body.get("slug", "").strip()
    if not SLUG_RE.match(slug):
        raise ValueError("이름은 영문/한글/숫자/-_. 만 쓸 수 있습니다")
    if (LECTURES / slug).exists():
        raise ValueError("이미 있는 강의입니다")
    LECTURES.mkdir(exist_ok=True)
    cmd = [sys.executable, str(TOOLS / "new_lecture.py"), slug, "--title", body.get("title", slug)]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError((p.stdout + p.stderr)[-2000:])
    return {"slug": slug}


# ---------------- HTTP ----------------

class Handler(BaseHTTPRequestHandler):
    server_version = "LectureStudio/1.0"

    def log_message(self, fmt, *args):  # quieter console
        if "/api/jobs/" not in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))

    def send_json(self, data, status=HTTPStatus.OK):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def send_file(self, path: Path):
        if not path.is_file():
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        size = path.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):  # range support so <video>/<audio> can seek
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else max(0, size - int(b))
            end = int(b) if a and b else size - 1
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(1 << 16, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

    def guard(self, fn):
        try:
            fn()
        except (ValueError, KeyError) as e:
            self.send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
        except FileNotFoundError as e:
            self.send_json({"error": f"없음: {e}"}, HTTPStatus.NOT_FOUND)
        except Exception as e:  # noqa: BLE001
            self.send_json({"error": f"{type(e).__name__}: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        parts = [p for p in path.split("/") if p]
        def route():
            if path in ("/", "/index.html"):
                return self.send_file(STUDIO / "index.html")
            if parts[:2] == ["api", "lectures"] and len(parts) == 2:
                return self.send_json({"lectures": list_lectures(), "config": load_config()})
            if parts[:2] == ["api", "lectures"] and len(parts) == 3:
                return self.send_json(lecture_view(parts[2]))
            if parts[:2] == ["api", "jobs"] and len(parts) == 3:
                job = JOBS.get(parts[2])
                return self.send_json(job_view(job) if job else {"error": "no job"},
                                      HTTPStatus.OK if job else HTTPStatus.NOT_FOUND)
            if parts and parts[0] == "media" and len(parts) >= 3:
                base = lecture_dir(parts[1]).resolve()
                target = (base / "/".join(parts[2:])).resolve()
                if base not in target.parents:
                    raise ValueError("bad path")
                return self.send_file(target)
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        self.guard(route)

    def do_POST(self):
        parts = [p for p in unquote(urlparse(self.path).path).split("/") if p]
        def route():
            if parts == ["api", "lectures"]:
                return self.send_json(new_lecture(self.body()))
            if parts == ["api", "config"]:
                cfg = load_config()
                cfg.update({k: v for k, v in self.body().items() if k in DEFAULT_CONFIG})
                save_config(cfg)
                return self.send_json(cfg)
            if len(parts) == 4 and parts[:2] == ["api", "lectures"]:
                return self.send_json(do_action(parts[2], parts[3], self.body()))
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        self.guard(route)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    SOURCES.mkdir(exist_ok=True)
    LECTURES.mkdir(exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Lecture Studio: http://127.0.0.1:{a.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
