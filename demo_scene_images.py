"""Verify Gemini visuals embed into export SVGs with strategy-aware bounds."""

from pathlib import Path
from tempfile import TemporaryDirectory

from presentation_generator.export_scene import enrich_scenes_for_export
from presentation_generator.scene_images import build_scene_image_map, resolve_scene_image_path
from presentation_generator.svg_templates import build_scene_svg
from presentation_generator.visual_strategy import resolve_visual_plan


def sample_state(scene_id: str = "hero-test"):
    return {
        "completed_scenes": [],
        "current_scene": {
            "id": scene_id,
            "kind": "hero",
            "status": "editing",
            "presentation_stage": "introduction",
            "content": {
                "title": "Extract AI",
                "subtitle": "Structured data from documents",
                "cards": [],
                "metrics": [],
                "accent": "lime",
            },
        },
    }


def test_embed_and_resolve():
    with TemporaryDirectory() as directory:
        session_id = "scene-images-test"
        images_dir = Path(directory) / session_id / "media" / "images"
        images_dir.mkdir(parents=True)
        image_path = images_dir / "hero-test.png"
        image_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        state = sample_state()
        import presentation_generator.scene_images as scene_images_module

        original = scene_images_module.PRESENTATION_ARTIFACT_DIR
        scene_images_module.PRESENTATION_ARTIFACT_DIR = Path(directory)
        try:
            resolved = resolve_scene_image_path("hero-test", session_id)
            assert resolved == image_path
            image_map = build_scene_image_map(state, session_id=session_id)
            assert image_map["hero-test"] == str(image_path)
            hero_scene = enrich_scenes_for_export(state)[0]
            plan = resolve_visual_plan(hero_scene)
            assert plan.strategy == "hero_split_visual"
            svg = build_scene_svg(hero_scene, background_image=image_path)
            assert "gemini-slide-visual" in svg
            assert "data:image/png;base64," in svg
            assert "gemini-background" not in svg

            cards_state = sample_state("cards-test")
            cards_state["current_scene"]["kind"] = "cards"
            cards_state["current_scene"]["content"]["card_items"] = [
                {"title": "PDFs", "body": "Reports"},
                {"title": "Invoices", "body": "Contracts"},
            ]
            cards_scene = enrich_scenes_for_export(cards_state)[0]
            cards_plan = resolve_visual_plan(cards_scene)
            assert cards_plan.strategy == "cards_with_small_visual"
            cards_svg = build_scene_svg(cards_scene, background_image=image_path)
            assert "gemini-slide-visual" in cards_svg
            assert "#FAFAFA" in cards_svg

            full_cards_state = sample_state("cards-full")
            full_cards_state["current_scene"]["kind"] = "cards"
            full_cards_state["current_scene"]["content"]["card_items"] = [
                {"title": "A", "body": "One"},
                {"title": "B", "body": "Two"},
                {"title": "C", "body": "Three"},
                {"title": "D", "body": "Four"},
            ]
            full_scene = enrich_scenes_for_export(full_cards_state)[0]
            assert resolve_visual_plan(full_scene).strategy == "cards_full_width"
            full_svg = build_scene_svg(full_scene, background_image=image_path)
            assert "gemini-slide-visual" not in full_svg
        finally:
            scene_images_module.PRESENTATION_ARTIFACT_DIR = original
    print("Scene image embed demo passed.")


if __name__ == "__main__":
    test_embed_and_resolve()
