from datetime import timezone

from .models import PredictionHistory, User, db


def _format_datetime(value) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def get_user_profile(user_id) -> dict:
    user = db.session.get(User, user_id)
    if user is None:
        return {}

    return {
        "name": user.name,
        "email": user.email,
        "account_created_at": _format_datetime(user.created_at),
    }


def get_last_prediction(user_id) -> dict:
    prediction = (
        PredictionHistory.query.filter_by(user_id=user_id)
        .order_by(PredictionHistory.created_at.desc())
        .first()
    )
    if prediction is None:
        return {}

    return {
        "score": prediction.score,
        "inputs": prediction.inputs,
        "timestamp": _format_datetime(prediction.created_at),
    }


def get_prediction_history(user_id) -> dict:
    predictions = (
        PredictionHistory.query.filter_by(user_id=user_id)
        .order_by(PredictionHistory.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "predictions": [
            {
                "score": prediction.score,
                "timestamp": _format_datetime(prediction.created_at),
            }
            for prediction in predictions
        ]
    }


def get_monitor_snapshot(user_id) -> dict:
    return {}


def build_context(user_id) -> str:
    context = {
        "user_profile": get_user_profile(user_id),
        "last_prediction": get_last_prediction(user_id),
        "prediction_history": get_prediction_history(user_id),
        "monitor_snapshot": get_monitor_snapshot(user_id),
    }

    return "\n".join(
        [
            "Injected Sleep Command user context:",
            f"Profile: {context['user_profile']}",
            f"Last prediction: {context['last_prediction']}",
            f"Recent prediction history: {context['prediction_history']}",
            f"Monitor snapshot: {context['monitor_snapshot']}",
        ]
    )
