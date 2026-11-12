#!/usr/bin/env python3
"""Measure a reference video (and later our own render) — "measure first, don't guess".

  python tools/ref_measure.py measure <video> [--range 0:30-1:30] [--out <dir>]
  python tools/ref_measure.py compare <reference spec.json|dir> <result video|spec.json|dir> [--tol 0.2] [--out <dir>]

measure writes <out>/spec.json (numbers), spec.md (a reference spec sheet a person or Claude can read),
contact.jpg (one frame every few seconds) and cuts.jpg (frames just before / after the first transitions).
compare measures the result with the *same code* and writes compare.md / compare.json: every metric side by side
with the difference, flagged when it is off by more than --tol (default ±20%, the 4-step workflow's acceptance rule).

What is measured (all on 96x54 grey frames at the source frame rate unless noted):
  transitions   consecutive-frame difference spikes; kind = cut (1-2 frames), gradual (dissolve/wipe/zoom —
                which one is "추정", look at cuts.jpg), fade-black, flash
  shots         length of each shot between transitions; mean / median / per minute
  animation fps hold pattern while things move: how many source frames each drawing is held (1s/2s/3s)
                -> effective fps (e.g. 24 fps on twos = 12)
  motion        mean frame difference per second, absolute (not normalised), plus per-shot and the last 2 s
  still jitter  difference left on "held" frames: grain / boil / handheld that changes every frame (추정)
  colour        8-colour palette (HEX + share) from 1 frame/s at 64x36, mean saturation / value, white ratio
Not measured here: sound (BPM, beats — later), camera direction, easing curves; write those as "추정" after looking.
Needs ffmpeg/ffprobe and numpy. A YouTube link is not read: download the file first (e.g. yt-dlp on your own machine).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_render import grey_frames, probe, runs  # noqa: E402  (shared frame reader)

MW, MH = 96, 54            # motion analysis size (as in the 4-step prompt)
CUT_ABS = 6.0              # a transition frame differs by at least this (0-255 grey mean)
CUT_REL = 4.0              # ... and by this many times the local median difference
GRAD_REL, GRAD_ADD = 2.2, 4.0   # gradual (dissolve/wipe): change over ~0.25 s >= 2.2x and +4 above its local median
HOLD_EPS = 0.35            # below this a frame counts as "the same drawing" (codec noise sits under it)
MOVING_MIN = 1.0           # a stretch counts as "moving" when its changed frames differ by at least this
MAX_FPS = 60
JITTER_ON = 0.1            # share of pixels changing every frame above this = live grain / boil
FONT = next((f for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",   # Linux
                          "/System/Library/Fonts/Supplemental/Arial Bold.ttf",       # macOS
                          "/System/Library/Fonts/Helvetica.ttc",
                          "C:/Windows/Fonts/arialbd.ttf") if Path(f).exists()), None)


def _has_drawtext() -> bool:
    """Homebrew's default ffmpeg is built without libfreetype -> no drawtext filter."""
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    except OSError:
        return False
    return any(line.split()[1:2] == ["drawtext"] for line in out.splitlines() if line.strip())


# timestamp label on sheet tiles; left out (sheets still made) when drawtext or a font is missing
STAMP = ("drawtext=fontfile='{}':text='%{{pts\\:hms}}':x=6:y=6:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.6,"
         .format(FONT.replace(":", "\\:")) if FONT and _has_drawtext() else "")


def parse_time(s: str) -> float:
    parts = [float(p) for p in s.split(":")]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


def parse_range(r: str | None) -> tuple[float | None, float | None]:
    if not r:
        return None, None
    a, _, b = r.partition("-")
    start = parse_time(a) if a else 0.0
    return start, (parse_time(b) - start) if b else None


# ---------------- measurements ----------------

def local_median(x: np.ndarray, k: int) -> np.ndarray:
    pad = np.pad(np.nan_to_num(x), k, mode="edge")
    return np.array([np.median(pad[i: i + 2 * k + 1]) for i in range(len(x))])


