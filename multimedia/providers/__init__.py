"""Provider adapters for external multimedia APIs."""

from multimedia.providers.base import ImageProvider, TextProvider, TTSProvider
from multimedia.providers.cloudflare_worker_image import CloudflareWorkerImageProvider
from multimedia.providers.edge_tts_provider import EdgeTTSProvider
from multimedia.providers.gemini_image import GeminiImageProvider
from multimedia.providers.gemini_text import GeminiTextProvider
from multimedia.providers.gemini_tts import GeminiTTSProvider
from multimedia.providers.pollinations_image import PollinationsImageProvider
from multimedia.providers.sarvam_tts import SarvamTTSProvider
from multimedia.providers.image_factory import configured_image_provider
from multimedia.providers.tts_factory import configured_tts_provider

__all__ = [
    "ImageProvider",
    "TextProvider",
    "TTSProvider",
    "CloudflareWorkerImageProvider",
    "EdgeTTSProvider",
    "GeminiImageProvider",
    "GeminiTextProvider",
    "GeminiTTSProvider",
    "PollinationsImageProvider",
    "SarvamTTSProvider",
    "configured_image_provider",
    "configured_tts_provider",
]
