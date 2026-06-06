#!/bin/bash
# sync.sh — 同步源码到已安装的 Application Support 副本
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/Library/Application Support/火花2.0"

rsync -av --checksum \
  "$SRC/app.py" "$SRC/server.py" "$SRC/automation.py" "$SRC/sync.sh" \
  "$DEST/"

rsync -av --checksum --delete \
  "$SRC/static/" "$DEST/static/"

rsync -av --checksum \
  "$DEST/app.py" "$DEST/server.py" "$DEST/automation.py" \
  "$SRC/"

echo "✓ 同步完成：$SRC ↔ $DEST"
