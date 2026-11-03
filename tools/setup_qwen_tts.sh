#!/usr/bin/env bash
# Install local Qwen3-TTS (voice clone) into ~/.edu-video/qwen-venv and pre-download the model.
# usage: setup_qwen_tts.sh [1.7B|0.6B]
#   1.7B  best quality, ~6-8 GB VRAM (NVIDIA) or Apple Silicon with 16 GB+ RAM
#   0.6B  ~4-6 GB VRAM, also usable on CPU (slow)
set -euo pipefail
SIZE="${1:-1.7B}"
MODEL="Qwen/Qwen3-TTS-12Hz-${SIZE}-Base"
HOME_DIR="$HOME/.edu-video"
VENV="$HOME_DIR/qwen-venv"
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
else
  echo "==> No NVIDIA GPU: installing default PyTorch (Apple MPS / CPU)"
  pip install -q torch torchaudio
  pip install -q qwen-tts
fi
pip install -q -U "huggingface_hub[cli]"

echo "==> Downloading $MODEL"
hf download "$MODEL" --local-dir "$HOME_DIR/models/$(basename "$MODEL")"

cat <<EOF

Done.
  activate : source $VENV/bin/activate
  model    : export QWEN_TTS_MODEL=$HOME_DIR/models/$(basename "$MODEL")
  next     : python .claude/skills/edu-video/scripts/voice_clone.py prep my-recording.m4a
EOF
