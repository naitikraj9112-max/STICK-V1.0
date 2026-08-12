"""Coordinate transcript detection, planning, and scene lifecycle updates."""

import inspect
import logging
from collections import deque
from copy import deepcopy
from threading import RLock, Thread
from uuid import uuid4

from critic import PresentationCritic
from execution_policy import should_plan_multimedia, should_run_critic
from memory import MemoryManager
from memory.extraction import MemoryExtractor
from multimedia import MultimediaManager
from multimedia.live_imagery import LiveImageryManager
from planner import presenter_planner
from presentation_generator import PresentationGenerator
from presentation_generator.scene_images import build_scene_image_map
from presentation_context import build_presentation_context
from semantic_detector import SemanticDetector
from session import new_presentation_state
from realtime_director import normalize_realtime_payload
from rendering import render_scene
from state_manager import apply_scene_action
from tools import SceneDecision
from reliability import failure, is_retryable

LOGGER = logging.getLogger(__name__)


class PresentationOrchestrator:
    """Coordinate the detector, planner, and state manager for one session."""

    def __init__(
        self,
        planner=presenter_planner,
        semantic_detector=None,
        critic=None,
        memory_manager=None,
        memory_extractor=None,
        presentation_generator=None,
        multimedia_manager=None,
        live_imagery_manager=None,
        presentation_state: dict | None = None,
        session_id: str | None = None,
        user_id: str = "local-user",
        presentation_id: str = "local-presentation",
    ):
        self.session_id = session_id or str(uuid4())
        self.planner = planner
        self.semantic_detector = semantic_detector or SemanticDetector()
        self.critic = critic or PresentationCritic()
        self.presentation_state = presentation_state if presentation_state is not None else new_presentation_state()
        self.memory_manager = memory_manager or MemoryManager(
            user_id=user_id, presentation_id=presentation_id, session_id=self.session_id
        )
        self.memory_extractor = memory_extractor or MemoryExtractor()
        self.presentation_generator = presentation_generator or PresentationGenerator(session_id=self.session_id)
        self.multimedia_manager = multimedia_manager or MultimediaManager(session_id=self.session_id)
        self.live_imagery = live_imagery_manager or LiveImageryManager(session_id=self.session_id)
        self.live_imagery.set_on_image_ready(self._on_live_image_ready)
        self.presentation_generator.scene_image_resolver = self._scene_image_map_for_export
        self.memory_manager.clear_session()
        self.last_transcript = ""
        self._lock = RLock()
        self._processed_events = deque(maxlen=100)

    def receive_transcript(self, latest_transcript: str, event_id: str | None = None, is_final: bool = True) -> dict:
        """Process one transcript snapshot and coordinate the next pipeline step."""
        with self._lock:
            return self._receive_transcript(latest_transcript, event_id, is_final)

    def finalize_session(self) -> None:
        """Clear session-scoped working memory without touching durable preferences."""
        try:
            self.memory_manager.clear_session()
        except Exception:
            LOGGER.warning("[%s] session memory cleanup failed", self.session_id)

    def apply_realtime_scene(self, scene_update: dict, call_id: str | None = None) -> dict:
        """Apply a Realtime stage_scene tool call and return the rendered slide immediately."""
        with self._lock:
            return self._apply_realtime_scene(scene_update, call_id)

    def _apply_realtime_scene(self, scene_update: dict, call_id: str | None) -> dict:
        correlation_id = call_id or str(uuid4())
        if call_id and call_id in self._processed_events:
            return {"success": False, "scene_updated": False, "reason": "Duplicate scene call ignored.", "correlation_id": correlation_id}

        has_current = bool(self.presentation_state.get("current_scene"))
        normalized = normalize_realtime_payload(scene_update, has_current, self.presentation_state)
        if normalized is None:
            if call_id:
                self._processed_events.append(call_id)
            LOGGER.info("[%s][%s] director hold — no scene change", self.session_id, correlation_id)
            return {"success": True, "scene_updated": False, "held": True, "correlation_id": correlation_id, "reason": "No visual change."}

        try:
            previous_scene = deepcopy(self.presentation_state.get("current_scene"))
            director_action = scene_update.get("action", "focus")
            scene = apply_scene_action(normalized, self.presentation_state)
            if call_id:
                self._processed_events.append(call_id)
            LOGGER.info("[%s][%s] realtime scene applied action=%s kind=%s scene=%s", self.session_id, correlation_id, normalized.get("action"), normalized.get("kind"), scene.get("id"))
        except Exception:
            LOGGER.error("[%s][%s] realtime scene rejected", self.session_id, correlation_id)
            return {"success": False, "scene_updated": False, "reason": "Invalid scene update rejected.", "correlation_id": correlation_id, **failure("state_manager", "Invalid scene update rejected")}

        action = normalized.get("action", "replace")
        state_snapshot = deepcopy(self.presentation_state)
        self._schedule_async_generation(action, state_snapshot, correlation_id)
        self.live_imagery.schedule(scene, director_action, previous_scene, correlation_id)
        self._schedule_async_realtime_memory(normalized, correlation_id)
        return {
            "success": True,
            "scene_updated": True,
            "correlation_id": correlation_id,
            "scene": render_scene(
                scene,
                session_id=self.session_id,
                scene_images=self.live_imagery.scene_image_map(),
                scene_image_status=self.live_imagery.scene_status_map(),
            ),
            "generation": {"status": "generating", "message": "Exporting PowerPoint in background…"},
        }

    def _receive_transcript(self, latest_transcript: str, event_id: str | None, is_final: bool) -> dict:
        latest_transcript = latest_transcript.strip()
        correlation_id = event_id or str(uuid4())
        accounting = {"event_id": correlation_id, "session_id": self.session_id, "detector_called": False, "memory_retrieved": False, "planner_called": False, "critic_called": False, "refinement_called": False, "scene_updated": False}
        if not is_final:
            return {"planned": False, "reason": "Partial transcript ignored until utterance completes.", "correlation_id": correlation_id, **accounting}
        if not latest_transcript or latest_transcript == self.last_transcript or correlation_id in self._processed_events:
            return {"planned": False, "reason": "Duplicate or empty transcript ignored.", "correlation_id": correlation_id, **accounting}

        try:
            accounting["detector_called"] = True
            decision = self._detect(latest_transcript, correlation_id)
            LOGGER.info("[%s][%s] semantic decision should_plan=%s type=%s", self.session_id, correlation_id, decision.should_plan, decision.update_type)
        except Exception as error:
            LOGGER.error("[%s][%s] semantic detector failed", self.session_id, correlation_id)
            return {"planned": False, "reason": "Semantic detector temporarily unavailable.", "correlation_id": correlation_id, **accounting, **failure("semantic_detector", "Semantic detector temporarily unavailable", is_retryable(error))}

        self.last_transcript = latest_transcript
        self._processed_events.append(correlation_id)

        result = {"planned": decision.should_plan, "success": True, "correlation_id": correlation_id, **accounting, **decision.model_dump()}
        result["execution"] = accounting
        if decision.should_plan:
            accounting["memory_retrieved"] = True
            relevant_memory = self._retrieve_memory(decision.approved_content, correlation_id)
            try:
                accounting["planner_called"] = True
                scene_update = SceneDecision.model_validate(self._plan(decision.approved_content, relevant_memory=relevant_memory, correlation_id=correlation_id)).model_dump()
                LOGGER.info("[%s][%s] planner action=%s kind=%s", self.session_id, correlation_id, scene_update["action"], scene_update["kind"])
            except Exception as error:
                LOGGER.error("[%s][%s] planner failed; state unchanged", self.session_id, correlation_id)
                result.update({"planned": False, "success": False, "reason": "Planner temporarily unavailable.", **failure("planner", "Planner temporarily unavailable", is_retryable(error))})
                result.update(accounting)
                return result
            context = build_presentation_context(decision.approved_content, self.presentation_state, relevant_memory)
            original_scene_update = scene_update
            critique = None
            if should_run_critic(scene_update, self.presentation_state):
                try:
                    accounting["critic_called"] = True
                    critique = self._review(scene_update, context, correlation_id)
                    result["critic"] = critique.model_dump()
                    LOGGER.info("[%s][%s] critic approved=%s", self.session_id, correlation_id, critique.approved)
                except Exception:
                    LOGGER.warning("[%s][%s] critic unavailable; using valid planner scene", self.session_id, correlation_id)
                    result["critic"] = {"approved": True, "reason": "Critic unavailable; planner fallback used.", "suggestions": [], "issue": "none"}
            else:
                result["critic"] = {"approved": True, "reason": "Critic skipped by execution policy.", "suggestions": [], "issue": "none"}

            if critique and not critique.approved:
                try:
                    accounting["refinement_called"] = True
                    accounting["planner_called"] = True
                    refined_scene_update = SceneDecision.model_validate(self._plan(decision.approved_content, critique.model_dump(), relevant_memory, correlation_id)).model_dump()
                    accounting["critic_called"] = True
                    critique = self._review(refined_scene_update, context, correlation_id)
                    result["refined"] = True
                    result["critic_after_refinement"] = critique.model_dump()
                    if critique.approved:
                        scene_update = refined_scene_update
                    else:
                        LOGGER.warning("[%s][%s] refined scene rejected; applying original planner scene", self.session_id, correlation_id)
                        scene_update = original_scene_update
                        result["refinement_fallback"] = True
                except Exception:
                    LOGGER.warning("[%s][%s] refinement unavailable; using original valid planner scene", self.session_id, correlation_id)
                    scene_update = original_scene_update
                    result["refinement_fallback"] = True

            try:
                previous_scene = deepcopy(self.presentation_state.get("current_scene"))
                result["scene"] = apply_scene_action(scene_update, self.presentation_state)
                accounting["scene_updated"] = True
                LOGGER.info("[%s][%s] state updated scene=%s", self.session_id, correlation_id, result["scene"].get("id"))
                self.live_imagery.schedule(
                    result["scene"],
                    scene_update.get("action", "replace"),
                    previous_scene,
                    correlation_id,
                )
            except Exception:
                LOGGER.error("[%s][%s] state update rejected; state unchanged", self.session_id, correlation_id)
                result.update({"planned": False, "success": False, "reason": "Invalid scene update rejected.", **failure("state_manager", "Invalid scene update rejected")})
                result.update(accounting)
                return result
            state_snapshot = deepcopy(self.presentation_state)
            self._schedule_async_generation(scene_update["action"], state_snapshot, correlation_id)
            self._schedule_async_multimedia(state_snapshot, correlation_id)
            self._record_memory(scene_update, decision)
            result["generation"] = self.presentation_generator.status()
        result.update(accounting)
        return result

    def _schedule_async_generation(self, action: str, state_snapshot: dict, correlation_id: str) -> None:
        def run() -> None:
            try:
                self.presentation_generator.schedule_for_action(action, state_snapshot)
                LOGGER.info("[%s][%s] background generation scheduled action=%s", self.session_id, correlation_id, action)
            except Exception:
                LOGGER.exception("[%s][%s] background generation failed", self.session_id, correlation_id)

        Thread(target=run, daemon=True).start()

    def _scene_image_map_for_export(self, state: dict) -> dict[str, str]:
        return build_scene_image_map(state, self.session_id, self.live_imagery.scene_image_map())

    def _on_live_image_ready(self, scene_id: str, image_path: str) -> None:
        LOGGER.info("[%s] Gemini image ready for scene=%s — syncing PPTX visuals", self.session_id, scene_id)
        self._schedule_async_generation("sync_images", deepcopy(self.presentation_state), f"image-{scene_id}")

    def _schedule_async_multimedia(self, state_snapshot: dict, correlation_id: str) -> None:
        if not should_plan_multimedia(state_snapshot):
            return

        def run() -> None:
            try:
                self.multimedia_manager.schedule_after_state_commit(state_snapshot, correlation_id)
            except Exception:
                LOGGER.exception("[%s][%s] background multimedia failed", self.session_id, correlation_id)

        Thread(target=run, daemon=True).start()

    def _schedule_async_realtime_memory(self, scene_update: dict, correlation_id: str) -> None:
        def run() -> None:
            try:
                stage = scene_update.get("presentation_stage", "other")
                topic = scene_update.get("primary_idea", scene_update.get("title", ""))
                self.memory_manager.remember("current_topic", topic)
                self.memory_manager.remember("current_stage", stage)
                if scene_update.get("action") == "start_new_scene":
                    self.memory_manager.record_event("topic_change", topic, {"stage": stage})
                elif not self.memory_manager.retrieve("presentation_started"):
                    self.memory_manager.remember("presentation_started", True)
                    self.memory_manager.record_event("presentation_started", topic, {"stage": stage})
            except Exception:
                LOGGER.warning("[%s][%s] async realtime memory update failed", self.session_id, correlation_id)

        Thread(target=run, daemon=True).start()

    def _plan(
        self, approved_content: str, refinement_feedback: dict | None = None, relevant_memory: list[dict] | None = None, correlation_id: str = "-"
    ) -> dict:
        parameters = inspect.signature(self.planner).parameters
        keyword_arguments = {}
        if "refinement_feedback" in parameters:
            keyword_arguments["refinement_feedback"] = refinement_feedback
        if "relevant_memory" in parameters:
            keyword_arguments["relevant_memory"] = relevant_memory
        if "correlation_id" in parameters:
            keyword_arguments["correlation_id"] = correlation_id
        return self.planner(approved_content, self.presentation_state, **keyword_arguments)

    def _detect(self, latest_transcript: str, correlation_id: str):
        parameters = inspect.signature(self.semantic_detector.detect).parameters
        if "correlation_id" in parameters:
            return self.semantic_detector.detect(self.last_transcript, latest_transcript, correlation_id=correlation_id)
        return self.semantic_detector.detect(self.last_transcript, latest_transcript)

    def _review(self, scene_update: dict, context: dict, correlation_id: str):
        parameters = inspect.signature(self.critic.review).parameters
        if "correlation_id" in parameters:
            return self.critic.review(scene_update, context, correlation_id=correlation_id)
        return self.critic.review(scene_update, context)

    def _retrieve_memory(self, approved_content: str, correlation_id: str) -> list[dict]:
        try:
            self._sync_working_memory()
            self.memory_manager.remember_explicit_preference(approved_content)
            memory = self.memory_manager.get_relevant_memory(approved_content)
            LOGGER.info("[%s][%s] memory retrieved count=%s", self.session_id, correlation_id, len(memory))
            return memory
        except Exception:
            LOGGER.warning("[%s][%s] memory unavailable; continuing without memory", self.session_id, correlation_id)
            return []

    def _record_memory(self, scene_update: dict, detector_decision) -> None:
        stage = scene_update.get("presentation_stage", "other")
        topic = scene_update.get("primary_idea", scene_update.get("title", ""))
        self.memory_manager.remember("current_topic", topic)
        self.memory_manager.remember("current_stage", stage)
        goal = self.presentation_state.get("metadata", {}).get("presentation_goal")
        if goal:
            self.memory_manager.remember("presentation_goal", goal)

        if detector_decision.update_type == "topic_change" or scene_update["action"] == "start_new_scene":
            self.memory_manager.record_event("topic_change", topic, {"stage": stage})
        elif not self.memory_manager.retrieve("presentation_started"):
            self.memory_manager.remember("presentation_started", True)
            self.memory_manager.record_event("presentation_started", topic, {"stage": stage})

        try:
            candidate = self.memory_extractor.extract(
                detector_decision.approved_content, scene_update, detector_decision
            )
            self.memory_manager.store_candidate(candidate)
        except Exception as error:
            LOGGER.warning("[%s] memory extraction failed; presentation continues: %s", self.session_id, error)

    def _sync_working_memory(self) -> None:
        metadata = self.presentation_state.get("metadata", {})
        for key in ("presentation_goal", "audience", "presentation_stage"):
            if metadata.get(key):
                memory_key = "current_stage" if key == "presentation_stage" else key
                self.memory_manager.remember(memory_key, metadata[key])
