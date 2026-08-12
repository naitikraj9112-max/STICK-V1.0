"""Evaluate a proposed scene before the state manager is allowed to apply it."""

from typing import Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from config import LLM_TIMEOUT_SECONDS
from presentation_context import slide_language_instructions, preferred_output_language
from reliability import retry_call


class CriticDecision(BaseModel):
    """Structured reflection that the orchestrator can route without parsing prose."""

    approved: bool
    reason: str = Field(description="Short explanation of the evaluation.")
    suggestions: list[str] = Field(default_factory=list)
    issue: Literal["none", "focus", "density", "visual_fit", "missing_information", "conciseness"] = "none"


class PresentationCritic:
    """Owns evaluation only; it never changes presentation state."""

    def __init__(self, critic_llm=None):
        llm = critic_llm or ChatOpenAI(model="gpt-4o-mini", temperature=0, timeout=LLM_TIMEOUT_SECONDS, max_retries=0)
        self.critic = llm.with_structured_output(CriticDecision)

    def review(self, scene_decision: dict, context: dict, correlation_id: str = "-") -> CriticDecision:
        """Approve a focused scene or provide feedback for one bounded retry."""
        metadata = context.get("metadata") or context.get("presentation_metadata") or {}
        language_rule = slide_language_instructions(preferred_output_language(metadata))
        prompt = f"""You are a concise presentation critic. Review this proposed scene.

{language_rule}

Proposed scene decision:
{scene_decision}

Presentation context:
{context}

Approve only when the scene has one clear primary idea, uses an appropriate visual
type, is concise, contains enough important information, is not crowded, and uses
the same language as the approved transcript (or the deck default when ambiguous).
Reject with issue=missing_information when slide copy is in the wrong language.
A scene with many points plus an unrelated major idea should be rejected for a new
scene. Return structured output only. Suggestions must be actionable and short."""
        return retry_call(lambda: self.critic.invoke(prompt), "critic", correlation_id)
