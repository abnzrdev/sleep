import argparse
import logging
import math
import os
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO

try:
    import smbus  # type: ignore
except ImportError:
    try:
        import smbus2 as smbus  # type: ignore
    except ImportError:
        smbus = None

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

LOGGER = logging.getLogger("sleep-dashboard")

MODEL_PATH = Path(__file__).resolve().parent / "xgboost_sleep_model.pkl"
model = joblib.load(MODEL_PATH)

FEATURE_ORDER = [
    "Age",
    "Gender",
    "Sleep duration",
    "REM sleep percentage",
    "Deep sleep percentage",
    "Light sleep percentage",
    "Awakenings",
    "Caffeine consumption",
    "Alcohol consumption",
    "Smoking status",
    "Exercise frequency",
]

INTEGER_FIELDS = {
    "Age",
    "Gender",
    "REM sleep percentage",
    "Deep sleep percentage",
    "Light sleep percentage",
    "Awakenings",
    "Caffeine consumption",
    "Alcohol consumption",
    "Smoking status",
    "Exercise frequency",
}

BINARY_FIELDS = {"Gender", "Smoking status"}

# --- MPU6050 SETUP ---
DEVICE_ADDRESS = 0x68
PWR_MGMT_1 = 0x6B
SMPLRT_DIV = 0x19
CONFIG = 0x1A
GYRO_CONFIG = 0x1B
INT_ENABLE = 0x38
ACCEL_XOUT_H = 0x3B

bus = None
sensor_source = "Simulation"
sensor_error = ""

_sensor_task_started = False
_sensor_lock = threading.Lock()
_external_feed_paused = False
_external_last_data: dict = {}
_external_control_lock = threading.Lock()
_external_metrics = {
    "started_at": None,
    "last_ts": None,
    "total_sleep_seconds": 0.0,
    "latest_efficiency": 0.0,
}


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def external_sensor_only_enabled() -> bool:
    # Default to external sensor feed to avoid local simulation conflicting with Pi data.
    return parse_bool(os.getenv("EXTERNAL_SENSOR_ONLY", "1"), True)


def _event_time_from_payload(data: dict) -> float:
    raw = data.get("timestamp")
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return time.time()
    return time.time()


def _enrich_external_sensor_data(data: dict) -> dict:
    now_ts = _event_time_from_payload(data)

    started_at = _external_metrics.get("started_at")
    last_ts = _external_metrics.get("last_ts")

    if started_at is None:
        _external_metrics["started_at"] = now_ts
        started_at = now_ts

    if last_ts is None:
        dt = 1.0
    else:
        dt = now_ts - float(last_ts)
        if dt <= 0 or dt > 5:
            dt = 1.0

    status_text = str(data.get("status", "")).lower()
    if status_text.startswith("sleeping"):
        _external_metrics["total_sleep_seconds"] = float(_external_metrics["total_sleep_seconds"]) + dt

    elapsed = max(now_ts - float(started_at), 1.0)
    efficiency = (float(_external_metrics["total_sleep_seconds"]) / elapsed) * 100.0

    _external_metrics["last_ts"] = now_ts
    _external_metrics["latest_efficiency"] = efficiency

    # Ensure UI always receives an efficiency value, even if sender omits it.
    data["efficiency"] = round(efficiency, 1)
    return data


def _reset_external_metrics() -> None:
    _external_metrics["started_at"] = None
    _external_metrics["last_ts"] = None
    _external_metrics["total_sleep_seconds"] = 0.0
    _external_metrics["latest_efficiency"] = 0.0


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


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {name}: {value}. Must be an integer.") from exc


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


def default_form_values() -> dict:
    return {
        "Age": 34,
        "Gender": 0,
        "Sleep duration": 7.5,
        "REM sleep percentage": 18,
        "Deep sleep percentage": 55,
        "Light sleep percentage": 27,
        "Awakenings": 1,
        "Caffeine consumption": 50,
        "Alcohol consumption": 0,
        "Smoking status": 0,
        "Exercise frequency": 3,
    }


def parse_payload(raw_data: dict) -> dict:
    cleaned = {}
    errors = []

    for feature in FEATURE_ORDER:
        value = raw_data.get(feature)
        if value in (None, ""):
            errors.append(f"{feature} is required.")
            continue

        try:
            if feature in INTEGER_FIELDS:
                cleaned[feature] = int(value)
            else:
                cleaned[feature] = float(value)
        except (TypeError, ValueError):
            expected = "integer" if feature in INTEGER_FIELDS else "number"
            errors.append(f"{feature} must be a valid {expected}.")

    for feature in BINARY_FIELDS:
        if feature in cleaned and cleaned[feature] not in (0, 1):
            errors.append(f"{feature} must be 0 or 1.")

    if errors:
        raise ValueError(" ".join(errors))

    return cleaned


