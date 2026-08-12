"""Gemini text generation provider for narration scripts."""

from config import GEMINI_MODEL
from multimedia.providers.base import TextProvider
from multimedia.providers.gemini_common import extract_text, gemini_available, gemini_request


class GeminiTextProvider(TextProvider):
    @property
    def available(self) -> bool:
        return gemini_available()

    def generate(self, prompt: str, correlation_id: str = "-") -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 512},
        }
        response = gemini_request(GEMINI_MODEL, payload, correlation_id)
        text = extract_text(response)
        if not text:
            raise RuntimeError("Gemini returned empty narration text")
        return text
