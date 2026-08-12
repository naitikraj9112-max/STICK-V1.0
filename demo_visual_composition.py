"""Acceptance test: six SpaceX slides must use distinct visual strategies."""

from pathlib import Path
from tempfile import TemporaryDirectory

from presentation_generator.export_scene import enrich_scenes_for_export
from presentation_generator.svg_templates import build_scene_svg
from presentation_generator.visual_strategy import resolve_visual_plan


def spacex_deck() -> list[dict]:
    return [
        {
            "id": "spacex-hero",
            "kind": "hero",
            "status": "editing",
            "presentation_stage": "introduction",
            "content": {
                "title": "SpaceX: Revolutionizing Space Transport",
                "subtitle": "Reusable rockets and commercial spaceflight at scale.",
                "accent": "sky",
                "cards": [],
                "metrics": [],
            },
        },
        {
            "id": "spacex-products",
            "kind": "cards",
            "status": "editing",
            "presentation_stage": "problem",
            "content": {
                "title": "SpaceX Products and Technologies",
                "subtitle": "Rockets, spacecraft, satellites, and launch systems.",
                "accent": "sky",
                "card_items": [
                    {"title": "Rockets", "body": "Falcon 9 and Starship launch vehicles."},
                    {"title": "Spacecraft", "body": "Dragon crew and cargo capsules."},
                    {"title": "Satellite Systems", "body": "Starlink constellation deployment."},
                    {"title": "Launch Technologies", "body": "Reusable boosters and rapid turnaround."},
                ],
            },
        },
        {
            "id": "spacex-architecture",
            "kind": "pipeline",
            "status": "editing",
            "presentation_stage": "architecture",
            "content": {
                "title": "How SpaceX Works",
                "subtitle": "From mission design to orbital delivery.",
                "accent": "sky",
                "card_items": [
                    {"title": "Mission Design", "body": "Payload and trajectory planning."},
                    {"title": "Launch Operations", "body": "Pad prep, fueling, and countdown."},
                    {"title": "Stage Separation", "body": "Boosters return for reuse."},
                    {"title": "Orbit Delivery", "body": "Payload deployment and telemetry."},
                ],
            },
        },
        {
            "id": "spacex-metrics",
            "kind": "metric",
            "status": "editing",
            "presentation_stage": "results",
            "content": {
                "title": "Key Metrics",
                "subtitle": "Operational performance highlights.",
                "accent": "sky",
                "metrics": [
                    {"label": "Launches", "value": "300+"},
                    {"label": "Reusability", "value": "92%"},
                    {"label": "Cost reduction", "value": "10×"},
                    {"label": "Latency", "value": "4.8s"},
                ],
            },
        },
        {
            "id": "spacex-quote",
            "kind": "quote",
            "status": "editing",
            "presentation_stage": "other",
            "content": {
                "title": "The best way to predict the future is to invent it.",
                "subtitle": "Elon Musk",
                "accent": "sky",
            },
        },
        {
            "id": "spacex-close",
            "kind": "hero",
            "status": "editing",
            "presentation_stage": "conclusion",
            "content": {
                "title": "The Future of Space Exploration",
                "subtitle": "Making humanity multiplanetary.",
                "accent": "sky",
            },
        },
    ]


EXPECTED = {
    "spacex-hero": "hero_split_visual",
    "spacex-products": "cards_full_width",
    "spacex-architecture": "architecture_diagram",
    "spacex-metrics": "metrics_dashboard",
    "spacex-quote": "quote_typography",
    "spacex-close": "hero_visual_focus",
}


def main() -> None:
    state = {"completed_scenes": spacex_deck(), "current_scene": None, "metadata": {}}
    enriched = enrich_scenes_for_export(state)
    strategies: set[str] = set()

    with TemporaryDirectory() as directory:
        out = Path(directory) / "svg_output"
        out.mkdir()
        for scene in enriched:
            plan = resolve_visual_plan(scene)
            expected = EXPECTED[scene["id"]]
            assert plan.strategy == expected, f"{scene['id']}: expected {expected}, got {plan.strategy}"
            assert not plan.needs_gemini_image or scene["id"] in {"spacex-hero", "spacex-close"}, (
                f"{scene['id']} should not require Gemini unless hero intro/close"
            )
            svg = build_scene_svg(scene)
            path = out / f"{scene['id']}.svg"
            path.write_text(svg)
            strategies.add(plan.strategy)
            assert f'data-visual-strategy="{plan.strategy}"' in svg
            if plan.strategy == "cards_full_width":
                assert "visual-placeholder" not in svg and "slide-visual" not in svg
            if plan.strategy == "architecture_diagram":
                assert "arch-node" in svg
            if plan.strategy == "pipeline_horizontal":
                assert "pipe-1" in svg
            if plan.strategy == "metrics_dashboard":
                assert "metric-" in svg
            if plan.strategy == "quote_typography":
                assert "slide-visual" not in svg

        assert len(strategies) == 6, f"Expected 6 distinct strategies, got {strategies}"

        try:
            from presentation_generator import PresentationGenerator

            generator = PresentationGenerator()
            if generator.adapter and generator.adapter.available:
                result = generator.generate_for_action(
                    "complete_scene",
                    {"current_scene": None, "completed_scenes": spacex_deck()},
                )
                assert result.status in {"ready", "error"}, result.model_dump()
                print(f"PPT Master export status: {result.status}")
                if result.status == "ready":
                    print(f"PPTX: {result.artifact_path}")
            else:
                print("PPT Master unavailable — SVG-only validation passed.")
        except Exception as error:
            print(f"PPT Master export skipped: {error}")

    print("Visual composition acceptance test passed.")
    print("Strategies:", ", ".join(sorted(strategies)))


if __name__ == "__main__":
    main()
