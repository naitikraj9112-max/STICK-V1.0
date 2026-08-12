"""Deterministic multimedia orchestration tests (no real Gemini required)."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from execution_policy import should_generate_scene_image, should_plan_multimedia
from multimedia.image_agent import ImageAgent
from multimedia.manager import MultimediaManager
from multimedia.models import MediaAsset, SceneMediaPlan
from multimedia.narration_agent import NarrationAgent
from multimedia.planner import MultimediaPlanner
from multimedia.timeline import TimelineBuilder
from multimedia.tts_agent import TTSAgent
from multimedia.video_renderer import VideoRenderer
from multimedia.workspace import MediaWorkspace


class FakeImageProvider:
    available = True

    def __init__(self, fail_ids=None):
        self.fail_ids = set(fail_ids or [])
        self.calls = 0

    def generate(self, prompt, output_path, correlation_id="-"):
        self.calls += 1
        scene_id = Path(output_path).stem
        if scene_id in self.fail_ids:
            raise RuntimeError("image failed")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-image")
        return {"path": str(output_path), "mime_type": "image/jpeg", "bytes": 10}


class FakeTextProvider:
    available = True

    def generate(self, prompt, correlation_id="-"):
        return "This is a grounded narration for the slide."


class FakeTTSProvider:
    available = True

    def __init__(self, fail=False):
        self.fail = fail

    def synthesize(self, text, output_path, correlation_id="-"):
        if self.fail:
            raise RuntimeError("tts failed")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-audio")
        return {"path": str(output_path), "mime_type": "audio/wav", "bytes": 10}


def sample_state():
    return {
        "metadata": {"presentation_goal": "Explain Stick", "audience": "builders"},
        "completed_scenes": [
            {
                "id": "hero-1",
                "kind": "hero",
                "status": "completed",
                "presentation_stage": "introduction",
                "content": {"title": "Stick", "subtitle": "Live presentations", "primary_idea": "Voice becomes slides", "cards": [], "metrics": []},
            },
            {
                "id": "cards-1",
                "kind": "cards",
                "status": "completed",
                "presentation_stage": "solution",
                "content": {"title": "Features", "subtitle": "", "cards": ["Realtime", "PPT export"], "metrics": []},
            },
            {
                "id": "pipeline-1",
                "kind": "pipeline",
                "status": "completed",
                "presentation_stage": "architecture",
                "content": {"title": "Pipeline", "subtitle": "Voice to deck", "cards": ["Listen", "Plan", "Export"], "metrics": []},
            },
        ],
        "current_scene": {},
    }


def test_planner_skips_unnecessary_images():
    plan = MultimediaPlanner().plan("session", sample_state())
    by_id = {item.scene_id: item for item in plan.scenes}
    assert by_id["hero-1"].needs_image is True
    assert by_id["pipeline-1"].needs_image is False
    assert by_id["pipeline-1"].visual_role == "svg_diagram"
    assert by_id["cards-1"].needs_image is True
    print("planner visual roles ok")


def test_gemini_missing_degrades():
    manager = MultimediaManager(session_id=str(uuid4()))
    assert manager.last_result.status in {"idle", "unavailable"}
    print("gemini missing degrades ok")


def test_parallel_image_tasks():
    async def run():
        provider = FakeImageProvider()
        workspace = MediaWorkspace("parallel-test")
        agent = ImageAgent(provider, workspace)
        plans = [
            SceneMediaPlan(scene_id=f"scene-{index}", needs_image=True, image_prompt=f"prompt {index}")
            for index in range(5)
        ]
        semaphore = asyncio.Semaphore(4)
        results = []

        async def one(plan):
            async with semaphore:
                return await asyncio.to_thread(agent.generate, plan.scene_id, plan.image_prompt)

        results = await asyncio.gather(*(one(plan) for plan in plans))
        assert len(results) == 5
        assert provider.calls == 5
        assert all(result.status == "success" for result in results)

    asyncio.run(run())
    print("parallel image tasks ok")


def test_partial_image_failure():
    provider = FakeImageProvider(fail_ids={"bad-scene"})
    workspace = MediaWorkspace("partial-fail")
    agent = ImageAgent(provider, workspace)
    good = agent.generate("good-scene", "prompt", "-")
    bad = agent.generate("bad-scene", "prompt", "-")
    assert good.status == "success"
    assert bad.status == "failure"
    print("partial image failure ok")


def test_narration_fallback():
    agent = NarrationAgent(provider=None)
    plan = SceneMediaPlan(scene_id="hero-1", needs_narration=True)
    scene = sample_state()["completed_scenes"][0]
    result = agent.generate(plan, scene)
    assert result.status == "success"
    assert "Voice becomes slides" in result.metadata["text"]
    print("narration fallback ok")


def test_tts_failure():
    workspace = MediaWorkspace("tts-fail")
    agent = TTSAgent(FakeTTSProvider(fail=True), workspace)
    result = agent.synthesize("scene", "hello", "-")
    assert result.status == "failure"
    print("tts failure ok")


def test_timeline_creation():
    workspace = MediaWorkspace("timeline")
    builder = TimelineBuilder()
    plans = MultimediaPlanner().plan("timeline", sample_state()).scenes
    assets = [
        MediaAsset(
            asset_id="hero-1-narration", scene_id="hero-1", type="narration", path="", status="ready"
        )
    ]
    timeline = builder.build("timeline", plans, assets, workspace)
    assert timeline.total_duration > 0
    assert len(timeline.items) == 3
    print("timeline creation ok")


def test_video_renderer_unavailable():
    renderer = VideoRenderer(ffmpeg_path="__missing_ffmpeg__")
    result = renderer.render({"segments": []}, Path("out.mp4"))
    assert result.error_code == "VIDEO_RENDERER_UNAVAILABLE"
    print("video renderer unavailable ok")


def test_session_isolation():
    with TemporaryDirectory() as directory:
        artifact_dir = Path(directory)
        one = MultimediaManager(session_id="session-a", artifact_dir=artifact_dir)
        two = MultimediaManager(session_id="session-b", artifact_dir=artifact_dir)
        one.workspace.ensure()
        two.workspace.ensure()
        one.workspace.image_path("scene").write_bytes(b"a")
        two.workspace.image_path("scene").write_bytes(b"b")
        assert one.workspace.image_path("scene").read_bytes() == b"a"
        assert two.workspace.image_path("scene").read_bytes() == b"b"
    print("session isolation ok")


def test_execution_policy():
    assert should_plan_multimedia(sample_state()) is True
    assert should_generate_scene_image({"kind": "quote"}) is False
    assert should_generate_scene_image({"kind": "hero", "presentation_stage": "introduction"}) is True
    assert should_generate_scene_image({"kind": "pipeline", "presentation_stage": "architecture"}) is False
    print("execution policy ok")


def main():
    test_planner_skips_unnecessary_images()
    test_gemini_missing_degrades()
    test_parallel_image_tasks()
    test_partial_image_failure()
    test_narration_fallback()
    test_tts_failure()
    test_timeline_creation()
    test_video_renderer_unavailable()
    test_session_isolation()
    test_execution_policy()
    print("Multimedia demo passed.")


if __name__ == "__main__":
    main()