def transitions(d: np.ndarray, luma: np.ndarray, fps: float, dk: np.ndarray | None = None, lag: int = 1) -> list[dict]:
    """d: frame-to-frame RGB difference (cuts, flashes, fades). dk: difference over `lag` frames, which catches
    dissolves and wipes whose single-frame change is small."""
    n = len(d)
    if n < 3:
        return []
    k = max(3, int(fps // 2))
    spike = (np.nan_to_num(d) > CUT_ABS) & (np.nan_to_num(d) > CUT_REL * (local_median(d, k) + 0.25))
    if dk is not None:
        kk = max(k, int(fps))
        mk = local_median(dk, kk)
        slow = (np.nan_to_num(dk) > GRAD_REL * (mk + 0.25)) & (np.nan_to_num(dk) > mk + GRAD_ADD)
        for t0, length in runs(slow, 1):    # the window [i-lag, i] changed a lot: mark it as one transition
            i0, i1 = int(t0), int(t0 + length)
            if not spike[max(0, i0 - lag): i1].any():
                spike[max(0, i0 - lag + 1): i1] = True
    out = []
    for t0, length in runs(spike, 1):          # in frames
        i0, i1 = int(t0), int(t0 + length)      # spike frames [i0, i1)
        lo, hi = max(0, i0 - 2), min(n, i1 + 2)
        if luma[lo:hi].min() < 8 and luma[lo:hi].min() < 0.4 * max(luma[lo], luma[hi - 1], 1):
            kind = "fade-black"
        elif luma[lo:hi].max() > 215 and luma[lo:hi].max() > 1.6 * max(luma[lo], luma[hi - 1], 1):
            kind = "flash"
        elif length <= 2:
            kind = "cut"
        else:
            kind = "gradual"
        out.append({"t": round(i0 / fps, 3), "frame": i0, "frames": int(length), "kind": kind,
                    "strength": round(float(np.nanmax(d[i0:i1])), 2)})
    # merge pieces of one transition (e.g. a fade whose first half looked "gradual"); a fade or flash wins
    merged: list[dict] = []
    for t in out:
        if merged and t["frame"] - (merged[-1]["frame"] + merged[-1]["frames"]) < 3 + lag:
            m = merged[-1]
            m["frames"] = t["frame"] + t["frames"] - m["frame"]
            m["strength"] = max(m["strength"], t["strength"])
            special = [x for x in (m["kind"], t["kind"]) if x in ("fade-black", "flash")]
            m["kind"] = special[0] if special else "gradual"
        else:
            merged.append(t)
    return merged


def shots(trans: list[dict], dur: float) -> list[dict]:
    edges = [0.0] + [t["t"] for t in trans] + [dur]
    return [{"start": round(a, 2), "seconds": round(b - a, 2)} for a, b in zip(edges, edges[1:]) if b - a > 0.05]


def hold_pattern(d: np.ndarray, trans: list[dict], fps: float) -> dict:
    """How long each drawing is held while something moves. Returns counts of hold lengths 1..6 frames."""
    dd = np.nan_to_num(d)
    skip = np.zeros(len(dd), bool)
    for t in trans:
        skip[max(0, t["frame"] - 1): t["frame"] + t["frames"] + 1] = True
    # noise floor: grain / codec noise that changes every frame; a new drawing must stand clearly above it
    floor = float(np.percentile(dd[~skip], 20)) if (~skip).sum() else 0.0
    eps = max(HOLD_EPS, 2.0 * floor)
    changed = (dd >= eps) & ~skip
    holds: dict[int, int] = {}
    idx = np.flatnonzero(changed)
    for a, b in zip(idx, idx[1:]):
        gap = int(b - a)                       # frames between two changes = how long the drawing was shown
        if gap <= 6 and not skip[a:b + 1].any():
            holds[gap] = holds.get(gap, 0) + 1
    total = sum(holds.values())
    if not total:
        return {"holds": {}, "mode": None, "effective_fps": None, "note": "움직이는 구간이 거의 없어 측정 못 함"}
    mode = max(holds, key=holds.get)
    share = holds[mode] / total
    return {"holds": {f"{k}s": v for k, v in sorted(holds.items())}, "mode": mode, "change_threshold": round(eps, 3),
            "mode_share": round(share, 2), "effective_fps": round(fps / mode, 2),
            "note": ("매 프레임 움직임 (부드러운 보간)" if mode == 1 else f"{mode}프레임씩 유지 (on {mode}s, 계단식)")
                    + ("" if share >= 0.6 else " — 섞여 있음")}


def still_jitter(video: Path, start: float | None, seconds: float) -> dict:
    """Grain / boil that changes every frame: share of pixels changing by more than 2 grey levels between
    consecutive frames, at 480x270 (the 96x54 analysis averages grain away). Median over three 2 s windows.
    A moving object touches only part of the frame; grain touches all of it."""
    shares = []
    for at in (0.25, 0.5, 0.75):
        t0 = (start or 0.0) + max(0.0, seconds * at - 1.0)
        g = grey_frames(video, fps=None, start=t0, dur=min(2.0, seconds), size=(480, 270))
        if len(g) > 2:
            a = np.abs(np.diff(g, axis=0)).reshape(len(g) - 1, -1)
            shares.append(float(np.median((a > 2).mean(1))))
    level = float(np.median(shares)) if shares else 0.0
    return {"level": round(level, 3), "metric": "매 프레임 바뀌는 픽셀 비율 (480×270, |차이|>2)",
            "note": "화면 전체가 매 프레임 조금씩 바뀜 — 그레인·보일링·핸드헬드 (어느 것인지는 추정)" if level > JITTER_ON
            else "정지된 부분은 고정 — 그레인 없음 또는 고정 질감"}


def motion_table(d: np.ndarray, fps: float) -> list[float]:
    dd = np.nan_to_num(d)
    step = max(1, int(round(fps)))
    return [round(float(dd[i: i + step].mean()), 3) for i in range(0, len(dd), step)]


def kmeans_palette(px: np.ndarray, k: int = 8, iters: int = 12) -> list[dict]:
    rng = np.random.default_rng(7)
    px = px[rng.choice(len(px), min(len(px), 40000), replace=False)]
    # init: k-means++ lite
    cent = [px[rng.integers(len(px))]]
    for _ in range(k - 1):
        dist = np.min([((px - c) ** 2).sum(1) for c in cent], axis=0)
        cent.append(px[rng.choice(len(px), p=dist / dist.sum())] if dist.sum() else px[rng.integers(len(px))])
    cent = np.array(cent)
    for _ in range(iters):
        lab = np.argmin(((px[:, None, :] - cent[None]) ** 2).sum(2), axis=1)
        for j in range(k):
            if (lab == j).any():
                cent[j] = px[lab == j].mean(0)
    lab = np.argmin(((px[:, None, :] - cent[None]) ** 2).sum(2), axis=1)
    out = [{"hex": "#%02X%02X%02X" % tuple(int(round(v)) for v in c), "share": round(float((lab == j).mean()), 3)}
           for j, c in enumerate(cent)]
    return sorted([o for o in out if o["share"] > 0.005], key=lambda o: -o["share"])


def colour(path: Path, start, dur) -> dict:
    rgb = grey_frames(path, fps=1, start=start, dur=dur, size=(64, 36), color=True) / 255.0
    if not len(rgb):
        return {}
    px = rgb.reshape(-1, 3)
    mx, mn = px.max(1), px.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    return {"palette": kmeans_palette(px * 255), "saturation": round(float(sat.mean()), 3),
            "value": round(float(mx.mean()), 3), "white_ratio": round(float(((mx > 0.9) & (sat < 0.1)).mean()), 3),
            "dark_ratio": round(float((mx < 0.15).mean()), 3)}


def stats(xs: list[float]) -> dict:
    a = np.array(xs, float)
    if not len(a):
        return {}
    return {"mean": round(float(a.mean()), 3), "median": round(float(np.median(a)), 3),
            "p90": round(float(np.percentile(a, 90)), 3), "max": round(float(a.max()), 3)}


# ---------------- sheets ----------------

def contact_sheet(path: Path, out: Path, start, dur, seconds: float) -> None:
    every = max(1.0, round(seconds / 24, 1))     # about 24 tiles
    cols = 6
    rows = max(1, int(np.ceil(seconds / every / cols)))
    vf = f"fps=1/{every},scale=320:-2,{STAMP}tile={cols}x{rows}:padding=4:color=gray"
    _ff(path, start, dur, vf, out)


def cuts_sheet(path: Path, out: Path, trans: list[dict], fps: float, offset: float) -> None:
    ts = []
    for t in trans[:8]:
        ts += [offset + max(0.0, t["t"] - 2 / fps), offset + t["t"] + (t["frames"] + 1) / fps]
    if not ts:
        return
    sel = "+".join(f"between(t,{x - 0.5 / fps:.4f},{x + 0.5 / fps:.4f})" for x in ts)
    vf = f"select='{sel}',scale=320:-2,{STAMP}tile=2x{max(1, len(ts) // 2)}:padding=4:color=gray"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vf", vf, "-fps_mode", "vfr",
                    "-frames:v", "1", str(out)], capture_output=True)


