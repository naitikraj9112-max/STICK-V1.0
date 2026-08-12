"""Shared Gemini REST helpers."""

import base64
import logging
import time

import requests

from config import GEMINI_API_KEY, MEDIA_RETRIES, MEDIA_RETRY_BACKOFF_SECONDS, MEDIA_TIMEOUT_SECONDS
from reliability import is_retryable

LOGGER = logging.getLogger(__name__)
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def gemini_available() -> bool:
    return bool(GEMINI_API_KEY)


def gemini_request(model: str, payload: dict, correlation_id: str = "-") -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}

    def call():
        response = requests.post(url, headers=headers, json=payload, timeout=MEDIA_TIMEOUT_SECONDS)
        if response.status_code >= 400:
            detail = response.text[:300]
            raise RuntimeError(f"Gemini API error {response.status_code}: {detail}")
        return response.json()

    for attempt in range(MEDIA_RETRIES + 1):
        try:
            return call()
        except Exception as error:
            if not is_retryable(error) or attempt == MEDIA_RETRIES:
                raise
            LOGGER.warning("[%s] multimedia retry %s/%s", correlation_id, attempt + 1, MEDIA_RETRIES)
            time.sleep(MEDIA_RETRY_BACKOFF_SECONDS * (2 ** attempt))
    raise RuntimeError("Gemini request failed")


def extract_text(response: dict) -> str:
    candidates = response.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            text = part.get("text")
            if text:
                return text.strip()
    return ""


def extract_inline_data(response: dict) -> tuple[bytes, str]:
    candidates = response.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if not inline:
                continue
            data = inline.get("data")
            mime = inline.get("mimeType") or inline.get("mime_type") or "application/octet-stream"
            if data:
                return base64.b64decode(data), mime
    raise RuntimeError("Gemini response contained no inline data")


def extension_for_mime(mime: str, default: str) -> str:
    mapping = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/ogg": "ogg",
    }
    return mapping.get(mime.lower(), default)
