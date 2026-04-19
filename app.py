import math
import os
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
    global bus, sensor_source, sensor_error

    if smbus is None:
        sensor_source = "Simulation (smbus unavailable)"
        sensor_error = "smbus module not installed."
        return

    try:
        bus = smbus.SMBus(1)
        mpu_init()
        sensor_source = "MPU6050 (I2C)"
        sensor_error = ""
    except Exception as exc:
        bus = None
        sensor_source = "Simulation (MPU6050 offline)"
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


init_sensor_source()

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    try:
        port = int(os.getenv("PORT", "5000"))
    except ValueError:
        port = 5000

    debug = os.getenv("DEBUG", "0").lower() in {"1", "true", "yes", "on"}
    socketio.run(
        app,
        host=host,
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True,
    )
