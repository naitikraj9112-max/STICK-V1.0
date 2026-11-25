"""Integration test: verify Pollinations AI image generation, multi-slide creation, and TTS."""

import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

# ── Pollinations Image Provider Tests ──────────────────────────────────────────

class PollinationsImageProviderTests(unittest.TestCase):
    def test_available_requires_key(self):
        from multimedia.providers.pollinations_image import PollinationsImageProvider

        with patch("multimedia.providers.pollinations_image.POLLINATIONS_API_KEY", ""):
            self.assertFalse(PollinationsImageProvider().available)

        with patch("multimedia.providers.pollinations_image.POLLINATIONS_API_KEY", "sk_test123"):
            self.assertTrue(PollinationsImageProvider().available)

    def test_generate_saves_image(self):
        from multimedia.providers.pollinations_image import PollinationsImageProvider

        # PNG signature
        png_data = b"\x89PNG\r\n\x1a\n" + b"test-image-data"
        response = Mock()
        response.headers = {"Content-Type": "image/png"}
        response.content = png_data
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "scene.webp"
            with patch("multimedia.providers.pollinations_image.POLLINATIONS_API_KEY", "sk_test"), \
                 patch("multimedia.providers.pollinations_image.requests.get", return_value=response) as get:
                result = PollinationsImageProvider().generate("A sunset over mountains", output)

            get.assert_called_once()
            call_kwargs = get.call_args
            self.assertIn("Bearer sk_test", call_kwargs.kwargs["headers"]["Authorization"])
            self.assertEqual(Path(result["path"]).suffix, ".png")
            self.assertEqual(Path(result["path"]).read_bytes(), png_data)

    def test_factory_prefers_pollinations(self):
        from multimedia.providers.image_factory import configured_image_provider
        from multimedia.providers.pollinations_image import PollinationsImageProvider

        with patch("multimedia.providers.image_factory.POLLINATIONS_API_KEY", "sk_test"):
            provider = configured_image_provider()
            self.assertIsInstance(provider, PollinationsImageProvider)


# ── Multi-Slide Creation Tests ─────────────────────────────────────────────────

