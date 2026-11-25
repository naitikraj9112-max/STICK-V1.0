"""End-to-end video pipeline tests with fakes and optional real FFmpeg."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from multimedia.composer import VideoComposer
from multimedia.manager import MultimediaManager
from multimedia.models import MediaAsset, TimelineItem, VideoTimeline
from multimedia.timeline import TimelineBuilder
from multimedia.video_renderer import VideoRenderer
from multimedia.workspace import MediaWorkspace
from presentation_generator import PresentationGenerator


class FakeImageProvider:
    available = True

    def generate(self, prompt, output_path, correlation_id="-"):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import Image

            Image.new("RGB", (1280, 720), color=(20, 30, 60)).save(output_path.with_suffix(".png"))
            path = output_path.with_suffix(".png")
        except ImportError:
            path = output_path.with_suffix(".jpg")
            path.write_bytes(b"\xff\xd8\xff\xd9")
        return {"path": str(path), "mime_type": "image/jpeg", "bytes": 10}


class FakeTextProvider:
    available = True

    def generate(self, prompt, correlation_id="-"):
        return "This slide explains the architecture in plain language for the audience."


class FakeTTSProvider:
    available = True

    def synthesize(self, text, output_path, correlation_id="-"):
        output_path = output_path.with_suffix(".wav")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        import wave

        with wave.open(str(output_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24000)
            handle.writeframes(b"\x00\x00" * 24000)
        return {"path": str(output_path), "mime_type": "audio/wav", "bytes": 100}


class FakePptMaster:
    available = True

    def write_scene_svg(self, scene, workspace, filename=None, scene_images=None):
        output = workspace / "svg_output"
        output.mkdir(parents=True, exist_ok=True)
        from presentation_generator.svg_templates import _slide_filename, build_scene_svg

        path = output / (filename or _slide_filename(scene.get("slide_index", 1), scene))
        path.write_text(build_scene_svg(scene))

    def write_all_scenes(self, scenes, workspace):
        output = workspace / "svg_output"
        output.mkdir(parents=True, exist_ok=True)
        for scene in scenes:
            self.write_scene_svg(scene, workspace)

    def validate(self, _workspace):
        return []

    def export(self, workspace):
        path = workspace / "exports" / "deck.pptx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"pptx")
        return path


def sample_state():
    return {
        "metadata": {"presentation_goal": "Demo video", "audience": "team"},
        "completed_scenes": [
            {
                "id": "intro",
                "kind": "hero",
                "status": "completed",
                "presentation_stage": "introduction",
                "content": {"title": "Intro", "subtitle": "Welcome", "primary_idea": "Welcome everyone", "cards": [], "metrics": []},
            },
            {
                "id": "solution",
                "kind": "cards",
                "status": "completed",
                "presentation_stage": "solution",
                "content": {"title": "Solution", "subtitle": "", "cards": ["Fast", "Reliable"], "metrics": []},
            },
        ],
        "current_scene": {},
    }


from unittest.mock import patch


def test_pptx_independent_when_video_fails():
    with patch("multimedia.manager.VIDEO_ENABLED", True):
        with TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            session_id = str(uuid4())
            ppt = PresentationGenerator(adapter=FakePptMaster(), artifact_dir=artifact_dir, session_id=session_id)
            ppt_result = ppt.generate_for_action("replace", sample_state())
            assert ppt_result.status == "ready"

            manager = MultimediaManager(
                session_id=session_id,
                artifact_dir=artifact_dir,
                image_provider=FakeImageProvider(),
                text_provider=FakeTextProvider(),
                tts_provider=FakeTTSProvider(),
                renderer=VideoRenderer(ffmpeg_path="__missing__"),
            )
            video_result = manager.generate_video(sample_state())
            assert video_result.status == "error"
            assert ppt.status()["status"] == "ready"
            assert Path(ppt.status()["artifact_path"]).is_file()
    print("pptx remains when video fails ok")


def test_duplicate_generation_request():
    with patch("multimedia.manager.VIDEO_ENABLED", True):
        with TemporaryDirectory() as directory:
            manager = MultimediaManager(
                session_id=str(uuid4()),
                artifact_dir=Path(directory),
                image_provider=FakeImageProvider(),
                text_provider=FakeTextProvider(),
                tts_provider=FakeTTSProvider(),
                renderer=VideoRenderer(ffmpeg_path="__missing__"),
            )
            manager._generating = True
            second = manager.generate_video(sample_state())
            assert "already in progress" in second.message.lower() or second.status != "planning"
    print("duplicate generation request ok")


def test_real_ffmpeg_if_available():
    if not shutil.which("ffmpeg"):
        print("Real FFmpeg render skipped: ffmpeg not installed")
        return
    with TemporaryDirectory() as directory:
        workspace = MediaWorkspace(str(uuid4()), Path(directory))
        workspace.ensure()
        slide = workspace.slide_path("intro", "png")
        from PIL import Image

        Image.new("RGB", (1280, 720), color=(12, 18, 40)).save(slide)
        audio = workspace.audio_path("intro", "wav")
        import wave

        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24000)
            handle.writeframes(b"\x00\x00" * 48000)
        timeline = VideoTimeline(
            session_id=workspace.session_id,
            items=[
                TimelineItem(
                    scene_id="intro",
                    start_time=0,
                    end_time=2,
                    duration=2,
                    slide_asset=str(slide),
                    audio_asset=str(audio),
                )
            ],
            total_duration=2,
        )
        composer = VideoComposer(workspace)
        manifest = composer.compose(timeline, [])
        renderer = VideoRenderer()
        result = renderer.render(manifest, workspace.video_path)
        assert result.status == "ready"
        assert Path(result.artifact_path).is_file()
        assert Path(result.artifact_path).stat().st_size > 1000
    print("real ffmpeg render ok")


def main():
    test_pptx_independent_when_video_fails()
    test_duplicate_generation_request()
    test_real_ffmpeg_if_available()
    print("Video pipeline demo passed.")


if __name__ == "__main__":
    main()