def _ff(path, start, dur, vf, out):
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    subprocess.run(cmd + ["-i", str(path), "-vf", vf, "-frames:v", "1", str(out)], capture_output=True)


# ---------------- measure ----------------

def measure(video: Path, rng: str | None = None, out: Path | None = None, sheets: bool = True) -> dict:
    info = probe(video)
    start, dur = parse_range(rng)
    src_fps = min(info["fps"] or 30, MAX_FPS)
    g = grey_frames(video, fps=None if (info["fps"] or 0) <= MAX_FPS else MAX_FPS, start=start, dur=dur,
                    size=(MW, MH))
    if not len(g):
        sys.exit(f"no frames read from {video}")
    seconds = round(len(g) / src_fps, 2)
    d = np.concatenate([[np.nan], np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))])
    luma = g.mean(axis=(1, 2))
    # transitions on colour, so a cut between two equally bright shots is not missed
    rgb = grey_frames(video, fps=None if (info["fps"] or 0) <= MAX_FPS else MAX_FPS, start=start, dur=dur,
                      size=(MW, MH), color=True)[: len(g)]
    dc = np.concatenate([[np.nan], np.abs(np.diff(rgb, axis=0)).mean(axis=(1, 2, 3))])
    lag = max(2, int(round(src_fps / 4)))
    dk = np.concatenate([[np.nan] * lag, np.abs(rgb[lag:] - rgb[:-lag]).mean(axis=(1, 2, 3))])
    del rgb
    trans = transitions(dc, luma, src_fps, dk, lag)
    sh = shots(trans, seconds)
    mt = motion_table(d, src_fps)
    tail_n = int(2 * src_fps)
    tail = np.nan_to_num(d[-tail_n:])
    ending = {"motion": round(float(tail.mean()), 3), "last_luma": round(float(luma[-1]), 1),
              "fades_to_black": bool(luma[-1] < 10 and luma[-tail_n] > 20),
              "transitions_in_last_2s": [t for t in trans if t["t"] >= seconds - 2]}
    shot_motion = []
    for s in sh:
        a, b = int(s["start"] * src_fps), int((s["start"] + s["seconds"]) * src_fps)
        shot_motion.append(round(float(np.nan_to_num(d[a + 2: b - 1]).mean()) if b - a > 3 else 0.0, 3))
    spec = {
        "file": video.name, "measured": dt.datetime.now().isoformat(timespec="seconds"),
        "range": {"start": start or 0.0, "seconds": seconds}, "source": info, "analysis_fps": src_fps,
        "transitions": trans,
        "transition_kinds": {k: sum(t["kind"] == k for t in trans) for k in ("cut", "gradual", "fade-black", "flash")},
        "shots": [dict(s, motion=m) for s, m in zip(sh, shot_motion)],
        "shot_seconds": stats([s["seconds"] for s in sh]),
        "transitions_per_minute": round(len(trans) / max(seconds, 1e-6) * 60, 2),
        "animation": hold_pattern(d, trans, src_fps), "still_jitter": still_jitter(video, start, seconds),
        "motion_per_second": mt, "motion": stats(mt), "ending": ending,
        "colour": colour(video, start, dur),
        "thresholds": {"size": [MW, MH], "cut_abs": CUT_ABS, "cut_rel": CUT_REL, "grad_rel": GRAD_REL,
                       "grad_add": GRAD_ADD, "hold_eps": HOLD_EPS,
                       "moving_min": MOVING_MIN},
    }
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "spec.md").write_text(spec_md(spec), encoding="utf-8")
        if sheets:
            contact_sheet(video, out / "contact.jpg", start, dur, seconds)
            cuts_sheet(video, out / "cuts.jpg", trans, src_fps, start or 0.0)
    return spec


