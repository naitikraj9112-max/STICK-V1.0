"""Non-blocking AI image generation for slide visuals."""

import logging
from threading import Lock, Thread

from config import CF_WORKER_URL, GEMINI_API_KEY, POLLINATIONS_API_KEY
from multimedia.image_agent import ImageAgent
from multimedia.providers.image_factory import configured_image_provider
from multimedia.workspace import MediaWorkspace

from presentation_generator.visual_strategy import resolve_visual_plan

LOGGER = logging.getLogger(__name__)

LIVE_IMAGE_KINDS = {"hero", "cards", "pipeline", "metric", "quote"}

ACCENT_DESCRIPTIONS = {
    "ember": "electric orange-red",
    "lime": "acid lime green",
    "sky": "clear cyan blue",
    "violet": "luminous violet",
}


class LiveImageryManager:
    """Non-blocking panel imagery for every slide; generations run in parallel and are never discarded."""

    def __init__(self, session_id: str, artifact_dir=None, on_image_ready=None):
        self.session_id = session_id
        self.workspace = MediaWorkspace(session_id, artifact_dir)
        self.image_agent = ImageAgent(configured_image_provider(), self.workspace)
        self._on_image_ready = on_image_ready
        self._lock = Lock()
        self._active_scene_id: str | None = None
        self._inflight: set[str] = set()
        self._paths: dict[str, str] = {}
        self._status: dict[str, str] = {}
        self._fingerprints: dict[str, str] = {}
        self._last_error: str | None = None

    def status_summary(self) -> dict:
        with self._lock:
            generating = any(status == "generating" for status in self._status.values())
            ready_count = sum(1 for status in self._status.values() if status == "ready")
            return {
                "gemini_configured": bool(GEMINI_API_KEY),
                "image_provider_configured": self.image_agent.provider.available if self.image_agent.provider else False,
                "image_provider": "pollinations" if POLLINATIONS_API_KEY else "cloudflare" if CF_WORKER_URL else "gemini" if GEMINI_API_KEY else "unavailable",
                "generating": generating,
                "ready_count": ready_count,
                "last_error": self._last_error,
                "active_scene_id": self._active_scene_id,
            }

    def set_on_image_ready(self, callback) -> None:
        self._on_image_ready = callback

    def schedule(self, scene: dict, director_action: str, previous_scene: dict | None, correlation_id: str = "-") -> None:
        if not self.image_agent.provider or not self.image_agent.provider.available:
            with self._lock:
                self._last_error = "No image provider configured"
            LOGGER.info("[%s] live imagery skipped — no image provider configured", correlation_id)
            return
        kind = scene.get("kind", "hero")
        if kind not in LIVE_IMAGE_KINDS:
            return
        content = scene.get("content") or {}
        if content.get("is_cover"):
            return

        scene_id = scene["id"]
        plan = resolve_visual_plan(scene)
        if not plan.needs_gemini_image:
            with self._lock:
                self._status[scene_id] = "skipped"
            LOGGER.info("[%s] live imagery skipped scene=%s strategy=%s", correlation_id, scene_id, plan.strategy)
            return

        fingerprint = self._content_fingerprint(scene)
        logical_update = director_action in {"focus", "merge_cards"} and previous_scene and previous_scene.get("id") == scene_id
        with self._lock:
            if logical_update and scene_id in self._paths and self._fingerprints.get(scene_id) == fingerprint:
                self._status[scene_id] = "ready"
                return
            if scene_id in self._inflight:
                self._active_scene_id = scene_id
                return
            self._active_scene_id = scene_id
            self._status[scene_id] = "generating"
            self._last_error = None
            self._inflight.add(scene_id)

        prompt = self._build_prompt(scene)

        def run() -> None:
            try:
                result = self.image_agent.generate(scene_id, prompt, correlation_id)
                image_path = None
                callback = None
                with self._lock:
                    self._inflight.discard(scene_id)
                    if result.status == "success" and result.path:
                        self._paths[scene_id] = result.path
                        self._fingerprints[scene_id] = fingerprint
                        self._status[scene_id] = "ready"
                        image_path = result.path
                        callback = self._on_image_ready
                    else:
                        self._status[scene_id] = "error"
                        self._last_error = result.error or "Image generation failed"
                if callback and image_path:
                    try:
                        callback(scene_id, image_path)
                    except Exception:
                        LOGGER.exception("[%s] live imagery ready callback failed scene=%s", correlation_id, scene_id)
            except Exception as error:
                LOGGER.exception("[%s] live imagery failed scene=%s", correlation_id, scene_id)
                with self._lock:
                    self._inflight.discard(scene_id)
                    self._status[scene_id] = "error"
                    self._last_error = str(error)

        Thread(target=run, daemon=True).start()

    def scene_image_map(self) -> dict[str, str]:
        with self._lock:
            return dict(self._paths)

    def scene_status_map(self) -> dict[str, str]:
        with self._lock:
            return dict(self._status)

    def _content_fingerprint(self, scene: dict) -> str:
        content = scene.get("content") or {}
        cards = content.get("card_items") or []
        card_sig = "|".join(f"{item.get('title', '')}:{item.get('body', '')}" for item in cards[:6])
        return f"{scene.get('kind', 'hero')}::{content.get('title', '')}::{content.get('subtitle', '')}::{card_sig}"

    def _build_prompt(self, scene: dict) -> str:
        content = scene.get("content") or {}
        plan = resolve_visual_plan(scene)
        accent = ACCENT_DESCRIPTIONS.get(content.get("accent", "sky"), "clear cyan blue")
        title = content.get("title", "")
        subtitle = content.get("subtitle", "")
        cards = content.get("card_items") or []
        card_summary = "; ".join(
            f"{item.get('title', '')}: {item.get('body', '')}".strip(": ")
            for item in cards[:4]
            if item.get("title")
        )
        context = subtitle
        if card_summary:
            context = f"{subtitle}. Key points: {card_summary}" if subtitle else f"Key points: {card_summary}"
        aspect_hint = {
            "square": "Square composition",
            "landscape": "Landscape composition",
            "wide": "Wide cinematic composition",
        }.get(plan.prompt_aspect, "Square composition")
        return (
            f"Create a photorealistic cinematic photograph for a presentation slide visual. "
            f"{aspect_hint}. "
            f"Topic: {title}. Context: {context}. "
            f"Lighting mood: {accent}. "
            "Natural lighting, realistic materials, depth of field, high detail. "
            "One clear subject that explains the topic. "
            "No text, no logos, no watermarks, no slide UI, no illustration style, no cartoon, no diagram."
        )
