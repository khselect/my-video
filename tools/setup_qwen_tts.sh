#!/usr/bin/env bash
# Install local Qwen3-TTS (voice clone) into ~/.edu-video/qwen-venv and pre-download the model.
# usage: setup_qwen_tts.sh [1.7B|0.6B]
#   1.7B  best quality, ~6-8 GB VRAM (NVIDIA), Apple Silicon 16 GB+, or CPU with 16 GB RAM (slow)
#   0.6B  ~4-6 GB VRAM, also usable on CPU (slow)
# Downloads both models narrate.py uses:
#   <SIZE>-CustomVoice  built-in speakers (narrate.py --backend customvoice, the default)
#   <SIZE>-Base         voice clone (voice_clone.py, narrate.py --backend clone)
# Env: QWEN_VENV=<dir> puts the venv elsewhere (e.g. video-tools/qwen-tts-env); models stay in ~/.edu-video/models
set -euo pipefail
SIZE="${1:-1.7B}"
MODEL="Qwen/Qwen3-TTS-12Hz-${SIZE}-Base"
HOME_DIR="$HOME/.edu-video"
VENV="${QWEN_VENV:-$HOME_DIR/qwen-venv}"   # override: QWEN_VENV=../qwen-tts-env
mkdir -p "$HOME_DIR/models" "$HOME_DIR/voices"

PY="$(command -v python3.12 || command -v python3.11 || command -v python3)"
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required (3.12 recommended)"'
command -v ffmpeg >/dev/null || { echo "ffmpeg required (brew install ffmpeg / apt install ffmpeg / winget install ffmpeg)"; exit 1; }
command -v sox >/dev/null || echo "note: sox not found (brew install sox / apt install sox); qwen-tts may warn without it"

[ -d "$VENV" ] || "$PY" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install -U pip -q

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "==> NVIDIA GPU: installing CUDA build of PyTorch"
  pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cu128
  pip install -q qwen-tts
  pip install -q -U flash-attn --no-build-isolation || echo "  [skip] flash-attn failed to build; runs without it (more VRAM)"
elif [ "$(uname -s)" = "Linux" ]; then
  echo "==> Linux without NVIDIA GPU: installing CPU build of PyTorch (avoids multi-GB CUDA wheels)"
  pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu
  pip install -q qwen-tts
else
  echo "==> No NVIDIA GPU: installing default PyTorch (Apple MPS / CPU)"
  pip install -q torch torchaudio
  pip install -q qwen-tts
fi
# transformers 4.x (pulled in by qwen-tts) refuses huggingface_hub >= 1.0 at import time
pip install -q "huggingface_hub[cli]>=0.34,<1.0"

CV_MODEL="Qwen/Qwen3-TTS-12Hz-${SIZE}-CustomVoice"
for M in "$CV_MODEL" "$MODEL"; do
  echo "==> Downloading $M"
  hf download "$M" --local-dir "$HOME_DIR/models/$(basename "$M")"
done

cat <<EOF

Done.
  activate : source $VENV/bin/activate
  models   : export QWEN_TTS_CUSTOMVOICE_MODEL=$HOME_DIR/models/$(basename "$CV_MODEL")
             export QWEN_TTS_MODEL=$HOME_DIR/models/$(basename "$MODEL")
  next     : python .claude/skills/edu-video/scripts/voice_clone.py prep my-recording.m4a
EOF
