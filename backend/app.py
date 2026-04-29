import logging
import os

from flask import Flask, jsonify, render_template, request
from flask_login import login_required
from flask_socketio import SocketIO
from flask_wtf import CSRFProtect

from .auth import auth_bp
from .config import ROOT_DIR, external_sensor_only_enabled, resolve_runtime_config
from .models import db, login_manager
from .predictor import default_form_values, parse_payload, predict_sleep_efficiency
from .sensor import SensorState

PREDICT_STEPS = [
    {
        "index": 1,
        "title": "Profile basics",
        "fields": [
            ("Age", "Your age in years. Sleep patterns often shift by age group.", "number", "1"),
            ("Gender", "Use the same 0 or 1 encoding used by the training data.", "number", "1"),
            ("Sleep duration", "How many hours you slept, including decimals such as 7.5.", "number", "0.1"),
        ],
    },
    {
        "index": 2,
        "title": "Sleep stages",
        "fields": [
            ("REM sleep percentage", "Percent of the night spent in REM sleep.", "number", "1"),
            ("Deep sleep percentage", "Percent of the night spent in deep sleep.", "number", "1"),
            ("Light sleep percentage", "Percent of the night spent in light sleep.", "number", "1"),
        ],
    },
    {
        "index": 3,
        "title": "Night interruptions",
        "fields": [
            ("Awakenings", "How many times you woke up during the night.", "number", "1"),
            ("Caffeine consumption", "Approximate caffeine intake before sleep, in milligrams.", "number", "1"),
        ],
    },
    {
        "index": 4,
        "title": "Lifestyle factors",
        "fields": [
            ("Alcohol consumption", "Number of alcoholic drinks before sleep.", "number", "1"),
            ("Smoking status", "Use 0 for no and 1 for yes.", "number", "1"),
            ("Exercise frequency", "How many exercise sessions you usually complete per week.", "number", "1"),
        ],
    },
]

app = Flask(
    __name__,
    template_folder=str(ROOT_DIR / "frontend" / "templates"),
    instance_path=str(ROOT_DIR / "instance"),
)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "dev-change-me"),
    SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", f"sqlite:///{ROOT_DIR / 'instance' / 'sleep.db'}"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
)

os.makedirs(app.instance_path, exist_ok=True)

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message_category = "auth-required"
csrf = CSRFProtect(app)
app.register_blueprint(auth_bp)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

LOGGER = logging.getLogger("sleep-dashboard")
sensor_state = SensorState(socketio)
sensor_state.init_sensor_source()


with app.app_context():
    db.create_all()


@app.get("/landing")
def landing_page():
    return render_template("landing.html", active_page="landing")


@app.get("/about")
def about_page():
    return render_template("coming_soon.html", page_title="About", active_page="about")


@app.get("/contact")
def contact_page():
    return render_template("coming_soon.html", page_title="Contact", active_page="contact")


@app.get("/")
@login_required
def predictor_page():
    return render_template(
        "index.html",
        active_page="predictor",
        form=default_form_values(),
        steps=PREDICT_STEPS,
        current_step=1,
    )


@app.post("/predict/step")
@login_required
def predict_step():
    incoming = request.form.to_dict()
    try:
        current_step = int(incoming.get("step", "1"))
    except ValueError:
        current_step = 1
    direction = incoming.get("direction", "next")
    next_step = current_step - 1 if direction == "back" else current_step + 1
    next_step = max(1, min(len(PREDICT_STEPS), next_step))
    return render_template(
        "partials/predict_form.html",
        form=incoming,
        steps=PREDICT_STEPS,
        current_step=next_step,
    )


@app.get("/monitor")
@login_required
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
@login_required
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
                steps=PREDICT_STEPS,
                current_step=len(PREDICT_STEPS),
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
        steps=PREDICT_STEPS,
        current_step=len(PREDICT_STEPS),
    )


@app.post("/sensor_data")
@csrf.exempt
def receive_sensor_data():
    payload, status_code = sensor_state.receive_sensor_data(request.get_json(silent=True) or {})
    return jsonify(payload), status_code


@app.post("/sensor_control/stop")
@login_required
def stop_sensor_feed():
    payload = sensor_state.stop_sensor_feed()
    return jsonify(payload)


@app.post("/sensor_control/start")
@login_required
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
