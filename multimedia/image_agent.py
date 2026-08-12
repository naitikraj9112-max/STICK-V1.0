"""Generate scene images via provider abstraction."""

import logging
from uuid import uuid4

from multimedia.models import MediaTaskResult
from multimedia.providers.base import ImageProvider
from multimedia.workspace import MediaWorkspace

LOGGER = logging.getLogger(__name__)


class ImageAgent:
    """Generates or skips images; never mutates presentation state."""

    def __init__(self, provider: ImageProvider | None, workspace: MediaWorkspace):
        self.provider = provider
        self.workspace = workspace

    def generate(self, scene_id: str, prompt: str, correlation_id: str = "-") -> MediaTaskResult:
        task_id = str(uuid4())
        if not prompt:
            return MediaTaskResult(
                task_id=task_id,
                scene_id=scene_id,
                task_type="image",
                status="skipped",
                metadata={"reason": "empty_prompt"},
            )
        if not self.provider or not self.provider.available:
            return MediaTaskResult(
                task_id=task_id,
                scene_id=scene_id,
                task_type="image",
                status="skipped",
                error="Image provider unavailable",
                metadata={"reason": "provider_unavailable"},
            )
        output = self.workspace.image_path(scene_id)
        try:
            result = self.provider.generate(prompt, output, correlation_id)
            return MediaTaskResult(
                task_id=task_id,
                scene_id=scene_id,
                task_type="image",
                status="success",
                path=result["path"],
                metadata=result,
            )
        except Exception as error:
            LOGGER.warning("[%s] image generation failed scene=%s: %s", correlation_id, scene_id, error)
            return MediaTaskResult(
                task_id=task_id,
                scene_id=scene_id,
                task_type="image",
                status="failure",
                error=str(error),
            )