KIND_KO = {"cut": "컷", "gradual": "점진 전환(디졸브·와이프·줌 중 하나, 추정)", "fade-black": "검은 화면으로 페이드", "flash": "플래시"}


def spec_md(s: dict) -> str:
    a, c, m = s["animation"], s.get("colour", {}), s["motion"]
    L = [f"# 레퍼런스 스펙 시트 — {s['file']}", "",
         f"측정 {s['measured']} · 구간 {s['range']['start']:g}초부터 {s['range']['seconds']:g}초 · "
         f"원본 {s['source']['width']}×{s['source']['height']} {s['source']['fps']}fps · 분석 {s['thresholds']['size'][0]}×{s['thresholds']['size'][1]} 회색",
         "", "모든 값은 `tools/ref_measure.py` 측정값이다. '(추정)' 표시는 숫자로 확정할 수 없어 눈으로 확인해야 하는 항목.", "",
         "## 연출", "",
         f"- 전환 {len(s['transitions'])}회 (분당 {s['transitions_per_minute']}) — " +
         ", ".join(f"{KIND_KO[k]} {v}" for k, v in s["transition_kinds"].items() if v) if s["transitions"] else "- 전환 없음 (원테이크)",
         f"- 샷 길이: 평균 {s['shot_seconds'].get('mean', 0)}초 · 중앙값 {s['shot_seconds'].get('median', 0)}초 · 최장 {s['shot_seconds'].get('max', 0)}초",
         "", "| # | 시각(초) | 프레임 | 길이(프레임) | 방식 | 세기 |", "|---|---|---|---|---|---|"]
    L += [f"| {i + 1} | {t['t']} | {t['frame']} | {t['frames']} | {KIND_KO[t['kind']]} | {t['strength']} |"
          for i, t in enumerate(s["transitions"][:40])]
    L += ["", "## 움직임 문법", "",
          f"- 실제 애니메이션: **{a['note']}**" + (f" → 실효 {a['effective_fps']}fps (유지 길이 분포 {a['holds']})" if a.get("effective_fps") else ""),
          f"- 그레인·보일링: {s['still_jitter']['level']} ({s['still_jitter']['metric']}) — {s['still_jitter']['note']}",
          f"- 움직임 양(초당 평균 프레임 차이, 0~255): 평균 {m.get('mean')} · 중앙값 {m.get('median')} · 상위10% {m.get('p90')} · 최대 {m.get('max')}",
          f"- 엔딩(마지막 2초): 움직임 {s['ending']['motion']}, " + ("검은 화면으로 페이드" if s["ending"]["fades_to_black"] else f"마지막 밝기 {s['ending']['last_luma']}"),
          "", "구간별 움직임 양 (초 단위, 절대값):", "", "```",
          " ".join(f"{v:.2f}" for v in s["motion_per_second"]), "```", "",
          "샷별 움직임 양: " + ", ".join(f"{x['start']}s {x['motion']}" for x in s["shots"][:30]), ""]
    if c:
        L += ["## 물성 — 색", "",
              f"- 평균 채도 {c['saturation']} · 평균 명도 {c['value']} · 흰색 비율 {c['white_ratio']} · 어두운 비율 {c['dark_ratio']}",
              "- 대표 팔레트: " + " ".join(f"`{p['hex']}` {p['share'] * 100:.0f}%" for p in c["palette"]), ""]
    L += ["## 눈으로 채울 항목 (추정으로 표시)", "",
          "- 카메라 이동 방향·속도, 이징(부드러움/계단/반동), 모션 블러, 레이어 깊이(그림자·시차), 질감·테두리, 하프톤·비네팅·색수차",
          "- 사운드: BPM·강박·효과음 위치 (이 도구는 아직 재지 않음)",
          "- 이 영상다움을 만드는 특징 3~5개 (우선순위)", "",
          "참고: `contact.jpg`(몇 초마다 한 장), `cuts.jpg`(앞쪽 전환 8개의 직전·직후 프레임)", ""]
    return "\n".join(L)


