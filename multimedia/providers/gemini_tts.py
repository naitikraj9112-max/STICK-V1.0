"""Gemini TTS provider."""

import logging
import wave
from pathlib import Path

from config import GEMINI_TTS_MODEL, TTS_VOICE
from multimedia.providers.base import TTSProvider
from multimedia.providers.gemini_common import (
    extension_for_mime,
    extract_inline_data,
    gemini_available,
    gemini_request,
)

LOGGER = logging.getLogger(__name__)


class GeminiTTSProvider(TTSProvider):
    @property
    def available(self) -> bool:
        return gemini_available()

    def synthesize(self, text: str, output_path: Path, correlation_id: str = "-") -> dict:
        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}},
                },
            },
        }
        response = gemini_request(GEMINI_TTS_MODEL, payload, correlation_id)
        data, mime = extract_inline_data(response)
        extension = extension_for_mime(mime, output_path.suffix.lstrip(".") or "wav")
        target = output_path.with_suffix(f".{extension}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if mime in {"audio/L16", "audio/pcm", "audio/raw"} or extension == "wav":
            _write_wav(target, data)
        else:
            target.write_bytes(data)
        LOGGER.info("[%s] gemini tts saved path=%s bytes=%s mime=%s", correlation_id, target.name, len(data), mime)
        return {"path": str(target), "mime_type": mime, "bytes": len(data)}


def _write_wav(path: Path, pcm_data: bytes, sample_rate: int = 24000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm_data)
