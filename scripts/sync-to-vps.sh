#!/usr/bin/env bash
# Sync job-engine to VPS (excludes local corpus/out/.venv).
#
# Usage:
#   ./scripts/sync-to-vps.sh
#   ./scripts/sync-to-vps.sh ubuntu@140.245.231.123 ~/job-engine
#
# Env:
#   VPS_HOST   default ubuntu@140.245.231.123
#   VPS_KEY    default ~/Downloads/ssh-key-2026-06-09.key
#   REMOTE_DIR default ~/job-engine

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="${VPS_KEY:-$HOME/Downloads/ssh-key-2026-06-09.key}"
HOST="${1:-${VPS_HOST:-ubuntu@140.245.231.123}}"
REMOTE_DIR="${2:-${REMOTE_DIR:-~/job-engine}}"

if [[ ! -f "$KEY" ]]; then
  echo "SSH key not found: $KEY" >&2
  exit 2
fi
chmod 600 "$KEY"

echo "[sync] local:  $ROOT"
echo "[sync] remote: $HOST:$REMOTE_DIR"
echo "[sync] key:    $KEY"

ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$HOST" "mkdir -p $REMOTE_DIR"

rsync -avz --progress \
  -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude 'out/' \
  --exclude 'data/corpus/' \
  --exclude '.env' \
  --exclude '*.pyc' \
  "$ROOT/" "$HOST:$REMOTE_DIR/"

echo "[sync] done"
echo
echo "On VPS:"
echo "  ssh -i $KEY $HOST"
echo "  cd $REMOTE_DIR && uv sync"
echo "  nohup uv run job-engine run --concurrency 8 --skip-push > logs/run.log 2>&1 &"
