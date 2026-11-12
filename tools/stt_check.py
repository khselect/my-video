#!/usr/bin/env python3
"""Listen back to the narration: transcribe each scene's audio and compare it with the script.

  python tools/stt_check.py <lecture> [--engine auto|faster-whisper|hyperframes|file] [--model small]
                            [--scenes s02 s05] [--heard heard.json] [--accept accept.json]

Catches what a person skims over: misread proper nouns and numbers, dropped or repeated words,
a sentence cut short. For every scene in build/audio/manifest.json:
  heard     what the speech recogniser hears (Korean)
  match     1 - character error rate, after removing spaces/punctuation and reading digits the same way
  diffs     word-level differences: script "…" -> heard "…"
  status    pass (match >= 92%) / warn (>= 80%) / fail (< 80%) / accepted (a person listened and it is right)
            A misheard key term — a word also shown on screen (on_screen), or one with digits or Latin
            letters — makes a scene at least "warn" even when the overall match is high (one wrong name
            is only 1 character in 30).
Results go to build/audio/stt.json and are cached per scene audio hash + engine + model, so after
regenerating two scenes only those two are transcribed again.

Engines (auto = first that works):
  faster-whisper  Python package faster-whisper in this interpreter (model downloads once, ~460 MB for small)
  hyperframes     `npx hyperframes transcribe` (whisper.cpp; installs its runtime and model on first use)
  file            --heard <json> {scene id: text} — import a transcript made elsewhere (also used in tests)
A recogniser makes its own mistakes, especially on short lines: when a flagged scene sounds right,
accept it (Studio "맞게 들림") — the acceptance holds until that scene's audio changes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

PASS_MATCH, WARN_MATCH = 0.92, 0.80
HF_VERSION = "0.9.7"   # same pin as the lecture projects

DIGITS = "영일이삼사오육칠팔구"
UNITS = [(10 ** 8, "억"), (10 ** 4, "만"), (1000, "천"), (100, "백"), (10, "십")]


def sino(n: int) -> str:
    """Sino-Korean reading of an integer (123 -> 백이십삼). Native counters (세 개) are not guessed."""
    if n == 0:
        return "영"
    out = ""
    for v, name in UNITS:
        q, n = divmod(n, v)
        if q:
            out += ("" if q == 1 and v < 10 ** 8 else sino(q)) + name
    return out + (DIGITS[n] if n else "")


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFC", text or "").lower()
    t = re.sub(r"\d+(?:\.\d+)?", lambda m: "점".join(sino(int(p)) for p in m.group(0).split(".")), t)
    return re.sub(r"[\W_]+", "", t)


def cer(ref: str, hyp: str) -> float:
    a, b = normalize(ref), normalize(hyp)
    if not a:
        return 0.0 if not b else 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return min(1.0, prev[-1] / len(a))


def word_diffs(ref: str, hyp: str) -> list[dict]:
    rw = [w for w in re.split(r"\s+", ref.strip()) if w]
    hw = [w for w in re.split(r"\s+", hyp.strip()) if w]
    rn, hn = [normalize(w) for w in rw], [normalize(w) for w in hw]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=rn, b=hn, autojunk=False).get_opcodes():
        if op != "equal":
            exp, got = " ".join(rw[i1:i2]), " ".join(hw[j1:j2])
            if normalize(exp) != normalize(got):        # only spacing differs: not a reading error
                out.append({"script": exp, "heard": got})
    return out


# ---------------- engines ----------------

class Engine:
    name = "?"

    def __init__(self, model: str):
        self.model = model

    def transcribe(self, wav: Path, scene_id: str) -> str:
        raise NotImplementedError


class FasterWhisper(Engine):
    name = "faster-whisper"

    def __init__(self, model: str):
        super().__init__(model)
        from faster_whisper import WhisperModel   # noqa: PLC0415 (optional dependency)
        self.m = WhisperModel(model, device="auto", compute_type="auto")

    def transcribe(self, wav: Path, scene_id: str) -> str:
        segs, _ = self.m.transcribe(str(wav), language="ko", beam_size=5, vad_filter=False,
                                    condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segs).strip()


class HyperFrames(Engine):
    name = "hyperframes"

    def __init__(self, model: str):
        super().__init__(model)
        self.npx = shutil.which("npx")
        if not self.npx:
            raise RuntimeError("npx not found")

    def transcribe(self, wav: Path, scene_id: str) -> str:
        with tempfile.TemporaryDirectory() as td:   # transcribe writes into its project dir: keep it out of ours
            r = subprocess.run([self.npx, "--yes", f"hyperframes@{HF_VERSION}", "transcribe", str(wav), "-d", td,
                                "-l", "ko", "-m", self.model, "--json"], capture_output=True, text=True, timeout=900)
            if r.returncode:   # with --json the CLI reports {"ok": false, "error": {...}} on stdout
                msg = r.stderr.strip()[-400:]
                try:
                    msg = json.loads(r.stdout.strip().splitlines()[-1])["error"]["message"]
                except (ValueError, KeyError, IndexError, TypeError):
                    msg = msg or r.stdout.strip()[-400:]
                raise RuntimeError(msg or f"exit {r.returncode}")
            return _words_to_text(r.stdout) or _words_to_text(_newest_json(Path(td)))


def _newest_json(d: Path) -> str:
    files = sorted(d.rglob("*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1].read_text(encoding="utf-8") if files else ""


def _words_to_text(raw: str) -> str:
    """Pull the spoken text out of whatever JSON shape the transcriber printed."""
    try:
        data = json.loads(raw)
    except ValueError:
        lines = [l for l in raw.splitlines() if l.strip().startswith("{")]
        data = json.loads(lines[-1]) if lines else None
    if data is None:
        return ""
    if isinstance(data, dict):
        for k in ("text", "transcript"):
            if isinstance(data.get(k), str):
                return data[k].strip()
        for k in ("words", "segments", "transcript", "result"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    if isinstance(data, list):
        parts = [str(w.get("text") or w.get("word") or "") for w in data if isinstance(w, dict)]
        return re.sub(r"\s+", " ", " ".join(p.strip() for p in parts)).strip()
    return ""


class FromFile(Engine):
    name = "file"

    def __init__(self, model: str, heard: Path):
        super().__init__(model)
        self.heard = json.loads(heard.read_text(encoding="utf-8"))

    def transcribe(self, wav: Path, scene_id: str) -> str:
        if scene_id not in self.heard:
            raise RuntimeError(f"no transcript for {scene_id} in --heard file")
        return self.heard[scene_id]


def make_engine(kind: str, model: str, heard: Path | None) -> Engine:
    if kind == "file":
        if not heard:
            sys.exit("--engine file needs --heard <json>")
        return FromFile(model, heard)
    errors = []
    for k in (["faster-whisper", "hyperframes"] if kind == "auto" else [kind]):
        try:
            return FasterWhisper(model) if k == "faster-whisper" else HyperFrames(model)
        except Exception as e:  # noqa: BLE001 — try the next engine, report all at the end
            errors.append(f"{k}: {e}")
    sys.exit("no speech recogniser available — " + "; ".join(errors) +
             "\n  install one: pip install faster-whisper  (or let npx hyperframes transcribe install whisper.cpp)")


# ---------------- main ----------------

def classify(match: float) -> str:
    return "pass" if match >= PASS_MATCH else "warn" if match >= WARN_MATCH else "fail"


STOP_STEMS = {"하는", "하지", "하고", "해요", "있는", "있어", "없는", "그리", "그런", "이런", "저런", "우리", "모든",
              "어떻", "이라", "라는", "에서", "으로", "그리고", "하나"}


def recurring_stems(scenes: dict) -> set[str]:
    """2-character word stems that occur in the narration of two or more scenes (names, the topic word)."""
    seen: dict[str, set] = {}
    for sid, sc in scenes.items():
        for w in re.split(r"\s+", sc.get("narration") or sc.get("text") or ""):
            n = normalize(w)
            if len(n) >= 2 and n[:2] not in STOP_STEMS:
                seen.setdefault(n[:2], set()).add(sid)
    return {k for k, v in seen.items() if len(v) >= 2}


def key_terms(scene: dict, recurring: set[str] | None = None) -> set[str]:
    """Words worth hearing exactly: shown on screen, containing digits / Latin letters, or recurring across
    scenes (a character's name, the topic word)."""
    shown = scene.get("on_screen") or ""
    shown = " ".join(map(str, shown)) if isinstance(shown, list) else str(shown)
    words = {normalize(w) for w in re.split(r"\s+", shown) if len(normalize(w)) >= 2}
    narr = scene.get("narration") or scene.get("text") or ""
    words |= {normalize(w) for w in re.split(r"\s+", narr) if re.search(r"[0-9A-Za-z]", w)}
    words |= {normalize(w)[:2] for w in re.split(r"\s+", narr) if normalize(w)[:2] in (recurring or set())}
    return {w for w in words if w}


def touches_key(diff: dict, keys: set[str]) -> list[str]:
    s = normalize(diff["script"])
    # a key term matches a script word by its stem (Korean particles follow the noun: 지우는 / 지우가)
    return sorted(k for k in keys if k and (k in s or (len(s) >= 2 and s[:-1] and k.startswith(s[:-1]))))


def run(lecture: Path, engine: Engine, only: list[str] | None = None, accept: dict | None = None) -> dict:
    audio = lecture / "build" / "audio"
    manifest = json.loads((audio / "manifest.json").read_text(encoding="utf-8"))
    scenes = {s["id"]: s for s in json.loads((lecture / "scenes.json").read_text(encoding="utf-8"))["scenes"]}
    script = {k: (s.get("narration") or s.get("text") or "").strip() for k, s in scenes.items()}
    out_p = audio / "stt.json"
    old = json.loads(out_p.read_text(encoding="utf-8")) if out_p.exists() else {}
    cache = {r["id"]: r for r in old.get("scenes", [])}
    accept = accept or {}
    rec = recurring_stems(scenes)
    rows = []
    for sc in manifest["scenes"]:
        sid, wav = sc["id"], audio / (sc.get("file") or "")
        expected = script.get(sid, "")
        if not sc.get("file") or not wav.exists() or not expected:
            continue
        key = f"{sc.get('hash')}|{engine.name}|{engine.model}"
        prev = cache.get(sid)
        if prev and prev.get("key") == key and (only is None or sid not in only):
            heard = prev["heard"]
            print(f"scene {sid} cached", flush=True)
        else:
            print(f"scene {sid} transcribing…", flush=True)
            try:
                heard = engine.transcribe(wav, sid)
            except Exception as e:  # noqa: BLE001 — one clear line for the Studio log instead of a traceback
                hint = (" — 모델을 내려받지 못했습니다(네트워크). 인터넷이 되는 곳에서 한 번 실행하면 이후엔 오프라인으로 됩니다"
                        if re.search(r"ENOTFOUND|huggingface|resolve|connect|network|timed out", str(e), re.I) else "")
                sys.exit(f"음성 인식 실패 ({engine.name} {engine.model}, 장면 {sid}): {e}{hint}")
        match = round(1 - cer(expected, heard), 3)
        status = classify(match)
        diffs = word_diffs(expected, heard)
        keys = key_terms(scenes.get(sid, {}), rec)
        missed = sorted({k for d in diffs for k in touches_key(d, keys)})
        if missed and status == "pass":
            status = "warn"
        if status != "pass" and accept.get(sid) == sc.get("hash"):
            status = "accepted"
        rows.append({"id": sid, "key": key, "hash": sc.get("hash"), "script": expected, "heard": heard,
                     "match": match, "status": status, "diffs": diffs, "key_terms_missed": missed})
        print(f"scene {sid} {status} {match:.0%}", flush=True)
    bad = [r["id"] for r in rows if r["status"] in ("warn", "fail")]
    result = {"checked": dt.datetime.now().isoformat(timespec="seconds"), "engine": engine.name, "model": engine.model,
              "thresholds": {"pass": PASS_MATCH, "warn": WARN_MATCH}, "scenes": rows, "flagged": bad,
              "overall": "fail" if any(r["status"] == "fail" for r in rows) else "warn" if bad else "pass"}
    out_p.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lecture", type=Path)
    ap.add_argument("--engine", default="auto", choices=["auto", "faster-whisper", "hyperframes", "file"])
    ap.add_argument("--model", default="small", help="whisper model (small is a good speed/accuracy balance for Korean)")
    ap.add_argument("--scenes", nargs="*", help="transcribe these again even if cached")
    ap.add_argument("--heard", type=Path, help="engine file: {scene id: transcript}")
    ap.add_argument("--accept", type=Path, help="{scene id: audio hash} accepted by a person")
    a = ap.parse_args()
    lec = a.lecture.resolve()
    if not (lec / "build" / "audio" / "manifest.json").exists():
        sys.exit("no narration yet: build/audio/manifest.json missing")
    accept = json.loads(a.accept.read_text(encoding="utf-8")) if a.accept and a.accept.exists() else {}
    r = run(lec, make_engine(a.engine, a.model, a.heard), a.scenes, accept)
    for x in r["scenes"]:
        if x["status"] in ("warn", "fail"):
            print(f"  {x['id']}: " + " / ".join(f"\"{d['script']}\" -> \"{d['heard']}\"" for d in x["diffs"][:5]))
    print(f"=> {r['overall']}: {len(r['scenes'])} scenes, flagged {r['flagged'] or 'none'} ({r['engine']} {r['model']})")


if __name__ == "__main__":
    main()
