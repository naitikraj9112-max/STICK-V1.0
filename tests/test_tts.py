"""Tests for Text-to-Speech (TTS) providers and TTS agent."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from multimedia.models import MediaTaskResult
from multimedia.providers.edge_tts_provider import EdgeTTSProvider
from multimedia.providers.gemini_tts import GeminiTTSProvider
from multimedia.providers.sarvam_tts import SarvamTTSProvider
from multimedia.providers.tts_factory import configured_tts_provider
from multimedia.tts_agent import TTSAgent
from multimedia.workspace import MediaWorkspace


def test_edge_tts_provider_available():
    provider = EdgeTTSProvider()
    assert provider.available is True


def test_edge_tts_synthesize():
    provider = EdgeTTSProvider()
    with TemporaryDirectory() as directory:
        output_path = Path(directory) / "test_voice.mp3"
        result = provider.synthesize("Welcome to Stick presentation.", output_path, correlation_id="test-tts")
        assert Path(result["path"]).is_file()
        assert Path(result["path"]).stat().st_size > 500
        assert result["mime_type"] == "audio/mpeg"


def test_tts_factory():
    with patch("multimedia.providers.tts_factory.SARVAM_API_KEY", ""), \
         patch("multimedia.providers.tts_factory.GEMINI_API_KEY", ""):
        provider = configured_tts_provider()
        assert isinstance(provider, EdgeTTSProvider)

    with patch("multimedia.providers.tts_factory.SARVAM_API_KEY", ""), \
         patch("multimedia.providers.tts_factory.GEMINI_API_KEY", "fake-key"):
        provider = configured_tts_provider()
        assert isinstance(provider, GeminiTTSProvider)

    with patch("multimedia.providers.tts_factory.SARVAM_API_KEY", "fake-key"):
        provider = configured_tts_provider()
        assert isinstance(provider, SarvamTTSProvider)


def test_sarvam_tts_synthesizes_to_wav():
    provider = SarvamTTSProvider()
    client = MagicMock()
    response = MagicMock()
    client.text_to_speech.convert.return_value = response

    with TemporaryDirectory() as directory:
        output_path = Path(directory) / "sarvam_test.wav"

        def write_audio(audio_response, filename):
            assert audio_response is response
            Path(filename).write_bytes(b"test-audio")

        with patch("multimedia.providers.sarvam_tts.SARVAM_API_KEY", "fake-key"), \
             patch("multimedia.providers.sarvam_tts.SarvamAI", return_value=client), \
             patch("multimedia.providers.sarvam_tts.save", side_effect=write_audio):
            result = provider.synthesize("Welcome to Stick.", output_path, "test-tts")

        assert Path(result["path"]).is_file()
        assert result["mime_type"] == "audio/wav"
        assert result["voice"] == "shubh_en_narration"
        client.text_to_speech.convert.assert_called_once_with(
            text="Welcome to Stick.",
            language_code="en-IN",
            model="bulbul:v4-flash",
            speaker="shubh_en_narration",
            pace=1.0,
        )


def test_sarvam_tts_rejects_text_over_service_limit():
    provider = SarvamTTSProvider()
    with patch("multimedia.providers.sarvam_tts.SARVAM_API_KEY", "fake-key"), \
         patch("multimedia.providers.sarvam_tts.SarvamAI") as client:
        try:
            provider.synthesize("x" * 2501, Path("unused.wav"))
        except ValueError as error:
            assert "2500" in str(error)
        else:
            raise AssertionError("Expected long text to be rejected")
        client.assert_not_called()


def test_tts_agent_empty_text():
    with TemporaryDirectory() as directory:
        workspace = MediaWorkspace("test-session", Path(directory))
        agent = TTSAgent(EdgeTTSProvider(), workspace)
        result = agent.synthesize("scene-1", "   ")
        assert result.status == "skipped"
        assert result.task_type == "tts"


def test_tts_agent_synthesize_success():
    with TemporaryDirectory() as directory:
        workspace = MediaWorkspace("test-session", Path(directory))
        workspace.ensure()
        agent = TTSAgent(EdgeTTSProvider(), workspace)
        result = agent.synthesize("scene-1", "Here is our solution.")
        assert result.status == "success"
        assert result.path is not None
        assert Path(result.path).is_file()


def test_gemini_tts_handles_riff_and_pcm():
    provider = GeminiTTSProvider()
    with TemporaryDirectory() as directory:
        output_path = Path(directory) / "gemini_test"
        
        # Test RIFF WAV data (already has header)
        riff_data = b"RIFF" + b"\x00" * 40
        with patch("multimedia.providers.gemini_tts.gemini_request", return_value={}), \
             patch("multimedia.providers.gemini_tts.extract_inline_data", return_value=(riff_data, "audio/wav")), \
             patch("multimedia.providers.gemini_tts.gemini_available", return_value=True):
            res = provider.synthesize("hello", output_path)
            assert Path(res["path"]).read_bytes() == riff_data
