#!/usr/bin/env python3
"""Narration wrapper: scene script JSON -> per-scene wav + narration.wav + manifest.json.

usage
  python tools/narrate.py scenes.json --out build/audio                      # speaker from the JSON (e.g. sohee)
  python tools/narrate.py scenes.json --out build/audio --force s02 s05      # redo only these scenes
  python tools/narrate.py scenes.json --out build/audio --force              # redo everything
  python tools/narrate.py scenes.json --out build/audio --backend clone --voice me    # my cloned voice
  python tools/narrate.py scenes.json --out build/audio --backend silent    # no model: timing dry run
  python tools/narrate.py scenes.json --out build/audio --scene-speaker s02=ryan   # one scene in another voice

Backends
  customvoice  Qwen3-TTS CustomVoice model, built-in speaker (default; "speaker" in the JSON, e.g. sohee)
  clone        Qwen3-TTS Base model + a voice profile from tools/voice_clone.py enroll (~/.edu-video/voices/<name>.pt)
  silent       silence sized from text length (Korean ~7.5 chars/s); for layout work without a GPU
  fish         Fish Audio voice (e.g. my cloned voice). The audio is fetched through the Fish Audio MCP by
               tools/fish_audio.py narrate into <out>/fish/<id>-<hash>.mp3; this backend only converts it.

Cache: a scene is skipped when its wav exists and its text/voice settings hash is unchanged.
Editing a scene's text regenerates only that scene. --force [ids] regenerates on demand.

Output (build/audio/)
  <id>.wav          one per scene
  narration.wav     all scenes on one track, each at its manifest start
  manifest.json     {scenes: [{id, start, duration, voice_seconds, file, hash}], total_duration, ...}
The video is cut to this manifest: scene N starts at manifest start and lasts duration.
Windows: set PYTHONUTF8=1 (PowerShell: $env:PYTHONUTF8="1").
"""
import argparse
import hashlib
import json
import os
import sys
import time
import wave
from array import array
from pathlib import Path

SR = 24000
LOCAL_MODELS = Path.home() / ".edu-video" / "models"   # where setup_qwen_tts.sh downloads


def model_ref(env: str, hf_id: str) -> str:
    """Env override > local copy from setup_qwen_tts.sh > Hugging Face id (would re-download)."""
    local = LOCAL_MODELS / hf_id.split("/")[-1]
    return os.environ.get(env) or (str(local) if (local / "config.json").exists() else hf_id)


MODELS = {
    "customvoice": model_ref("QWEN_TTS_CUSTOMVOICE_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    "clone": model_ref("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-Base"),
}
VOICES_DIR = Path(os.environ.get("EDU_VOICES_DIR", Path.home() / ".edu-video" / "voices"))


# ---------- wav I/O with the standard library (16-bit mono) ----------

def write_wav(path: Path, samples, sr: int) -> None:
    """samples: numpy float array in [-1, 1] or an array('h')."""
    if not isinstance(samples, array):
        import numpy as np
        pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
        samples = array("h", pcm.tobytes())
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.tobytes())


def read_wav(path: Path) -> tuple[array, int]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            sys.exit(f"{path}: expected 16-bit mono wav")
        data = array("h")
        data.frombytes(w.readframes(w.getnframes()))
        return data, w.getframerate()


# ---------- backends ----------

