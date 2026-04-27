from pathlib import Path

import joblib
import pandas as pd

MODEL_PATH = Path(__file__).resolve().parent / "models" / "xgboost_sleep_model.pkl"
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