class MultiSlideTests(unittest.TestCase):
    """Verify that the realtime director allows multiple slides to be created."""

    def test_start_new_scene_allowed_after_dwell_time(self):
        """When the current scene is old enough, start_new_scene must NOT be downgraded to merge."""
        from realtime_director import apply_structured_scene_guard
        from datetime import datetime, timezone, timedelta

        # Simulate a scene that was updated 30 seconds ago (well past the guard)
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        state = {
            "current_scene": {
                "id": "scene-1",
                "kind": "hero",
                "status": "editing",
                "created_at": old_time,
                "updated_at": old_time,
                "content": {
                    "title": "Extract AI",
                    "subtitle": "Turn documents into data",
                    "presentation_stage": "introduction",
                },
            },
            "metadata": {"presentation_stage": "introduction"},
        }
        scene_update = {
            "action": "start_new_scene",
            "kind": "hero",
            "title": "The Problem",
            "subtitle": "Manual extraction wastes hours",
            "presentation_stage": "problem",
            "primary_idea": "Manual work is slow",
        }
        result = apply_structured_scene_guard(scene_update, state, min_new_scene_seconds=6.0)
        # Stage advanced (introduction -> problem), so this must remain start_new_scene
        self.assertEqual(result["action"], "start_new_scene",
                         "Bug: start_new_scene was incorrectly downgraded to merge!")

    def test_start_new_scene_blocked_within_dwell_time(self):
        """During dwell time, start_new_scene should be downgraded to merge (anti-flicker)."""
        from realtime_director import apply_structured_scene_guard
        from datetime import datetime, timezone

        # Scene was just created (now)
        now = datetime.now(timezone.utc).isoformat()
        state = {
            "current_scene": {
                "id": "scene-1",
                "kind": "hero",
                "status": "editing",
                "created_at": now,
                "updated_at": now,
                "content": {
                    "title": "Same topic",
                    "subtitle": "Same subtitle",
                    "presentation_stage": "other",
                },
            },
            "metadata": {"presentation_stage": "other"},
        }
        scene_update = {
            "action": "start_new_scene",
            "kind": "hero",  # same kind
            "title": "Same topic",  # same title
            "subtitle": "Updated subtitle",
            "presentation_stage": "other",  # same stage
            "primary_idea": "Same topic continued",
        }
        result = apply_structured_scene_guard(scene_update, state, min_new_scene_seconds=15.0)
        self.assertEqual(result["action"], "merge",
                         "Slide should merge within dwell time when no clear advancement")

    def test_normalize_realtime_replace_creates_new_scene(self):
        """A 'replace' action from the director should map to 'start_new_scene' when a substantive slide exists."""
        from realtime_director import normalize_realtime_payload
        from datetime import datetime, timezone, timedelta

        old_time = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        state = {
            "current_scene": {
                "id": "scene-1",
                "kind": "hero",
                "status": "editing",
                "created_at": old_time,
                "updated_at": old_time,
                "content": {
                    "title": "Extract AI",
                    "subtitle": "Turn documents into data",
                    "presentation_stage": "introduction",
                },
            },
            "completed_scenes": [],
            "metadata": {"presentation_stage": "introduction"},
        }
        payload = {
            "action": "replace",
            "kind": "hero",
            "title": "Manual extraction fails",
            "subtitle": "Teams waste hours",
            "presentation_stage": "problem",
            "primary_idea": "Manual work is slow",
        }
        with patch("config.MIN_NEW_SCENE_SECONDS", 6.0):
            result = normalize_realtime_payload(payload, True, state)

        self.assertIsNotNone(result, "Result should not be None for a replace action")
        self.assertEqual(result["action"], "start_new_scene",
                         "replace with a new title on a substantive deck should become start_new_scene")

    def test_multiple_slides_end_to_end(self):
        """Simulate 3 transcript events and verify all 3 become separate slides (not merged into 1)."""
        from state_manager import apply_scene_action
        from session import new_presentation_state
        from datetime import datetime, timezone, timedelta

        state = new_presentation_state()

        # Slide 1: Introduction
        scene1 = {
            "action": "replace",
            "kind": "hero",
            "title": "Extract AI",
            "subtitle": "Turn messy docs into structured data",
            "primary_idea": "Product intro",
            "presentation_stage": "introduction",
        }
        apply_scene_action(scene1, state)
        self.assertEqual(state["current_scene"]["content"]["title"], "Extract AI")
        self.assertEqual(len(state["completed_scenes"]), 0)

        # Slide 2: start_new_scene should finalize slide 1 and create slide 2
        scene2 = {
            "action": "start_new_scene",
            "kind": "hero",
            "title": "Manual extraction fails",
            "subtitle": "Teams waste hours copying from PDFs",
            "primary_idea": "The problem",
            "presentation_stage": "problem",
        }
        apply_scene_action(scene2, state)
        self.assertEqual(state["current_scene"]["content"]["title"], "Manual extraction fails")
        self.assertEqual(len(state["completed_scenes"]), 1,
                         "First slide should have been completed and archived!")
        self.assertEqual(state["completed_scenes"][0]["content"]["title"], "Extract AI")

        # Slide 3: Another new scene
        scene3 = {
            "action": "start_new_scene",
            "kind": "cards",
            "title": "What Extract AI does",
            "subtitle": "Three core capabilities",
            "primary_idea": "Core features",
            "presentation_stage": "solution",
        }
        apply_scene_action(scene3, state)
        self.assertEqual(state["current_scene"]["content"]["title"], "What Extract AI does")
        self.assertEqual(len(state["completed_scenes"]), 2,
                         "Should have 2 completed slides + 1 current!")


# ── TTS Tests ──────────────────────────────────────────────────────────────────

class TTSProviderTests(unittest.TestCase):
    def test_edge_tts_is_available(self):
        from multimedia.providers.edge_tts_provider import EdgeTTSProvider
        provider = EdgeTTSProvider()
        self.assertTrue(provider.available, "edge-tts should be installed and available")

    def test_tts_factory_returns_working_provider(self):
        from multimedia.providers.tts_factory import configured_tts_provider
        provider = configured_tts_provider()
        self.assertTrue(provider.available, "TTS provider should be available")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2)
    sys.exit(0 if result.result.wasSuccessful() else 1)
