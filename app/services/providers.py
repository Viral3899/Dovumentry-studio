from flask import jsonify

import time
import os

from .api_keys import get_groq_client, get_gemini_client
from .session import log_event
import sqlite3


class ProviderRequiredError(RuntimeError):
    def __init__(self, provider, reason, alternate=None, detail=""):
        super().__init__(reason)
        self.provider = provider
        self.reason = reason
        self.alternate = alternate
        self.detail = detail


def is_resource_exhausted(exc) -> bool:
    msg = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return status == 429 or any(x in msg for x in (
        "rate limit", "quota", "resource exhausted", "too many requests",
        "limit exceeded", "capacity", "429", "exhausted"
    ))


def is_auth_error(exc) -> bool:
    msg = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return status in {401, 403} or any(x in msg for x in (
        "invalid api key", "authentication", "unauthorized", "api key not valid",
        "permission denied", "forbidden"
    ))


def call_text_provider(prompt, system_prompt, session_dir=None, purpose="text", groq_kwargs=None):
    """Use Groq first, but do not mistake model/empty responses for bad API keys.

    Authentication failures require a new Groq key. Quota/capacity exhaustion falls
    through to Gemini. Empty responses are retried briefly, then fall through to
    Gemini when available. This prevents repeated, misleading API-key prompts.
    """
    groq = get_groq_client()
    if groq is None:
        exc = ProviderRequiredError(
            "groq",
            "Groq API key is required for this step. Enter and save your Groq API key.",
            "gemini"
        )
        exc.purpose = purpose
        raise exc

    kwargs = dict(groq_kwargs or {})
    kwargs.setdefault("model", os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
    kwargs.setdefault("messages", [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ])

    last_groq_error = None
    for attempt in range(1, 3):
        try:
            r = groq.chat.completions.create(**kwargs)
            text = (r.choices[0].message.content or "").strip()
            if text:
                return text, "groq"
            last_groq_error = RuntimeError("Groq returned an empty response. The selected Groq model did not return usable text.")
            if session_dir:
                log_event(session_dir, f"Groq {purpose} empty response (attempt {attempt}/2)")
            if attempt < 2:
                time.sleep(1.0)
                continue
            break
        except Exception as ge:
            last_groq_error = ge
            if session_dir:
                log_event(session_dir, f"Groq {purpose} failed (attempt {attempt}/2): {ge}")
            if is_auth_error(ge):
                exc = ProviderRequiredError(
                    "groq",
                    "Groq authentication failed. Re-enter or replace the Groq API key, then retry.",
                    "gemini",
                    str(ge)
                )
                exc.purpose = purpose
                raise exc
            if is_resource_exhausted(ge):
                break
            if attempt < 2:
                time.sleep(1.0)
                continue
            break

    # Groq was unavailable after retrying. Prefer a saved Gemini key for text work.
    gemini = get_gemini_client()
    if gemini is not None:
        try:
            from google.genai import types
            r = gemini.models.generate_content(
                model=os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash"),
                contents=f"{system_prompt}\n\n{prompt}",
            )
            text = (getattr(r, "text", "") or "").strip()
            if text:
                if session_dir:
                    log_event(session_dir, f"{purpose} completed with Gemini fallback after Groq unavailable")
                return text, "gemini"
            raise RuntimeError("Gemini returned an empty response")
        except Exception as ee:
            if session_dir:
                log_event(session_dir, f"Gemini fallback for {purpose} failed: {ee}")
            if is_auth_error(ee) or is_resource_exhausted(ee):
                exc = ProviderRequiredError(
                    "gemini",
                    "Gemini is unavailable. Enter or replace the Gemini API key to continue.",
                    "gemini",
                    str(ee)
                )
                exc.purpose = purpose
                raise exc
            raise RuntimeError(f"AI generation failed after Groq retry and Gemini fallback: {ee}") from ee

    # No Gemini key is available. If Groq was exhausted/failed, ask only for the
    # alternate key; do not repeatedly ask for the same Groq key.
    detail = str(last_groq_error or "Groq did not return usable text.")
    exc = ProviderRequiredError(
        "gemini",
        "Groq is temporarily unavailable. Enter a Gemini API key to continue with the alternate provider.",
        "gemini",
        detail,
    )
    exc.purpose = purpose
    raise exc


def provider_required_response(exc):
    labels = {"groq": "Groq", "gemini": "Gemini"}
    purpose = getattr(exc, "purpose", "")
    return jsonify({
        "success": False,
        "provider_required": True,
        "provider": exc.provider,
        "alternate_provider": exc.alternate,
        "resource_exhausted": is_resource_exhausted(exc.detail),
        "purpose": purpose,
        "allow_default_voice": purpose == "audio",
        "message": f"{labels[exc.provider]} API key is required. {exc.reason}" + (f"\n\nProvider error: {exc.detail}" if exc.detail else "")
    }), 409