import argparse
import logging
import os
import socket
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent

load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / ".env.local", override=True)

LOGGER = logging.getLogger("sleep-dashboard")


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {name}: {value}. Must be an integer.") from exc


def external_sensor_only_enabled() -> bool:
    # Default to external sensor feed to avoid local simulation conflicting with Pi data.
    return parse_bool(os.getenv("EXTERNAL_SENSOR_ONLY", "1"), True)


def remote_sender_autocontrol_enabled() -> bool:
    # Enabled by default for EXTERNAL_SENSOR_ONLY mode so the dashboard controls Pi sender lifecycle.
    return parse_bool(os.getenv("RPI_AUTOCONTROL", "1"), True)


def valid_port(value: int) -> bool:
    return 1 <= value <= 65535


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(host: str, start_port: int, max_port: int) -> int | None:
    for candidate in range(start_port, max_port + 1):
        if is_port_available(host, candidate):
            return candidate
    return None


def resolve_runtime_config() -> tuple[str, int, bool]:
    parser = argparse.ArgumentParser(
        description="Sleep Dashboard (ML Predictor + Live IMU Monitor)",
    )
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=env_int("PORT", 5000))
    parser.add_argument("--max-port", type=int, default=env_int("MAX_PORT", 5100))
    parser.add_argument("--debug", action="store_true", default=parse_bool(os.getenv("DEBUG"), False))
    parser.add_argument(
        "--no-port-fallback",
        action="store_true",
        help="Disable automatic port fallback when --port is busy.",
    )

    args = parser.parse_args()

    host = args.host
    port = args.port
    max_port = args.max_port
    debug = args.debug
    auto_fallback = not args.no_port_fallback

    if not valid_port(port):
        raise SystemExit(f"Invalid PORT: {port}. Allowed range is 1-65535.")
    if not valid_port(max_port):
        raise SystemExit(f"Invalid MAX_PORT: {max_port}. Allowed range is 1-65535.")
    if max_port < port:
        raise SystemExit(f"MAX_PORT ({max_port}) must be >= PORT ({port}).")

    if not is_port_available(host, port):
        if not auto_fallback:
            raise SystemExit(
                f"Port {port} is busy on host {host}. "
                "Use another port or remove --no-port-fallback."
            )

        selected = find_available_port(host, port + 1, max_port)
        if selected is None:
            raise SystemExit(
                f"No free port found in range {port}-{max_port} on host {host}."
            )
        LOGGER.warning(
            "Port %s is busy. Falling back to free port %s.",
            port,
            selected,
        )
        port = selected

    return host, port, debug