def predict_sleep_efficiency(patient_data: dict) -> tuple[float, float]:
    df = pd.DataFrame([patient_data])[FEATURE_ORDER]
    raw = float(model.predict(df)[0])
    bounded = float(max(0.0, min(1.0, raw)))
    return bounded, raw


def mpu_init() -> None:
    if bus is None:
        raise RuntimeError("I2C bus not initialized.")

    bus.write_byte_data(DEVICE_ADDRESS, SMPLRT_DIV, 7)
    bus.write_byte_data(DEVICE_ADDRESS, PWR_MGMT_1, 1)
    bus.write_byte_data(DEVICE_ADDRESS, CONFIG, 0)
    bus.write_byte_data(DEVICE_ADDRESS, GYRO_CONFIG, 24)
    bus.write_byte_data(DEVICE_ADDRESS, INT_ENABLE, 1)


def read_raw_data(addr: int) -> int:
    if bus is None:
        raise RuntimeError("I2C bus not initialized.")

    high = bus.read_byte_data(DEVICE_ADDRESS, addr)
    low = bus.read_byte_data(DEVICE_ADDRESS, addr + 1)
    value = (high << 8) | low
    if value > 32768:
        value -= 65536
    return value


def init_sensor_source() -> None:
    global bus, sensor_source, sensor_error, DEVICE_ADDRESS

    if external_sensor_only_enabled():
        bus = None
        sensor_source = "External sensor feed (waiting for data)"
        sensor_error = ""
        return

    if smbus is None:
        sensor_source = "Simulation (smbus unavailable)"
        sensor_error = "smbus module not installed."
        return

    try:
        bus_number = int(os.getenv("I2C_BUS", "1"))
    except ValueError:
        sensor_source = "Simulation (invalid I2C config)"
        sensor_error = "I2C_BUS must be an integer. Example: I2C_BUS=1"
        return

    raw_addr = os.getenv("MPU6050_ADDR", "0x68")
    try:
        device_address = int(raw_addr, 0)
    except ValueError:
        sensor_source = "Simulation (invalid I2C config)"
        sensor_error = "MPU6050_ADDR must be numeric (for example 0x68)."
        return

    if not (0 <= device_address <= 0x7F):
        sensor_source = "Simulation (invalid I2C config)"
        sensor_error = "MPU6050_ADDR must be in 0x00..0x7F range."
        return

    try:
        DEVICE_ADDRESS = device_address
        bus = smbus.SMBus(bus_number)
        mpu_init()
        sensor_source = f"MPU6050 (I2C bus {bus_number}, addr 0x{DEVICE_ADDRESS:02X})"
        sensor_error = ""
    except Exception as exc:
        bus = None
        sensor_source = f"Simulation (MPU6050 offline on bus {bus_number})"
        sensor_error = str(exc)


def read_accelerometer() -> tuple[float, float, float]:
    if bus is not None:
        acc_x = read_raw_data(ACCEL_XOUT_H) / 16384.0
        acc_y = read_raw_data(ACCEL_XOUT_H + 2) / 16384.0
        acc_z = read_raw_data(ACCEL_XOUT_H + 4) / 16384.0
        return acc_x, acc_y, acc_z

    # Fallback simulation keeps the UI alive even without hardware.
    t = time.time()
    acc_x = 0.05 * math.sin(t / 2.0)
    acc_y = 0.04 * math.cos(t / 2.6)
    acc_z = 1.00 + 0.02 * math.sin(t / 3.3)
    return acc_x, acc_y, acc_z


def sensor_loop() -> None:
    test_mode = os.getenv("TEST_MODE", "1").lower() in {"1", "true", "yes", "on"}
    movement_threshold = float(os.getenv("MOVEMENT_THRESHOLD", "0.05"))

    if test_mode:
        time_to_fall_asleep = 10
        time_to_wake_up = 3
    else:
        time_to_fall_asleep = 10 * 60
        time_to_wake_up = 30

    start_bed_time = time.time()
    is_sleeping = False
    total_sleep_seconds = 0
    awakenings_count = 0
    quiet_seconds = 0
    active_seconds = 0
    prev_acc_mag = 0.0
    first_sleep_time = "--:--:--"

    while True:
        try:
            acc_x, acc_y, acc_z = read_accelerometer()

            try:
                roll = math.atan2(acc_y, acc_z)
                pitch = math.atan2(-acc_x, math.sqrt(acc_y * acc_y + acc_z * acc_z))
            except Exception:
                roll, pitch = 0.0, 0.0

            acc_mag = math.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
            movement = abs(acc_mag - prev_acc_mag)
            prev_acc_mag = acc_mag

            if movement > movement_threshold:
                active_seconds += 1
                quiet_seconds = 0
            else:
                quiet_seconds += 1
                active_seconds = 0

            if not is_sleeping:
                if quiet_seconds >= time_to_fall_asleep:
                    is_sleeping = True
                    if first_sleep_time == "--:--:--":
                        first_sleep_time = datetime.now().strftime("%H:%M:%S")
                    active_seconds = 0
            else:
                total_sleep_seconds += 1
                if active_seconds >= time_to_wake_up:
                    is_sleeping = False
                    awakenings_count += 1
                    quiet_seconds = 0

            total_time_in_bed = time.time() - start_bed_time
            efficiency = (total_sleep_seconds / total_time_in_bed) * 100 if total_time_in_bed > 0 else 0

            sensor_data = {
                "status": "Sleeping zZz" if is_sleeping else "Awake",
                "movement": round(movement, 3),
                "first_sleep": first_sleep_time,
                "awakenings": awakenings_count,
                "efficiency": round(efficiency, 1),
                "pitch": pitch,
                "roll": roll,
                "x": f"{acc_x:.2f}",
                "y": f"{acc_y:.2f}",
                "z": f"{acc_z:.2f}",
                "sensor_source": sensor_source,
            }
            socketio.emit("sensor_update", sensor_data)
            socketio.sleep(1)
        except OSError:
            # Hardware read error; keep server alive and retry.
            socketio.sleep(1)


