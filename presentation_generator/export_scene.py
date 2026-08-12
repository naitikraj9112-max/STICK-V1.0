"""Prepare presentation state scenes for PPT Master quick-generate export."""


from presentation_cover import is_cover_scene


def scenes_for_export(state: dict) -> list[dict]:
    """Return completed slides plus the active slide in presentation order."""
    scenes = [scene for scene in (state.get("completed_scenes") or []) if not is_cover_scene(scene)]
    current = state.get("current_scene")
    if current and not is_cover_scene(current):
        scenes.append(current)
    return scenes

STAGE_PAGE_ROLE = {
    "introduction": "cover",
    "conclusion": "ending",
    "problem": "content",
    "solution": "content",
    "architecture": "content",
    "workflow": "content",
    "results": "content",
    "other": "content",
}

STAGE_SECTION_LABEL = {
    "introduction": "Introduction",
    "problem": "Problem",
    "solution": "Solution",
    "architecture": "Architecture",
    "workflow": "Workflow",
    "results": "Results",
    "conclusion": "Conclusion",
    "other": "Section",
}


def enrich_scenes_for_export(state: dict) -> list[dict]:
    """Attach deck index, narrative stage, and page role for structured SVG export."""
    scenes = scenes_for_export(state)
    metadata = state.get("metadata") or {}
    fallback_stage = metadata.get("presentation_stage", "other")
    total = len(scenes)
    enriched = []
    for index, scene in enumerate(scenes, start=1):
        content = dict(scene.get("content") or {})
        stage = content.get("presentation_stage") or scene.get("presentation_stage") or fallback_stage
        if not content.get("eyebrow"):
            content["eyebrow"] = STAGE_SECTION_LABEL.get(stage, "Section")
        enriched.append({
            **scene,
            "content": content,
            "presentation_stage": stage,
            "page_role": STAGE_PAGE_ROLE.get(stage, "content"),
            "slide_index": index,
            "slide_total": total,
        })
    return enriched


def compact_scene_for_retry(scene: dict) -> dict:
    """Apply a conservative content reduction pass after a failed quality check."""
    content = dict(scene.get("content") or {})
    content["subtitle"] = " ".join(str(content.get("subtitle", "")).split()[:14])
    cards = content.get("card_items") or []
    if cards:
        trimmed = []
        for card in cards[:3]:
            item = dict(card)
            item["body"] = " ".join(str(item.get("body", "")).split()[:12])
            item["title"] = " ".join(str(item.get("title", "")).split()[:4])
            trimmed.append(item)
        content["card_items"] = trimmed
        content["cards"] = [
            f"{item['title']}: {item['body']}".strip(": ") if item.get("body") else item["title"]
            for item in trimmed
        ]
    content["title"] = " ".join(str(content.get("title", "")).split()[:6])
    return {**scene, "content": content}
