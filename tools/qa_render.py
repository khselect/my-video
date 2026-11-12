#!/usr/bin/env python3
"""Automatic checks on a rendered video, before a person watches it (Lecture Studio stage 6).

  python tools/qa_render.py renders/v003.mp4 [--lecture lectures/<name>] [--out qa.json] [--normalize]

Checks (each: pass / warn / fail, with numbers):
  blank     frames with (almost) nothing on screen — black, or a flat background with no shapes or text.
            Measured on 192x108 grey frames at 10 fps: edge energy (mean |dx|+|dy|) and pixel spread.
  freeze    long stretches where nothing moves (mean frame difference ~0) — the "slide show" feel.
  loudness  integrated loudness / true peak (ffmpeg loudnorm). Target -14 LUFS, true peak <= -1 dBTP.
  readtime  (with --lecture) each scene's on-screen text vs. its length: chars / 5 + 1.5 s (Korean, a
            starting value from motion-rules.md). Scene-level approximation, not per text element.
  timings   (with --lecture) how long the Studio jobs took (build/logs), for the "time spent" record.

--normalize rewrites the audio to -14 LUFS (two-pass loudnorm, video stream copied) before checking.
The motion series (per-second frame difference) is saved too; the reference-measurement tool reuses it.
Needs ffmpeg/ffprobe and numpy.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

SAMPLE_FPS = 10
W, H = 192, 108
BLANK_EDGE = 0.6        # mean |dx|+|dy| (0-255 grey) below this = no shapes/text on screen
BLANK_STD = 12.0        # ... and pixel spread below this (plain or graded background; soft photos stay above)
BLACK_LUMA = 10.0       # mean grey below this and blank = black frame
BLANK_WARN_S, BLANK_FAIL_S = 0.3, 1.0
FREEZE_DIFF = 0.15      # mean |frame - previous| below this = nothing moves
FREEZE_WARN_S = 4.0
TARGET_LUFS, LUFS_TOL, MAX_TP = -14.0, 1.0, -1.0
READ_CPS, READ_PAD = 5.0, 1.5   # Korean: chars / 5 + 1.5 s
CHECK_NAMES = {"blank": "빈 화면", "freeze": "멈춤", "loudness": "음량", "readtime": "읽기 시간"}


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(path: Path) -> dict:
    out = sh(["ffprobe", "-v", "error", "-show_entries",
              "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(path)])
    if out.returncode:
        sys.exit(f"ffprobe failed: {out.stderr.strip()}")
    d = json.loads(out.stdout)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    num, _, den = (v.get("r_frame_rate") or "0/1").partition("/")
    return {"seconds": round(float(d.get("format", {}).get("duration", 0)), 2),
            "width": v.get("width"), "height": v.get("height"),
            "fps": round(float(num) / float(den or 1), 3) if float(den or 1) else None,
            "has_audio": any(s.get("codec_type") == "audio" for s in d.get("streams", []))}


# ---------------- picture ----------------

def grey_frames(path: Path, fps: float | None = SAMPLE_FPS, start: float | None = None, dur: float | None = None,
                size: tuple[int, int] = (W, H), color: bool = False) -> np.ndarray:
    """All frames as (n, h, w) float32 grey (or (n, h, w, 3) RGB with color=True), sampled at `fps`
    (fps=None keeps every source frame — needed to see hold patterns)."""
    w, h = size
    ch = 3 if color else 1
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    vf = ([f"fps={fps}"] if fps else []) + [f"scale={w}:{h}:flags=area", "format=rgb24" if color else "format=gray"]
    cmd += ["-i", str(path), "-vf", ",".join(vf), "-vsync", "passthrough", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (w * h * ch)
    shape = (n, h, w, 3) if color else (n, h, w)
    return np.frombuffer(raw[: n * w * h * ch], dtype=np.uint8).reshape(shape).astype(np.float32)


def frame_stats(frames: np.ndarray) -> dict[str, np.ndarray]:
    edge = (np.abs(np.diff(frames, axis=2)).mean(axis=(1, 2)) + np.abs(np.diff(frames, axis=1)).mean(axis=(1, 2)))
    diff = np.concatenate([[np.nan], np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))]) if len(frames) else np.array([])
    return {"edge": edge, "std": frames.std(axis=(1, 2)), "luma": frames.mean(axis=(1, 2)), "diff": diff}


def runs(mask: np.ndarray, fps: int) -> list[tuple[float, float]]:
    """(start s, length s) of consecutive True samples."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append((round(i / fps, 2), round((j - i) / fps, 2)))
            i = j
        else:
            i += 1
    return out


