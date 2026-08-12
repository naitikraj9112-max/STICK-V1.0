"""Tests for slide path resolution used by video composition."""

from pathlib import Path
from tempfile import TemporaryDirectory

from multimedia.composer import VideoComposer
from multimedia.workspace import MediaWorkspace
from presentation_generator.export_scene import enrich_scenes_for_export
from presentation_generator.slide_paths import expected_svg_path, resolve_scene_svg
from presentation_generator.svg_templates import _slide_filename, build_scene_svg


class FakeAdapter:
    available = True

    def write_all_scenes(self, scenes, workspace):
        output = workspace / "svg_output"
        output.mkdir(parents=True, exist_ok=True)
        for scene in scenes:
            path = output / _slide_filename(scene["slide_index"], scene)
            path.write_text(build_scene_svg(scene))


def sample_state():
    return {
        "metadata": {"presentation_stage": "introduction"},
        "completed_scenes": [
            {
                "id": "uuid-hero-abc",
                "kind": "hero",
                "status": "completed",
                "presentation_stage": "introduction",
                "content": {"title": "Intro", "subtitle": "Welcome", "cards": [], "metrics": []},
            },
            {
                "id": "uuid-cards-def",
                "kind": "cards",
                "status": "completed",
                "presentation_stage": "solution",
                "content": {"title": "Solution", "subtitle": "", "cards": ["Fast", "Reliable"], "metrics": []},
            },
        ],
        "current_scene": {},
    }


def test_resolve_by_structured_filename():
    with TemporaryDirectory() as directory:
        workspace = Path(directory) / "ppt_master"
        FakeAdapter().write_all_scenes(enrich_scenes_for_export(sample_state()), workspace)
        scenes = enrich_scenes_for_export(sample_state())
        first = resolve_scene_svg(scenes[0], workspace / "svg_output")
        assert first == expected_svg_path(scenes[0], workspace / "svg_output")
        assert "uuid-hero-abc" not in first.name
        print("structured filename resolution ok")


def test_composer_prefers_ppt_over_fallback():
    with TemporaryDirectory() as directory:
        session_id = "slide-resolve-test"
        media_workspace = MediaWorkspace(session_id, Path(directory))
        ppt_dir = media_workspace.ppt_master_svg_dir
        FakeAdapter().write_all_scenes(enrich_scenes_for_export(sample_state()), ppt_dir.parent)
        composer = VideoComposer(media_workspace)
        scenes = enrich_scenes_for_export(sample_state())
        slide_path, is_real = composer.resolve_slide_asset(scenes[0])
        assert is_real
        assert slide_path.endswith(".png")
        print("composer ppt resolution ok")


def main():
    test_resolve_by_structured_filename()
    test_composer_prefers_ppt_over_fallback()
    print("Slide path demo passed.")


if __name__ == "__main__":
    main()
