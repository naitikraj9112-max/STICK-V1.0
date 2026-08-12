"""Generate grounded narration scripts for presentation scenes."""

import logging
from uuid import uuid4

from multimedia.models import MediaTaskResult, SceneMediaPlan
from multimedia.providers.base import TextProvider

LOGGER = logging.getLogger(__name__)


class NarrationAgent:
    """Produces presenter-style narration grounded in scene content."""

    def __init__(self, provider: TextProvider | None = None):
        self.provider = provider

    def generate(self, plan: SceneMediaPlan, scene: dict, correlation_id: str = "-") -> MediaTaskResult:
        task_id = str(uuid4())
        if not plan.needs_narration:
            return MediaTaskResult(task_id=task_id, scene_id=plan.scene_id, task_type="narration", status="skipped")
        try:
            if self.provider and self.provider.available:
                text = self.provider.generate(plan.narration_prompt, correlation_id)
            else:
                text = self._fallback_narration(scene)
            return MediaTaskResult(
                task_id=task_id,
                scene_id=plan.scene_id,
                task_type="narration",
                status="success",
                metadata={"text": text},
            )
        except Exception as error:
            LOGGER.warning("[%s] narration failed scene=%s: %s", correlation_id, plan.scene_id, error)
            text = self._fallback_narration(scene)
            return MediaTaskResult(
                task_id=task_id,
                scene_id=plan.scene_id,
                task_type="narration",
                status="success" if text else "failure",
                metadata={"text": text, "fallback": True},
                error=str(error) if not text else "",
            )

    def _fallback_narration(self, scene: dict) -> str:
        content = scene.get("content") or {}
        title = content.get("title", "").strip()
        subtitle = content.get("subtitle", "").strip()
        primary = content.get("primary_idea", "").strip()
        cards = content.get("cards") or []
        if primary:
            lead = primary
        elif subtitle:
            lead = subtitle
        elif title:
            lead = f"Let's look at {title}."
        else:
            return ""
        if cards:
            highlights = ", ".join(cards[:3])
            return f"{lead} The key points here are {highlights}."
        return lead
