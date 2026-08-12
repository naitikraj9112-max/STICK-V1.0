"""Propose structured presentation memories; persistence remains a manager decision."""

from memory.models import MemoryCandidate


class MemoryExtractor:
    """Deterministic default extractor; an LLM implementation can use the same candidate schema later."""

    def extract(self, transcript: str, scene_decision: dict, detector_decision) -> MemoryCandidate | None:
        if detector_decision.update_type not in ("new_concept", "topic_change") and scene_decision["action"] != "start_new_scene":
            return None
        topic = scene_decision.get("presentation_stage", "other")
        detail = scene_decision.get("primary_idea", scene_decision.get("title", ""))
        return MemoryCandidate(
            type="presentation_memory",
            content={"topic": topic, "important_detail": detail, "source": "approved_transcript"},
            importance=0.8 if scene_decision["action"] == "start_new_scene" else 0.6,
        )
