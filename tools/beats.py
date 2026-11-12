#!/usr/bin/env python3
"""Music beat analysis and beat-sync check (numpy + ffmpeg only).

  python tools/beats.py analyze <music file> [--out beats.json] [--bpm-hint 120]
  python tools/beats.py check <beats.json> <video> [--window 0.3]
  python tools/beats.py snap <beats.json> 3.2 7.95 12.4 [--window 0.3]

analyze  tempo (BPM), every beat, bar starts (downbeats, 4/4 assumed), and accents — the strongest hits
         (kick/stomp/clap) — as times in seconds. Onset strength = spectral flux on a log-magnitude
         spectrogram; tempo = autocorrelation of that envelope with a mild prior around 120 BPM;
         beats = dynamic programming that follows the envelope at that tempo (Ellis 2007).
check    finds the video's transitions (same detector as ref_measure.py) and how far each is from the
         nearest beat: median |offset| in ms and the share within one frame. Pass when >= 80% of
         transitions are within max(1 frame, 50 ms).
snap     prints the nearest beat / downbeat for the given times (for hand-placing cuts).

Rule of this project (CLAUDE.md principle 1): with narration, scene boundaries come from the narration
manifest and are not moved; only in-scene entrances, emphasis hits and transition starts snap to a beat
within --window seconds. Without narration (promo), every cut lands on a beat and the video = the music.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 22050
HOP = 256                       # 11.6 ms per envelope frame
NFFT = 1024
BPM_MIN, BPM_MAX = 60.0, 200.0
BPM_PRIOR, PRIOR_WIDTH = 120.0, 1.0   # log2-octave width of the tempo prior


def load_audio(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True).stdout
    if not raw:
        sys.exit(f"no audio decoded from {path}")
    return np.frombuffer(raw, dtype=np.float32).copy()


def onset_envelope(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(spectral flux envelope, low-band flux envelope) at SR/HOP frames per second."""
    n = 1 + (len(y) - NFFT) // HOP if len(y) >= NFFT else 1
    y = np.pad(y, (0, max(0, NFFT + (n - 1) * HOP - len(y))))
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    frames = y[idx] * np.hanning(NFFT)[None, :]
    mag = np.log1p(100 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0.0, np.diff(mag, axis=0, prepend=mag[:1]))
    freqs = np.fft.rfftfreq(NFFT, 1 / SR)
    env = flux.mean(1)
    low = flux[:, freqs < 200].mean(1)          # kick / stomp / bass hits
    def norm(e):
        e = e - np.convolve(e, np.ones(16) / 16, mode="same")   # remove slow loudness drift
        e = np.maximum(e, 0)
        return e / (e.std() + 1e-9)
    return norm(env), norm(low)


def estimate_tempo(env: np.ndarray, fps: float, hint: float | None = None) -> float:
    lags = np.arange(int(fps * 60 / BPM_MAX), int(fps * 60 / BPM_MIN) + 1)
    e = env - env.mean()
    ac = np.array([np.dot(e[:-l], e[l:]) / (len(e) - l) for l in lags])
    bpm = 60 * fps / lags
    center = hint or BPM_PRIOR
    w = np.exp(-0.5 * (np.log2(bpm / center) / PRIOR_WIDTH) ** 2)
    score = ac * w
    # reinforce with the double-lag (a true beat period also correlates at 2x)
    score2 = score + 0.5 * np.interp(lags * 2, lags, ac, right=0) * w
    i = int(np.argmax(score2))
    # parabolic refinement of the lag
    if 0 < i < len(score2) - 1:
        a, b, c = score2[i - 1], score2[i], score2[i + 1]
        d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
        return float(60 * fps / (lags[i] + d))
    return float(bpm[i])


