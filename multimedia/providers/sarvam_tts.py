"""Sarvam Bulbul text-to-speech provider."""

import logging
from pathlib import Path

from sarvamai import SarvamAI
from sarvamai.play import save

from config import (
    PRESENTATION_LANGUAGE,
    SARVAM_API_KEY,
    SARVAM_TTS_MODEL,
    SARVAM_TTS_SPEAKER,
    TTS_SPEED,
)
from multimedia.providers.base import TTSProvider

LOGGER = logging.getLogger(__name__)

V3_LANGUAGES = {"bn", "en", "gu", "hi", "kn", "ml", "mr", "od", "pa", "ta", "te"}
V4_SPEAKERS = {
    "bn": "arnab_bn_conversation",
    "en": "shubh_en_narration",
    "gu": "bhavik_gu_conversation",
    "hi": "simran_hi_narration",
    "kn": "chaitra_kn_narration",
    "mr": "neha_mr_narration",
    "pa": "harpreet_pa_narration",
    "ta": "gokul_ta_narration",
    "te": "kavitha_te_narration",
}


class SarvamTTSProvider(TTSProvider):
    """Generate scene narration using Sarvam's Bulbul speech API."""

    @property
    def available(self) -> bool:
        return bool(SARVAM_API_KEY)

    def _language_code(self) -> str:
        language = (PRESENTATION_LANGUAGE or "en").split("-")[0].lower()
        if language not in V3_LANGUAGES:
            raise ValueError(f"Sarvam TTS does not support presentation language: {PRESENTATION_LANGUAGE}")
        return f"{language}-IN"

    def _speaker(self, language: str) -> str:
        if SARVAM_TTS_SPEAKER:
            return SARVAM_TTS_SPEAKER
        if SARVAM_TTS_MODEL == "bulbul:v3":
            return "shubh"
        try:
            return V4_SPEAKERS[language.split("-")[0]]
        except KeyError as error:
            raise ValueError(
                f"Bulbul v4 Flash has no configured speaker for {language}; "
                "use Bulbul v3 or set SARVAM_TTS_SPEAKER."
            ) from error

    def synthesize(self, text: str, output_path: Path, correlation_id: str = "-") -> dict:
        if not self.available:
            raise RuntimeError("SARVAM_API_KEY is not configured")
        if len(text) > 2500:
            raise ValueError("Sarvam REST TTS accepts at most 2500 characters per request")
        if SARVAM_TTS_MODEL not in {"bulbul:v3", "bulbul:v4-flash"}:
            raise ValueError(f"Unsupported Sarvam TTS model: {SARVAM_TTS_MODEL}")
        if not 0.5 <= TTS_SPEED <= 2.0:
            raise ValueError("TTS_SPEED must be between 0.5 and 2.0 for Sarvam TTS")

        language = self._language_code()
        speaker = self._speaker(language)
        target = output_path.with_suffix(".wav")
        target.parent.mkdir(parents=True, exist_ok=True)

        client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
        response = client.text_to_speech.convert(
            text=text,
            language_code=language,
            model=SARVAM_TTS_MODEL,
            speaker=speaker,
            pace=TTS_SPEED,
        )
        save(response, str(target))
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError("Sarvam TTS returned no audio data")

        size = target.stat().st_size
        LOGGER.info(
            "[%s] sarvam tts saved path=%s bytes=%s model=%s speaker=%s",
            correlation_id,
            target.name,
            size,
            SARVAM_TTS_MODEL,
            speaker,
        )
        return {
            "path": str(target),
            "mime_type": "audio/wav",
            "bytes": size,
            "model": SARVAM_TTS_MODEL,
            "voice": speaker,
            "language_code": language,
        }
