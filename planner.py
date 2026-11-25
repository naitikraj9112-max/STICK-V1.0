"""The planner decides *how* a slide should change; it never gates updates."""

import json

from deepseek_client import create_chat_model
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
    llm_with_tools = (planner_llm or create_chat_model()).bind_tools(
        tools, tool_choice="required"
    )
    context = build_presentation_context(transcript_chunk, current_state, relevant_memory)
    language_rule = slide_language_instructions(preferred_output_language(current_state.get("metadata")))
    prompt = f"""You are an expert AI Presentation Planner.

Turn the approved spoken content into one concise presentation-scene update.
Treat clear spoken directions as instructions for what the next slide should
communicate. Use the active slide, deck topic, presentation goal, and prior
sections to resolve references such as "the topic" or "why it matters". Create
useful slide copy from that context; do not copy a generic instruction verbatim
as the slide title or subtitle.

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
required fixed order.

CRITICAL SLIDE LIFECYCLE RULES:
- Presentations consist of multiple sequential slides built as the speaker talks.
- When the active slide already has content (title/primary idea) and the speaker
  introduces a new point, problem, solution, feature, architecture, metric, comparison,
  or conclusion, you MUST choose action='start_new_scene' so the previous slide is
  completed and a new slide appears on screen!
- Use action='merge' ONLY when the speaker is adding a quick supplementary bullet
  or secondary detail specifically to the active slide.
- Use action='replace' ONLY when the speaker explicitly corrects, edits, or rephrases
  the active slide (e.g., 'let's change the title to...', 'actually make it 40%', etc.).
- When starting from a blank deck or cover slide, use action='start_new_scene' or 'replace'."""
    response = retry_call(lambda: llm_with_tools.invoke(prompt), "planner", correlation_id)
    if not response.tool_calls:
        raise RuntimeError("Planner did not return a stage_scene tool call.")

    tool_call = response.tool_calls[0]
    if tool_call["name"] != stage_scene.name:
        raise RuntimeError(f"Unexpected planner tool: {tool_call['name']}")
    return SceneDecision.model_validate(tool_call["args"]).model_dump()
