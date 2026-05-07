import json
from pathlib import Path

from flask import g, session

ROOT_DIR = Path(__file__).resolve().parents[1]
TRANSLATION_DIR = ROOT_DIR / "translations"

SUPPORTED_LANGUAGES = {
    "en": "English",
    "ru": "Russian",
    "kk": "Kazakh",
}

_TRANSLATION_CACHE = {}


def get_current_language() -> str:
    try:
        lang = session.get("lang", "en")
    except RuntimeError:
        lang = "en"

    return lang if lang in SUPPORTED_LANGUAGES else "en"


def get_language_name(lang: str | None = None) -> str:
    lang = lang or get_current_language()
    return SUPPORTED_LANGUAGES.get(lang, "English")


def set_current_language(lang: str) -> str:
    selected = lang if lang in SUPPORTED_LANGUAGES else "en"
    session["lang"] = selected
    session.modified = True
    return selected


def load_translations(lang: str) -> dict:
    if lang not in SUPPORTED_LANGUAGES:
        lang = "en"

    if lang not in _TRANSLATION_CACHE:
        path = TRANSLATION_DIR / f"{lang}.json"
        with path.open("r", encoding="utf-8") as file:
            _TRANSLATION_CACHE[lang] = json.load(file)

    return _TRANSLATION_CACHE[lang]


def t(key: str) -> str:
    lang = getattr(g, "lang", "en")
    data = load_translations(lang)

    value = data
    for part in key.split("."):
        if not isinstance(value, dict):
            return key
        value = value.get(part)

        if value is None:
            return key

    return str(value)


def translate_error(message: str) -> str:
    error_map = {
        "This field is required.": "errors.required",
        "Invalid email address.": "errors.invalid_email",
        "Field must be between 2 and 120 characters long.": "errors.name_length",
        "Field must be between 8 and 128 characters long.": "errors.password_length",
        "Passwords must match.": "errors.passwords_must_match",
        "Invalid email or password.": "errors.invalid_credentials",
        "An account with this email already exists.": "errors.email_exists",
        "Check the form fields and try again.": "errors.check_form",
    }
    return t(error_map.get(message, message))
