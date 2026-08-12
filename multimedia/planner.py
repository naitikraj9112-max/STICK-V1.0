"""Inspect committed presentation state and produce a structured media plan."""

import json

from presentation_generator.export_scene import STAGE_SECTION_LABEL, enrich_scenes_for_export
from presentation_generator.visual_strategy import resolve_visual_plan
from multimedia.models import MediaPlan, SceneMediaPlan


ACCENT_DESCRIPTIONS = {
    "ember": "electric orange-red",
    "lime": "acid lime green",
    "sky": "clear cyan blue",
    "violet": "luminous violet",
}


class MultimediaPlanner:
    """Read-only planner: never mutates presentation state."""

    def plan(self, session_id: str, state: dict) -> MediaPlan:
        metadata = state.get("metadata") or {}
        summary = metadata.get("presentation_summary") or {}
        goal = summary.get("goal") or metadata.get("presentation_goal") or metadata.get("goal") or ""
        audience = summary.get("audience") or metadata.get("audience") or "a professional audience"
        scenes = enrich_scenes_for_export(state)
        scene_plans = []
        for index, scene in enumerate(scenes):
            previous = scenes[index - 1] if index > 0 else None
            nxt = scenes[index + 1] if index + 1 < len(scenes) else None
            scene_plans.append(self._plan_scene(scene, previous, nxt, goal, audience))
        return MediaPlan(session_id=session_id, scenes=scene_plans, presentation_goal=goal, audience=audience)

    def _visual_role(self, strategy: str) -> str:
        if strategy in {"hero_split_visual", "hero_visual_focus"}:
            return "hero_visual"
        if strategy == "cards_with_small_visual":
            return "supporting_visual"
        if strategy in {"architecture_diagram", "pipeline_horizontal", "metrics_dashboard"}:
            return "svg_diagram"
        if strategy == "quote_typography":
            return "none"
        return "none"

    def _plan_scene(self, scene: dict, previous: dict | None, nxt: dict | None, goal: str, audience: str) -> SceneMediaPlan:
        content = scene.get("content") or {}
        kind = scene.get("kind", "hero")
        stage = scene.get("presentation_stage", "other")
        plan = resolve_visual_plan(scene)
        needs_image = plan.needs_gemini_image
        visual_role = self._visual_role(plan.strategy)
        narration_prompt = self._narration_prompt(scene, previous, nxt, goal, audience)
        image_prompt = self._image_prompt(scene, plan) if needs_image else ""
        estimated = self._estimate_duration(content, kind)
        priority = {"introduction": 90, "conclusion": 80, "problem": 70, "solution": 65}.get(stage, 50)
        return SceneMediaPlan(
            scene_id=scene["id"],
            needs_image=needs_image,
            needs_narration=True,
            needs_tts=True,
            needs_video_motion=True,
            media_priority=priority,
            image_prompt=image_prompt,
            narration_prompt=narration_prompt,
            estimated_duration=estimated,
            visual_role=visual_role,
        )

    def _image_prompt(self, scene: dict, plan) -> str:
        content = scene.get("content") or {}
        accent = ACCENT_DESCRIPTIONS.get(content.get("accent", "sky"), "clear cyan blue")
        title = content.get("title", "")
        subtitle = content.get("subtitle", "")
        stage = scene.get("presentation_stage", "other")
        section = STAGE_SECTION_LABEL.get(stage, "Section")
        cards = content.get("card_items") or []
        card_summary = "; ".join(
            f"{item.get('title', '')}: {item.get('body', '')}".strip(": ")
            for item in cards[:3]
            if item.get("title")
        )
        context = subtitle
        if card_summary:
            context = f"{subtitle}. Key points: {card_summary}" if subtitle else f"Key points: {card_summary}"
        aspect_hint = {
            "square": "Square composition",
            "landscape": "Landscape composition",
            "wide": "Wide cinematic composition",
        }.get(plan.prompt_aspect, "Square composition")
        return (
            f"Create a photorealistic cinematic photograph for a presentation slide visual. "
            f"{aspect_hint}. Section: {section}. Topic: {title}. Context: {context}. "
            f"Lighting mood: {accent}. Natural lighting, realistic materials, depth of field. "
            f"No text, no logos, no watermarks, no slide UI, no illustration style."
        )

    def _narration_prompt(self, scene: dict, previous: dict | None, nxt: dict | None, goal: str, audience: str) -> str:
        content = scene.get("content") or {}
        context = {
            "title": content.get("title", ""),
            "subtitle": content.get("subtitle", ""),
            "primary_idea": content.get("primary_idea", ""),
            "cards": content.get("cards", [])[:4],
            "metrics": content.get("metrics", [])[:3],
            "stage": scene.get("presentation_stage", "other"),
            "kind": scene.get("kind", "hero"),
            "previous_title": (previous or {}).get("content", {}).get("title", ""),
            "next_title": (nxt or {}).get("content", {}).get("title", ""),
            "presentation_goal": goal,
            "audience": audience,
        }
        return (
            "Write a natural presenter narration for this slide. "
            "Sound like a confident human presenter, not a slide reader. "
            "Use only facts present in the slide context. Do not invent statistics or product names. "
            "Keep it to 2-4 sentences (roughly 20-45 seconds spoken). "
            "Do not list bullet labels verbatim.\n\n"
            f"Slide context:\n{json.dumps(context, indent=2)}"
        )

    def _estimate_duration(self, content: dict, kind: str) -> float:
        words = " ".join(
            [
                str(content.get("title", "")),
                str(content.get("subtitle", "")),
                " ".join(content.get("cards") or []),
            ]
        ).split()
        base = max(6.0, min(18.0, len(words) * 0.45))
        if kind == "quote":
            base += 2.0
        if kind == "pipeline":
            base += 3.0
        return round(base, 1)
