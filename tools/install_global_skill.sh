#!/bin/sh
# Install the motion-video skill globally (~/.claude/skills/motion-video) so every Claude Code project can use it.
#   sh tools/install_global_skill.sh            # copy (re-run after pulling to update)
#   sh tools/install_global_skill.sh --link     # symlink SKILL.md/references to this repo (edits show up at once)
#   sh tools/install_global_skill.sh --package  # also write dist/motion-video.skill (zip) to upload in claude.ai
# The measuring tools are copied from tools/ into the skill's scripts/ — tools/ stays the single source.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC="$ROOT/skills/motion-video"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/motion-video"
TOOLS="qa_render.py ref_measure.py beats.py stt_check.py"

mkdir -p "$SRC/scripts"
for t in $TOOLS; do cp "$ROOT/tools/$t" "$SRC/scripts/$t"; done

rm -rf "$DEST"
mkdir -p "$DEST"
if [ "$1" = "--link" ]; then
  ln -s "$SRC/SKILL.md" "$DEST/SKILL.md"
  ln -s "$SRC/references" "$DEST/references"
  ln -s "$SRC/scripts" "$DEST/scripts"
else
  cp -R "$SRC/SKILL.md" "$SRC/references" "$SRC/scripts" "$DEST/"
fi
echo "installed: $DEST"

if [ "$1" = "--package" ]; then
  mkdir -p "$ROOT/dist"
  (cd "$(dirname "$SRC")" && rm -f "$ROOT/dist/motion-video.skill" && \
   zip -qr "$ROOT/dist/motion-video.skill" motion-video -x 'motion-video/scripts/__pycache__/*' 'motion-video/evals/*')
  echo "package:   $ROOT/dist/motion-video.skill"
fi
