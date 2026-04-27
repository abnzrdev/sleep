#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x "./run.sh" ]; then
  chmod +x ./run.sh
fi

# Raspberry Pi friendly defaults.
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-5000}"
export MAX_PORT="${MAX_PORT:-5100}"

exec ./run.sh --no-open "$@"