def track_beats(env: np.ndarray, fps: float, bpm: float, tightness: float = 100.0) -> np.ndarray:
    """Dynamic-programming beat tracker: frame indices of beats."""
    period = 60 * fps / bpm
    n = len(env)
    score = env.copy()
    back = np.full(n, -1)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    for i in range(n):
        if i < lo:
            continue
        prev = np.arange(max(0, i - hi), i - lo + 1)
        if not len(prev):
            continue
        pen = -tightness * np.log((i - prev) / period) ** 2
        cand = score[prev] + pen
        j = int(np.argmax(cand))
        if cand[j] > 0:
            score[i] = env[i] + cand[j]
            back[i] = prev[j]
    # start from the best-scoring frame in the last period
    tail = np.arange(max(0, n - int(period) - 1), n)
    i = int(tail[np.argmax(score[tail])])
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    return np.array(beats[::-1])


def pulse_contrast(env: np.ndarray, beats: np.ndarray) -> float:
    """Mean onset strength on the beats minus halfway between them. The true beat level has strong hits
    (kick, clap) on the beat and weaker ones (hats) between; double tempo puts beats on the weak hits,
    half tempo puts strong hits (beats 2 and 4) between its beats."""
    if len(beats) < 4:
        return -1.0
    pk = lambda i: env[max(0, i - 2): i + 3].max()  # noqa: E731
    on = np.mean([pk(b) for b in beats])
    off = np.mean([pk((a + b) // 2) for a, b in zip(beats, beats[1:])])
    return float(on - off)


def analyze(path: Path, bpm_hint: float | None = None) -> dict:
    y = load_audio(path)
    fps = SR / HOP
    env, low = onset_envelope(y)
    comb = env + low                                   # full-band hits + kick/bass hits
    bpm0 = estimate_tempo(comb, fps, bpm_hint)
    cands = sorted({b for b in (bpm0, bpm0 * 2, bpm0 / 2) if BPM_MIN <= b <= BPM_MAX})
    if bpm_hint:   # the user knows the tempo: keep the candidate nearest to it
        cands = [min(cands, key=lambda b: abs(np.log2(b / bpm_hint)))]
    tracked = {b: track_beats(comb, fps, b) for b in cands}
    scores = {b: pulse_contrast(comb, tracked[b]) for b in cands}
    bpm = max(cands, key=lambda b: scores[b])
    beats = tracked[bpm]
    t = (beats * HOP + NFFT / 2) / SR                  # frame index -> centre of its analysis window
    # refine BPM from the tracked beats (median interval)
    if len(t) > 4:   # least-squares slope of beat time vs beat number = the average beat length
        bpm = 60.0 / float(np.polyfit(np.arange(len(t)), t, 1)[0])
    # downbeat phase: the beat position (0..3) whose beats carry the most low-band energy
    strength = np.array([low[max(0, b - 2): b + 3].max() for b in beats]) if len(beats) else np.array([])
    phase = int(np.argmax([strength[p::4].mean() if len(strength[p::4]) else 0 for p in range(4)])) if len(beats) >= 4 else 0
    downbeats = t[phase::4]
    # accents: hits clearly stronger than an ordinary beat (>= 1.3x the median beat), at least a half beat apart
    acc_env = np.maximum(env, low)
    at_beats = [acc_env[max(0, i - 2): i + 3].max() for i in beats] if len(beats) else [0.0]
    thr = max(np.percentile(acc_env, 97), 1.3 * float(np.median(at_beats)))   # clearly above a normal beat
    peaks = [i for i in range(1, len(acc_env) - 1)
             if acc_env[i] >= thr and acc_env[i] >= acc_env[i - 1] and acc_env[i] >= acc_env[i + 1]]
    accents, gap = [], 0.5 * 60 / bpm
    for i in sorted(peaks, key=lambda k: -acc_env[k]):
        at = (i * HOP + NFFT / 2) / SR
        if all(abs(at - a) >= gap for a in accents):
            accents.append(at)
    accents.sort()
    dur = len(y) / SR
    return {"file": path.name, "seconds": round(dur, 3), "bpm": round(bpm, 2),
            "beat_seconds": round(60 / bpm, 4), "meter": "4/4 (assumed)",
            "beats": [round(float(x), 3) for x in t], "downbeats": [round(float(x), 3) for x in downbeats],
            "accents": [round(float(x), 3) for x in accents[:64]],
            "first_beat": round(float(t[0]), 3) if len(t) else None,
            "tempo_candidates": {f"{b:.1f}": round(v, 3) for b, v in scores.items()},
            "method": "spectral-flux + low-band onset envelope, autocorrelation tempo, T/2T/T÷2 chosen by "
                      "on-beat vs off-beat contrast, DP beat tracking"}


def nearest(beats: list[float], x: float) -> tuple[float, float]:
    b = np.asarray(beats)
    i = int(np.argmin(np.abs(b - x)))
    return float(b[i]), float(x - b[i])


def check(spec: dict, video: Path, window: float = 0.3) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ref_measure
    m = ref_measure.measure(video, sheets=False)
    fps = m["analysis_fps"]
    tol = max(1.0 / fps, 0.05)
    rows = []
    for t in m["transitions"]:
        # a cut lands on its first new frame; a gradual transition is judged by where it starts
        at = t["t"]
        b, off = nearest(spec["beats"], at)
        db, doff = nearest(spec["downbeats"], at) if spec["downbeats"] else (None, None)
        rows.append({"t": at, "kind": t["kind"], "beat": round(b, 3), "offset_ms": round(off * 1000),
                     "on_beat": abs(off) <= tol, "snappable": abs(off) <= window,
                     "downbeat": round(db, 3) if db is not None else None,
                     "on_downbeat": doff is not None and abs(doff) <= tol})
    on = sum(r["on_beat"] for r in rows)
    med = float(np.median([abs(r["offset_ms"]) for r in rows])) if rows else None
    status = "pass" if rows and on / len(rows) >= 0.8 else ("warn" if rows else "pass")
    return {"video": video.name, "bpm": spec["bpm"], "transitions": len(rows), "on_beat": on,
            "on_downbeat": sum(r["on_downbeat"] for r in rows), "median_offset_ms": med,
            "tolerance_ms": round(tol * 1000), "status": status,
            "message": (f"전환 {len(rows)}개 중 {on}개가 박 위 (±{round(tol * 1000)}ms), 중앙값 {med:.0f}ms" if rows
                        else "전환이 없어 박 맞춤을 잴 수 없음"),
            "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analyze")
    p.add_argument("audio")
    p.add_argument("--out")
    p.add_argument("--bpm-hint", type=float)
    p = sub.add_parser("check")
    p.add_argument("beats")
    p.add_argument("video")
    p.add_argument("--window", type=float, default=0.3)
    p.add_argument("--out")
    p = sub.add_parser("snap")
    p.add_argument("beats")
    p.add_argument("times", nargs="+", type=float)
    p.add_argument("--window", type=float, default=0.3)
    a = ap.parse_args()

    if a.cmd == "analyze":
        src = Path(a.audio).resolve()
        spec = analyze(src, a.bpm_hint)
        out = Path(a.out) if a.out else src.with_name(src.stem + ".beats.json")
        out.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{spec['bpm']} BPM ({spec['beat_seconds']} s/beat), {len(spec['beats'])} beats, "
              f"{len(spec['downbeats'])} bars, {len(spec['accents'])} accents, first beat {spec['first_beat']} s -> {out}")
    elif a.cmd == "check":
        spec = json.loads(Path(a.beats).read_text(encoding="utf-8"))
        r = check(spec, Path(a.video).resolve(), a.window)
        if a.out:
            Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for x in r["rows"]:
            print(f"{x['t']:8.3f}s {x['kind']:<10} nearest beat {x['beat']:8.3f}s  {x['offset_ms']:+5d} ms"
                  + ("  ON" if x["on_beat"] else ("  snap" if x["snappable"] else "")))
        print(f"=> {r['status']}: {r['message']}")
    else:
        spec = json.loads(Path(a.beats).read_text(encoding="utf-8"))
        for x in a.times:
            b, off = nearest(spec["beats"], x)
            db, doff = nearest(spec["downbeats"], x) if spec["downbeats"] else (None, 0)
            tip = f"-> {b:.3f}" if abs(off) <= a.window else "(keep: no beat within window)"
            print(f"{x:.3f}s  nearest beat {b:.3f} ({off * 1000:+.0f} ms)  bar {db}  {tip}")


if __name__ == "__main__":
    main()