def ensure_sensor_task_started() -> None:
    global _sensor_task_started
    with _sensor_lock:
        if _sensor_task_started:
            return
        socketio.start_background_task(sensor_loop)
        _sensor_task_started = True


@app.get("/")
def predictor_page():
    return render_template(
        "index.html",
        form=default_form_values(),
    )


@app.get("/monitor")
def monitor_page():
    if not external_sensor_only_enabled():
        ensure_sensor_task_started()
    return render_template(
        "monitor.html",
        sensor_source=sensor_source,
        sensor_error=sensor_error,
    )


@app.post("/predict")
def predict():
    incoming = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    incoming = incoming or {}

    try:
        patient_data = parse_payload(incoming)
    except ValueError as exc:
        if request.is_json:
            return jsonify({"error": str(exc)}), 400
        return (
            render_template(
                "index.html",
                error=str(exc),
                form=incoming,
            ),
            400,
        )

    bounded, raw = predict_sleep_efficiency(patient_data)
    prediction_percent = round(bounded * 100, 2)

    if request.is_json:
        return jsonify(
            {
                "prediction_percent": prediction_percent,
                "bounded_score": round(bounded, 4),
                "raw_score": raw,
            }
        )

    return render_template(
        "index.html",
        prediction_percent=prediction_percent,
        raw_score=raw,
        bounded_score=round(bounded, 4),
        form=incoming,
    )


@app.post("/sensor_data")
def receive_sensor_data():
    global _external_last_data

    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify(success=False, error="JSON body is required."), 400

    with _external_control_lock:
        paused = _external_feed_paused
        if not paused:
            enriched = _enrich_external_sensor_data(dict(data))
            _external_last_data = dict(enriched)
        else:
            enriched = dict(data)

    if paused:
        return jsonify(success=True, paused=True, message="Feed is paused."), 202

    socketio.emit("sensor_update", enriched)
    return jsonify(success=True, paused=False)


@app.post("/sensor_control/stop")
def stop_sensor_feed():
    global _external_feed_paused

    with _external_control_lock:
        _external_feed_paused = True
        snapshot = dict(_external_last_data)

    if snapshot:
        snapshot["status"] = "Stopped"
        snapshot["sensor_source"] = snapshot.get("sensor_source", "External sensor feed (stopped)")
    else:
        snapshot = {
            "status": "Stopped",
            "movement": 0.0,
            "first_sleep": "--:--:--",
            "awakenings": 0,
            "efficiency": 0,
            "pitch": 0.0,
            "roll": 0.0,
            "x": "0.00",
            "y": "0.00",
            "z": "0.00",
            "sensor_source": "External sensor feed (stopped)",
        }

    socketio.emit("sensor_update", snapshot)
    return jsonify(success=True, paused=True, snapshot=snapshot)


@app.post("/sensor_control/start")
def start_sensor_feed():
    global _external_feed_paused, _external_last_data

    with _external_control_lock:
        _external_feed_paused = False
        _external_last_data = {}
        _reset_external_metrics()

    return jsonify(success=True, paused=False)


init_sensor_source()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )

    host, port, debug = resolve_runtime_config()

    open_host = "127.0.0.1" if host == "0.0.0.0" else host
    LOGGER.info("Sleep Dashboard starting")
    LOGGER.info("Host: %s", host)
    LOGGER.info("Port: %s", port)
    LOGGER.info("Debug: %s", debug)
    LOGGER.info("Sensor mode: %s", sensor_source)
    if sensor_error:
        LOGGER.warning("Sensor warning: %s", sensor_error)
    LOGGER.info("Open in browser: http://%s:%s/", open_host, port)
    LOGGER.info("Live monitor: http://%s:%s/monitor", open_host, port)

    socketio.run(
        app,
        host=host,
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True,
    )
