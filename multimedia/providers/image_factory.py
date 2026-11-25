"""Select the configured image-generation provider."""

from config import CF_WORKER_URL, POLLINATIONS_API_KEY
from multimedia.providers.base import ImageProvider
from multimedia.providers.pollinations_image import PollinationsImageProvider
from multimedia.providers.cloudflare_worker_image import CloudflareWorkerImageProvider
from multimedia.providers.gemini_image import GeminiImageProvider


def configured_image_provider() -> ImageProvider:
    """Prefer Pollinations AI, then Cloudflare Worker, falling back to Gemini."""
    if POLLINATIONS_API_KEY:
        return PollinationsImageProvider()
    if CF_WORKER_URL:
        return CloudflareWorkerImageProvider()
    return GeminiImageProvider()
