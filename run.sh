#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 027

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OPEN_BROWSER=1
for arg in "$@"; do
  case "$arg" in
    --no-open)
      OPEN_BROWSER=0
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: ./run.sh [--no-open]"
      exit 1
      ;;
  esac
done

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required but was not found on PATH."
  exit 1
}

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --disable-pip-version-check --no-input -r requirements.txt

START_PORT="${PORT:-5000}"
MAX_PORT="${MAX_PORT:-5100}"
HOST_VALUE="${HOST:-127.0.0.1}"

validate_port() {
  local value="$1"
  [[ "$value" =~ ^[0-9]+$ ]] && [ "$value" -ge 1 ] && [ "$value" -le 65535 ]
}

if ! validate_port "$START_PORT"; then
  echo "Invalid PORT value: $START_PORT"
  exit 1
fi

if ! validate_port "$MAX_PORT"; then
  echo "Invalid MAX_PORT value: $MAX_PORT"
  exit 1
fi

if [ "$START_PORT" -gt "$MAX_PORT" ]; then
  echo "PORT ($START_PORT) must be <= MAX_PORT ($MAX_PORT)."
  exit 1
fi

AVAILABLE_PORT="$(
  python - "$START_PORT" "$MAX_PORT" <<'PY'
import socket
import sys

start = int(sys.argv[1])
end = int(sys.argv[2])

for port in range(start, end + 1):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        raise SystemExit(0)

raise SystemExit(1)
PY
)"

if [ -z "${AVAILABLE_PORT:-}" ]; then
  echo "No free port found in range $START_PORT-$MAX_PORT."
  exit 1
fi

OPEN_HOST="$HOST_VALUE"
if [ "$OPEN_HOST" = "0.0.0.0" ]; then
  OPEN_HOST="127.0.0.1"
fi
APP_URL="http://$OPEN_HOST:$AVAILABLE_PORT"

echo "Starting Sleep Efficiency Predictor on $APP_URL"

if [ "$OPEN_BROWSER" -eq 1 ]; then
  (
    sleep 1
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$APP_URL" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
      open "$APP_URL" >/dev/null 2>&1 || true
    fi
  ) &
fi

export HOST="$HOST_VALUE"
export PORT="$AVAILABLE_PORT"
export DEBUG="${DEBUG:-0}"

exec python app.py