def check_blank(s: dict, fps: int) -> dict:
    blank = (s["edge"] < BLANK_EDGE) & (s["std"] < BLANK_STD)
    segs = []
    for t, length in runs(blank, fps):
        i0 = int(t * fps)
        black = bool(s["luma"][i0: i0 + max(1, int(length * fps))].mean() < BLACK_LUMA)
        segs.append({"t": t, "seconds": length, "kind": "black" if black else "empty"})
    longest = max((g["seconds"] for g in segs), default=0.0)
    first = bool(len(blank) and blank[0])
    status = "fail" if longest >= BLANK_FAIL_S else "warn" if longest >= BLANK_WARN_S or first else "pass"
    msg = (f"빈 화면 {len(segs)}구간, 가장 긴 것 {longest:.1f}초" if segs else "빈 화면 없음") + \
          (" · 0초 프레임이 비어 있음(썸네일)" if first else "")
    return {"status": status, "message": msg, "segments": segs[:30],
            "thresholds": {"edge": BLANK_EDGE, "std": BLANK_STD, "warn_s": BLANK_WARN_S, "fail_s": BLANK_FAIL_S}}


def check_freeze(s: dict, fps: int) -> dict:
    still = np.nan_to_num(s["diff"], nan=1.0) < FREEZE_DIFF
    segs = [{"t": t, "seconds": d} for t, d in runs(still, fps) if d >= FREEZE_WARN_S]
    return {"status": "warn" if segs else "pass",
            "message": f"{FREEZE_WARN_S:g}초 이상 멈춘 구간 {len(segs)}개" if segs else f"{FREEZE_WARN_S:g}초 이상 멈춘 구간 없음",
            "segments": segs, "thresholds": {"diff": FREEZE_DIFF, "warn_s": FREEZE_WARN_S}}


def motion_series(s: dict, fps: int) -> list[float]:
    """Mean frame difference per second (absolute, 0-255 grey at 192x108)."""
    d = np.nan_to_num(s["diff"], nan=0.0)
    return [round(float(d[i: i + fps].mean()), 3) for i in range(0, len(d), fps)]


# ---------------- sound ----------------

def measure_loudness(path: Path) -> dict | None:
    out = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
              "-af", f"loudnorm=I={TARGET_LUFS}:TP={MAX_TP}:LRA=11:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", out.stderr)
    return json.loads(m.group(0)) if m else None


def check_loudness(info: dict, ln: dict | None) -> dict:
    if not info["has_audio"]:
        return {"status": "warn", "message": "오디오 트랙 없음"}
    if not ln:
        return {"status": "warn", "message": "음량을 측정하지 못함"}
    i, tp = float(ln["input_i"]), float(ln["input_tp"])
    if i < -60:
        return {"status": "warn", "message": f"거의 무음 ({i:.1f} LUFS)", "lufs": i, "true_peak": tp}
    ok_i, ok_tp = abs(i - TARGET_LUFS) <= LUFS_TOL, tp <= MAX_TP
    return {"status": "pass" if ok_i and ok_tp else "warn",
            "message": f"{i:.1f} LUFS (목표 {TARGET_LUFS:g}±{LUFS_TOL:g}), 피크 {tp:.1f} dBTP (≤ {MAX_TP:g})",
            "lufs": i, "true_peak": tp, "lra": float(ln["input_lra"])}


