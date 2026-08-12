"""Convert narration scripts into audio via provider abstraction."""

import logging
from uuid import uuid4

from multimedia.models import MediaTaskResult
from multimedia.providers.base import TTSProvider
from multimedia.workspace import MediaWorkspace

LOGGER = logging.getLogger(__name__)


class TTSAgent:
    """Synthesizes narration audio; never mutates presentation state."""

    def __init__(self, provider: TTSProvider | None, workspace: MediaWorkspace):
        self.provider = provider
        self.workspace = workspace

    def synthesize(self, scene_id: str, text: str, correlation_id: str = "-") -> MediaTaskResult:
        task_id = str(uuid4())
        if not text.strip():
            return MediaTaskResult(task_id=task_id, scene_id=scene_id, task_type="tts", status="skipped")
        if not self.provider or not self.provider.available:
            return MediaTaskResult(
                task_id=task_id,
                scene_id=scene_id,
                task_type="tts",
                status="skipped",
                error="TTS provider unavailable",
                metadata={"reason": "provider_unavailable"},
            )
        output = self.workspace.audio_path(scene_id)
        try:
            result = self.provider.synthesize(text, output, correlation_id)
            return MediaTaskResult(
                task_id=task_id,
                scene_id=scene_id,
                task_type="tts",
                status="success",
                path=result["path"],
                metadata=result,
            )
        except Exception as error:
            LOGGER.warning("[%s] tts failed scene=%s: %s", correlation_id, scene_id, error)
            return MediaTaskResult(
                task_id=task_id,
                scene_id=scene_id,
                task_type="tts",
                status="failure",
                error=str(error),
            )