class Backend:
    def __init__(self, a, script: dict):
        self.a = a
        self.kind = a.backend
        self.language = a.language or script.get("language", "korean")
        self.speaker = a.speaker or script.get("speaker", "sohee")
        self.voice = a.voice or script.get("voice", "me")
        self.fish_voice = a.fish_voice or ""
        self.current = None   # (scene id, hash) being synthesized — the fish backend reads its prefetched file
        self.tts = None
        self.prompt = None

    def scene_speaker(self, sc: dict) -> str:
        """CustomVoice speaker for one scene: --scene-speaker > scene "speaker" field > default."""
        return self.a.scene_speakers.get(sc["id"]) or sc.get("speaker") or self.speaker

    def settings_key(self, sc: dict | None = None) -> str:
        spk = self.scene_speaker(sc) if sc else self.speaker
        who = {"customvoice": spk, "clone": self.voice, "silent": "-", "fish": self.fish_voice}[self.kind]
        return f"{self.kind}|{who}|{self.language}"

    def load(self) -> None:
        if self.kind in ("silent", "fish") or self.tts is not None:
            return
        import torch
        from qwen_tts import Qwen3TTSModel

        device = self.a.device
        if device == "auto":
            device = "cuda:0" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
        dtype = torch.bfloat16 if device.startswith("cuda") else (torch.float16 if device == "mps" else torch.float32)
        model = self.a.model or MODELS[self.kind]
        print(f"loading {model} on {device}", flush=True)
        self.tts = Qwen3TTSModel.from_pretrained(model, device_map=device, dtype=dtype)
        if self.kind == "clone":
            pt = VOICES_DIR / f"{self.voice}.pt"
            if not pt.exists():
                sys.exit(f"voice profile {pt} not found: run tools/voice_clone.py enroll first")
            self.prompt = torch.load(pt, weights_only=False)

    def synth(self, text: str, instruct: str | None, speaker: str | None = None):
        if self.kind == "silent":
            secs = max(1.0, len(text.replace(" ", "")) / 7.5)
            return array("h", bytes(int(secs * SR) * 2)), SR
        if self.kind == "fish":
            sid, h = self.current
            src = fish_file(self.a.out, sid, h)
            if not src.exists():
                sys.exit(f"{src} not found: run tools/fish_audio.py narrate first (it fetches the audio via Fish Audio)")
            import subprocess
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                                 capture_output=True, check=True).stdout
            pcm = array("h")
            pcm.frombytes(raw[: len(raw) // 2 * 2])
            return pcm, SR
        self.load()
        if self.kind == "customvoice":
            wavs, sr = self.tts.generate_custom_voice(text=text, speaker=speaker or self.speaker, language=self.language,
                                                      instruct=instruct or None)
        else:
            wavs, sr = self.tts.generate_voice_clone(text=text, language=self.language,
                                                     voice_clone_prompt=self.prompt)
        return wavs[0], sr


# ---------- main ----------

def scene_text(sc: dict) -> str:
    return (sc.get("narration") or sc.get("text") or "").strip()


def pace_warning(text: str, seconds: float) -> str:
    """Flag a take whose length doesn't fit its text: TTS sometimes rambles on (or stops early).
    Korean narration runs about 4-7 syllables a second; Latin letters count as a third of a syllable."""
    units = sum(1 for c in text if "가" <= c <= "힣" or c.isdigit()) + sum(1 for c in text if c.isascii() and c.isalpha()) / 3
    if units < 8 or seconds <= 0:
        return ""
    rate = units / seconds
    if rate < 2.5:
        return f"글자 수에 비해 너무 김 ({seconds:.1f}초, 초당 {rate:.1f}음절) — 말이 늘어지거나 끝에 군소리"
    if rate > 10:
        return f"글자 수에 비해 너무 짧음 ({seconds:.1f}초, 초당 {rate:.1f}음절) — 문장이 잘렸을 수 있음"
    return ""


def fish_file(out: Path, sid: str, h: str) -> Path:
    return out / "fish" / f"{sid}-{h}.mp3"


def scene_hash(sc: dict, key: str) -> str:
    raw = json.dumps([scene_text(sc), sc.get("instruct", ""), key], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def plan(script: dict, out: Path, backend: str, speaker: str | None = None, voice: str | None = None,
         fish_voice: str | None = None, scene_speakers: dict | None = None, language: str | None = None) -> dict:
    """Which scenes the next (non --force) run will synthesize, and why — same cache rule as main(),
    without loading a model. reasons per scene: "new" (no audio yet), "voice" (speaker / backend / voice
    profile changed), "text" (narration or instruct changed). Studio shows this on the generate button."""
    a = argparse.Namespace(backend=backend, language=language, speaker=speaker, voice=voice,
                           fish_voice=fish_voice or "", scene_speakers=scene_speakers or {}, out=out)
    be = Backend(a, script)
    try:
        old = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    old_by_id = {s["id"]: s for s in old.get("scenes", [])}
    pending, total = [], 0
    for sc in script.get("scenes", []):
        if not scene_text(sc):
            continue
        total += 1
        key = be.settings_key(sc)
        prev = old_by_id.get(sc["id"])
        if not prev or not prev.get("hash") or not (out / f"{sc['id']}.wav").exists():
            pending.append({"id": sc["id"], "reasons": ["new"]})
            continue
        if prev["hash"] == scene_hash(sc, key):
            continue
        # rebuild the key the old take was made with (manifest keeps backend, per-scene speaker, voice)
        ob = old.get("backend")
        who = {"customvoice": prev.get("speaker") or old.get("speaker"), "silent": "-"}.get(ob, old.get("voice"))
        old_key = f"{ob}|{who}|{old.get('language')}"
        reasons = []
        if old_key != key:
            reasons.append("voice")
        if scene_hash(sc, old_key) != prev["hash"]:   # text / instruct differ too (or old key not recoverable)
            reasons.append("text")
        pending.append({"id": sc["id"], "reasons": reasons or ["text"]})
    return {"backend": be.kind, "total": total, "pending": pending}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenes", type=Path)
    ap.add_argument("--out", type=Path, default=Path("build/audio"))
    ap.add_argument("--backend", choices=["customvoice", "clone", "silent", "fish"],
                    default=os.environ.get("NARRATE_BACKEND", "customvoice"))
    ap.add_argument("--speaker", help="CustomVoice speaker (default: JSON 'speaker' or sohee)")
    ap.add_argument("--voice", help="clone profile name (default: JSON 'voice' or me)")
    ap.add_argument("--fish-voice", help="Fish Audio voice id (backend fish)")
    ap.add_argument("--scene-speaker", action="append", default=[], metavar="ID=SPEAKER",
                    help="CustomVoice speaker for one scene (repeatable); overrides the scene's own 'speaker'")
    ap.add_argument("--language", help="default: JSON 'language' or korean")
    ap.add_argument("--model", help="override model id or local folder")
    ap.add_argument("--device", default="auto", help="auto | cuda:0 | mps | cpu")
    ap.add_argument("--pause", type=float, default=0.5, help="silence after each scene (scene 'pause_after' wins)")
    ap.add_argument("--lead", type=float, default=0.3, help="silence before the first word of each scene")
    ap.add_argument("--min", type=float, default=3.0, help="minimum scene length in seconds")
    ap.add_argument("--force", nargs="*", metavar="ID", help="regenerate these scene ids (no ids = all)")
    ap.add_argument("--plan", action="store_true", help="print which scenes would be made and why (JSON), make nothing")
    a = ap.parse_args()
    a.scene_speakers = dict(x.split("=", 1) for x in a.scene_speaker if "=" in x)
    if a.plan:
        print(json.dumps(plan(json.loads(a.scenes.read_text(encoding="utf-8")), a.out, a.backend, a.speaker, a.voice,
                              a.fish_voice, a.scene_speakers, a.language), ensure_ascii=False, indent=2))
        return

    script = json.loads(a.scenes.read_text(encoding="utf-8"))
    scenes = script["scenes"]
    ids = [sc["id"] for sc in scenes]
    if len(set(ids)) != len(ids):
        sys.exit("scene ids must be unique")
    if a.force:
        unknown = set(a.force) - set(ids)
        if unknown:
            sys.exit(f"--force: unknown scene ids {sorted(unknown)}")

    a.out.mkdir(parents=True, exist_ok=True)
    manifest_path = a.out / "manifest.json"
    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"scenes": []}
    old_hash = {s["id"]: s.get("hash") for s in old.get("scenes", [])}

    be = Backend(a, script)
    entries, made, skipped = [], 0, 0
    for sc in scenes:
        text = scene_text(sc)
        wav_path = a.out / f"{sc['id']}.wav"
        h = scene_hash(sc, be.settings_key(sc))
        spk = be.scene_speaker(sc) if be.kind == "customvoice" else None
        forced = a.force is not None and (len(a.force) == 0 or sc["id"] in a.force)
        if text and (forced or not wav_path.exists() or old_hash.get(sc["id"]) != h):
            t0 = time.time()
            be.current = (sc["id"], h)
            samples, sr = be.synth(text, sc.get("instruct"), spk)
            if sr != SR:
                import numpy as np
                import librosa
                samples = librosa.resample(np.asarray(samples, dtype=np.float32), orig_sr=sr, target_sr=SR)
            write_wav(wav_path, samples, SR)
            made += 1
            secs = len(samples) / SR
            print(f"  made {sc['id']:<8} 음성 {secs:4.1f}초 (생성 {time.time() - t0:4.1f}초)  "
                  f"{(spk + ' · ') if spk else ''}{text[:40]}", flush=True)
            warn = pace_warning(text, secs)
            if warn:
                print(f"  WARN {sc['id']:<8} {warn} — 들어 보고 이상하면 이 장면만 다시 생성(--force {sc['id']})", flush=True)
        elif text:
            skipped += 1
            print(f"  skip {sc['id']:<8} (cached)", flush=True)
        voice_seconds = 0.0
        if text:
            data, _ = read_wav(wav_path)
            voice_seconds = len(data) / SR
        pause = float(sc.get("pause_after", a.pause))
        entries.append({"id": sc["id"], "file": wav_path.name if text else None, "hash": h if text else None, "speaker": spk,
                        "voice_seconds": round(voice_seconds, 3), "warn": pace_warning(text, voice_seconds) if text else "",
                        "duration": round(max(a.min, a.lead + voice_seconds + pause), 3)})

    # lay every scene on one track at its start
    start = 0.0
    track = array("h")
    for e in entries:
        e["start"] = round(start, 3)
        e["voice_start"] = round(start + a.lead, 3)
        begin = int(round(e["voice_start"] * SR))
        end = int(round((start + e["duration"]) * SR))
        if len(track) < end:
            track.extend([0] * (end - len(track)))
        if e["file"]:
            data, _ = read_wav(a.out / e["file"])
            track[begin:begin + len(data)] = data
        start += e["duration"]
    write_wav(a.out / "narration.wav", track, SR)

    manifest = {
        "title": script.get("title", ""),
        "source_script": str(a.scenes),
        "backend": be.kind, "speaker": be.speaker if be.kind == "customvoice" else None,
        "voice": be.voice if be.kind == "clone" else (be.fish_voice if be.kind == "fish" else None), "language": be.language,
        "sample_rate": SR, "lead": a.lead, "total_duration": round(start, 3),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scenes": entries,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{made} made, {skipped} cached -> {a.out / 'narration.wav'}  total {start:.2f}s")


if __name__ == "__main__":
    main()
