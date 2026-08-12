"""The planner decides *how* a slide should change; it never gates updates."""

import json

from langchain_openai import ChatOpenAI

from config import LLM_TIMEOUT_SECONDS
from presentation_context import build_presentation_context, preferred_output_language, slide_language_instructions
from reliability import retry_call
from tools import SceneDecision, stage_scene, tools


def presenter_planner(
    transcript_chunk: str,
    current_state: dict | None = None,
    planner_llm=None,
    refinement_feedback: dict | None = None,
    relevant_memory: dict | None = None,
    correlation_id: str = "-",
) -> dict:
    """Return one scene update for already-approved transcript content."""
    current_state = current_state if current_state is not None else {}
    llm_with_tools = (planner_llm or ChatOpenAI(model="gpt-4o-mini", temperature=0, timeout=LLM_TIMEOUT_SECONDS, max_retries=0)).bind_tools(
        tools, tool_choice="required"
    )
    context = build_presentation_context(transcript_chunk, current_state, relevant_memory)
    language_rule = slide_language_instructions(preferred_output_language(current_state.get("metadata")))
    prompt = f"""You are an expert AI Presentation Planner.

Turn the approved spoken content into one concise presentation-scene update.

{language_rule}

Global presentation context:
{json.dumps(context)}

Critic feedback from a previous attempt (empty on the first attempt):
{json.dumps(refinement_feedback or {})}

Call stage_scene exactly once. Do not answer in prose or generate layouts.
Reason from the meaning, not simple keyword matching: hero suits a product or
section introduction; cards compare several features or ideas; pipeline shows a
sequence; metric shows results or statistics; quote emphasizes a memorable
statement. Select the presentation_stage as a helpful narrative hint, not a
required fixed order. Consider current and completed scenes to tell whether this
is a new section. If the active scene is crowded, mixes major ideas, or no longer
supports one primary idea, use start_new_scene instead of merge. Use replace to
revise the active slide, merge to add detail to it, start_new_scene to finalize
it and start a new one, or complete_scene to finalize the active slide."""
    response = retry_call(lambda: llm_with_tools.invoke(prompt), "planner", correlation_id)
    if not response.tool_calls:
        raise RuntimeError("Planner did not return a stage_scene tool call.")

    tool_call = response.tool_calls[0]
    if tool_call["name"] != stage_scene.name:
        raise RuntimeError(f"Unexpected planner tool: {tool_call['name']}")
    return SceneDecision.model_validate(tool_call["args"]).model_dump()
