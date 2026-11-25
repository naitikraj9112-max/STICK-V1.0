"""Live Speech-to-Presentation Director.

Takes chunks of speech, gives them to the AI, and lets the AI decide which
slide appears on the screen in real-time.
"""

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

from config import DEEPSEEK_API_KEY, PRESENTATION_PORT
from planner import presenter_planner
from presentation_context import build_presentation_context
from realtime_director import normalize_realtime_payload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("speech_to_presentation")

BASE_URL = f"http://127.0.0.1:{PRESENTATION_PORT}"


def http_post(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ensure_server_session(specific_session_id: Optional[str] = None) -> tuple[str, dict]:
    """Connect to the user's active presentation session or create a new one."""
    try:
        health = http_get("/health")
        LOGGER.info("Connected to presentation server (status: %s)", health.get("status"))
    except Exception as exc:
        raise RuntimeError(
            f"Cannot connect to Stick presentation server at {BASE_URL}. "
            f"Please run 'python ingestion.py' first in a terminal."
        ) from exc

    if specific_session_id:
        LOGGER.info("Using explicitly requested session ID: %s", specific_session_id)
        return specific_session_id, fetch_presentation(specific_session_id)

    # If an active or connected browser session exists, use it so screen updates live
    sessions = health.get("sessions", {}).get("sessions", [])
    for s in reversed(sessions):
        if s.get("connection_status") == "connected" or s.get("status") in {"active", "connected"}:
            active_id = s.get("session_id")
            LOGGER.info("Attached to user's active browser session: %s", active_id)
            return active_id, fetch_presentation(active_id)

    # Otherwise create a new session
    session_resp = http_post("/session", {"output_language": "en"})
    session_id = session_resp["session_id"]
    presentation = session_resp.get("presentation", {})
    return session_id, presentation


def fetch_presentation(session_id: str) -> dict:
    """Fetch current presentation deck from server."""
    return http_get(f"/presentation?session_id={session_id}")


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def process_speech_chunk(
    session_id: str,
    speech_chunk: str,
    call_id: Optional[str] = None,
) -> dict:
    """Give a chunk of speech to the AI; the AI decides which slide to appear on screen.

    1. Fetches current presentation state from server.
    2. Sends the speech chunk to the AI planner (DeepSeek).
    3. The AI decides the slide action (replace, start_new_scene, merge),
       slide kind (hero, cards, pipeline, metric, quote), title, cards, etc.
    4. Applies the scene decision to the presentation server so it appears on screen.
    """
    speech_chunk = speech_chunk.strip()
    if not speech_chunk:
        return {"success": False, "reason": "Empty speech chunk"}

    corr_id = call_id or f"speech-chunk-{int(time.time() * 1000)}"
    print("\n" + "=" * 65)
    print(f"[SPEECH CHUNK] \"{speech_chunk}\"")
    print("=" * 65)
    print("-> AI is deciding the slide (layout, action, title, and content)...")

    # Method 1: Send directly via /transcript so orchestrator processes it
    try:
        result = http_post(
            "/transcript",
            {
                "session_id": session_id,
                "transcript": speech_chunk,
                "is_final": True,
                "event_id": corr_id,
            },
        )
        if result.get("scene_updated"):
            deck = fetch_presentation(session_id)
            curr = deck.get("current_scene", {}).get("props", {})
            slide_count = len(deck.get("completed_scenes", [])) + (1 if not curr.get("is_cover") else 0)
            print("\n[AI DECIDED SLIDE TO APPEAR ON SCREEN]")
            print(f"   Action:        {result.get('action', 'start_new_scene')}")
            print(f"   Layout Kind:   {curr.get('component', curr.get('kind', 'Hero'))}")
            print(f"   Title:         {curr.get('title', 'Untitled')}")
            if curr.get("subtitle"):
                print(f"   Subtitle:      {curr.get('subtitle')}")
            if curr.get("cards") or curr.get("card_items"):
                cards = curr.get("card_items") or curr.get("cards")
                print("   Content Cards:")
                for i, c in enumerate(cards, 1):
                    if isinstance(c, dict):
                        print(f"      {i}. {c.get('title')}: {c.get('body', '')}")
                    else:
                        print(f"      {i}. {c}")
            if curr.get("metrics"):
                print("   Metrics:")
                for m in curr.get("metrics"):
                    print(f"      * {m.get('value')} ({m.get('label')})")
            print(f"\n   >>> SCREEN UPDATED! Slide #{slide_count} is now LIVE on http://127.0.0.1:{PRESENTATION_PORT}")
            return result
    except Exception as exc:
        LOGGER.warning("Direct /transcript call failed: %s; falling back to direct AI planner call", exc)

    # Method 2 (Fallback): Direct planner invoke -> /scene stage
    current_pres = fetch_presentation(session_id)
    scene_decision = presenter_planner(speech_chunk, current_pres)
    print(f"   AI Plan: action={scene_decision.get('action')} kind={scene_decision.get('kind')} title=\"{scene_decision.get('title')}\"")

    stage_result = http_post(
        "/scene",
        {
            "session_id": session_id,
            "call_id": corr_id,
            "scene_update": scene_decision,
        },
    )
    deck = fetch_presentation(session_id)
    curr = deck.get("current_scene", {}).get("props", {})
    slide_count = len(deck.get("completed_scenes", [])) + (1 if not curr.get("is_cover") else 0)
    print(f"\n   >>> SCREEN UPDATED! Slide #{slide_count} is now LIVE on http://127.0.0.1:{PRESENTATION_PORT}")
    return stage_result


def run_interactive_mode(session_id: str) -> None:
    """Prompt the user for speech chunks continuously."""
    print("\n" + "#" * 65)
    print("  STICK LIVE SPEECH CHUNKER — AI SLIDE DIRECTOR")
    print(f"  Connected Session ID: {session_id}")
    print(f"  Live Screen URL:     http://127.0.0.1:{PRESENTATION_PORT}")
    print("#" * 65)
    print("\nHow to use:")
    print("  1. Keep http://127.0.0.1:8001 open in your browser.")
    print("  2. Speak or paste your chunks of speech below.")
    print("  3. The AI analyzes each chunk and decides which slide appears on screen!")
    print("  Type 'quit' or 'exit' to stop.\n")

    chunk_num = 1
    while True:
        try:
            chunk = input(f"\n[Speech Chunk #{chunk_num}] > ").strip()
            if not chunk:
                continue
            if chunk.lower() in {"quit", "exit", "q"}:
                print("Exiting speech director. Goodbye!")
                break
            process_speech_chunk(session_id, chunk, f"interactive-chunk-{chunk_num}")
            chunk_num += 1
        except (KeyboardInterrupt, EOFError):
            print("\nExiting speech director.")
            break


def run_demo_mode(session_id: str) -> None:
    """Demonstrate how speech chunks are converted to live slides on screen."""
    print("\nRunning automated speech-to-presentation demo...")
    demo_chunks = [
        "Welcome everyone! Today I am thrilled to introduce Stick, an AI that builds presentations live as you speak.",
        "The problem today is that preparing slide decks takes hours of manual formatting, designing layouts, and hunting for visuals.",
        "Stick solves this with three key innovations: real-time speech understanding, intelligent layout planning, and automatic AI visual generation.",
        "Our architecture has a voice ingestion layer, DeepSeek narrative reasoning, and Pollinations generative visuals.",
        "In our early benchmarks, teams created complete decks 4 times faster with a 95% user satisfaction rate.",
        "Our mission is simple: speak your ideas, and let AI build the presentation.",
    ]

    for i, chunk in enumerate(demo_chunks, 1):
        print(f"\n[Turn {i}/{len(demo_chunks)}] Simulating speaker talking...")
        process_speech_chunk(session_id, chunk, f"demo-turn-{i}")
        if i < len(demo_chunks):
            print("Waiting 5 seconds before next speech chunk...")
            time.sleep(5)

    print("\n🎉 Demo finished! Check your browser window to see all generated slides.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert chunks of speech to live presentation slides via AI.")
    parser.add_argument("--chunk", type=str, help="Process a single speech chunk and exit.")
    parser.add_argument("--demo", action="store_true", help="Run the automated multi-slide speech demo.")
    args = parser.parse_args()

    session_id, _ = ensure_server_session()

    if args.chunk:
        process_speech_chunk(session_id, args.chunk)
    elif args.demo:
        run_demo_mode(session_id)
    else:
        run_interactive_mode(session_id)


if __name__ == "__main__":
    main()
