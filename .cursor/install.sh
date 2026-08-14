#!/usr/bin/env bash
# Idempotent Cloud Agent setup for job-engine.
#
# Prepares both halves of the repo:
#   - Python "job-engine" pipeline (managed by uv)
#   - Node/Hono read API (api/) backed by a local Typesense server
#
# Safe to run repeatedly: every step is guarded or naturally idempotent.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# uv installs here; make sure it (and the typesense-server binary) are on PATH.
export PATH="$HOME/.local/bin:$PATH"

# 1. uv — Python package/venv manager -------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "[install] installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 2. Python dependencies (creates .venv, installs project + dev extras) ----
echo "[install] uv sync --extra dev"
uv sync --extra dev

# 3. Typesense server binary ----------------------------------------------
# Cloud Agent VMs have no Docker, so we run the native server instead of the
# docker-compose service described in the README. Same 27.1 image/version.
TYPESENSE_VERSION="27.1"
TS_BIN="$HOME/.local/bin/typesense-server"
if [ ! -x "$TS_BIN" ]; then
  echo "[install] installing typesense-server $TYPESENSE_VERSION"
  mkdir -p "$HOME/.local/bin"
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/typesense.tar.gz" \
    "https://dl.typesense.org/releases/${TYPESENSE_VERSION}/typesense-server-${TYPESENSE_VERSION}-linux-amd64.tar.gz"
  tar -xzf "$tmp/typesense.tar.gz" -C "$HOME/.local/bin"
  chmod +x "$TS_BIN"
  rm -rf "$tmp"
fi

# 4. API (Node) dependencies ----------------------------------------------
echo "[install] npm install (api)"
(cd api && npm install)

# 5. Local .env -----------------------------------------------------------
# The API and CLI read config via `node --env-file`/env vars. Real secrets
# injected as Cloud Agent env vars take precedence over these placeholders
# (`node --env-file` never overrides an already-set environment variable),
# so this only supplies local Typesense defaults when no secret is provided.
if [ ! -f .env ]; then
  echo "[install] creating .env from .env.example"
  cp .env.example .env
fi

echo "[install] done"
