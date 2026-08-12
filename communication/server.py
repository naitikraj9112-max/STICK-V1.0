"""Small HTTP boundary between the browser WebRTC client and the AI pipeline."""

import json
import logging
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

import requests

from communication.events import TranscriptEvent
from config import DATABASE_URL, GEMINI_API_KEY, HTTP_TIMEOUT_SECONDS, OPENAI_API_KEY, PPT_MASTER_ROOT, PRESENTATION_PORT, RECONNECT_MAX_ATTEMPTS, VIDEO_ENABLED
from presentation_generator.ppt_master_adapter import PptMasterAdapter
from presentation_context import normalize_output_language
from realtime_tools import build_realtime_session_config
from reliability import failure
from rendering import render_presentation
from session import session_summary

STATIC_DIR = Path(__file__).with_name("static")
OPENAI_CALL_URL = "https://api.openai.com/v1/realtime/calls"
LOGGER = logging.getLogger(__name__)


def create_webrtc_session(offer_sdp: str, output_language: str | None = None) -> str:
    """Send the browser SDP offer to OpenAI and return its SDP answer."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to .env before starting the application.")

    session = build_realtime_session_config(output_language)
    response = requests.post(
        OPENAI_CALL_URL,
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        files={
            # OpenAI expects sdp as a multipart form field, not a file upload.
            "sdp": (None, offer_sdp),
            "session": (None, json.dumps(session), "application/json"),
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.text


def ppt_master_status() -> str:
    if not PPT_MASTER_ROOT:
        return "unconfigured"
    adapter = PptMasterAdapter(PPT_MASTER_ROOT, "")
    return "ready" if adapter.scripts.is_dir() else "unavailable"


def start_communication_server(session_manager, host: str = "127.0.0.1", port: int = PRESENTATION_PORT, block: bool = True):
    """Serve the browser client and receive its OpenAI Realtime transcript events."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to .env before starting the application.")

    server = ThreadingHTTPServer((host, port), make_request_handler(session_manager))
    LOGGER.info("Presentation server listening on http://%s:%s", host, port)
    if block:
        server.serve_forever()
    return server


