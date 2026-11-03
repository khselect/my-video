#!/usr/bin/env python3
"""Generate narration per scene from script.json and write each scene's duration back.

usage: tts.py <project>/script.json --provider {google,elevenlabs,openai,azure,none} [--voice NAME] [--pad 0.6]

Keys come from environment variables (or <project>/.env):
  google      GOOGLE_TTS_API_KEY        voice default ko-KR-Chirp3-HD-Charon
  elevenlabs  ELEVENLABS_API_KEY        voice = voice_id (default: ELEVENLABS_VOICE_ID)
  openai      OPENAI_API_KEY            voice default "alloy", model gpt-4o-mini-tts
  azure       AZURE_SPEECH_KEY + AZURE_SPEECH_REGION   voice default ko-KR-SunHiNeural
  none        no audio; duration estimated from text length (Korean ~7.5 chars/s)

Output: <project>/assets/voice/<scene-id>.mp3 and script.json scenes[].duration / .voice
Only the standard library is used; ffprobe (ffmpeg) measures audio length.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape


def load_env(project: Path) -> None:
    env = project / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def need(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"missing environment variable {name} (set it or put it in <project>/.env)")
    return val


def post(url: str, body: bytes, headers: dict) -> bytes:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def tts_google(text: str, voice: str | None) -> bytes:
    key = need("GOOGLE_TTS_API_KEY")
    voice = voice or "ko-KR-Chirp3-HD-Charon"
    body = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": voice[:5], "name": voice},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.0},
    }).encode()
    res = json.loads(post(f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}", body,
                          {"Content-Type": "application/json"}))
    return base64.b64decode(res["audioContent"])


def tts_elevenlabs(text: str, voice: str | None) -> bytes:
    key = need("ELEVENLABS_API_KEY")
    voice = voice or need("ELEVENLABS_VOICE_ID")
    body = json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode()
    return post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128", body,
                {"xi-api-key": key, "Content-Type": "application/json"})


def tts_openai(text: str, voice: str | None) -> bytes:
    key = need("OPENAI_API_KEY")
    body = json.dumps({"model": "gpt-4o-mini-tts", "voice": voice or "alloy", "input": text,
                       "response_format": "mp3"}).encode()
    return post("https://api.openai.com/v1/audio/speech", body,
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})


def tts_azure(text: str, voice: str | None) -> bytes:
    key, region = need("AZURE_SPEECH_KEY"), need("AZURE_SPEECH_REGION")
    voice = voice or "ko-KR-SunHiNeural"
    ssml = (f"<speak version='1.0' xml:lang='{voice[:5]}'><voice name='{voice}'>"
            f"{escape(text)}</voice></speak>").encode()
    return post(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1", ssml, {
        "Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3", "User-Agent": "edu-video"})


PROVIDERS = {"google": tts_google, "elevenlabs": tts_elevenlabs, "openai": tts_openai, "azure": tts_azure}


def audio_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script", type=Path)
    ap.add_argument("--provider", default="google", choices=[*PROVIDERS, "none"])
    ap.add_argument("--voice")
    ap.add_argument("--pad", type=float, default=0.6, help="seconds of air after each line")
    ap.add_argument("--min", type=float, default=3.5, help="minimum scene length")
    a = ap.parse_args()

    project = a.script.parent
    load_env(project)
    data = json.loads(a.script.read_text(encoding="utf-8"))
    voice_dir = project / "assets" / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)

    start = 0.0
    for sc in data["scenes"]:
        text = sc.get("narration", "").strip()
        if a.provider == "none" or not text:
            secs = max(a.min, len(text.replace(" ", "")) / 7.5) if text else sc.get("duration", a.min)
            sc.pop("voice", None)
        else:
            mp3 = voice_dir / f"{sc['id']}.mp3"
            mp3.write_bytes(PROVIDERS[a.provider](text, a.voice))
            secs = audio_seconds(mp3)
            sc["voice"] = f"assets/voice/{mp3.name}"
            sc["voice_seconds"] = round(secs, 2)
        sc["start"] = round(start, 2)
        sc["duration"] = round(max(a.min, secs + a.pad), 2)
        start += sc["duration"]
        print(f"{sc['id']:<12} start {sc['start']:>6.2f}s  dur {sc['duration']:>5.2f}s  {text[:40]}")

    data["total_duration"] = round(start, 2)
    a.script.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"total {start:.2f}s -> {a.script}")


if __name__ == "__main__":
    main()
