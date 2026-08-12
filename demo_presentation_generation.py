"""No-network checks for the downstream PPT Master generation boundary."""

from pathlib import Path
from tempfile import TemporaryDirectory

from presentation_generator import PresentationGenerator


def scene(kind, action="replace", stage="other"):
    return {"id": f"{kind}-{stage}", "kind": kind, "status": "editing", "content": {"title": kind.title(), "subtitle": "", "cards": ["One", "Two", "Three", "Four"], "metrics": [], "primary_idea": kind}, "presentation_stage": stage, "action": action}


class FakePptMaster:
    available = True
    def __init__(self, fail=False, quality_once=False): self.fail, self.quality_once, self.calls, self.last_scene_count = fail, quality_once, 0, 0
    def write_scene_svg(self, _scene, workspace, filename=None, scene_images=None):
        path = workspace / "svg_output" / (filename or "slide.svg"); path.parent.mkdir(parents=True, exist_ok=True); path.write_text("<svg/>"); return path
    def write_all_scenes(self, scenes, workspace, scene_images=None):
        self.last_scene_count = len(scenes)
        for scene in scenes:
            self.write_scene_svg(scene, workspace, f"{scene['id']}.svg")
    def validate(self, _workspace):
        self.calls += 1
        return ["dense"] if self.quality_once and self.calls == 1 else []
    def export(self, workspace):
        if self.fail: raise RuntimeError("export failed")
        path = workspace / "exports" / "slide.pptx"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"pptx"); return path


def main():
    with TemporaryDirectory() as directory:
        generator = PresentationGenerator(adapter=FakePptMaster(quality_once=True), artifact_dir=directory)
        for kind in ("hero", "cards", "pipeline", "metric", "quote"):
            result = generator.generate_for_action("replace", {"current_scene": scene(kind), "completed_scenes": []})
            assert result.status == "ready" and Path(result.artifact_path).is_file()
        architecture = generator.generate_for_action("start_new_scene", {"current_scene": scene("cards", stage="architecture"), "completed_scenes": [scene("hero")]})
        assert architecture.status == "ready"
        assert generator.adapter.last_scene_count == 2
        complete = generator.generate_for_action("complete_scene", {"current_scene": {}, "completed_scenes": [scene("pipeline", "complete_scene")]})
        assert complete.status == "ready"
        previous = generator.status()["artifact_path"]
        failed = PresentationGenerator(adapter=FakePptMaster(fail=True), artifact_dir=directory)
        failed.last_result.artifact_path = previous
        result = failed.generate_for_action("merge", {"current_scene": scene("cards", "merge"), "completed_scenes": []})
        assert result.status == "error" and result.artifact_path == previous
    print("Presentation generation demo passed.")


if __name__ == "__main__":
    main()
