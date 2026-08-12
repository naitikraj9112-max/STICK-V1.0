"""Render final MP4 using FFmpeg."""

import logging
import shutil
import subprocess
from pathlib import Path

from config import FFMPEG_PATH, VIDEO_OUTPUT_FORMAT
from multimedia.models import VideoGenerationResult

LOGGER = logging.getLogger(__name__)


class VideoRenderer:
    """Production local renderer; returns structured failure when FFmpeg is unavailable."""

    def __init__(self, ffmpeg_path: str = FFMPEG_PATH):
        self.ffmpeg_path = ffmpeg_path

    @property
    def available(self) -> bool:
        return bool(shutil.which(self.ffmpeg_path))

    def render(self, manifest: dict, output_path: Path, correlation_id: str = "-") -> VideoGenerationResult:
        if not self.available:
            return VideoGenerationResult(
                status="error",
                message="FFmpeg is not available on this system.",
                error_code="VIDEO_RENDERER_UNAVAILABLE",
            )
        segments = manifest.get("segments") or []
        if not segments:
            return VideoGenerationResult(
                status="error",
                message="No timeline segments to render.",
                error_code="EMPTY_TIMELINE",
            )
        output_path = Path(output_path)
        if VIDEO_OUTPUT_FORMAT != "mp4":
            output_path = output_path.with_suffix(f".{VIDEO_OUTPUT_FORMAT}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = output_path.parent / "video"
        work_dir.mkdir(parents=True, exist_ok=True)

        segment_files: list[Path] = []
        try:
            for index, segment in enumerate(segments):
                segment_path = work_dir / f"segment_{index:03d}.mp4"
                self._render_segment(segment, segment_path, correlation_id)
                segment_files.append(segment_path)
            self._concat_segments(segment_files, output_path, correlation_id)
            return VideoGenerationResult(
                status="ready",
                message=f"Video rendered · {len(segments)} scenes",
                artifact_path=str(output_path),
            )
        except Exception as error:
            LOGGER.exception("[%s] video render failed", correlation_id)
            return VideoGenerationResult(
                status="error",
                message=str(error),
                error_code="VIDEO_RENDER_FAILED",
            )

    def _render_segment(self, segment: dict, output: Path, correlation_id: str) -> None:
        duration = float(segment.get("duration") or 6.0)
        slide = segment.get("render_path") or segment.get("slide") or segment.get("visual") or ""
        audio = segment.get("audio") or ""
        if not slide or not Path(slide).is_file():
            raise RuntimeError(f"No visual for scene {segment.get('scene_id')}")

        command = [
            self.ffmpeg_path,
            "-y",
            "-loop",
            "1",
            "-t",
            str(duration),
            "-i",
            slide,
        ]
        if audio and Path(audio).is_file():
            command.extend(["-i", audio, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)])
        else:
            command.extend(
                [
                    "-vf",
                    "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-an",
                    str(output),
                ]
            )
        subprocess.run(command, capture_output=True, check=True, timeout=120)

    def _concat_segments(self, segments: list[Path], output: Path, correlation_id: str) -> None:
        concat_file = output.parent / "video" / "concat.txt"
        concat_file.write_text("\n".join(f"file '{path.resolve()}'" for path in segments))
        subprocess.run(
            [
                self.ffmpeg_path,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(output),
            ],
            capture_output=True,
            check=True,
            timeout=180,
        )
        LOGGER.info("[%s] video concat complete path=%s segments=%s", correlation_id, output, len(segments))
