"""Build deterministic video timelines from media assets."""

import json
import wave
from pathlib import Path

from multimedia.models import MediaAsset, TimelineItem, VideoTimeline
from multimedia.workspace import MediaWorkspace


def _audio_duration(path: str) -> float | None:
    if not path or not Path(path).is_file():
        return None
    suffix = Path(path).suffix.lower()
    if suffix == ".wav":
        try:
            with wave.open(path, "rb") as handle:
                frames = handle.getnframes()
                rate = handle.getframerate() or 1
                return frames / rate
        except (wave.Error, OSError):
            return None
    return None


class TimelineBuilder:
    """Transform scenes + narration + media into a VideoTimeline."""

    def build(
        self,
        session_id: str,
        scene_plans: list,
        assets: list[MediaAsset],
        workspace: MediaWorkspace,
    ) -> VideoTimeline:
        by_scene: dict[str, dict[str, MediaAsset]] = {}
        for asset in assets:
            by_scene.setdefault(asset.scene_id, {})[asset.type] = asset

        items: list[TimelineItem] = []
        cursor = 0.0
        for plan in scene_plans:
            scene_assets = by_scene.get(plan.scene_id, {})
            narration_asset = scene_assets.get("narration")
            audio_asset = scene_assets.get("audio")
            image_asset = scene_assets.get("image")
            slide_asset = scene_assets.get("slide")

            duration = plan.estimated_duration
            if audio_asset and audio_asset.status == "ready":
                measured = _audio_duration(audio_asset.path)
                if measured and measured > 0:
                    duration = max(duration, measured)
            duration = max(4.0, min(duration, 30.0))

            item = TimelineItem(
                scene_id=plan.scene_id,
                start_time=round(cursor, 2),
                end_time=round(cursor + duration, 2),
                duration=round(duration, 2),
                visual_asset=image_asset.path if image_asset and image_asset.status == "ready" else "",
                narration_asset=narration_asset.path if narration_asset and narration_asset.status == "ready" else "",
                audio_asset=audio_asset.path if audio_asset and audio_asset.status == "ready" else "",
                slide_asset=slide_asset.path if slide_asset and slide_asset.status == "ready" else "",
                transition="fade",
                animation={"visual_role": plan.visual_role},
            )
            items.append(item)
            cursor += duration

        timeline = VideoTimeline(session_id=session_id, items=items, total_duration=round(cursor, 2))
        workspace.ensure()
        workspace.timeline_path.write_text(timeline.model_dump_json(indent=2))
        return timeline
