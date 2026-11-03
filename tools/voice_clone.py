#!/usr/bin/env python3
"""My-voice narration with local Qwen3-TTS (Base model, voice clone).

Subcommands
  prep     <recording> -o voices/me.wav          clean a phone/mic recording -> 24 kHz mono wav (ffmpeg)
  enroll   <ref.wav> --text "녹음한 문장" --name me  build a reusable voice profile voices/me.pt (+ me.json)
  say      --voice me "문장"  -o out.wav           one-off line (listen test)
  narrate  <project>/script.json --voice me       every scene -> assets/voice/<id>.wav, durations into script.json
  mux      <video.mp4> <script.json> -o out.mp4   lay the narration onto an already-rendered video (no re-render)

Model: Qwen/Qwen3-TTS-12Hz-1.7B-Base (default) or Qwen/Qwen3-TTS-12Hz-0.6B-Base (--model, less VRAM).
Device: auto picks cuda > mps > cpu. Set QWEN_TTS_MODEL to a local folder to stay offline.

Only clone a voice you own or have written consent for.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_MODEL = os.environ.get("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
VOICES_DIR = Path(os.environ.get("EDU_VOICES_DIR", Path.home() / ".edu-video" / "voices"))
REF_SR = 24000


# ---------- audio helpers (ffmpeg only, no model needed) ----------

def ffmpeg(*args: str) -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def cmd_prep(a) -> None:
    """Mono 24 kHz, high-pass rumble, trim leading/trailing silence, loudness to -20 LUFS."""
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    filt = ("highpass=f=70,"
            "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,"
            "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.25,areverse,"
            "loudnorm=I=-20:TP=-2:LRA=11")
    ffmpeg("-i", a.recording, "-ac", "1", "-ar", str(REF_SR), "-af", filt, str(out))
    dur = seconds(out)
    print(f"{out}  {dur:.1f}s")
    if dur < 3:
        print("too short: record at least 5 s (10-15 s is best)")
    elif dur > 20:
        print("long reference: 10-15 s of clean speech clones better; trim with --to or re-record")


# ---------- model ----------

def load_model(model_id: str, device: str):
    import torch
    from qwen_tts import Qwen3TTSModel

    if device == "auto":
        device = "cuda:0" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    dtype = torch.bfloat16 if device.startswith("cuda") else (torch.float16 if device == "mps" else torch.float32)
    kwargs = {"device_map": device, "dtype": dtype}
    if device.startswith("cuda"):
        try:
            import flash_attn  # noqa: F401
            kwargs["attn_implementation"] = "flash_attention_2"
        except ImportError:
            pass
    print(f"loading {model_id} on {device} ({str(dtype).split('.')[-1]})", file=sys.stderr)
    return Qwen3TTSModel.from_pretrained(model_id, **kwargs)


def voice_paths(name: str) -> tuple[Path, Path]:
    return VOICES_DIR / f"{name}.pt", VOICES_DIR / f"{name}.json"


def load_voice(name: str):
    import torch
    pt, meta = voice_paths(name)
    if not pt.exists():
        sys.exit(f"voice '{name}' not found in {VOICES_DIR}: run enroll first")
    info = json.loads(meta.read_text(encoding="utf-8"))
    items = torch.load(pt, weights_only=False)
    return items, info


def gen_kwargs(a) -> dict:
    kw = {}
    for k in ("temperature", "top_p", "top_k", "repetition_penalty"):
        v = getattr(a, k, None)
        if v is not None:
            kw[k] = v
    return kw


def synth(tts, items, info, texts: list[str], a) -> tuple[list, int]:
    return tts.generate_voice_clone(text=texts, language=a.language, voice_clone_prompt=items, **gen_kwargs(a))


def write_wav(path: Path, wav, sr: int) -> None:
    import soundfile as sf
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), wav, sr)


def cmd_enroll(a) -> None:
    import torch
    if not a.text and not a.xvector_only:
        sys.exit("--text (exact words spoken in the reference) is required, or pass --xvector-only (lower similarity)")
    tts = load_model(a.model, a.device)
    items = tts.create_voice_clone_prompt(ref_audio=str(a.ref), ref_text=a.text or None,
                                          x_vector_only_mode=a.xvector_only)
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    pt, meta = voice_paths(a.name)
    torch.save(items, pt)
    shutil.copy(a.ref, VOICES_DIR / f"{a.name}.ref.wav")
    meta.write_text(json.dumps({"name": a.name, "model": a.model, "ref_text": a.text,
                                "xvector_only": a.xvector_only, "ref_seconds": round(seconds(Path(a.ref)), 2)},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"voice '{a.name}' saved -> {pt}")
    if a.test:
        wavs, sr = synth(tts, items, {}, [a.test], a)
        out = VOICES_DIR / f"{a.name}.test.wav"
        write_wav(out, wavs[0], sr)
        print(f"test line -> {out}")


def cmd_say(a) -> None:
    items, info = load_voice(a.voice)
    tts = load_model(a.model or info["model"], a.device)
    wavs, sr = synth(tts, items, info, [a.text], a)
    write_wav(Path(a.output), wavs[0], sr)
    print(f"{a.output}  {len(wavs[0]) / sr:.1f}s")


def cmd_narrate(a) -> None:
    script = Path(a.script)
    project = script.parent
    data = json.loads(script.read_text(encoding="utf-8"))
    items, info = load_voice(a.voice)
    tts = load_model(a.model or info["model"], a.device)
    voice_dir = project / "assets" / "voice"

    todo = [sc for sc in data["scenes"] if sc.get("narration", "").strip()]
    for i in range(0, len(todo), a.batch):
        chunk = todo[i:i + a.batch]
        wavs, sr = synth(tts, items, info, [sc["narration"].strip() for sc in chunk], a)
        for sc, wav in zip(chunk, wavs):
            path = voice_dir / f"{sc['id']}.wav"
            write_wav(path, wav, sr)
            sc["voice"] = f"assets/voice/{path.name}"
            sc["voice_seconds"] = round(len(wav) / sr, 2)
            print(f"{sc['id']:<12} {sc['voice_seconds']:>5.2f}s  {sc['narration'][:40]}")

    if a.keep_timing:
        for sc in data["scenes"]:
            if sc.get("voice_seconds", 0) > sc.get("duration", 1e9):
                print(f"warning: {sc['id']} narration {sc['voice_seconds']}s > scene {sc['duration']}s (will overlap)")
    else:
        start = 0.0
        for sc in data["scenes"]:
            secs = sc.get("voice_seconds", 0.0)
            sc["start"] = round(start, 2)
            sc["duration"] = round(max(a.min, secs + a.pad) if secs else sc.get("duration", a.min), 2)
            start += sc["duration"]
        data["total_duration"] = round(start, 2)
    data["narrator"] = {"engine": "qwen3-tts", "voice": a.voice, "model": a.model or info["model"]}
    script.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"script updated -> {script}" + ("" if a.keep_timing else f"  total {data['total_duration']}s (re-render the video)"))


def cmd_mux(a) -> None:
    """Place each scene's narration at its scene start on top of an existing video; video stream is copied."""
    script = Path(a.script)
    project = script.parent
    data = json.loads(script.read_text(encoding="utf-8"))
    if (project / "narration.wav").exists() and any("voice_start" in sc for sc in data["scenes"]):
        # build/audio/manifest.json from tools/narrate.py: one track already laid out on the timeline
        clips = [(project / "narration.wav", 0.0)]
    else:
        clips = [(project / sc["voice"], float(sc["start"]) + a.offset) for sc in data["scenes"]
                 if sc.get("voice") and "start" in sc]
    if not clips:
        sys.exit("no narration in script.json: run narrate first")
    inputs, filters, labels = ["-i", a.video], [], []
    for n, (path, start) in enumerate(clips, 1):
        inputs += ["-i", str(path)]
        ms = int(round(start * 1000))
        filters.append(f"[{n}:a]aresample=48000,adelay={ms}|{ms},volume={a.voice_gain}[v{n}]")
        labels.append(f"[v{n}]")
    mix = "".join(labels)
    if a.music:
        inputs += ["-stream_loop", "-1", "-i", a.music]
        m = len(clips) + 1
        filters.append(f"[{m}:a]aresample=48000,volume={a.music_gain}[bg]")
        # duck the music under the voice
        filters.append(f"{mix}amix=inputs={len(clips)}:normalize=0[vo]")
        filters.append("[vo]asplit=2[vo1][vo2]")
        filters.append("[bg][vo1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
        filters.append("[duck][vo2]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5,apad[out]")
    else:
        filters.append(f"{mix}amix=inputs={len(clips)}:normalize=0,loudnorm=I=-16:TP=-1.5,apad[out]")
    ffmpeg(*inputs, "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[out]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", a.output)
    print(f"{a.output}  ({len(clips)} narration clips{', music ducked' if a.music else ''})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def model_opts(p, model_default=DEFAULT_MODEL):
        p.add_argument("--model", default=model_default)
        p.add_argument("--device", default="auto", help="auto | cuda:0 | mps | cpu")
        p.add_argument("--language", default="korean")
        p.add_argument("--temperature", type=float)
        p.add_argument("--top-p", dest="top_p", type=float)
        p.add_argument("--top-k", dest="top_k", type=int)
        p.add_argument("--repetition-penalty", dest="repetition_penalty", type=float)

    p = sub.add_parser("prep", help="clean a recording into a 24 kHz mono reference wav")
    p.add_argument("recording")
    p.add_argument("-o", "--output", default=str(VOICES_DIR / "me.wav"))
    p.set_defaults(fn=cmd_prep)

    p = sub.add_parser("enroll", help="build and save a voice profile")
    p.add_argument("ref", type=Path)
    p.add_argument("--name", default="me")
    p.add_argument("--text", help="exact transcript of the reference recording")
    p.add_argument("--xvector-only", action="store_true", help="no transcript; speaker embedding only")
    p.add_argument("--test", help="speak this line after enrolling")
    model_opts(p)
    p.set_defaults(fn=cmd_enroll)

    p = sub.add_parser("say", help="synthesize one line")
    p.add_argument("text")
    p.add_argument("--voice", default="me")
    p.add_argument("-o", "--output", default="say.wav")
    model_opts(p, model_default=None)
    p.set_defaults(fn=cmd_say)

    p = sub.add_parser("narrate", help="voice every scene of script.json")
    p.add_argument("script")
    p.add_argument("--voice", default="me")
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--pad", type=float, default=0.6)
    p.add_argument("--min", type=float, default=3.5)
    p.add_argument("--keep-timing", action="store_true",
                   help="keep existing scene start/duration (for mux onto a finished video)")
    model_opts(p, model_default=None)
    p.set_defaults(fn=cmd_narrate)

    p = sub.add_parser("mux", help="lay narration onto a rendered video without re-rendering")
    p.add_argument("video")
    p.add_argument("script")
    p.add_argument("-o", "--output", default="lecture-voiced.mp4")
    p.add_argument("--offset", type=float, default=0.2, help="seconds after each scene start")
    p.add_argument("--voice-gain", type=float, default=1.0)
    p.add_argument("--music", help="optional background music file (ducked under the voice)")
    p.add_argument("--music-gain", type=float, default=0.25)
    p.set_defaults(fn=cmd_mux)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
