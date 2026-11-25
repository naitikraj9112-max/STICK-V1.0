"""Edge TTS provider using Microsoft Edge neural speech synthesis."""

import asyncio
import logging
from pathlib import Path

from config import PRESENTATION_LANGUAGE, TTS_VOICE
from multimedia.providers.base import TTSProvider

LOGGER = logging.getLogger(__name__)

# Default high-quality neural voices per language
DEFAULT_VOICES = {
    "en": "en-US-GuyNeural",
    "hi": "hi-IN-SwaraNeural",
    "es": "es-ES-AlvaroNeural",
    "fr": "fr-FR-HenriNeural",
    "de": "de-DE-ConradNeural",
    "ja": "ja-JP-KeitaNeural",
    "zh": "zh-CN-YunxiNeural",
}


class EdgeTTSProvider(TTSProvider):
    """Local, free, zero-credential high-quality neural TTS provider."""

    @property
    def available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    def _resolve_voice(self) -> str:
        # If TTS_VOICE looks like a full Edge voice ID, use it directly
        if TTS_VOICE and "-" in TTS_VOICE and "Neural" in TTS_VOICE:
            return TTS_VOICE
        # Otherwise match by configured presentation language
        lang = (PRESENTATION_LANGUAGE or "en").split("-")[0].lower()
        return DEFAULT_VOICES.get(lang, "en-US-GuyNeural")

    def synthesize(self, text: str, output_path: Path, correlation_id: str = "-") -> dict:
        if not self.available:
            raise RuntimeError("edge-tts is not installed")

        import edge_tts

        voice = self._resolve_voice()
        target = output_path.with_suffix(".mp3")
        target.parent.mkdir(parents=True, exist_ok=True)

        async def _run():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(target))

        try:
            # Handle both running and fresh event loops
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_run(), loop)
                future.result(timeout=30)
            else:
                asyncio.run(_run())
        except Exception as error:
            LOGGER.warning("[%s] edge-tts error: %s", correlation_id, error)
            raise

        file_bytes = target.stat().st_size if target.is_file() else 0
        LOGGER.info("[%s] edge-tts saved path=%s bytes=%s voice=%s", correlation_id, target.name, file_bytes, voice)
        return {"path": str(target), "mime_type": "audio/mpeg", "bytes": file_bytes, "voice": voice}
