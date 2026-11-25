"""Pollinations.ai image-generation provider."""

import logging
from pathlib import Path
from urllib.parse import quote

import requests

from config import POLLINATIONS_API_KEY, MEDIA_TIMEOUT_SECONDS
from multimedia.providers.base import ImageProvider

LOGGER = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {
    "image/png": (".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/webp": (".webp", lambda data: len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"),
}

POLLINATIONS_BASE = "https://gen.pollinations.ai"


class PollinationsImageProvider(ImageProvider):
    @property
    def available(self) -> bool:
        return bool(POLLINATIONS_API_KEY)

    def generate(self, prompt: str, output_path: Path, correlation_id: str = "-") -> dict:
        if not self.available:
            raise RuntimeError("POLLINATIONS_API_KEY is not configured")

        encoded_prompt = quote(prompt, safe="")
        url = f"{POLLINATIONS_BASE}/image/{encoded_prompt}"
        params = {
            "width": 1024,
            "height": 1024,
            "nologo": "true",
            "enhance": "true",
        }
        headers = {
            "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
        }
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=MEDIA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        mime_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()

        # Pollinations returns raw image bytes; detect format from content
        data = response.content
        detected_ext = None
        for mime, (ext, sig_check) in IMAGE_EXTENSIONS.items():
            if sig_check(data):
                detected_ext = ext
                mime_type = mime
                break
        if not detected_ext:
            # Default to PNG if we can't detect
            detected_ext = ".png"
            mime_type = "image/png"

        target = output_path.with_suffix(detected_ext)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        LOGGER.info(
            "[%s] pollinations image saved scene_path=%s bytes=%s mime=%s",
            correlation_id,
            target.name,
            len(data),
            mime_type,
        )
        return {"path": str(target), "mime_type": mime_type, "bytes": len(data)}