# ---------------- compare ----------------

def metrics(s: dict) -> dict[str, float | None]:
    c = s.get("colour", {})
    return {
        "transitions_per_minute": s["transitions_per_minute"],
        "shot_seconds_median": s["shot_seconds"].get("median"),
        "effective_fps": s["animation"].get("effective_fps"),
        "motion_mean": s["motion"].get("mean"),
        "motion_median": s["motion"].get("median"),
        "motion_p90": s["motion"].get("p90"),
        "still_jitter": s["still_jitter"]["level"],
        "saturation": c.get("saturation"), "value": c.get("value"), "white_ratio": c.get("white_ratio"),
    }


LABELS = {"transitions_per_minute": "분당 전환 수", "shot_seconds_median": "샷 길이 중앙값(초)",
          "effective_fps": "실효 애니메이션 fps", "motion_mean": "움직임 양 평균", "motion_median": "움직임 양 중앙값",
          "motion_p90": "움직임 양 상위10%", "still_jitter": "매 프레임 바뀌는 픽셀 비율(그레인)", "saturation": "평균 채도",
          "value": "평균 명도", "white_ratio": "흰색 비율"}


def palette_distance(a: list[dict], b: list[dict]) -> float | None:
    """Share-weighted mean RGB distance from each reference colour to the closest result colour (0-441)."""
    if not a or not b:
        return None
    h = lambda x: np.array([int(x[i: i + 2], 16) for i in (1, 3, 5)], float)  # noqa: E731
    bb = np.array([h(p["hex"]) for p in b])
    return round(float(sum(p["share"] * np.sqrt(((bb - h(p["hex"])) ** 2).sum(1)).min() for p in a)
                       / max(sum(p["share"] for p in a), 1e-6)), 1)


