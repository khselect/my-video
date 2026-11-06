#!/usr/bin/env python3
"""Fish Audio (claude.ai connector "Fish Audio" MCP) for Lecture Studio: clone my voice, narrate with it.

The MCP tools are only reachable from Claude, so each step runs a short, tightly scoped `claude -p`
(only the named Fish tools + curl for upload/download). Everything else (audio prep, caching, timing,
manifest) stays deterministic in Python / tools/narrate.py.

  python tools/fish_audio.py clone  <recording> --title "내 목소리" --consent      # -> ~/.edu-video/voices/fish.json
  python tools/fish_audio.py verify <recording>                                   # only if clone asked for verification
  python tools/fish_audio.py narrate <scenes.json> --out build/audio [--voice-id ID] [--force [ids]]

Costs: cloning is done by Fish; text_to_speech is charged by Fish credits (~1 credit per UTF-8 byte of text,
Korean ~3 bytes per character). narrate checks the balance first and stops if it would not cover the job.
Only clone a voice you own or have written consent for.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import narrate as N  # noqa: E402  (scene_text / scene_hash / fish_file: same cache key as narrate.py)

VOICES_DIR = Path(os.environ.get("EDU_VOICES_DIR", Path.home() / ".edu-video" / "voices"))
STATE = VOICES_DIR / "fish.json"
MAX_BYTES = 500          # Fish MCP per-call TTS text budget (get_credit_balance.tts_max_text_bytes_per_call)
TOOL = "mcp__claude_ai_Fish_Audio__"


def state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_state(d: dict) -> None:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prep(recording: Path) -> Path:
    """Clean mono 44.1 kHz wav: rumble filter, trimmed silence, even loudness."""
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found")
    out = VOICES_DIR / f"fish-{time.strftime('%Y%m%d-%H%M%S')}.wav"
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    filt = ("highpass=f=70,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,"
            "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.25,areverse,"
            "loudnorm=I=-18:TP=-2:LRA=11")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(recording), "-ac", "1",
                    "-ar", "44100", "-af", filt, str(out)], check=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(out)], capture_output=True, text=True, check=True).stdout.strip())
    print(f"sample {out.name}  {dur:.1f}s", flush=True)
    if dur < 8:
        sys.exit("녹음이 너무 짧습니다 — 조용한 곳에서 15~60초 읽어 주세요")
    return out


def run_claude(claude: str, prompt: str, tools: list[str], bash: list[str], cwd: Path, watch=None) -> dict:
    """Run a scoped claude -p; return the JSON on its last 'RESULT:' line. watch() is polled while it runs."""
    cmd = [claude, "-p", prompt, "--permission-mode", "acceptEdits",
           "--allowedTools", "ToolSearch", *(TOOL + t for t in tools), *(f"Bash({b})" for b in bash)]
    with tempfile.TemporaryFile("w+", encoding="utf-8") as out:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True)
        while p.poll() is None:
            if watch:
                watch()
            time.sleep(1.5)
        if watch:
            watch()
        out.seek(0)
        text = out.read()
    print(text.strip()[-1500:], flush=True)
    m = re.findall(r"^RESULT:\s*(\{.*\})\s*$", text, re.M)
    if not m:
        sys.exit("Claude 가 결과(RESULT)를 남기지 않았습니다 — 위 로그를 확인하세요")
    res = json.loads(m[-1])
    if res.get("error"):
        sys.exit(f"Fish Audio: {res['error']}")
    return res


UPLOAD = """1. {t}get_upload_url 을 filename "{name}" 으로 호출한다.
2. Bash 로 정확히 이 형태만 실행해 파일을 올린다: curl -sSf -X PUT --upload-file "{path}" "<upload_url>"
   (실패하면 한 번만 새 upload_url 로 다시 시도)
