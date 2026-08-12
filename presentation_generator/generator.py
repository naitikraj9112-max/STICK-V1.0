"""Generate only the affected slide artifact after state has already been committed."""

import logging
import shutil
from pathlib import Path
from threading import Lock, Timer

from config import GENERATION_DEBOUNCE_SECONDS, GENERATION_MAX_CORRECTIONS, PPT_MASTER_ROOT, PPT_MASTER_WORKSPACE, PRESENTATION_ARTIFACT_DIR
from presentation_generator.export_scene import compact_scene_for_retry, enrich_scenes_for_export
from presentation_generator.models import GenerationResult, visual_strategy
from presentation_generator.ppt_master_adapter import PptMasterAdapter, prepare_session_workspace
from presentation_generator.scene_images import build_scene_image_map
from presentation_generator.svg_templates import _slide_filename

LOGGER = logging.getLogger(__name__)


class PresentationGenerator:
    """Downstream design/generation layer; it reads state but never writes it."""

    def __init__(self, adapter=None, artifact_dir: str | Path | None = None, session_id: str | None = None, scene_image_resolver=None):
        self.session_id = session_id
        self.artifact_dir = Path(artifact_dir or PRESENTATION_ARTIFACT_DIR)
        self.session_artifact_dir = self.artifact_dir / session_id if session_id else self.artifact_dir
        self.session_workspace = self.session_artifact_dir / "ppt_master"
        self.scene_image_resolver = scene_image_resolver
        if adapter is not None:
            self.adapter = adapter
        elif PPT_MASTER_ROOT:
            workspace = str(self.session_workspace) if session_id else PPT_MASTER_WORKSPACE
            self.adapter = PptMasterAdapter(PPT_MASTER_ROOT, workspace)
        else:
            self.adapter = None
        self.last_result = GenerationResult(status="idle")
        self._debounce_lock = Lock()
        self._debounce_timer: Timer | None = None
        self._pending_action: str | None = None
        self._pending_state: dict | None = None

    def schedule_for_action(self, action: str, state: dict) -> None:
        """Debounce rapid merge/focus updates before exporting PPTX."""
        with self._debounce_lock:
            self._pending_action = action
            self._pending_state = state
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = Timer(GENERATION_DEBOUNCE_SECONDS, self._run_pending)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _run_pending(self) -> None:
        with self._debounce_lock:
            action = self._pending_action
            state = self._pending_state
            self._pending_action = None
            self._pending_state = None
        if action and state:
            self.generate_for_action(action, state)

    def generate_for_action(self, action: str, state: dict) -> GenerationResult:
        scenes = enrich_scenes_for_export(state)
        if not scenes:
            return self._set(GenerationResult(status="idle", message="No scene requires generation."))
        scene = scenes[-1]
        if not self.adapter or not self.adapter.available:
            return self._set(GenerationResult(status="unavailable", scene_id=scene.get("id"), message="PPT Master is not configured."))
        previous = self.last_result
        log_prefix = f"[{self.session_id}]" if self.session_id else "[generation]"
        try:
            adapter_workspace = getattr(self.adapter, "workspace", None)
            workspace = Path(adapter_workspace) if adapter_workspace else self.session_workspace
            if self.session_id:
                workspace = prepare_session_workspace(workspace)
            else:
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "validation").mkdir(parents=True, exist_ok=True)
            LOGGER.info("%s generation started scenes=%s action=%s stage=%s", log_prefix, len(scenes), action, scene.get("presentation_stage"))
            self._set(GenerationResult(
                status="generating",
                scene_id=scene["id"],
                message=f"Building {visual_strategy(scene)} for {scene.get('presentation_stage', 'slide')}…",
            ))
            self._write_scenes(action, scenes, workspace, self._resolve_scene_images(state))
            self._set(GenerationResult(status="validating", scene_id=scene["id"], message="Validating structured SVG pages…"))
            issues = self.adapter.validate(workspace)
            corrected = False
            if issues and GENERATION_MAX_CORRECTIONS:
                LOGGER.info("%s applying structured correction pass issues=%s", log_prefix, len(issues))
                corrected_scenes = [compact_scene_for_retry(item) for item in scenes]
                self.adapter.write_all_scenes(corrected_scenes, workspace)
                issues = self.adapter.validate(workspace)
                corrected = True
            if issues:
                LOGGER.warning("%s generation failed validation scene=%s issues=%s", log_prefix, scene.get("id"), issues[:3])
                return self._set(GenerationResult(
                    status="error",
                    scene_id=scene["id"],
                    message="Generated slide did not pass structured quality validation.",
                    quality_issues=issues,
                    artifact_path=previous.artifact_path,
                ))
            artifact = self.adapter.export(workspace)
            self.session_artifact_dir.mkdir(parents=True, exist_ok=True)
            final = self.session_artifact_dir / "presentation.pptx"
            shutil.copy2(artifact, final)
            LOGGER.info("%s generation completed artifact=%s slides=%s corrected=%s", log_prefix, final, len(scenes), corrected)
            return self._set(GenerationResult(
                status="ready",
                scene_id=scene["id"],
                artifact_path=str(final),
                corrected=corrected,
                message=f"Deck synced · {len(scenes)} slide{'s' if len(scenes) != 1 else ''} exported",
            ))
        except Exception:
            LOGGER.exception("%s generation failed; existing presentation artifact remains usable", log_prefix)
            return self._set(GenerationResult(
                status="error",
                scene_id=scene.get("id"),
                message="Presentation generation failed; previous artifact remains available.",
                artifact_path=previous.artifact_path,
            ))

    def _resolve_scene_images(self, state: dict) -> dict[str, str]:
        if self.scene_image_resolver:
            return self.scene_image_resolver(state) or {}
        if self.session_id:
            return build_scene_image_map(state, session_id=self.session_id)
        return {}

    def _write_scenes(self, action: str, scenes: list[dict], workspace: Path, scene_images: dict[str, str] | None = None) -> None:
        images = scene_images or {}
        if self._should_incremental(action, scenes):
            target = scenes[-1]
            filename = _slide_filename(target["slide_index"], target)
            self.adapter.write_scene_svg(target, workspace, filename=filename, scene_images=images)
            return
        self.adapter.write_all_scenes(scenes, workspace, scene_images=images)

    @staticmethod
    def _should_incremental(action: str, scenes: list[dict]) -> bool:
        if action == "sync_images":
            return False
        return action in {"merge", "replace"} and bool(scenes)

    def status(self) -> dict:
        return self.last_result.model_dump()

    def _set(self, result: GenerationResult) -> GenerationResult:
        self.last_result = result
        return result
