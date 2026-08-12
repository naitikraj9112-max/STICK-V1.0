"""Structured models for multimedia planning, tasks, and video output."""

from typing import Any, Literal

from pydantic import BaseModel, Field

MediaTaskType = Literal["image", "narration", "tts", "metadata"]
MediaTaskStatus = Literal["pending", "running", "success", "failure", "skipped"]
VideoStatus = Literal[
    "idle",
    "planning",
    "generating_media",
    "synthesizing_audio",
    "composing",
    "rendering",
    "ready",
    "error",
    "unavailable",
]
VisualRole = Literal[
    "hero_visual",
    "supporting_visual",
    "diagram_background",
    "ambient_background",
    "svg_diagram",
    "none",
]


class SceneMediaPlan(BaseModel):
    scene_id: str
    needs_image: bool = False
    needs_narration: bool = True
    needs_tts: bool = True
    needs_video_motion: bool = True
    media_priority: int = 50
    image_prompt: str = ""
    narration_prompt: str = ""
    estimated_duration: float = 8.0
    visual_role: VisualRole = "none"


class MediaPlan(BaseModel):
    session_id: str
    scenes: list[SceneMediaPlan] = Field(default_factory=list)
    presentation_goal: str = ""
    audience: str = ""


class MediaTask(BaseModel):
    task_id: str
    session_id: str
    scene_id: str
    task_type: MediaTaskType
    status: MediaTaskStatus = "pending"
    priority: int = 50
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class MediaTaskResult(BaseModel):
    task_id: str
    scene_id: str
    task_type: MediaTaskType
    status: MediaTaskStatus
    path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class MediaAsset(BaseModel):
    asset_id: str
    scene_id: str
    type: Literal["image", "narration", "audio", "slide", "video"]
    path: str
    status: Literal["pending", "ready", "error", "skipped"] = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimelineItem(BaseModel):
    scene_id: str
    start_time: float
    end_time: float
    duration: float
    visual_asset: str = ""
    narration_asset: str = ""
    audio_asset: str = ""
    slide_asset: str = ""
    transition: str = "fade"
    animation: dict[str, Any] = Field(default_factory=dict)


class VideoTimeline(BaseModel):
    session_id: str
    items: list[TimelineItem] = Field(default_factory=list)
    total_duration: float = 0.0


class VideoGenerationResult(BaseModel):
    status: VideoStatus = "idle"
    message: str = ""
    artifact_path: str = ""
    error_code: str = ""
    timeline_path: str = ""
    media_assets: list[MediaAsset] = Field(default_factory=list)
