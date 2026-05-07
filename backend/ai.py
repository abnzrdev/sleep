import os
import string
import time
from collections import deque
from pathlib import Path
from threading import RLock

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - keeps the app bootable until dependencies are installed.
    OpenAI = None

from .i18n import get_language_name, t
from .tools import build_context

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_FALLBACK_CHAIN = [
    "meta/llama-3.1-8b-instruct",
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
    "mistralai/mistral-nemo-12b-instruct",
]
RATE_LIMIT_MESSAGE = "Too many requests right now, please wait a moment and try again."
UNAVAILABLE_MESSAGE = "AI assistant is unavailable right now."
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
MAX_REQUESTS_PER_MINUTE = 40
CHARACTER_DELAY_SECONDS = 0.035

_client = None
_client_lock = RLock()
_rate_limit_lock = RLock()
_request_times = deque()


def _get_client():
    global _client
    if OpenAI is None:
        return None

    api_key = os.getenv("NIM_API_KEY")
    if not api_key:
        return None

    with _client_lock:
        if _client is None:
            _client = OpenAI(base_url=NIM_BASE_URL, api_key=api_key)
        return _client


def _is_rate_limit_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        return True
    return error.__class__.__name__ == "RateLimitError"


def _reserve_request_slot() -> bool:
    now = time.monotonic()
    with _rate_limit_lock:
        while _request_times and now - _request_times[0] >= 60:
            _request_times.popleft()
        if len(_request_times) >= MAX_REQUESTS_PER_MINUTE:
            return False
        _request_times.append(now)
        return True


def _completion(messages: list[dict[str, str]], *, stream: bool, max_tokens: int | None = None, temperature: float = 0.4):
    client = _get_client()
    if client is None:
        return None, UNAVAILABLE_MESSAGE

    errors = []
    for index, model in enumerate(MODEL_FALLBACK_CHAIN):
        if not _reserve_request_slot():
            return None, RATE_LIMIT_MESSAGE

        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": stream,
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            return client.chat.completions.create(**kwargs), None
        except Exception as error:  # noqa: BLE001 - provider fallback needs broad exception handling.
            errors.append(error)
            if index < len(MODEL_FALLBACK_CHAIN) - 1:
                time.sleep(0.35 * (2**index))

    if errors and all(_is_rate_limit_error(error) for error in errors):
        return None, RATE_LIMIT_MESSAGE
    return None, UNAVAILABLE_MESSAGE


def _build_chat_messages(user_id: int, history: list[dict[str, str]], message: str) -> list[dict[str, str]]:
    language_name = get_language_name()
    language_instruction = (
        f"User selected language: {language_name}. "
        "Answer in this language unless the user clearly asks for another language. "
        "If the user writes in Russian or Kazakh, reply in the same language."
    )
    return [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{language_instruction}\n\n{build_context(user_id)}"},
        *history,
        {"role": "user", "content": message},
    ]


def stream_chat_response(user_id: int, history: list[dict[str, str]], message: str):
    stream, error_message = _completion(_build_chat_messages(user_id, history, message), stream=True)
    if error_message:
        for character in error_message:
            time.sleep(CHARACTER_DELAY_SECONDS)
            yield character
        return

    for chunk in stream:
        token = chunk.choices[0].delta.content if chunk.choices else None
        if not token:
            continue
        for character in token:
            time.sleep(CHARACTER_DELAY_SECONDS)
            yield character


def generate_session_name(first_message: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "Generate a short chat title. Max 5 words. No punctuation. Return only the title.",
        },
        {"role": "user", "content": first_message},
    ]
    response, error_message = _completion(messages, stream=False, max_tokens=10, temperature=0.2)
    if error_message or response is None:
        return t("chat.sleep_coach")

    title = response.choices[0].message.content or t("chat.sleep_coach")
    title = title.translate(str.maketrans("", "", string.punctuation))
    words = [word.strip() for word in title.split() if word.strip()]
    return " ".join(words[:5]) or t("chat.sleep_coach")


def generate_daily_tip_text(user_id: int, user_name: str, score: float | None, time_of_day: str, previous_tip: str | None) -> str:
    score_text = "No prediction score yet" if score is None else f"Last prediction score: {round(score * 100, 1)}%"
    previous_text = f"Do not repeat this exact previous tip: {previous_tip}" if previous_tip else "No previous tip."
    language_name = get_language_name()
    messages = [
        {
            "role": "system",
            "content": (
                "Write a warm personal AI sleep brief for LunaSleep AI. "
                "Use exactly 2 short sentences. Mention latest score and recent trend direction when possible. "
                "Do not include bullets or a heading. Do not diagnose medical conditions. "
                f"User selected language: {language_name}. "
                "Answer in this language unless the user clearly asks for another language. "
                "If the user writes in Russian or Kazakh, reply in the same language."
            ),
        },
        {
            "role": "user",
            "content": f"User: {user_name}. Time of day: {time_of_day}. {score_text}. {previous_text}\n\n{build_context(user_id)}",
        },
    ]
    response, error_message = _completion(messages, stream=False, max_tokens=120, temperature=0.55)
    if error_message or response is None:
        narrative = t("dashboard.ai_brief_fallback")
    else:
        narrative = (response.choices[0].message.content or "").strip()

    narrative = narrative.replace("\r", "\n").strip()
    narrative_lines = [line.strip() for line in narrative.splitlines() if line.strip() and not line.strip().startswith("-")]
    narrative_text = " ".join(narrative_lines).strip() or t("dashboard.ai_brief_fallback")
    return (
        f"{narrative_text}\n\n"
        f"{t('dashboard.next_steps_label')}:\n"
        f"- {t('dashboard.next_step_1')}\n"
        f"- {t('dashboard.next_step_2')}\n"
        f"- {t('dashboard.next_step_3')}"
    )
