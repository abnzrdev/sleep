from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from werkzeug.security import generate_password_hash

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app import app  # noqa: E402
from backend.models import ChatMessage, ChatSession, PredictionHistory, User, db  # noqa: E402


def prediction_inputs(index: int) -> dict:
    return {
        "Age": 31 + (index % 5),
        "Gender": index % 2,
        "Sleep duration": round(5.8 + (index % 7) * 0.35, 1),
        "REM sleep percentage": 16 + (index % 8),
        "Deep sleep percentage": 38 + (index % 16),
        "Light sleep percentage": 26 + (index % 18),
        "Awakenings": index % 5,
        "Caffeine consumption": [0, 30, 50, 80, 120][index % 5],
        "Alcohol consumption": [0, 0, 1, 1, 2][index % 5],
        "Smoking status": 1 if index in {3, 11, 17} else 0,
        "Exercise frequency": [1, 2, 3, 4, 5][index % 5],
    }


def create_predictions(user: User) -> int:
    existing_count = PredictionHistory.query.filter_by(user_id=user.id).count()
    if existing_count >= 20:
        return 0

    scores = [
        0.48,
        0.54,
        0.69,
        0.73,
        0.86,
        0.91,
        0.52,
        0.67,
        0.75,
        0.83,
        0.88,
        0.46,
        0.71,
        0.65,
        0.92,
        0.55,
        0.74,
        0.84,
        0.68,
        0.89,
    ]
    now = datetime.now(timezone.utc)
    for index, score in enumerate(scores):
        created_at = now - timedelta(days=14 - (index * 14 / len(scores)), hours=index % 4)
        db.session.add(
            PredictionHistory(
                user_id=user.id,
                score=score,
                inputs=prediction_inputs(index),
                created_at=created_at,
            )
        )
    return len(scores)


def create_chat_sessions(user: User) -> int:
    existing_names = {session.name for session in ChatSession.query.filter_by(user_id=user.id).all()}
    samples = [
        (
            "Improving Sleep Score",
            [
                ("user", "Why was my sleep score lower this week?"),
                ("assistant", "Your recent lower scores line up with shorter duration and more awakenings. Start with a consistent wake time and reduce caffeine after lunch."),
                ("user", "What should I try tonight?"),
                ("assistant", "Keep the plan simple: dim lights early, avoid alcohol close to bed, and give yourself a 20-minute wind-down window."),
            ],
        ),
        (
            "Consistent Bedtime Plan",
            [
                ("user", "How can I make my sleep schedule more consistent?"),
                ("assistant", "Anchor your wake time first, then move bedtime gradually by 15 minutes. Consistency matters more than a perfect schedule."),
                ("user", "Should I exercise at night?"),
                ("assistant", "Light movement is usually fine, but intense workouts close to bed can make it harder to settle."),
            ],
        ),
    ]

    created = 0
    now = datetime.now(timezone.utc)
    for offset, (name, messages) in enumerate(samples):
        if name in existing_names:
            continue
        chat_session = ChatSession(
            user_id=user.id,
            name=name,
            created_at=now - timedelta(days=offset + 2),
            updated_at=now - timedelta(days=offset + 1),
        )
        db.session.add(chat_session)
        db.session.flush()
        for message_index, (role, content) in enumerate(messages):
            db.session.add(
                ChatMessage(
                    session_id=chat_session.id,
                    role=role,
                    content=content,
                    created_at=chat_session.created_at + timedelta(minutes=message_index * 3),
                )
            )
        created += 1
    return created


def main() -> None:
    with app.app_context():
        user = User.query.filter_by(email="alex@test.com").first()
        user_created = False
        if user is None:
            user = User(
                name="Alex",
                email="alex@test.com",
                password_hash=generate_password_hash("test1234"),
            )
            db.session.add(user)
            db.session.flush()
            user_created = True

        predictions_created = create_predictions(user)
        sessions_created = create_chat_sessions(user)
        db.session.commit()

        print("Seed complete")
        print(f"User created: {user_created}")
        print(f"Predictions created: {predictions_created}")
        print(f"Chat sessions created: {sessions_created}")
        print("Login: alex@test.com / test1234")


if __name__ == "__main__":
    main()
