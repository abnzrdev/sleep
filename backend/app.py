import logging
import os
import time
from datetime import datetime, timezone

from flask import Flask, Response, g, jsonify, redirect, render_template, request, session, stream_with_context, url_for
from flask_login import current_user, login_required
from flask_socketio import SocketIO
from flask_wtf import CSRFProtect

from .ai import CHARACTER_DELAY_SECONDS, generate_daily_tip_text, generate_session_name, stream_chat_response
from .auth import auth_bp
from .config import ROOT_DIR, external_sensor_only_enabled, resolve_runtime_config
from .i18n import SUPPORTED_LANGUAGES, get_current_language, load_translations, set_current_language, t
from .models import ChatMessage, ChatSession, PredictionHistory, db, login_manager
from .predictor import FEATURE_ORDER, default_form_values, parse_payload, predict_sleep_efficiency
from .sensor import SensorState

PREDICT_STEP_CONFIG = [
    {
        "index": 1,
        "title_key": "predictor.steps.profile.title",
        "fields": [
            ("Age", "predictor.fields.Age.label", "predictor.fields.Age.help", "number", "1"),
            ("Gender", "predictor.fields.Gender.label", "predictor.fields.Gender.help", "number", "1"),
            ("Sleep duration", "predictor.fields.Sleep duration.label", "predictor.fields.Sleep duration.help", "number", "0.1"),
        ],
    },
    {
        "index": 2,
        "title_key": "predictor.steps.stages.title",
        "fields": [
            ("REM sleep percentage", "predictor.fields.REM sleep percentage.label", "predictor.fields.REM sleep percentage.help", "number", "1"),
            ("Deep sleep percentage", "predictor.fields.Deep sleep percentage.label", "predictor.fields.Deep sleep percentage.help", "number", "1"),
            ("Light sleep percentage", "predictor.fields.Light sleep percentage.label", "predictor.fields.Light sleep percentage.help", "number", "1"),
        ],
    },
    {
        "index": 3,
        "title_key": "predictor.steps.interruptions.title",
        "fields": [
            ("Awakenings", "predictor.fields.Awakenings.label", "predictor.fields.Awakenings.help", "number", "1"),
            ("Caffeine consumption", "predictor.fields.Caffeine consumption.label", "predictor.fields.Caffeine consumption.help", "number", "1"),
        ],
    },
    {
        "index": 4,
        "title_key": "predictor.steps.lifestyle.title",
        "fields": [
            ("Alcohol consumption", "predictor.fields.Alcohol consumption.label", "predictor.fields.Alcohol consumption.help", "number", "1"),
            ("Smoking status", "predictor.fields.Smoking status.label", "predictor.fields.Smoking status.help", "number", "1"),
            ("Exercise frequency", "predictor.fields.Exercise frequency.label", "predictor.fields.Exercise frequency.help", "number", "1"),
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


@app.before_request
def set_request_language() -> None:
    g.lang = get_current_language()


@app.context_processor
def inject_i18n_context() -> dict:
    return {
        "t": t,
        "current_lang": get_current_language(),
        "languages": SUPPORTED_LANGUAGES,
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def relative_time(value: datetime | None) -> str:
    if value is None:
        return t("common.just_now")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    seconds = max(0, int((utc_now() - value.astimezone(timezone.utc)).total_seconds()))
    if seconds < 60:
        return t("common.just_now")
    minutes = seconds // 60
    if minutes < 60:
        return t("common.minutes_ago").format(count=minutes)
    hours = minutes // 60
    if hours < 24:
        return t("common.hours_ago").format(count=hours)
    days = hours // 24
    return t("common.days_ago").format(count=days)


def get_predict_steps() -> list[dict]:
    steps = []
    for step in PREDICT_STEP_CONFIG:
        steps.append(
            {
                "index": step["index"],
                "title": t(step["title_key"]),
                "fields": [
                    {
                        "name": field[0],
                        "label": t(field[1]),
                        "help": t(field[2]),
                        "type": field[3],
                        "step": field[4],
                    }
                    for field in step["fields"]
                ],
            }
        )
    return steps


def default_chat_session_name() -> str:
    return t("chat.new_session")


def is_default_chat_session_name(name: str) -> bool:
    default_names = {"New coach session", "New chat"}
    for lang in SUPPORTED_LANGUAGES:
        translations = load_translations(lang)
        chat_labels = translations.get("chat") if isinstance(translations, dict) else None
        if isinstance(chat_labels, dict):
            localized_name = chat_labels.get("new_session")
            if isinstance(localized_name, str):
                default_names.add(localized_name)
    return name in default_names


def predictor_session_key() -> str:
    return f"predictor_state:{current_user.id}"


def get_predictor_state() -> dict:
    default_state = {"step": 1, "values": default_form_values()}
    stored = session.get(predictor_session_key())
    if not isinstance(stored, dict):
        return default_state

    values = default_form_values()
    values.update(stored.get("values") or {})
    try:
        step = int(stored.get("step", 1))
    except (TypeError, ValueError):
        step = 1
    return {"step": max(1, min(len(PREDICT_STEP_CONFIG), step)), "values": values}


def save_predictor_state(step: int, incoming: dict) -> dict:
    state = get_predictor_state()
    values = dict(state["values"])
    for feature in FEATURE_ORDER:
        if feature in incoming:
            values[feature] = incoming.get(feature, "")

    session[predictor_session_key()] = {
        "step": max(1, min(len(PREDICT_STEP_CONFIG), step)),
        "values": values,
    }
    session.modified = True
    return values


def clear_predictor_state() -> None:
    session.pop(predictor_session_key(), None)
    session.modified = True


def chat_session_or_404(session_id: int) -> ChatSession | None:
    return ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()


def serialize_chat_session(chat_session: ChatSession) -> dict:
    return {
        "id": chat_session.id,
        "name": chat_session.name,
        "updated_at": iso_datetime(chat_session.updated_at),
        "relative_time": relative_time(chat_session.updated_at),
    }


def score_suggestions(score: float | None) -> list[str]:
    if score is None:
        return [
            t("chat.suggestions.no_score.1"),
            t("chat.suggestions.no_score.2"),
            t("chat.suggestions.no_score.3"),
        ]
    percent = score * 100
    if percent < 60:
        return [
            t("chat.suggestions.low.1"),
            t("chat.suggestions.low.2"),
            t("chat.suggestions.low.3"),
        ]
    if percent <= 80:
        return [
            t("chat.suggestions.medium.1"),
            t("chat.suggestions.medium.2"),
            t("chat.suggestions.medium.3"),
        ]
    return [
        t("chat.suggestions.high.1"),
        t("chat.suggestions.high.2"),
        t("chat.suggestions.high.3"),
    ]


def score_insight(score_percent: float) -> str:
    if score_percent <= 50:
        return t("dashboard.latest_insight.low")
    if score_percent <= 75:
        return t("dashboard.latest_insight.medium")
    if score_percent <= 89:
        return t("dashboard.latest_insight.good")
    return t("dashboard.latest_insight.excellent")


def greeting_period() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return t("common.period_morning")
    if hour < 18:
        return t("common.period_afternoon")
    return t("common.period_evening")


@app.get("/")
def home_page():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_page"))
    return render_template("landing.html", active_page="home")


@app.get("/landing")
def landing_page():
    return redirect(url_for("home_page"))


@app.get("/about")
def about_page():
    return render_template("about.html", active_page="about")


@app.get("/contact")
def contact_page():
    return render_template("contact.html", active_page="contact")


@app.get("/learn")
def learn_page():
    return render_template("learn.html", active_page="learn")


@app.get("/language/<lang>")
def switch_language(lang: str):
    set_current_language(lang)
    return redirect(request.referrer or url_for("home_page"))


@app.get("/dashboard")
@login_required
def dashboard_page():
    last_prediction = (
        PredictionHistory.query.filter_by(user_id=current_user.id)
        .order_by(PredictionHistory.created_at.desc())
        .first()
    )
    chart_predictions = (
        PredictionHistory.query.filter_by(user_id=current_user.id)
        .order_by(PredictionHistory.created_at.desc())
        .limit(7)
        .all()
    )
    tip_key = f"daily_tip:{current_user.id}"
    return render_template(
        "dashboard.html",
        active_page="dashboard",
        latest_prediction=last_prediction,
        latest_prediction_percent=round(last_prediction.score * 100, 2) if last_prediction else None,
        latest_prediction_insight=score_insight(last_prediction.score * 100) if last_prediction else None,
        chart_points=[
            {
                "date": prediction.created_at.strftime("%d.%m"),
                "score": round(prediction.score * 100, 2),
                "recorded_at": prediction.created_at.strftime("%b %d, %Y %H:%M"),
            }
            for prediction in reversed(chart_predictions)
        ],
        cached_daily_tip=(session.get(tip_key) or {}).get("tip") if (session.get(tip_key) or {}).get("date") == datetime.now().date().isoformat() else "",
        greeting_period=greeting_period(),
    )


@app.get("/predictor")
@login_required
def predictor_page():
    predictor_state = get_predictor_state()
    translated_steps = get_predict_steps()
    return render_template(
        "index.html",
        active_page="predictor",
        form=predictor_state["values"],
        steps=translated_steps,
        current_step=predictor_state["step"],
    )


@app.post("/predict/step")
@login_required
def predict_step():
    incoming = request.form.to_dict()
    translated_steps = get_predict_steps()
    try:
        current_step = int(incoming.get("step", "1"))
    except ValueError:
        current_step = 1
    direction = incoming.get("direction", "next")
    next_step = current_step - 1 if direction == "back" else current_step + 1
    next_step = max(1, min(len(PREDICT_STEP_CONFIG), next_step))
    form_values = save_predictor_state(next_step, incoming)
    return render_template(
        "partials/predict_form.html",
        form=form_values,
        steps=translated_steps,
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
    translated_steps = get_predict_steps()
    incoming = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    incoming = incoming or {}

    try:
        patient_data = parse_payload(incoming)
    except ValueError as exc:
        form_values = save_predictor_state(len(PREDICT_STEP_CONFIG), incoming)
        if request.is_json:
            return jsonify({"error": str(exc)}), 400
        if is_hx_request:
            return render_template("partials/predict_result.html", error=str(exc))
        return (
            render_template(
                "index.html",
                active_page="predictor",
                error=str(exc),
                form=form_values,
                steps=translated_steps,
                current_step=len(PREDICT_STEP_CONFIG),
            ),
            400,
        )

    bounded, raw = predict_sleep_efficiency(patient_data)
    prediction_percent = round(bounded * 100, 2)
    bounded_score = round(bounded, 4)

    try:
        db.session.add(
            PredictionHistory(
                user_id=current_user.id,
                score=bounded_score,
                inputs=dict(patient_data),
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        LOGGER.exception("Failed to save prediction history for user_id=%s", current_user.id)

    clear_predictor_state()

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
        steps=translated_steps,
        current_step=len(PREDICT_STEP_CONFIG),
    )


@app.get("/chat")
@login_required
def chat_page():
    chat_sessions = (
        ChatSession.query.filter_by(user_id=current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    if not chat_sessions:
        chat_session = ChatSession(user_id=current_user.id, name=default_chat_session_name())
        db.session.add(chat_session)
        db.session.commit()
        chat_sessions = [chat_session]

    try:
        requested_session_id = int(request.args.get("session_id", chat_sessions[0].id))
    except (TypeError, ValueError):
        requested_session_id = chat_sessions[0].id

    active_session = chat_session_or_404(requested_session_id) or chat_sessions[0]
    chat_messages = (
        ChatMessage.query.filter_by(session_id=active_session.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    last_prediction = (
        PredictionHistory.query.filter_by(user_id=current_user.id)
        .order_by(PredictionHistory.created_at.desc())
        .first()
    )
    chart_predictions = (
        PredictionHistory.query.filter_by(user_id=current_user.id)
        .order_by(PredictionHistory.created_at.desc())
        .limit(7)
        .all()
    )

    return render_template(
        "chat.html",
        active_page="chat",
        active_session=active_session,
        chat_sessions=[serialize_chat_session(chat_session) for chat_session in chat_sessions],
        chat_messages=chat_messages,
        suggested_questions=score_suggestions(last_prediction.score if last_prediction else None),
        last_prediction_score=last_prediction.score if last_prediction else None,
        chart_points=[
            {
                "date": prediction.created_at.strftime("%d.%m"),
                "score": round(prediction.score * 100, 2),
            }
            for prediction in reversed(chart_predictions)
        ],
    )


@app.get("/api/chat/sessions")
@login_required
def api_chat_sessions():
    chat_sessions = (
        ChatSession.query.filter_by(user_id=current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return jsonify([serialize_chat_session(chat_session) for chat_session in chat_sessions])


@app.post("/api/chat/sessions/new")
@login_required
def api_chat_session_new():
    chat_session = ChatSession(user_id=current_user.id, name=default_chat_session_name())
    db.session.add(chat_session)
    db.session.commit()
    return jsonify({"id": chat_session.id})


@app.post("/api/chat/sessions/<int:session_id>/rename")
@login_required
def api_chat_session_rename(session_id: int):
    chat_session = chat_session_or_404(session_id)
    if chat_session is None:
        return jsonify({"error": t("errors.chat_session_not_found")}), 404

    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()[:80]
    if not name:
        return jsonify({"error": t("errors.name_required")}), 400

    chat_session.name = name
    chat_session.updated_at = utc_now()
    db.session.commit()
    return jsonify(serialize_chat_session(chat_session))


@app.delete("/api/chat/sessions/<int:session_id>")
@login_required
def api_chat_session_delete(session_id: int):
    chat_session = chat_session_or_404(session_id)
    if chat_session is None:
        return jsonify({"error": t("errors.chat_session_not_found")}), 404

    db.session.delete(chat_session)
    db.session.commit()
    return jsonify({"deleted": True})


@app.post("/api/chat")
@login_required
def api_chat():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"error": t("errors.message_required")}), 400

    try:
        session_id = int(payload.get("session_id"))
    except (TypeError, ValueError):
        return jsonify({"error": t("errors.session_id_required")}), 400

    chat_session = chat_session_or_404(session_id)
    if chat_session is None:
        return jsonify({"error": t("errors.chat_session_not_found")}), 404

    user_id = current_user.id
    chat_session_id = chat_session.id
    existing_messages = (
        ChatMessage.query.filter_by(session_id=chat_session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    history = [{"role": chat_message.role, "content": chat_message.content} for chat_message in existing_messages]
    is_first_message = len(existing_messages) == 0

    db.session.add(ChatMessage(session_id=chat_session_id, role="user", content=message))
    chat_session.updated_at = utc_now()
    db.session.commit()

    def generate():
        assistant_parts = []
        for character in stream_chat_response(user_id, history, message):
            assistant_parts.append(character)
            yield character

        assistant_message = "".join(assistant_parts).strip()
        if assistant_message:
            db.session.add(ChatMessage(session_id=chat_session_id, role="assistant", content=assistant_message))
            stored_session = db.session.get(ChatSession, chat_session_id)
            if stored_session and stored_session.user_id == user_id:
                if is_first_message and is_default_chat_session_name(stored_session.name):
                    stored_session.name = generate_session_name(message)
                stored_session.updated_at = utc_now()
            db.session.commit()

    return Response(
        stream_with_context(generate()),
        mimetype="text/plain; charset=utf-8",
    )


@app.get("/api/tip")
@login_required
def api_tip():
    today = datetime.now().date().isoformat()
    tip_key = f"daily_tip:{current_user.id}"
    previous_key = f"daily_tip_previous:{current_user.id}"
    cached = session.get(tip_key) or {}
    if cached.get("date") == today and cached.get("tip"):
        return Response(cached["tip"], mimetype="text/plain; charset=utf-8")

    last_prediction = (
        PredictionHistory.query.filter_by(user_id=current_user.id)
        .order_by(PredictionHistory.created_at.desc())
        .first()
    )
    previous_tip = session.get(previous_key)

    tip = generate_daily_tip_text(
        current_user.id,
        current_user.name,
        last_prediction.score if last_prediction else None,
        greeting_period(),
        previous_tip,
    ).strip()
    if previous_tip and tip == previous_tip:
        tip = t("predictor.daily_tip_fallback")
    session[previous_key] = tip
    session[tip_key] = {"date": today, "tip": tip}
    session.modified = True

    def generate():
        for character in tip:
            time.sleep(CHARACTER_DELAY_SECONDS)
            yield character

    return Response(stream_with_context(generate()), mimetype="text/plain; charset=utf-8")


@app.post("/api/tip/dismiss")
@login_required
def api_tip_dismiss():
    session[f"daily_tip_dismissed:{current_user.id}"] = datetime.now().date().isoformat()
    session.modified = True
    return jsonify({"dismissed": True})


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
    LOGGER.info("LunaSleep AI starting")
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