3. 응답의 file_url 을 다음 단계에 쓴다."""


def cmd_clone(a) -> None:
    if not a.consent:
        sys.exit("--consent 없이 목소리를 복제하지 않습니다 (본인 목소리 또는 서면 동의가 필요)")
    wav = prep(Path(a.recording))
    prompt = f"""Fish Audio MCP 로 사용자의 목소리 화자를 만든다. 아래 도구 외에는 아무것도 호출하지 않는다.
먼저 ToolSearch 로 필요한 Fish Audio 도구를 불러온다.
{UPLOAD.format(t=TOOL, name=wav.name, path=wav)}
4. {TOOL}create_voice_clone 을 audio_urls=[file_url], confirm_voice_rights=true (사용자가 Studio 에서 본인 목소리임을 확인함),
   title="{a.title}", visibility="private" 로 호출한다. 경고가 나와도 proceed_despite_warnings 는 쓰지 않는다.
5. 마지막 줄에 정확히 한 줄로 결과를 출력한다 (JSON 한 줄):
   - 화자가 만들어졌으면: RESULT: {{"voice_id": "<id>", "title": "<title>"}}
   - 화자 본인 확인(verification_required)이 필요하면: RESULT: {{"status": "verification_required", "preflight_id": "<id>",
     "verification_text": "<사용자가 소리 내어 읽어야 할 문장 그대로>", "note": "<응답의 안내 한두 문장>"}}
   - 경고·실패면: RESULT: {{"error": "<이유를 한국어로 짧게>"}}"""
    res = run_claude(a.claude, prompt, ["get_upload_url", "create_voice_clone"],
                     ["curl -sSf -X PUT --upload-file *"], VOICES_DIR)
    st = state()
    if res.get("voice_id"):
        st.update({"voice_id": res["voice_id"], "title": res.get("title", a.title), "sample": wav.name,
                   "created": time.strftime("%Y-%m-%dT%H:%M:%S")})
        st.pop("pending", None)
        print(f"Fish 화자 생성: {res['voice_id']}")
    else:
        st["pending"] = {**res, "title": a.title, "sample": wav.name}
        print("본인 확인 필요: Studio 에 표시된 문장을 녹음해 올리세요")
    save_state(st)


def cmd_verify(a) -> None:
    st = state()
    pend = st.get("pending") or {}
    if not pend.get("preflight_id"):
        sys.exit("확인 대기 중인 복제가 없습니다")
    wav = prep(Path(a.recording))
    prompt = f"""Fish Audio MCP 로 목소리 복제의 화자 본인 확인을 마친다. 아래 도구 외에는 호출하지 않는다.
먼저 ToolSearch 로 필요한 Fish Audio 도구를 불러온다.
{UPLOAD.format(t=TOOL, name=wav.name, path=wav)}
4. {TOOL}verify_voice_clone 을 preflight_id="{pend['preflight_id']}", recording_url=file_url,
   title="{pend.get('title', '내 목소리')}", visibility="private" 로 호출한다.
