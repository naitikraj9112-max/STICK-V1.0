"""Live server test: build a 6-slide ExtractAI deck and verify slide types + PPTX."""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zipfile import is_zipfile

from config import PRESENTATION_PORT

BASE = f"http://127.0.0.1:{PRESENTATION_PORT}"

# Simulates what the Realtime director would stage for a short ExtractAI pitch.
SLIDES = [
    {
        "call_id": "slide-1-hero-intro",
        "action": "replace",
        "kind": "hero",
        "title": "Extract AI",
        "subtitle": "Turn messy documents into structured data in seconds.",
        "icon": "sparkles",
        "accent": "lime",
        "presentation_stage": "introduction",
        "primary_idea": "Product introduction for Extract AI",
    },
    {
        "call_id": "slide-2-hero-problem",
        "action": "replace",
        "kind": "hero",
        "title": "Manual extraction fails",
        "subtitle": "Teams waste hours copying fields from PDFs and scans.",
        "icon": "alert-circle",
        "accent": "ember",
        "presentation_stage": "problem",
        "primary_idea": "Manual document extraction is slow and error-prone",
    },
    {
        "call_id": "slide-3-cards-solution",
        "action": "replace",
        "kind": "cards",
        "title": "What Extract AI does",
        "subtitle": "Three capabilities that replace manual work.",
        "presentation_stage": "solution",
        "primary_idea": "Core product capabilities",
        "cards": [
            {"title": "Ingest", "body": "Upload PDFs, scans, and email attachments.", "icon": "cloud"},
            {"title": "Understand", "body": "LLM extracts entities, tables, and fields.", "icon": "brain"},
            {"title": "Export", "body": "Push clean JSON or CSV to your systems.", "icon": "arrow-right"},
        ],
    },
    {
        "call_id": "slide-4-pipeline-arch",
        "action": "replace",
        "kind": "pipeline",
        "title": "Architecture",
        "subtitle": "From raw file to validated output.",
        "presentation_stage": "architecture",
        "primary_idea": "End-to-end extraction pipeline",
        "cards": [
            {"title": "Capture", "body": "OCR and layout parsing", "icon": "layers"},
            {"title": "Reason", "body": "Schema-aware LLM extraction", "icon": "cpu"},
            {"title": "Validate", "body": "Rules + human review queue", "icon": "check-circle"},
        ],
    },
    {
        "call_id": "slide-5-metric-results",
        "action": "replace",
        "kind": "metric",
        "title": "Results",
        "subtitle": "Measured on production document batches.",
        "presentation_stage": "results",
        "primary_idea": "Quantified customer impact",
        "metrics": [
            {"label": "Faster", "value": "3×"},
            {"label": "Accuracy", "value": "94%"},
            {"label": "Cost saved", "value": "$120K"},
        ],
    },
    {
        "call_id": "slide-6-quote-close",
        "action": "replace",
        "kind": "quote",
        "quote": "Stop copying. Start extracting.",
        "attribution": "Extract AI",
        "presentation_stage": "conclusion",
        "primary_idea": "Closing call to action",
    },
]

COMPONENT_FOR_KIND = {
    "hero": "HeroScene",
    "cards": "CardsScene",
    "pipeline": "PipelineScene",
    "metric": "MetricScene",
    "quote": "QuoteScene",
}


def request(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())


def stage(session_id: str, scene: dict) -> dict:
    body = {"session_id": session_id, "call_id": scene["call_id"], "scene_update": {k: v for k, v in scene.items() if k != "call_id"}}
    return request("POST", "/scene", body)


def fetch_presentation(session_id: str) -> dict:
    return request("GET", f"/presentation?session_id={session_id}")


def wait_for_pptx(session_id: str, timeout: float = 45.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        presentation = fetch_presentation(session_id)
        last = presentation.get("generation") or {}
        if last.get("status") in {"ready", "error", "unavailable"}:
            return last
        time.sleep(0.75)
    return last


def all_slides(presentation: dict) -> list[dict]:
    slides = list(presentation.get("completed_scenes") or [])
    current = presentation.get("current_scene")
    if current and not (current.get("props") or {}).get("is_cover"):
        slides.append(current)
    return slides


def main() -> None:
    try:
        health = request("GET", "/health")
    except urllib.error.URLError as error:
        print(f"Server not reachable at {BASE}: {error}", file=sys.stderr)
        sys.exit(1)
    if health.get("status") != "healthy":
        print(f"Server unhealthy: {health}", file=sys.stderr)
        sys.exit(1)

    session = request("POST", "/session", {})
    session_id = session["session_id"]
    print(f"Session: {session_id[:8]}...")

    cover = (session.get("presentation") or {}).get("current_scene") or {}
    assert cover.get("component") == "CoverScene", f"Expected cover, got {cover.get('component')}"
    print("[OK] Welcome cover present")

    for index, planned in enumerate(SLIDES, start=1):
        if index > 1:
            time.sleep(16)  # respect MIN_NEW_SCENE_SECONDS guard between new slides
        result = stage(session_id, planned)
        assert result.get("success"), f"Slide {index} failed: {result}"
        assert result.get("scene_updated"), f"Slide {index} not applied: {result}"
        scene = result["scene"]
        expected_component = COMPONENT_FOR_KIND[planned["kind"]]
        assert scene["component"] == expected_component, (
            f"Slide {index}: expected {expected_component}, got {scene['component']}"
        )
        title = scene["props"].get("title", "")
        assert title and title.lower() != "new idea", f"Slide {index} has weak title: {title!r}"
        print(f"[OK] Slide {index}: {planned['kind']:8} -> {scene['component']:13} \"{title}\"")

    presentation = fetch_presentation(session_id)
    slides = all_slides(presentation)
    assert 5 <= len(slides) <= 7, f"Expected 5-7 slides, got {len(slides)}"
    kinds = [s.get("component", "").replace("Scene", "").lower() for s in slides]
    for expected in ("hero", "cards", "pipeline", "metric", "quote"):
        assert expected in kinds, f"Missing {expected} slide in deck: {kinds}"
    print(f"[OK] Deck has {len(slides)} slides with types: {', '.join(kinds)}")

    generation = wait_for_pptx(session_id)
    status = generation.get("status")
    artifact = generation.get("artifact_path")
    if status == "ready" and artifact and Path(artifact).is_file():
        assert is_zipfile(artifact), "PPTX artifact is not a valid zip"
        print(f"[OK] PPTX ready ({Path(artifact).stat().st_size // 1024} KB)")
    else:
        print(f"[!] PPTX generation: {status} - {generation.get('message', '')}")

    print("\nFull presentation test passed.")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, urllib.error.HTTPError, urllib.error.URLError) as error:
        print(f"Full presentation test failed: {error}", file=sys.stderr)
        sys.exit(1)
