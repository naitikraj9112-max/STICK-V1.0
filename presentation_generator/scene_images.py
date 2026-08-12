"""Resolve Gemini scene backgrounds for live UI and PPT export."""

from pathlib import Path

from config import PRESENTATION_ARTIFACT_DIR
from presentation_generator.export_scene import enrich_scenes_for_export

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def _safe_scene_id(scene_id: str) -> str:
    return scene_id.replace("/", "_").replace(":", "_")


def resolve_scene_image_path(
    scene_id: str,
    session_id: str | None = None,
    image_map: dict[str, str] | None = None,
) -> Path | None:
    """Return an on-disk image for a scene, if one exists."""
    if image_map:
        mapped = image_map.get(scene_id)
        if mapped:
            path = Path(mapped)
            if path.is_file():
                return path
    if not session_id:
        return None
    images_dir = Path(PRESENTATION_ARTIFACT_DIR) / session_id / "media" / "images"
    if not images_dir.is_dir():
        return None
    safe = _safe_scene_id(scene_id)
    for ext in IMAGE_EXTENSIONS:
        candidate = images_dir / f"{safe}{ext}"
        if candidate.is_file():
            return candidate
    for path in images_dir.iterdir():
        if path.suffix.lower() in IMAGE_EXTENSIONS and path.stem == safe:
            return path
    return None


def build_scene_image_map(
    state: dict,
    session_id: str | None = None,
    live_image_map: dict[str, str] | None = None,
) -> dict[str, str]:
    """Map scene id → image path for every exportable slide."""
    resolved: dict[str, str] = {}
    for scene in enrich_scenes_for_export(state):
        scene_id = scene.get("id")
        if not scene_id:
            continue
        path = resolve_scene_image_path(scene_id, session_id, live_image_map)
        if path:
            resolved[scene_id] = str(path)
    return resolved
