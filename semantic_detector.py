"""Decide whether a transcript update contains enough information to plan."""

from typing import Literal

from pydantic import BaseModel, Field

from deepseek_client import create_chat_model
from reliability import retry_call

class UpdateDecision(BaseModel):
    should_plan: bool = Field(description="True only for a complete, presentable idea.")
    reason: str = Field(description="Short explanation of the decision.")
    approved_content: str = Field(description="New self-contained content for the planner.")
    update_type: Literal["completed_idea", "new_concept", "topic_change", "incomplete", "repetition"]


class SemanticDetector:
    """Owns the semantic detection model and its prompt."""

    def __init__(self, detector_llm=None):
        llm = detector_llm or create_chat_model()
        self.detector = llm.with_structured_output(UpdateDecision, method="function_calling")

    def detect(self, previous_transcript: str, latest_transcript: str, correlation_id: str = "-") -> UpdateDecision:
        """Return whether the latest snapshot justifies a planner call."""
        prompt = f"""You decide when a live presentation planner should run.

Previous transcript snapshot:
{previous_transcript or '(none)'}

Latest transcript snapshot:
{latest_transcript}

Compare the snapshots semantically. Set should_plan true only if the latest
snapshot adds a self-contained completed idea, a meaningful new concept, or a
topic change that deserves a presentation update. Also treat a clear spoken
slide-building direction (such as "introduce the topic", "explain the problem",
"compare the options", or "add a slide about benefits") as an actionable request
to build presentation content. These are not disposable meta-instructions: the
planner should apply them to the current topic and deck context. When the previous
snapshot is empty and the latest contains a complete spoken sentence, should_plan
should usually be true. Do not trigger for partial phrases, filler, or when the
latest snapshot is essentially the same as the previous one with no new request.
approved_content must contain only the newly approved idea or slide direction."""
        return retry_call(lambda: self.detector.invoke(prompt), "semantic detector", correlation_id)
