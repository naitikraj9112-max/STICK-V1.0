"""Coordinate multimedia planning, parallel execution, and video rendering."""

import asyncio
import json
import logging
from copy import deepcopy
from threading import RLock, Thread
from uuid import uuid4

from config import GEMINI_API_KEY, MEDIA_MAX_CONCURRENCY, VIDEO_ENABLED
from multimedia.composer import VideoComposer
from multimedia.image_agent import ImageAgent
from multimedia.models import MediaAsset, MediaPlan, MediaTaskResult, VideoGenerationResult
from multimedia.narration_agent import NarrationAgent
from multimedia.planner import MultimediaPlanner
from multimedia.providers.gemini_image import GeminiImageProvider
from multimedia.providers.gemini_text import GeminiTextProvider
from multimedia.providers.gemini_tts import GeminiTTSProvider
from multimedia.timeline import TimelineBuilder
from multimedia.tts_agent import TTSAgent
from multimedia.video_renderer import VideoRenderer
from multimedia.workspace import MediaWorkspace
from presentation_generator.export_scene import enrich_scenes_for_export

LOGGER = logging.getLogger(__name__)


class MultimediaManager:
    """Owns media planning, task scheduling, asset aggregation, and video lifecycle."""

    def __init__(
        self,
        session_id: str,
        artifact_dir=None,
        image_provider=None,
        text_provider=None,
        tts_provider=None,
        renderer=None,
    ):
        self.session_id = session_id
        self.workspace = MediaWorkspace(session_id, artifact_dir)
        self.planner = MultimediaPlanner()
        self.image_agent = ImageAgent(image_provider or GeminiImageProvider(), self.workspace)
        self.narration_agent = NarrationAgent(text_provider or GeminiTextProvider())
        self.tts_agent = TTSAgent(tts_provider or GeminiTTSProvider(), self.workspace)
        self.timeline_builder = TimelineBuilder()
        self.composer = VideoComposer(self.workspace)
        self.renderer = renderer or VideoRenderer()
        self._lock = RLock()
        self._generating = False
        self._last_plan: MediaPlan | None = None
        self.last_result = VideoGenerationResult(
            status="unavailable" if not self.multimedia_enabled else "idle",
            message=self._capability_message(),
        )
        self.media_assets: list[MediaAsset] = []
        self._load_state()

    @property
    def multimedia_enabled(self) -> bool:
        return VIDEO_ENABLED

    @property
    def gemini_configured(self) -> bool:
        return bool(GEMINI_API_KEY)

    def _capability_message(self) -> str:
        if not VIDEO_ENABLED:
            return "Video generation is disabled."
        if not self.gemini_configured:
            return "Multimedia unavailable — configure GEMINI_API_KEY to enable image and TTS generation."
        return "Video generation ready."

    def schedule_after_state_commit(self, state_snapshot: dict, correlation_id: str = "-") -> None:
        """Non-blocking incremental media planning after presentation state commit."""
        if not self.multimedia_enabled:
            return

        def run() -> None:
            try:
                self._plan_and_generate_media(state_snapshot, correlation_id, video_render=False)
            except Exception:
                LOGGER.exception("[%s] async multimedia planning failed", correlation_id)

        Thread(target=run, daemon=True).start()

    def generate_video(self, state_snapshot: dict, correlation_id: str = "-") -> VideoGenerationResult:
        """Full video pipeline; failures do not affect PPTX."""
        with self._lock:
            if self._generating:
                return self.last_result.model_copy(
                    update={"message": "Video generation already in progress.", "status": self.last_result.status}
                )
            self._generating = True
        try:
            return self._plan_and_generate_media(state_snapshot, correlation_id, video_render=True)
        finally:
            with self._lock:
                self._generating = False

    def status(self) -> dict:
        with self._lock:
            payload = self.last_result.model_dump()
            payload["multimedia_enabled"] = self.multimedia_enabled
            payload["gemini_configured"] = self.gemini_configured
            payload["media_assets"] = [asset.model_dump() for asset in self.media_assets]
            payload["generating"] = self._generating
            return payload

    def _plan_and_generate_media(self, state_snapshot: dict, correlation_id: str, video_render: bool) -> VideoGenerationResult:
        if not self.multimedia_enabled:
            return self._set(VideoGenerationResult(status="unavailable", message="Video generation is disabled."))

        self.workspace.ensure()
        self._set(VideoGenerationResult(status="planning", message="Planning multimedia…"))
        plan = self.planner.plan(self.session_id, state_snapshot)
        self._last_plan = plan

        self._set(VideoGenerationResult(status="generating_media", message="Generating visuals and narration…"))
        task_results = asyncio.run(self._execute_media_tasks(plan, state_snapshot, correlation_id))
        assets = self._aggregate_assets(task_results, state_snapshot)
        self.media_assets = assets
        self._save_state()

        self._set(VideoGenerationResult(status="synthesizing_audio", message="Synthesizing narration audio…"))
        tts_results = asyncio.run(self._execute_tts_tasks(plan, task_results, correlation_id))
        assets = self._merge_assets(assets, tts_results)
        self.media_assets = assets
        self._save_state()

        if not video_render:
            message = "Media assets prepared." if self.gemini_configured else "Media plan saved (Gemini not configured)."
            return self._set(VideoGenerationResult(status="idle", message=message, media_assets=assets))

        self._set(VideoGenerationResult(status="composing", message="Composing video timeline…"))
        timeline = self.timeline_builder.build(self.session_id, plan.scenes, assets, self.workspace)
        scenes = enrich_scenes_for_export(state_snapshot)
        manifest = self.composer.compose(timeline, assets, scenes)

        self._set(VideoGenerationResult(status="rendering", message="Rendering video…"))
        render_result = self.renderer.render(manifest, self.workspace.video_path, correlation_id)
        render_result.media_assets = assets
        render_result.timeline_path = str(self.workspace.timeline_path)
        if render_result.status == "ready":
            render_result.message = f"Video ready · {len(timeline.items)} scenes"
        return self._set(render_result)

    async def _execute_media_tasks(self, plan: MediaPlan, state: dict, correlation_id: str) -> list[MediaTaskResult]:
        scenes = {scene["id"]: scene for scene in enrich_scenes_for_export(state)}
        semaphore = asyncio.Semaphore(MEDIA_MAX_CONCURRENCY)
        results: list[MediaTaskResult] = []

        async def run_scene(scene_plan):
            async with semaphore:
                scene = scenes.get(scene_plan.scene_id, {"id": scene_plan.scene_id, "content": {}})
                image_task = asyncio.create_task(
                    asyncio.to_thread(
                        self.image_agent.generate,
                        scene_plan.scene_id,
                        scene_plan.image_prompt if scene_plan.needs_image else "",
                        correlation_id,
                    )
                )
                narration_task = asyncio.create_task(
                    asyncio.to_thread(self.narration_agent.generate, scene_plan, scene, correlation_id)
                )
                image_result, narration_result = await asyncio.gather(image_task, narration_task)
                if narration_result.status == "success":
                    text = narration_result.metadata.get("text", "")
                    narration_path = self.workspace.narration_path(scene_plan.scene_id)
                    narration_path.write_text(text)
                    narration_result.path = str(narration_path)
                return [image_result, narration_result]

        gathered = await asyncio.gather(*(run_scene(scene_plan) for scene_plan in plan.scenes))
        for pair in gathered:
            results.extend(pair)
        return results

    async def _execute_tts_tasks(
        self, plan: MediaPlan, prior_results: list[MediaTaskResult], correlation_id: str
    ) -> list[MediaTaskResult]:
        narration_by_scene = {
            result.scene_id: result.metadata.get("text", "")
            for result in prior_results
            if result.task_type == "narration" and result.status == "success"
        }
        semaphore = asyncio.Semaphore(MEDIA_MAX_CONCURRENCY)
        results: list[MediaTaskResult] = []

        async def run_tts(scene_plan):
            if not scene_plan.needs_tts:
                return MediaTaskResult(
                    task_id=str(uuid4()),
                    scene_id=scene_plan.scene_id,
                    task_type="tts",
                    status="skipped",
                )
            async with semaphore:
                text = narration_by_scene.get(scene_plan.scene_id, "")
                return await asyncio.to_thread(
                    self.tts_agent.synthesize, scene_plan.scene_id, text, correlation_id
                )

        results = await asyncio.gather(*(run_tts(scene_plan) for scene_plan in plan.scenes))
        return list(results)

    def _aggregate_assets(self, task_results: list[MediaTaskResult], state: dict) -> list[MediaAsset]:
        assets: list[MediaAsset] = []
        scenes = enrich_scenes_for_export(state)
        scene_ids = {scene["id"] for scene in scenes}
        for result in task_results:
            if result.scene_id not in scene_ids:
                continue
            asset_type = "narration" if result.task_type == "narration" else result.task_type
            if result.task_type == "image":
                asset_type = "image"
            status = "ready" if result.status == "success" else ("skipped" if result.status == "skipped" else "error")
            assets.append(
                MediaAsset(
                    asset_id=f"{result.scene_id}-{result.task_type}",
                    scene_id=result.scene_id,
                    type=asset_type,  # type: ignore[arg-type]
                    path=result.path,
                    status=status,
                    metadata=result.metadata,
                )
            )
        for scene in scenes:
            slide_path, slide_is_real = self.composer.resolve_slide_asset(scene)
            if slide_path:
                assets.append(
                    MediaAsset(
                        asset_id=f"{scene['id']}-slide",
                        scene_id=scene["id"],
                        type="slide",
                        path=slide_path,
                        status="ready",
                        metadata={"from_ppt": slide_is_real},
                    )
                )
        return assets

    def scene_image_map(self) -> dict[str, str]:
        """Ready Gemini image paths keyed by scene id."""
        result: dict[str, str] = {}
        for asset in self.media_assets:
            if asset.type == "image" and asset.status == "ready" and asset.path:
                result[asset.scene_id] = asset.path
        return result

    def _merge_assets(self, assets: list[MediaAsset], tts_results: list[MediaTaskResult]) -> list[MediaAsset]:
        merged = [asset for asset in assets if asset.type != "audio"]
        for result in tts_results:
            status = "ready" if result.status == "success" else ("skipped" if result.status == "skipped" else "error")
            merged.append(
                MediaAsset(
                    asset_id=f"{result.scene_id}-audio",
                    scene_id=result.scene_id,
                    type="audio",
                    path=result.path,
                    status=status,
                    metadata=result.metadata,
                )
            )
        return merged

    def _set(self, result: VideoGenerationResult) -> VideoGenerationResult:
        with self._lock:
            if result.media_assets:
                self.media_assets = result.media_assets
            self.last_result = result
            self._save_state()
            return result

    def _save_state(self) -> None:
        self.workspace.ensure()
        payload = {
            "session_id": self.session_id,
            "video_status": self.last_result.status,
            "message": self.last_result.message,
            "artifact_path": self.last_result.artifact_path,
            "error_code": self.last_result.error_code,
            "media_assets": [asset.model_dump() for asset in self.media_assets],
        }
        self.workspace.state_path.write_text(json.dumps(payload, indent=2))

    def _load_state(self) -> None:
        if not self.workspace.state_path.is_file():
            return
        try:
            payload = json.loads(self.workspace.state_path.read_text())
            self.media_assets = [MediaAsset.model_validate(item) for item in payload.get("media_assets", [])]
            self.last_result = VideoGenerationResult(
                status=payload.get("video_status", "idle"),
                message=payload.get("message", ""),
                artifact_path=payload.get("artifact_path", ""),
                error_code=payload.get("error_code", ""),
                media_assets=self.media_assets,
            )
        except (json.JSONDecodeError, ValueError):
            LOGGER.warning("[%s] could not load media state", self.session_id)
