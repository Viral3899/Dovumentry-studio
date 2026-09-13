import json
import os
from pathlib import Path
import sqlite3

from ..utils.paths import RUNTIME_DIR

API_KEYS_FILE = RUNTIME_DIR / "api_keys.json"


def _load_saved_api_keys() -> dict:
    try:
        return json.loads(API_KEYS_FILE.read_text(encoding="utf-8")) if API_KEYS_FILE.exists() else {}
    except Exception:
        return {}


def _save_api_key(provider: str, key: str) -> None:
    if provider not in {"groq", "gemini"} or len(key.strip()) < 10:
        raise ValueError("Enter a valid Groq or Gemini API key.")
    data = _load_saved_api_keys()
    data[provider] = key.strip()
    API_KEYS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.environ["GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY"] = key.strip()


def _get_api_key(provider: str) -> str:
    env = "GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY"
    return (os.getenv(env) or _load_saved_api_keys().get(provider) or "").strip()


def provider_status() -> dict:
    saved = _load_saved_api_keys()
    return {
        "groq": bool(os.getenv("GROQ_API_KEY") or saved.get("groq")),
        "gemini": bool(os.getenv("GEMINI_API_KEY") or saved.get("gemini")),
    }


def get_groq_client():
    from groq import Groq
    key = _get_api_key("groq")
    if not key:
        return None
    return Groq(api_key=key)


def get_gemini_client():
    from google import genai
    key = _get_api_key("gemini")
    if not key:
        return None
    try:
        return genai.Client(api_key=key)
    except Exception:
        return None