def compare(ref: dict, res: dict, tol: float = 0.2) -> dict:
    rows = []
    mr, ms = metrics(ref), metrics(res)
    for k in mr:
        a, b = mr[k], ms[k]
        if a is None or b is None:
            rows.append({"metric": k, "reference": a, "result": b, "diff": None, "ok": None})
            continue
        rel = (b - a) / abs(a) if abs(a) > 1e-9 else (0.0 if abs(b) < 1e-9 else float("inf"))
        ok = abs(rel) <= tol
        if k == "still_jitter":       # near zero on both sides is common: judge "live grain or not"
            ok = (a > JITTER_ON) == (b > JITTER_ON) and (a <= JITTER_ON or abs(rel) <= tol)
        rows.append({"metric": k, "reference": a, "result": b, "diff": round(rel, 3) if rel != float("inf") else None,
                     "ok": ok})
    # motion over normalised time (10 bins), absolute values
    def bins(xs):
        a = np.array(xs, float)
        return [round(float(x.mean()), 3) if len(x) else 0.0 for x in np.array_split(a, 10)] if len(a) else []
    rb, sb = bins(ref["motion_per_second"]), bins(res["motion_per_second"])
    timeline = [{"bin": i + 1, "reference": a, "result": b,
                 "diff": round((b - a) / a, 3) if a > 1e-9 else None,
                 "ok": (abs((b - a) / a) <= tol) if a > 1e-9 else (b < 0.05)} for i, (a, b) in enumerate(zip(rb, sb))]
    pd = palette_distance(ref.get("colour", {}).get("palette", []), res.get("colour", {}).get("palette", []))
    off = [r["metric"] for r in rows if r["ok"] is False] + [f"motion_bin_{t['bin']}" for t in timeline if not t["ok"]]
    return {"reference": ref["file"], "result": res["file"], "tolerance": tol, "metrics": rows,
            "motion_timeline": timeline, "palette_distance": pd,
            "palette_ok": None if pd is None else pd <= 40, "off": off,
            "kinds": {"reference": ref["transition_kinds"], "result": res["transition_kinds"]}}


