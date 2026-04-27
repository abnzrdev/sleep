import logging

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO

from .config import ROOT_DIR, external_sensor_only_enabled, resolve_runtime_config
from .predictor import default_form_values, parse_payload, predict_sleep_efficiency
from .sensor import SensorState

app = Flask(__name__, template_folder=str(ROOT_DIR / "frontend" / "templates"))
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

LOGGER = logging.getLogger("sleep-dashboard")
sensor_state = SensorState(socketio)
sensor_state.init_sensor_source()


@app.get("/")
def predictor_page():
    return render_template(
        "index.html",
        active_page="predictor",
        form=default_form_values(),
    )


@app.get("/monitor")
def monitor_page():
    if not external_sensor_only_enabled():
        sensor_state.ensure_sensor_task_started()
    return render_template(
        "monitor.html",
        active_page="monitor",
        sensor_source=sensor_state.sensor_source,
        sensor_error=sensor_state.sensor_error,
    )


@app.post("/predict")
def predict():
    is_hx_request = request.headers.get("HX-Request") == "true"
    incoming = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    incoming = incoming or {}

    try:
        patient_data = parse_payload(incoming)
    except ValueError as exc:
        if request.is_json:
            return jsonify({"error": str(exc)}), 400
        if is_hx_request:
            return render_template("partials/predict_result.html", error=str(exc))
        return (
            render_template(
                "index.html",
                active_page="predictor",
                error=str(exc),
                form=incoming,
            ),
            400,
        )

    bounded, raw = predict_sleep_efficiency(patient_data)
    prediction_percent = round(bounded * 100, 2)
    bounded_score = round(bounded, 4)

    if request.is_json:
        return jsonify(
            {
                "prediction_percent": prediction_percent,
                "bounded_score": bounded_score,
                "raw_score": raw,
            }
        )

    if is_hx_request:
        return render_template(
            "partials/predict_result.html",
            prediction_percent=prediction_percent,
            raw_score=raw,
            bounded_score=bounded_score,
        )

    return render_template(
        "index.html",
        active_page="predictor",
        prediction_percent=prediction_percent,
        raw_score=raw,
        bounded_score=bounded_score,
        form=incoming,
    )


@app.post("/sensor_data")
def receive_sensor_data():
    payload, status_code = sensor_state.receive_sensor_data(request.get_json(silent=True) or {})
    return jsonify(payload), status_code


@app.post("/sensor_control/stop")
def stop_sensor_feed():
    payload = sensor_state.stop_sensor_feed()
    return jsonify(payload)


@app.post("/sensor_control/start")
def start_sensor_feed():
    payload, status_code = sensor_state.start_sensor_feed(request)
    return jsonify(payload), status_code


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )

    host, port, debug = resolve_runtime_config()
    sensor_state.set_runtime_address(host, port)

    open_host = "127.0.0.1" if host == "0.0.0.0" else host
    LOGGER.info("Sleep Dashboard starting")
    LOGGER.info("Host: %s", host)
    LOGGER.info("Port: %s", port)
    LOGGER.info("Debug: %s", debug)
    LOGGER.info("Sensor mode: %s", sensor_state.sensor_source)
    if sensor_state.sensor_error:
        LOGGER.warning("Sensor warning: %s", sensor_state.sensor_error)
    LOGGER.info("Open in browser: http://%s:%s/", open_host, port)
    LOGGER.info("Live monitor: http://%s:%s/monitor", open_host, port)

    socketio.run(
        app,
        host=host,
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    main()
