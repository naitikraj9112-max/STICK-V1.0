"""Real PPT Master integration test using paths configured in .env."""

import shutil
import tempfile
import time
from pathlib import Path
from zipfile import is_zipfile

from config import PPT_MASTER_ROOT, PPT_MASTER_WORKSPACE
from critic import CriticDecision
from demo_memory import InMemoryRepository
from memory import MemoryManager
from orchestrator import PresentationOrchestrator
from presentation_generator import PresentationGenerator
from presentation_generator.ppt_master_adapter import PptMasterAdapter
from semantic_detector import UpdateDecision


def make_scene(kind: str, stage: str = "other") -> dict:
    return {
        "id": f"real-{kind}-{stage}", "kind": kind, "status": "editing",
        "content": {"title": "ExtractAI" if kind == "hero" else kind.title(), "subtitle": "AI-powered resume analysis", "cards": ["Capture", "Reason", "Present"], "metrics": [{"label": "faster", "value": "3×"}] if kind == "metric" else [], "primary_idea": kind},
        "presentation_stage": stage,
    }


class Detector:
    def detect(self, _previous, transcript):
        return UpdateDecision(should_plan=True, reason="test", approved_content=transcript, update_type="completed_idea")


class Critic:
    def review(self, _decision, _context):
        return CriticDecision(approved=True, reason="test")


def planner(_transcript, _state, **_kwargs):
    return {"action": "replace", "kind": "hero", "title": "ExtractAI", "subtitle": "AI-powered resume analysis", "cards": [], "metrics": [], "primary_idea": "Introduction", "presentation_stage": "introduction"}


def assert_pptx(result):
    assert result.status == "ready", result.model_dump()
    assert result.artifact_path
    path = Path(result.artifact_path)
    assert path.is_file() and path.stat().st_size > 0 and is_zipfile(path)
    from pptx import Presentation
    assert len(Presentation(path).slides) >= 1


def assert_failure_boundaries() -> None:
    """Exercise configuration and quality failures without touching live state."""
    assert not PptMasterAdapter("/path/that/does/not/exist", PPT_MASTER_WORKSPACE).available
    missing_script = PptMasterAdapter(PPT_MASTER_ROOT, PPT_MASTER_WORKSPACE)
    missing_script.scripts = Path("/path/with/no/ppt-master-scripts")
    assert not missing_script.available

    generator = PresentationGenerator(adapter=missing_script, artifact_dir=Path(tempfile.mkdtemp()) / "artifacts")
    result = generator.generate_for_action(
        "replace", {"current_scene": make_scene("hero", "invalid"), "completed_scenes": []}
    )
    assert result.status == "unavailable"


def main():
    generator = PresentationGenerator()
    assert generator.adapter and generator.adapter.available, "Configure PPT_MASTER_ROOT and PPT_MASTER_WORKSPACE in .env."
    for kind, stage in (("hero", "introduction"), ("cards", "solution"), ("pipeline", "architecture"), ("pipeline", "workflow"), ("metric", "results"), ("quote", "conclusion")):
        result = generator.generate_for_action("replace", {"current_scene": make_scene(kind, stage), "completed_scenes": []})
        assert_pptx(result)

    assert_failure_boundaries()

    orchestrator = PresentationOrchestrator(
        planner=planner, semantic_detector=Detector(), critic=Critic(),
        memory_manager=MemoryManager(repository=InMemoryRepository()),
        presentation_generator=PresentationGenerator(),
        session_id="real-ppt-master-flow",
    )
    result = orchestrator.receive_transcript("Introduce ExtractAI", "real-ppt-master-flow")
    assert result["scene"]["content"]["title"] == "ExtractAI"
    generation = orchestrator.presentation_generator.status()
    for _ in range(40):
        if generation.get("status") in {"ready", "error", "unavailable"}:
            break
        time.sleep(0.5)
        generation = orchestrator.presentation_generator.status()
    assert generation.get("status") == "ready", generation
    assert generation.get("artifact_path")
    print("Real PPT Master hero, cards, architecture, pipeline, metric, quote, and orchestrator flow passed.")


if __name__ == "__main__":
    main()
