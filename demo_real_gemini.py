"""Optional real Gemini verification — skipped when GEMINI_API_KEY is missing."""

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from config import GEMINI_API_KEY
from multimedia.providers.gemini_image import GeminiImageProvider
from multimedia.providers.gemini_text import GeminiTextProvider
from multimedia.providers.gemini_tts import GeminiTTSProvider
from multimedia.workspace import MediaWorkspace


def main():
    if not GEMINI_API_KEY:
        print("Skipping real Gemini test: GEMINI_API_KEY not configured")
        raise SystemExit(0)

    session_id = f"gemini-verify-{uuid4()}"
    with TemporaryDirectory() as directory:
        workspace = MediaWorkspace(session_id, Path(directory))
        workspace.ensure()
        correlation = "real-gemini"

        text_provider = GeminiTextProvider()
        narration = text_provider.generate(
            "Write one short presenter sentence about a live AI presentation product called Stick.",
            correlation,
        )
        assert narration
        narration_path = workspace.narration_path("verify")
        narration_path.write_text(narration)
        print(f"Gemini text ok: {len(narration)} chars")

        image_provider = GeminiImageProvider()
        if image_provider.available:
            try:
                image_result = image_provider.generate(
                    "Cinematic 16:9 abstract technology background, deep blue, no text.",
                    workspace.image_path("verify"),
                    correlation,
                )
                assert Path(image_result["path"]).is_file()
                print(f"Gemini image ok: {image_result['path']}")
            except Exception as error:
                print(f"Gemini image skipped or failed: {error}")

        tts_provider = GeminiTTSProvider()
        if tts_provider.available:
            try:
                tts_result = tts_provider.synthesize(narration[:120], workspace.audio_path("verify"), correlation)
                assert Path(tts_result["path"]).is_file()
                print(f"Gemini TTS ok: {tts_result['path']}")
            except Exception as error:
                print(f"Gemini TTS skipped or failed: {error}")

    print("Real Gemini verification passed.")


if __name__ == "__main__":
    main()
