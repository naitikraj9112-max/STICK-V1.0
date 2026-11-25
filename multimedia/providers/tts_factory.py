"""Select the configured TTS provider."""

from config import GEMINI_API_KEY, SARVAM_API_KEY
from multimedia.providers.base import TTSProvider
from multimedia.providers.edge_tts_provider import EdgeTTSProvider
from multimedia.providers.gemini_tts import GeminiTTSProvider
from multimedia.providers.sarvam_tts import SarvamTTSProvider


def configured_tts_provider() -> TTSProvider:
    """Prefer configured Sarvam, then Gemini, then Edge TTS."""
    if SARVAM_API_KEY:
        return SarvamTTSProvider()
    if GEMINI_API_KEY:
        return GeminiTTSProvider()
    edge = EdgeTTSProvider()
    if edge.available:
        return edge
    return GeminiTTSProvider()
