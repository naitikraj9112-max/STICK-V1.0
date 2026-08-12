"""Session-scoped media workspace paths."""

from pathlib import Path

from config import PRESENTATION_ARTIFACT_DIR, VIDEO_OUTPUT_FORMAT


class MediaWorkspace:
    """Filesystem layout for one session's multimedia artifacts."""

    def __init__(self, session_id: str, artifact_dir: Path | None = None):
        self.session_id = session_id
        root = Path(artifact_dir or PRESENTATION_ARTIFACT_DIR) / session_id
        self.presentation_dir = root
        self.media_dir = root / "media"
        self.images_dir = self.media_dir / "images"
        self.narration_dir = self.media_dir / "narration"
        self.audio_dir = self.media_dir / "audio"
        self.video_dir = self.media_dir / "video"
        self.slides_dir = self.media_dir / "slides"
        self.state_path = self.media_dir / "media_state.json"
        self.compose_manifest_path = self.media_dir / "compose_manifest.json"
        self.timeline_path = self.media_dir / "timeline.json"
        self.video_path = root / f"presentation.{VIDEO_OUTPUT_FORMAT}"
        self.pptx_path = root / "presentation.pptx"
        self.ppt_master_svg_dir = root / "ppt_master" / "svg_output"

    def ensure(self) -> None:
        for folder in (
            self.media_dir,
            self.images_dir,
            self.narration_dir,
            self.audio_dir,
            self.video_dir,
            self.slides_dir,
        ):
            folder.mkdir(parents=True, exist_ok=True)

    def image_path(self, scene_id: str, extension: str = "jpg") -> Path:
        safe = scene_id.replace("/", "_").replace(":", "_")
        return self.images_dir / f"{safe}.{extension}"

    def narration_path(self, scene_id: str) -> Path:
        safe = scene_id.replace("/", "_").replace(":", "_")
        return self.narration_dir / f"{safe}.txt"

    def audio_path(self, scene_id: str, extension: str = "wav") -> Path:
        safe = scene_id.replace("/", "_").replace(":", "_")
        return self.audio_dir / f"{safe}.{extension}"

    def slide_path(self, scene_id: str, extension: str = "png") -> Path:
        safe = scene_id.replace("/", "_").replace(":", "_")
        return self.slides_dir / f"{safe}.{extension}"
