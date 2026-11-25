"""Cloudflare Worker image-generation provider."""

import logging
from pathlib import Path

import requests

from config import CF_WORKER_URL, MEDIA_TIMEOUT_SECONDS
from multimedia.providers.base import ImageProvider

LOGGER = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {
    "image/png": (".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/webp": (".webp", lambda data: len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"),
}


class CloudflareWorkerImageProvider(ImageProvider):
    @property
    def available(self) -> bool:
        return bool(CF_WORKER_URL)

    def generate(self, prompt: str, output_path: Path, correlation_id: str = "-") -> dict:
        if not self.available:
            raise RuntimeError("CF_WORKER_URL is not configured")

        base_url = CF_WORKER_URL.rstrip("/")
        generate_url = base_url if base_url.endswith("/generate") else f"{base_url}/generate"
        response = requests.post(
            generate_url,
            json={"prompt": prompt},
            timeout=MEDIA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        mime_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        image_format = IMAGE_EXTENSIONS.get(mime_type)
        if not image_format:
            raise RuntimeError(f"Cloudflare image worker returned unsupported content type: {mime_type or 'missing'}")
        extension, matches_signature = image_format
        if not matches_signature(response.content):
            raise RuntimeError(f"Cloudflare image worker returned invalid {mime_type} data")

        target = output_path.with_suffix(extension)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        LOGGER.info(
            "[%s] cloudflare image saved scene_path=%s bytes=%s mime=%s",
            correlation_id,
            target.name,
            len(response.content),
            mime_type,
        )
        return {"path": str(target), "mime_type": mime_type, "bytes": len(response.content)}