def normalize(path: Path) -> dict:
    """Two-pass loudnorm to -14 LUFS in place (video copied). Returns what was done."""
    info = probe(path)
    if not info["has_audio"]:
        return {"done": False, "reason": "no audio"}
    ln = measure_loudness(path)
    if not ln or float(ln["input_i"]) < -60:
        return {"done": False, "reason": "silent or unmeasurable"}
    i, tp = float(ln["input_i"]), float(ln["input_tp"])
    if abs(i - TARGET_LUFS) <= 0.5 and tp <= MAX_TP:
        return {"done": False, "reason": "already on target", "lufs": i}
    filt = (f"loudnorm=I={TARGET_LUFS}:TP={MAX_TP}:LRA=11:measured_I={ln['input_i']}:measured_TP={ln['input_tp']}"
            f":measured_LRA={ln['input_lra']}:measured_thresh={ln['input_thresh']}:offset={ln['target_offset']}"
            ":linear=true")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / ("norm" + path.suffix)
        r = sh(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-map", "0:v?", "-map", "0:a", "-c:v", "copy",
                "-af", filt, "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp)])
        if r.returncode or not tmp.exists():
            return {"done": False, "reason": "ffmpeg failed: " + r.stderr.strip()[-300:]}
        shutil.move(str(tmp), path)
    return {"done": True, "before_lufs": i, "before_tp": tp}


# ---------------- lecture context ----------------

def _chars(text: str) -> int:
    return len(re.sub(r"[\s\W_]+", "", text or ""))


def check_readtime(lecture: Path) -> dict | None:
    scenes = _read(lecture / "scenes.json")
    manifest = _read(lecture / "build" / "audio" / "manifest.json")
    if not scenes or not manifest:
        return None
    dur = {s.get("id"): float(s.get("duration", 0)) for s in manifest.get("scenes", [])}
    short = []
    for sc in scenes.get("scenes", []):
        text = sc.get("on_screen") or ""
        if isinstance(text, list):
            text = " ".join(map(str, text))
        n = _chars(str(text))
        d = dur.get(sc.get("id"))
        if not n or not d:
            continue
        need = round(n / READ_CPS + READ_PAD, 1)
        if d < need:
            short.append({"scene": sc.get("id"), "chars": n, "seconds": round(d, 1), "need": need})
    return {"status": "warn" if short else "pass",
            "message": (f"글자에 비해 짧은 장면 {len(short)}개" if short else "모든 장면이 화면 글자를 읽을 만큼 길다")
                       + f" (기준: 글자 수÷{READ_CPS:g}+{READ_PAD:g}초, 장면 단위 근사)",
            "scenes": short}


def job_timings(lecture: Path) -> dict:
    """Latest run time per Studio job kind, from build/logs/<YYYYmmdd-HHMMSS>-<kind>.log (start) and mtime (end)."""
    out: dict[str, dict] = {}
    for log in sorted((lecture / "build" / "logs").glob("*.log")):
        m = re.match(r"(\d{8}-\d{6})-(.+)\.log$", log.name)
        if not m:
            continue
        start = dt.datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").timestamp()
        out[m.group(2)] = {"started": dt.datetime.fromtimestamp(start).isoformat(timespec="seconds"),
                           "seconds": round(max(0.0, log.stat().st_mtime - start), 1)}
    return out


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------- main ----------------

def run_qa(video: Path, lecture: Path | None = None, do_normalize: bool = False) -> dict:
    norm = normalize(video) if do_normalize else None
    info = probe(video)
    frames = grey_frames(video)
    s = frame_stats(frames)
    checks = {"blank": check_blank(s, SAMPLE_FPS), "freeze": check_freeze(s, SAMPLE_FPS),
              "loudness": check_loudness(info, measure_loudness(video) if info["has_audio"] else None)}
    timings = None
    if lecture:
        rt = check_readtime(lecture)
        if rt:
            checks["readtime"] = rt
        timings = job_timings(lecture)
    order = {"pass": 0, "warn": 1, "fail": 2}
    overall = max((c["status"] for c in checks.values()), key=order.get, default="pass")
    return {"file": video.name, "checked": dt.datetime.now().isoformat(timespec="seconds"), "overall": overall,
            "media": info, "normalized": norm, "checks": checks,
            "motion_per_second": motion_series(s, SAMPLE_FPS), "timings": timings}


def summary(qa: dict) -> dict:
    """Small version for renders/manifest.json."""
    return {"overall": qa["overall"], **{k: c["status"] for k, c in qa["checks"].items()},
            "messages": [f"{CHECK_NAMES.get(k, k)}: {c['message']}" for k, c in qa["checks"].items() if c["status"] != "pass"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--lecture", help="lecture folder (scenes.json, build/audio/manifest.json, build/logs)")
    ap.add_argument("--out", help="write the full report here (default: <video>.qa.json)")
    ap.add_argument("--normalize", action="store_true", help="loudness-normalize the audio to -14 LUFS first (in place)")
    a = ap.parse_args()
    video = Path(a.video).resolve()
    if not video.exists():
        sys.exit(f"{video} not found")
    qa = run_qa(video, Path(a.lecture).resolve() if a.lecture else None, a.normalize)
    out = Path(a.out) if a.out else video.with_name(video.name + ".qa.json")
    out.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mark = {"pass": "OK  ", "warn": "WARN", "fail": "FAIL"}
    for k, c in qa["checks"].items():
        print(f"[{mark[c['status']]}] {k:<9} {c['message']}")
    if qa["normalized"] and qa["normalized"].get("done"):
        print(f"       loudness normalized from {qa['normalized']['before_lufs']:.1f} LUFS")
    print(f"=> {qa['overall']}  ({out})")
    sys.exit(2 if qa["overall"] == "fail" else 0)


if __name__ == "__main__":
    main()
