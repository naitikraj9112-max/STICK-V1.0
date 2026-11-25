"""HTTP localhost: typed chat and spoken snapshots both build slides."""

import json
import unittest
from http.client import HTTPConnection
from threading import Thread

from communication.server import start_communication_server
from critic import CriticDecision
from demo_memory import InMemoryRepository
from memory import MemoryManager
from orchestrator import PresentationOrchestrator
from presentation_cover import is_cover_scene
from presentation_generator import PresentationGenerator
from semantic_detector import UpdateDecision
from session_manager import SessionManager


class LocalDetector:
    def detect(self, _previous, latest):
        words = latest.split()
        complete = len(words) >= 5
        return UpdateDecision(
            should_plan=complete,
            reason="local",
            approved_content=latest,
            update_type="completed_idea" if complete else "incomplete",
        )


class LocalCritic:
    def review(self, _decision, _context):
        return CriticDecision(approved=True, reason="ok")


def local_planner(transcript, state, **_kwargs):
    if is_cover_scene(state.get("current_scene")):
        action, kind, stage = "replace", "hero", "introduction"
        title = "Stick"
    else:
        action, kind, stage = "start_new_scene", "cards", "problem"
        title = "Next"
    return {
        "action": action,
        "kind": kind,
        "title": title,
        "subtitle": transcript[:90],
        "cards": [transcript[:40]] if kind == "cards" else [],
        "metrics": [],
        "primary_idea": transcript[:120],
        "presentation_stage": stage,
    }


def _wire_local_session(manager: SessionManager) -> None:
    def _build_orchestrator(session):
        return PresentationOrchestrator(
            session_id=session.session_id,
            planner=local_planner,
            semantic_detector=LocalDetector(),
            critic=LocalCritic(),
            memory_manager=MemoryManager(repository=InMemoryRepository(), session_id=session.session_id),
            presentation_generator=PresentationGenerator(session_id=session.session_id, adapter=None),
        )

    manager._build_orchestrator = _build_orchestrator  # type: ignore[method-assign]


class LocalhostSpeechTests(unittest.TestCase):
    port = 18011

    @classmethod
    def setup_class(cls):
        cls.manager = SessionManager()
        _wire_local_session(cls.manager)
        cls.server = start_communication_server(cls.manager, host="127.0.0.1", port=cls.port, block=False)
        Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def teardown_class(cls):
        cls.server.shutdown()

    def _req(self, method, path, body=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=8)
        payload = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        data = json.loads(raw) if raw else {}
        return response.status, data

    def test_typed_and_spoken_snapshots_both_build_slides(self):
        status, session = self._req("POST", "/session", {"output_language": "en"})
        assert status == 200
        session_id = session["session_id"]

        typed = "Welcome to Stick, a live presentation engine that builds decks as you speak."
        status, typed_result = self._req(
            "POST",
            "/transcript",
            {"session_id": session_id, "transcript": typed, "is_final": True, "event_id": "typed-local-1"},
        )
        assert status == 200
        assert typed_result.get("scene_updated") is True

        status, spoken_session = self._req("POST", "/session", {"output_language": "en"})
        spoken_id = spoken_session["session_id"]
        self._req("POST", "/session/connect", {"session_id": spoken_id})

        # Browser often sends fragments first, then a growing snapshot — same as the fixed client.
        status, first = self._req(
            "POST",
            "/transcript",
            {"session_id": spoken_id, "transcript": "The problem is", "is_final": True, "event_id": "speech-1"},
        )
        assert status == 200
        status, second = self._req(
            "POST",
            "/transcript",
            {
                "session_id": spoken_id,
                "transcript": "The problem is that slide decks take hours of manual design work",
                "is_final": True,
                "event_id": "speech-2",
            },
        )
        assert status == 200
        assert second.get("scene_updated") is True

        status, presentation = self._req("GET", f"/presentation?session_id={spoken_id}")
        assert status == 200
        current = presentation.get("current_scene") or {}
        assert current.get("component") != "CoverScene"
        assert current.get("props", {}).get("is_cover") is not True

    def test_hindi_transcript_with_detected_language_builds_slide(self):
        status, session = self._req("POST", "/session", {"output_language": "en"})
        assert status == 200
        session_id = session["session_id"]

        hindi_text = "नमस्ते, आज हम स्टिक के माध्यम से हिंदी में प्रस्तुति बना रहे हैं।"
        status, result = self._req(
            "POST",
            "/transcript",
            {
                "session_id": session_id,
                "transcript": hindi_text,
                "is_final": True,
                "source": "sarvam-saaras-v4-realtime",
                "language": "hi-IN",
                "event_id": "hindi-speech-1",
            },
        )
        assert status == 200
        assert result.get("scene_updated") is True

        status, presentation = self._req("GET", f"/presentation?session_id={session_id}")
        assert status == 200
        assert presentation.get("metadata", {}).get("output_language") == "hi"
        current = presentation.get("current_scene") or {}
        assert current.get("component") != "CoverScene"
        assert "नमस्ते" in current.get("props", {}).get("subtitle", "")

    def test_frontend_defines_thinking_ms_for_speech_handlers(self):
        from pathlib import Path
        import re

        html = (Path(__file__).resolve().parents[1] / "communication" / "static" / "index.html").read_text(encoding="utf-8")
        assert re.search(r"\b(?:const|let|var)\s+THINKING_MS\s*=", html), "THINKING_MS must be defined in index.html"
