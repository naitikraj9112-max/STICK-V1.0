"""Sarvam Saaras speech-to-text provider."""

from io import BytesIO

from sarvamai import SarvamAI

from config import SARVAM_API_KEY, SARVAM_STT_MODEL


def transcribe_audio(audio: bytes, content_type: str = "audio/webm") -> dict:
    """Transcribe a short browser audio clip with automatic language detection."""
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not configured")
    if not audio:
        raise ValueError("Audio clip is empty")

    mime_type = content_type.split(";", 1)[0].strip().lower()
    extension = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mp4": "m4a",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
    }.get(mime_type)
    if not extension:
        raise ValueError(f"Unsupported browser audio type: {mime_type or 'unknown'}")

    client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
    response = client.speech_to_text.transcribe(
        file=(f"speech.{extension}", BytesIO(audio), mime_type),
        model=SARVAM_STT_MODEL,
        mode="transcribe",
        language_code="unknown",
    )
    return {
        "transcript": (response.transcript or "").strip(),
        "language_code": response.language_code,
        "request_id": response.request_id,
    }
