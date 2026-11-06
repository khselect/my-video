#!/usr/bin/env bash
# Local image generation for story styles (tools/sticker_local.py): mflux (MIT) + FLUX.1-schnell (Apache-2.0) + rembg (MIT).
# Apple Silicon only (MLX). Free, nothing leaves the machine. Model ~9.6 GB.
# Env: IMAGE_VENV=<dir> (default ~/.edu-video/image-venv), FLUX_REPO=<hf repo> (default: a pre-quantized 4-bit copy that
#      needs no Hugging Face login; the official black-forest-labs/FLUX.1-schnell needs `hf auth login` + accepting its terms).
set -euo pipefail
[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] || { echo "mflux needs Apple Silicon (MLX)"; exit 1; }
HOME_DIR="$HOME/.edu-video"
VENV="${IMAGE_VENV:-$HOME_DIR/image-venv}"
REPO="${FLUX_REPO:-dhairyashil/FLUX.1-schnell-mflux-4bit}"
PY="$(command -v python3.12 || command -v python3.11 || command -v python3)"
"$PY" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
[ -d "$VENV" ] || "$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install -q -U pip
"$VENV/bin/python" -m pip install -q mflux "rembg[cpu]"
echo "==> Downloading $REPO"
"$VENV/bin/hf" download "$REPO" --local-dir "$HOME_DIR/models/FLUX.1-schnell-mflux-4bit"
cat <<EOF

Done.
  python : $VENV/bin/python   (Studio: 이 PC 설정 → 이미지 생성 Python)
  test   : $VENV/bin/python tools/sticker_local.py --subject "a smiling girl holding a pencil" --out /tmp/test.png
EOF
