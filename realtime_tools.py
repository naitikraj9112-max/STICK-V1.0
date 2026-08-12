"""OpenAI Realtime session configuration for live presentation tool calls."""

from config import OPENAI_REALTIME_MODEL, OPENAI_TRANSCRIPTION_MODEL, PRESENTATION_LANGUAGE, REALTIME_SILENCE_MS, REALTIME_TOOL_CHOICE
from realtime_director import build_stage_scene_tool, director_instructions


def build_realtime_session_config(output_language: str | None = None) -> dict:
    """Build the Realtime session payload used when establishing WebRTC."""
    language = output_language or PRESENTATION_LANGUAGE
    return {
        "type": "realtime",
        "model": OPENAI_REALTIME_MODEL,
        "instructions": director_instructions(language),
        "tools": [build_stage_scene_tool()],
        "tool_choice": REALTIME_TOOL_CHOICE,
        "audio": {
            "input": {
                "transcription": {"model": OPENAI_TRANSCRIPTION_MODEL},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.35,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": REALTIME_SILENCE_MS,
                    "create_response": True,
                    "interrupt_response": False,
                },
            },
        },
    }
