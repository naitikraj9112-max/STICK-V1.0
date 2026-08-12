"""Resolve PPT Master SVG files for export scenes."""

from pathlib import Path

from presentation_generator.svg_templates import _slide_filename


def expected_svg_path(scene: dict, svg_dir: Path) -> Path:
    return svg_dir / _slide_filename(scene["slide_index"], scene)


def resolve_scene_svg(scene: dict, svg_dir: Path) -> Path | None:
    """Find the SVG for a scene by structured filename, id, or deck order."""
    svg_dir = Path(svg_dir)
    if not svg_dir.is_dir():
        return None

    expected = expected_svg_path(scene, svg_dir)
    if expected.is_file():
        return expected

    scene_id = scene.get("id", "")
    if scene_id:
        for svg in sorted(svg_dir.glob("*.svg")):
            if scene_id in svg.stem:
                return svg

    svgs = sorted(svg_dir.glob("*.svg"))
    index = int(scene.get("slide_index", 1)) - 1
    if 0 <= index < len(svgs):
        return svgs[index]
    return None