def make_request_handler(session_manager):
    """Create a handler with access to the session-scoped presentation pipeline."""

    class CommunicationHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            path = parsed.path

            if path == "/health":
                memory_status = session_manager.sample_memory_health()
                ppt_status = ppt_master_status()
                core_degraded = ppt_status == "unavailable"
                self.send_json({
                    "status": "degraded" if core_degraded else "healthy",
                    "backend": "healthy",
                    "neon": memory_status,
                    "openai_configuration": "healthy" if OPENAI_API_KEY else "unavailable",
                    "realtime": "ready",
                    "ppt_master": ppt_status,
                    "multimedia": {
                        "enabled": VIDEO_ENABLED,
                        "gemini_configured": bool(GEMINI_API_KEY),
                    },
                    "sessions": session_manager.health_summary(),
                })
                return

            if path == "/presentation/media":
                orchestrator = self._resolve_orchestrator(query)
                if not orchestrator:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                scene_ids = query.get("scene_id", [])
                if not scene_ids:
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                image_path = orchestrator.live_imagery.scene_image_map().get(scene_ids[0])
                if not image_path:
                    image_path = orchestrator.multimedia_manager.scene_image_map().get(scene_ids[0])
                if not image_path or not Path(image_path).is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                content = Path(image_path).read_bytes()
                suffix = Path(image_path).suffix.lower()
                mime = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                }.get(suffix, "application/octet-stream")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            if path == "/presentation":
                orchestrator = self._resolve_orchestrator(query)
                if not orchestrator:
                    self.send_json(failure("session", "Unknown or missing session_id"), HTTPStatus.NOT_FOUND)
                    return
                session = session_manager.get(orchestrator.session_id)
                scene_images = orchestrator.live_imagery.scene_image_map()
                scene_image_status = orchestrator.live_imagery.scene_status_map()
                rendered = render_presentation(
                    orchestrator.presentation_state,
                    session_id=orchestrator.session_id,
                    scene_images=scene_images,
                    scene_image_status=scene_image_status,
                )
                rendered["generation"] = orchestrator.presentation_generator.status()
                rendered["video"] = orchestrator.multimedia_manager.status()
                rendered["live_imagery"] = orchestrator.live_imagery.status_summary()
                rendered["session"] = session_summary(session) if session else {}
                self.send_json(rendered)
                return

            if path == "/presentation/download":
                orchestrator = self._resolve_orchestrator(query)
                if not orchestrator:
                    self.send_json(failure("session", "Unknown or missing session_id"), HTTPStatus.NOT_FOUND)
                    return
                artifact = orchestrator.presentation_generator.status().get("artifact_path")
                if not artifact or not Path(artifact).is_file():
                    self.send_json(failure("presentation_generator", "No generated presentation is available"), HTTPStatus.NOT_FOUND)
                    return
                content = Path(artifact).read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.presentationml.presentation")
                self.send_header("Content-Disposition", "attachment; filename=presentation.pptx")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            if path == "/presentation/video/status":
                orchestrator = self._resolve_orchestrator(query)
                if not orchestrator:
                    self.send_json(failure("session", "Unknown or missing session_id"), HTTPStatus.NOT_FOUND)
                    return
                self.send_json(orchestrator.multimedia_manager.status())
                return

            if path == "/presentation/video/download":
                orchestrator = self._resolve_orchestrator(query)
                if not orchestrator:
                    self.send_json(failure("session", "Unknown or missing session_id"), HTTPStatus.NOT_FOUND)
                    return
                status = orchestrator.multimedia_manager.status()
                artifact = status.get("artifact_path")
                if not artifact or not Path(artifact).is_file():
                    self.send_json(failure("multimedia", "No generated video is available"), HTTPStatus.NOT_FOUND)
                    return
                content = Path(artifact).read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Disposition", "attachment; filename=presentation.mp4")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            if path.startswith("/static/"):
                rel = path.removeprefix("/static/").lstrip("/")
                asset = (STATIC_DIR / rel).resolve()
                if not str(asset).startswith(str(STATIC_DIR.resolve())):
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                if not asset.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                mime = {
                    ".svg": "image/svg+xml",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                }.get(asset.suffix.lower(), "application/octet-stream")
                content = asset.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            if path != "/":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content = (STATIC_DIR / "index.html").read_text().replace("__RECONNECT_MAX_ATTEMPTS__", str(RECONNECT_MAX_ATTEMPTS)).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self):
            try:
                data = self.read_json()
                parsed = urlparse(self.path)
                path = parsed.path

                if path == "/session":
                    session = session_manager.create()
                    orchestrator = session_manager.get_orchestrator(session.session_id)
                    output_language = data.get("output_language")
                    if output_language:
                        orchestrator.presentation_state.setdefault("metadata", {})["output_language"] = normalize_output_language(output_language)
                    presentation = render_presentation(
                        orchestrator.presentation_state,
                        session_id=session.session_id,
                    )
                    self.send_json({
                        "session_id": session.session_id,
                        "session": session_summary(session),
                        "presentation": presentation,
                    })
                    return

                if path == "/session/disconnect":
                    session_id = data.get("session_id")
                    if session_id:
                        session_manager.disconnect(session_id)
                    self.send_json({"success": True})
                    return

                if path == "/realtime/session":
                    session_id = data.get("session_id")
                    if not session_id or not session_manager.connect(session_id):
                        self.send_json(failure("session", "Unknown session_id"), HTTPStatus.NOT_FOUND)
                        return
                    orchestrator = session_manager.get_orchestrator(session_id)
                    output_language = None
                    if orchestrator:
                        output_language = (orchestrator.presentation_state.get("metadata") or {}).get("output_language")
                    self.send_sdp(create_webrtc_session(data["sdp"], output_language))
                    return

                if path == "/scene":
                    session_id = data.get("session_id")
                    orchestrator = session_manager.get_orchestrator(session_id) if session_id else None
                    if not orchestrator:
                        self.send_json(failure("session", "Unknown session_id"), HTTPStatus.NOT_FOUND)
                        return
                    session_manager.note_transcript(session_id)
                    scene_update = data.get("scene_update") or data.get("scene")
                    if not scene_update:
                        self.send_json(failure("communication", "scene_update is required"), HTTPStatus.BAD_REQUEST)
                        return
                    call_id = data.get("call_id")
                    LOGGER.info("[%s] realtime scene call_id=%s action=%s", session_id, call_id, scene_update.get("action"))
                    result = orchestrator.apply_realtime_scene(scene_update, call_id)
                    self.send_json(result, HTTPStatus.OK if result.get("success") else HTTPStatus.BAD_REQUEST)
                    return

                if path == "/presentation/video/generate":
                    session_id = data.get("session_id")
                    orchestrator = session_manager.get_orchestrator(session_id) if session_id else None
                    if not orchestrator:
                        self.send_json(failure("session", "Unknown session_id"), HTTPStatus.NOT_FOUND)
                        return
                    correlation_id = data.get("correlation_id") or f"video-{session_id}"

                    def run_video() -> None:
                        try:
                            orchestrator.multimedia_manager.generate_video(
                                deepcopy(orchestrator.presentation_state),
                                correlation_id,
                            )
                        except Exception:
                            LOGGER.exception("[%s] video generation failed", session_id)

                    Thread(target=run_video, daemon=True).start()
                    self.send_json({
                        "success": True,
                        "message": "Video generation started.",
                        "video": orchestrator.multimedia_manager.status(),
                    })
                    return

                if path == "/transcript":
                    session_id = data.get("session_id")
                    orchestrator = session_manager.get_orchestrator(session_id) if session_id else None
                    if not orchestrator:
                        self.send_json(failure("session", "Unknown session_id"), HTTPStatus.NOT_FOUND)
                        return
                    session_manager.note_transcript(session_id)
                    event = TranscriptEvent(
                        transcript=data["transcript"],
                        is_final=data.get("is_final", False),
                        source="openai-realtime-webrtc",
                        event_id=data.get("event_id", "browser-event"),
                    )
                    LOGGER.info("[%s] transcript received event_id=%s final=%s", session_id, event.event_id, event.is_final)
                    result = orchestrator.receive_transcript(event.transcript, event.event_id, event.is_final)
                    session = session_manager.get(session_id)
                    if session:
                        session.execution_metadata["last_result"] = {
                            "planned": result.get("planned"),
                            "correlation_id": result.get("correlation_id"),
                            "scene_updated": result.get("scene_updated"),
                        }
                    self.send_json({
                        "planned": result["planned"],
                        "reason": result.get("reason", ""),
                        "correlation_id": event.event_id,
                        "session_id": session_id,
                        "scene_updated": result.get("scene_updated", False),
                    })
                    return

                self.send_error(HTTPStatus.NOT_FOUND)
            except KeyError as error:
                LOGGER.warning("Communication request missing field: %s", error)
                self.send_json(failure("communication", "Request could not be processed", retryable=False), HTTPStatus.BAD_REQUEST)
            except json.JSONDecodeError:
                LOGGER.warning("Communication request had invalid JSON")
                self.send_json(failure("communication", "Request could not be processed", retryable=False), HTTPStatus.BAD_REQUEST)
            except requests.HTTPError as error:
                detail = error.response.text[:200] if error.response is not None else str(error)
                LOGGER.warning("OpenAI Realtime request failed: %s", detail)
                self.send_json(failure("communication", "Realtime connection could not be established", retryable=True), HTTPStatus.BAD_GATEWAY)
            except (RuntimeError, requests.RequestException) as error:
                LOGGER.warning("Communication request failed: %s", error)
                self.send_json(failure("communication", "Request could not be processed", retryable=True), HTTPStatus.BAD_GATEWAY)

        def _resolve_orchestrator(self, query: dict):
            session_ids = query.get("session_id", [])
            if not session_ids:
                return None
            return session_manager.get_orchestrator(session_ids[0])

        def read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length))

        def send_sdp(self, sdp: str) -> None:
            content = sdp.encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/sdp")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, data: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            content = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, _format, *_args):
            return

    return CommunicationHandler