def compare_md(c: dict) -> str:
    f = lambda v: "—" if v is None else (f"{v:+.0%}" if isinstance(v, float) and abs(v) < 100 else str(v))  # noqa: E731
    mark = lambda ok: "—" if ok is None else ("✅" if ok else "❌")  # noqa: E731
    L = [f"# 측정 대조표 — {c['reference']} vs {c['result']}", "",
         f"허용 오차 ±{c['tolerance']:.0%} (절대값 비교). ❌ 항목은 원인을 적고 파라미터를 고쳐 다시 렌더한다.", "",
         "| 항목 | 레퍼런스 | 결과 | 차이 | 판정 |", "|---|---|---|---|---|"]
    L += [f"| {LABELS[r['metric']]} | {r['reference']} | {r['result']} | {f(r['diff'])} | {mark(r['ok'])} |" for r in c["metrics"]]
    L += [f"| 팔레트 거리(RGB, 40 이하 통과) | — | {c['palette_distance']} | — | {mark(c['palette_ok'])} |", "",
          f"전환 방식: 레퍼런스 {c['kinds']['reference']} / 결과 {c['kinds']['result']}", "",
          "## 시간대별 움직임 양 (전체 길이를 10등분, 절대값)", "", "| 구간 | 레퍼런스 | 결과 | 차이 | 판정 |", "|---|---|---|---|---|"]
    L += [f"| {t['bin']} | {t['reference']} | {t['result']} | {f(t['diff'])} | {mark(t['ok'])} |" for t in c["motion_timeline"]]
    L += ["", f"**허용 오차를 넘은 항목 {len(c['off'])}개**: " + (", ".join(c["off"]) if c["off"] else "없음"), ""]
    return "\n".join(L)


def load_spec(p: Path, out: Path | None) -> dict:
    if p.is_dir():
        p = p / "spec.json"
    if p.suffix == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    return measure(p, out=out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("measure", help="measure one video")
    p.add_argument("video")
    p.add_argument("--range", help="e.g. 0:00-5:00, 30-90, 1:20- (seconds or m:ss)")
    p.add_argument("--out", help="output folder (default: <video>.measure/)")
    p = sub.add_parser("compare", help="measure the result with the same code and compare")
    p.add_argument("reference", help="reference spec.json, its folder, or a video")
    p.add_argument("result", help="result video, spec.json or folder")
    p.add_argument("--tol", type=float, default=0.2)
    p.add_argument("--out", help="output folder (default: next to the result)")
    a = ap.parse_args()

    if a.cmd == "measure":
        v = Path(a.video).resolve()
        if not v.exists():
            sys.exit(f"{v} not found")
        out = Path(a.out) if a.out else v.with_name(v.name + ".measure")
        s = measure(v, a.range, out)
        print(spec_md(s).split("## 물성")[0])
        print(f"=> {out}/spec.md, spec.json, contact.jpg, cuts.jpg")
        return
    res_p = Path(a.result).resolve()
    out = Path(a.out) if a.out else (res_p if res_p.is_dir() else res_p.with_name(res_p.name + ".measure"))
    ref = load_spec(Path(a.reference).resolve(), None)
    res = load_spec(res_p, out if res_p.suffix not in (".json",) and not res_p.is_dir() else None)
    c = compare(ref, res, a.tol)
    out.mkdir(parents=True, exist_ok=True)
    (out / "compare.json").write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "compare.md").write_text(compare_md(c), encoding="utf-8")
    print(compare_md(c))
    print(f"=> {out}/compare.md")


if __name__ == "__main__":
    main()
