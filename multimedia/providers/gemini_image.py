"""Gemini image generation provider."""

import logging
from pathlib import Path

from config import GEMINI_IMAGE_MODEL
from multimedia.providers.base import ImageProvider
from multimedia.providers.gemini_common import (
    extension_for_mime,
    extract_inline_data,
    gemini_available,
    gemini_request,
)

LOGGER = logging.getLogger(__name__)


class GeminiImageProvider(ImageProvider):
    @property
    def available(self) -> bool:
        return gemini_available()

    def generate(self, prompt: str, output_path: Path, correlation_id: str = "-") -> dict:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
        }
        response = gemini_request(GEMINI_IMAGE_MODEL, payload, correlation_id)
        data, mime = extract_inline_data(response)
        extension = extension_for_mime(mime, output_path.suffix.lstrip(".") or "jpg")
        target = output_path.with_suffix(f".{extension}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        LOGGER.info("[%s] gemini image saved scene_path=%s bytes=%s", correlation_id, target.name, len(data))
        return {"path": str(target), "mime_type": mime, "bytes": len(data)}
