"""Provider adapters for external multimedia APIs."""

from multimedia.providers.base import ImageProvider, TextProvider, TTSProvider
from multimedia.providers.gemini_image import GeminiImageProvider
from multimedia.providers.gemini_text import GeminiTextProvider
from multimedia.providers.gemini_tts import GeminiTTSProvider

__all__ = [
    "ImageProvider",
    "TextProvider",
    "TTSProvider",
    "GeminiImageProvider",
    "GeminiTextProvider",
    "GeminiTTSProvider",
]