5. 마지막 줄: RESULT: {{"voice_id": "<id>", "title": "<title>"}} 또는 RESULT: {{"error": "<이유>"}}"""
    res = run_claude(a.claude, prompt, ["get_upload_url", "verify_voice_clone"],
                     ["curl -sSf -X PUT --upload-file *"], VOICES_DIR)
    st.update({"voice_id": res["voice_id"], "title": res.get("title", pend.get("title")),
               "created": time.strftime("%Y-%m-%dT%H:%M:%S")})
    st.pop("pending", None)
    save_state(st)
    print(f"Fish 화자 생성: {res['voice_id']}")


def cmd_narrate(a) -> None:
    voice = a.voice_id or state().get("voice_id")
    if not voice:
        sys.exit("Fish 화자가 없습니다 — 4단계 '내 목소리 화자'에서 먼저 만드세요 (또는 --voice-id)")
    script = json.loads(a.scenes.read_text(encoding="utf-8"))
    lang = script.get("language", "korean")
    key = f"fish|{voice}|{lang}"   # must match narrate.Backend.settings_key for the fish backend
    force = None if a.force is None else set(a.force)
    todo = []
    for sc in script["scenes"]:
        text = N.scene_text(sc)
        if not text:
            continue
        h = N.scene_hash(sc, key)
        f = N.fish_file(a.out, sc["id"], h)
        if f.exists() and force is not None and (not force or sc["id"] in force):
            f.unlink()
        if not f.exists():
            if len(text.encode("utf-8")) > MAX_BYTES:
                sys.exit(f"{sc['id']}: 내레이션이 {len(text.encode())}바이트 — Fish 1회 한도 {MAX_BYTES}바이트(한글 약 160자) 이하로 줄이세요")
            todo.append({"id": sc["id"], "text": text, "out": str(f.resolve())})
    total = sum(len(t["text"].encode("utf-8")) for t in todo)
    print(f"fish todo {len(todo)} scenes, {total} bytes (~{total} credits)", flush=True)
    if todo:
        (a.out / "fish").mkdir(parents=True, exist_ok=True)
        seen = set()

        def watch():
            for t in todo:
                if t["id"] not in seen and Path(t["out"]).exists() and Path(t["out"]).stat().st_size > 1000:
                    seen.add(t["id"])
                    print(f"  fetched {t['id']}", flush=True)
        items = json.dumps(todo, ensure_ascii=False, indent=1)
        prompt = f"""Fish Audio MCP 로 강의 나레이션 음성 파일을 만든다. 아래 도구 외에는 호출하지 않는다.
먼저 ToolSearch 로 필요한 Fish Audio 도구를 불러온다.
1. {TOOL}get_credit_balance 를 호출한다. package_balance + package_extra_balance 가 {int(total * 1.1) + 10} 보다 작으면
   아무것도 생성하지 말고 마지막 줄에 RESULT: {{"error": "Fish 크레딧 부족 (필요 약 {total}, 잔액 <값>)"}} 를 출력하고 끝낸다.
2. 아래 항목마다 순서대로 {TOOL}text_to_speech 를 text=<text 그대로, 고치지 않음>, voice_id="{voice}", model="s2.1-pro" 로 호출하고
   (dry_run 쓰지 않음, 항목당 한 번만. 실패한 항목만 한 번 다시 시도),
   받은 오디오 URL 을 Bash 로 정확히 이 형태로 받는다: curl -sSfL -o "<out>" "<audio url>"
{items}
3. 마지막 줄: RESULT: {{"done": <받은 개수>, "failed": [<실패한 id>]}}"""
        res = run_claude(a.claude, prompt, ["get_credit_balance", "text_to_speech"], ["curl -sSfL -o *"],
                         a.out / "fish", watch)
        missing = [t["id"] for t in todo if not Path(t["out"]).exists()]
        if missing:
            sys.exit(f"음성을 받지 못한 장면: {', '.join(missing)} ({res})")
    # convert + lay out on the timeline with the normal narration pipeline (cache, manifest, narration.wav)
    cmd = [sys.executable, str(Path(__file__).with_name("narrate.py")), str(a.scenes), "--out", str(a.out),
           "--backend", "fish", "--fish-voice", voice]
    if a.force is not None:
        cmd += ["--force", *a.force]
    sys.exit(subprocess.run(cmd).returncode)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claude", default=shutil.which("claude") or "claude")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("clone"); p.add_argument("recording"); p.add_argument("--title", default="내 목소리")
    p.add_argument("--consent", action="store_true", help="the recording is my own voice (or I have written consent)")
    p = sub.add_parser("verify"); p.add_argument("recording")
    p = sub.add_parser("narrate"); p.add_argument("scenes", type=Path)
    p.add_argument("--out", type=Path, default=Path("build/audio")); p.add_argument("--voice-id")
    p.add_argument("--force", nargs="*", metavar="ID")
    p = sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "narrate":
        a.out = a.out.resolve()
    {"clone": cmd_clone, "verify": cmd_verify, "narrate": cmd_narrate,
     "status": lambda _a: print(json.dumps(state(), ensure_ascii=False, indent=2))}[a.cmd](a)


if __name__ == "__main__":
    main()
