#!/usr/bin/env python3
"""Render a lecture with an imported video-style skill and record it as a new version.

Called by Lecture Studio (6 render) with the command already filled from studio/styles/<id>.json:

  render_style.py <lecture-dir> --kind paper-cutout --out <tmp.mp4> --cmd-json '[...]' \
      [--audio-args-json '["--audio","{audio}"]'] [--narration n.wav] [--music m.mp3] [--cwd dir] \
      [--existing <work>/output.mp4] [--note "..."]

Audio: narration and/or music are mixed into build/style-audio.wav (music ducked under the voice).
If the skill's renderer takes an audio file ({audio} in --audio-args-json) it gets that file; otherwise the
audio is muxed onto the rendered video with ffmpeg. The result goes through render_version.py add.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def sh(cmd: list[str], cwd: Path | None = None) -> None:
    print("$ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode:
        sys.exit(f"failed (exit {r.returncode}): {cmd[0]}")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def build_audio(narration: Path | None, music: Path | None, out: Path) -> Path | None:
    if not narration and not music:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    if narration and music:
        # music bed at -18 dB under the voice, ending with the voice (2 s fade)
        d = duration(narration)
        filt = (f"[1:a]volume=0.13,afade=t=out:st={max(0, d - 2):.2f}:d=2[m];"
                "[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]")
        sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(narration), "-stream_loop", "-1",
            "-i", str(music), "-filter_complex", filt, "-map", "[a]", "-ar", "48000", str(out)])
    else:
        sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(narration or music), "-ar", "48000", str(out)])
    print(f"audio -> {out} ({duration(out):.1f}s)", flush=True)
    return out


def mux(video: Path, audio: Path) -> None:
    tmp = video.with_suffix(".mux.mp4")
    d = duration(video)
    sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-i", str(audio),
        "-filter_complex", f"[1:a]apad,atrim=0:{d:.3f},afade=t=out:st={max(0, d - 1.5):.3f}:d=1.5[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(tmp)])
    tmp.replace(video)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lecture", type=Path)
    ap.add_argument("--kind", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cmd-json", default="[]")
    ap.add_argument("--audio-args-json", default="[]")
    ap.add_argument("--narration", type=Path)
    ap.add_argument("--music", type=Path)
    ap.add_argument("--cwd", type=Path)
    ap.add_argument("--existing", type=Path, help="no render command: register this file (made in 5 visuals)")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    lecture = a.lecture.resolve()
    for p in (a.narration, a.music):
        if p and not p.exists():
            sys.exit(f"audio file not found: {p}")
    audio = build_audio(a.narration, a.music, lecture / "build" / "style-audio.wav")

    cmd, audio_args = json.loads(a.cmd_json), json.loads(a.audio_args_json)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.unlink(missing_ok=True)
    if cmd:
        if audio and audio_args:
            cmd += [x.replace("{audio}", str(audio)) for x in audio_args]
        sh(cmd, cwd=a.cwd or lecture)
        if not a.out.exists():
            sys.exit(f"the renderer finished but {a.out} was not written")
        if audio and not audio_args:
            mux(a.out, audio)
    else:
        if not a.existing or not a.existing.exists():
            sys.exit(f"no render command and no finished video at {a.existing} — run 5 visuals first")
        shutil.copy2(a.existing, a.out)
        if audio:
            mux(a.out, audio)

    sh([sys.executable, str(TOOLS / "render_version.py"), "add", str(a.out), str(lecture),
        "--kind", a.kind, "--move", "--note", a.note])


if __name__ == "__main__":
    main()
