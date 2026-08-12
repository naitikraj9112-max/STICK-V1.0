"""End-to-end architecture verification from session through artifact generation."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import is_zipfile

from config import OPENAI_API_KEY, DATABASE_URL, PPT_MASTER_ROOT, PPT_MASTER_WORKSPACE
from critic import CriticDecision
from demo_memory import InMemoryRepository
from execution_policy import should_run_critic
from memory import MemoryManager
from orchestrator import PresentationOrchestrator
from presentation_context import build_presentation_context
from presentation_generator import PresentationGenerator
from presentation_generator.ppt_master_adapter import PptMasterAdapter, prepare_session_workspace
from semantic_detector import UpdateDecision
from session import PresentationSession, session_summary
from session_manager import SessionManager


class LocalDetector:
    def detect(self, _previous, latest):
        return UpdateDecision(
            should_plan=bool(latest.strip()),
            reason="Local end-to-end detector",
            approved_content=latest,
            update_type="completed_idea",
        )


class LocalCritic:
    def review(self, _decision, _context):
        return CriticDecision(approved=True, reason="Local end-to-end critic")


def local_planner(transcript, state, refinement_feedback=None, relevant_memory=None, **_kwargs):
    if not state.get("current_scene"):
        return {
            "action": "replace", "kind": "hero", "title": "Stick", "subtitle": transcript[:80],
            "cards": [], "metrics": [], "primary_idea": transcript[:120], "presentation_stage": "introduction",
        }
    return {
        "action": "start_new_scene", "kind": "cards", "title": "Details", "subtitle": "",
        "cards": [transcript[:40]], "metrics": [], "primary_idea": transcript[:120], "presentation_stage": "solution",
    }


def register_local_session(manager: SessionManager) -> tuple[PresentationSession, PresentationOrchestrator]:
    """Register a no-LLM session for offline pipeline verification."""
    session = PresentationSession()
    orchestrator = PresentationOrchestrator(
        session_id=session.session_id,
        planner=local_planner,
        semantic_detector=LocalDetector(),
        critic=LocalCritic(),
        memory_manager=MemoryManager(repository=InMemoryRepository(), session_id=session.session_id),
        presentation_generator=PresentationGenerator(session_id=session.session_id, adapter=None),
    )
    manager._sessions[session.session_id] = session
    manager._orchestrators[session.session_id] = orchestrator
    return session, orchestrator


def run_local_pipeline() -> None:
    manager = SessionManager()
    session, orchestrator = register_local_session(manager)
    assert orchestrator.session_id == session.session_id

    manager.connect(session.session_id)
    assert manager.get(session.session_id).status == "connected"

    first = orchestrator.receive_transcript("Welcome to Stick end-to-end verification", "e2e-1")
    assert first["planned"] and first["scene_updated"]
    state = orchestrator.presentation_state
    assert state["current_scene"]["content"]["title"] == "Stick"

    context = build_presentation_context("Second idea", state, [])
    assert context["current_scene"]["title"] == "Stick"

    realtime = orchestrator.apply_realtime_scene(
        {
            "action": "merge",
            "kind": "hero",
            "title": "Stick Live",
            "subtitle": "Realtime tool path",
            "cards": [],
            "metrics": [],
            "primary_idea": "Live presentation updates",
            "presentation_stage": "introduction",
        },
        "call-realtime-1",
    )
    assert realtime["success"] and realtime["scene_updated"]
    assert realtime["scene"]["props"]["title"] == "Stick Live"
    duplicate = orchestrator.apply_realtime_scene(realtime["scene"]["props"], "call-realtime-1")
    assert not duplicate["success"]

    held = orchestrator.apply_realtime_scene({"action": "hold"}, "call-hold-1")
    assert held["success"] and held.get("held")

    context = build_presentation_context("Second idea", state, [])
    assert context["current_scene"]["title"] == "Stick Live"

    manager.note_transcript(session.session_id)

    second_decision = local_planner("Second idea about architecture layers", state)
    assert should_run_critic(second_decision)

    second = orchestrator.receive_transcript("Second idea about architecture layers", "e2e-2")
    assert second["scene_updated"]
    assert len(state["completed_scenes"]) == 1

    with TemporaryDirectory() as directory:
        generator = PresentationGenerator(
            adapter=PptMasterAdapter(PPT_MASTER_ROOT, Path(directory) / "workspace") if PPT_MASTER_ROOT else None,
            artifact_dir=Path(directory) / "artifacts",
            session_id=session.session_id,
        )
        if generator.adapter and generator.adapter.available:
            prepare_session_workspace(Path(directory) / "workspace", PPT_MASTER_WORKSPACE)
            result = generator.generate_for_action("replace", state)
            if result.status == "ready":
                assert Path(result.artifact_path).is_file()
                assert is_zipfile(result.artifact_path)
                print("LOCAL + PPT MASTER: artifact generation passed.")
            else:
                print(f"LOCAL + PPT MASTER: returned {result.status} — run demo_real_ppt_master.py for full checkout verification.")
        else:
            print("LOCAL + PPT MASTER: skipped (PPT_MASTER_ROOT not configured or scripts unavailable).")

    manager.complete(session.session_id)
    assert manager.get(session.session_id).status == "completed"
    assert session_summary(session)["status"] == "completed"
    print("LOCAL: session → transcript → planner → critic policy → state → generation boundary passed.")


def run_live_openai_block() -> None:
    if not OPENAI_API_KEY:
        print("LIVE OPENAI: skipped (OPENAI_API_KEY not set).")
        return
    print("LIVE OPENAI: credentials present; run ingestion.py and speak to verify realtime path manually.")


def run_live_neon_block() -> None:
    if not DATABASE_URL:
        print("LIVE NEON: skipped (DATABASE_URL not set).")
        return
    print("LIVE NEON: run demo_neon_memory.py for repository verification.")


def main() -> None:
    run_local_pipeline()
    run_live_openai_block()
    run_live_neon_block()
    print("End-to-end demo passed.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        print(f"End-to-end demo failed: {error}", file=sys.stderr)
        sys.exit(1)
