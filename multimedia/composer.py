"""Combine slide visuals, images, narration, and audio for video rendering."""

import json
import logging
import shutil
import subprocess
from pathlib import Path

from config import FFMPEG_PATH
from multimedia.models import MediaAsset, VideoTimeline
from multimedia.workspace import MediaWorkspace
from presentation_generator.slide_paths import resolve_scene_svg

LOGGER = logging.getLogger(__name__)


class VideoComposer:
    """Prepare a render manifest from timeline + assets."""

    def __init__(self, workspace: MediaWorkspace):
        self.workspace = workspace

    def compose(self, timeline: VideoTimeline, assets: list[MediaAsset], scenes: list[dict] | None = None) -> dict:
        self.workspace.ensure()
        scene_by_id = {scene["id"]: scene for scene in scenes or []}
        segments = []
        for item in timeline.items:
            scene = scene_by_id.get(item.scene_id, {"id": item.scene_id, "slide_index": 1})
            slide_path, slide_is_real = self.resolve_slide_asset(scene)
            if not slide_path and item.slide_asset and Path(item.slide_asset).is_file():
                slide_path = item.slide_asset
                slide_is_real = True
            visual = item.visual_asset or ""
            render_path = self._pick_render_path(slide_path, slide_is_real, visual, item.scene_id)
            segments.append(
                {
                    "scene_id": item.scene_id,
                    "duration": item.duration,
                    "slide": slide_path,
                    "visual": visual,
                    "render_path": render_path,
                    "audio": item.audio_asset,
                    "narration": item.narration_asset,
                    "transition": item.transition,
                }
            )
        manifest = {
            "session_id": timeline.session_id,
            "total_duration": timeline.total_duration,
            "segments": segments,
            "output": str(self.workspace.video_path),
        }
        self.workspace.compose_manifest_path.write_text(json.dumps(manifest, indent=2))
        return manifest

    def resolve_slide_asset(self, scene: dict) -> tuple[str, bool]:
        """Return PNG path for a scene and whether it came from a real PPT SVG."""
        svg = resolve_scene_svg(scene, self.workspace.ppt_master_svg_dir)
        if not svg:
            return "", False
        png = self.workspace.slide_path(scene["id"])
        if self._svg_to_png(svg, png):
            return str(png), True
        return "", False

    def _pick_render_path(self, slide_path: str, slide_is_real: bool, visual_asset: str, scene_id: str) -> str:
        if slide_is_real and slide_path and Path(slide_path).is_file():
            return slide_path
        if visual_asset and Path(visual_asset).is_file():
            return visual_asset
        fallback = self._render_fallback_slide(scene_id)
        if fallback:
            return fallback
        return slide_path or visual_asset

    def _svg_to_png(self, svg_path: Path, png_path: Path) -> bool:
        png_path.parent.mkdir(parents=True, exist_ok=True)
        for converter in (self._svg_to_png_qlmanage, self._svg_to_png_rsvg, self._svg_to_png_ffmpeg):
            if converter(svg_path, png_path):
                return png_path.is_file()
        try:
            from PIL import Image, ImageDraw

            img = Image.new("RGB", (1280, 720), color=(18, 24, 38))
            draw = ImageDraw.Draw(img)
            draw.rectangle([0, 0, 1280, 6], fill=(100, 201, 243))
            draw.text((64, 64), svg_path.stem, fill=(255, 255, 255))
            img.save(png_path)
            return png_path.is_file()
        except Exception:
            return False

    def _svg_to_png_qlmanage(self, svg_path: Path, png_path: Path) -> bool:
        if not shutil.which("qlmanage"):
            return False
        temp_dir = png_path.parent / ".svg_convert"
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["qlmanage", "-t", "-s", "1280", "-o", str(temp_dir), str(svg_path)],
                capture_output=True,
                check=True,
                timeout=30,
            )
            generated = temp_dir / f"{svg_path.name}.png"
            if generated.is_file():
                generated.replace(png_path)
                return True
        except (subprocess.SubprocessError, OSError):
            return False
        finally:
            for leftover in temp_dir.glob("*.png"):
                if leftover != png_path:
                    leftover.unlink(missing_ok=True)
        return False

    def _svg_to_png_rsvg(self, svg_path: Path, png_path: Path) -> bool:
        if not shutil.which("rsvg-convert"):
            return False
        try:
            subprocess.run(
                ["rsvg-convert", "-w", "1280", "-h", "720", "-o", str(png_path), str(svg_path)],
                capture_output=True,
                check=True,
                timeout=30,
            )
            return png_path.is_file()
        except (subprocess.SubprocessError, OSError):
            return False

    def _svg_to_png_ffmpeg(self, svg_path: Path, png_path: Path) -> bool:
        if not shutil.which(FFMPEG_PATH):
            return False
        try:
            subprocess.run(
                [FFMPEG_PATH, "-y", "-i", str(svg_path), "-frames:v", "1", str(png_path)],
                capture_output=True,
                check=True,
                timeout=30,
            )
            return png_path.is_file()
        except (subprocess.SubprocessError, OSError):
            return False

    def _render_fallback_slide(self, scene_id: str) -> str:
        try:
            from PIL import Image, ImageDraw

            png = self.workspace.slide_path(scene_id)
            png.parent.mkdir(parents=True, exist_ok=True)
            image = Image.new("RGB", (1280, 720), color=(11, 16, 32))
            draw = ImageDraw.Draw(image)
            draw.rectangle([0, 0, 1280, 4], fill=(100, 201, 243))
            draw.text((96, 320), scene_id[:48], fill=(255, 255, 255))
            image.save(png)
            return str(png)
        except ImportError:
            return ""
