#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --disable-pip-version-check --no-input -r requirements.txt

exec python diploma_web.py --host "${HOST:-0.0.0.0}" --port "${PORT:-5000}" --max-port "${MAX_PORT:-5100}" "$@"
