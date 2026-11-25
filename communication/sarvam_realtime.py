"""Local WebSocket bridge for Sarvam's real-time Saaras transcription."""

import asyncio
import json
import logging
import threading

from sarvamai import AsyncSarvamAI, RealtimeAudioInput, RealtimeEnd
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from config import SARVAM_API_KEY, SARVAM_STT_MODEL, SARVAM_STT_WS_PORT, PRESENTATION_PORT

LOGGER = logging.getLogger(__name__)


class SarvamRealtimeBridge:
    """Proxy local browser PCM streams to Sarvam without exposing its API key."""

    def __init__(self, host: str = "127.0.0.1", port: int = SARVAM_STT_WS_PORT):
        self.host = host
        self.port = port
        self._loop = None
        self._server = None
        self._thread = None
        self._ready = threading.Event()
        self._startup_error = None

    @property
    def available(self) -> bool:
        return self._ready.is_set() and self._startup_error is None

    def start(self, timeout: float = 5.0) -> bool:
        self._thread = threading.Thread(target=self._run, name="sarvam-stt-websocket", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            LOGGER.error("Sarvam realtime bridge did not start before timeout")
            return False
        if self._startup_error:
            LOGGER.error("Sarvam realtime bridge failed to start: %s", self._startup_error)
            return False
        LOGGER.info("Sarvam realtime STT bridge listening on ws://%s:%s", self.host, self.port)
        return True

    def stop(self, timeout: float = 3.0) -> None:
        if not self._loop or not self._server:
            return

        async def close_server():
            self._server.close()
            await self._server.wait_closed()

        try:
            future = asyncio.run_coroutine_threadsafe(close_server(), self._loop)
            future.result(timeout=timeout)
        except Exception:
            LOGGER.warning("Sarvam realtime bridge shutdown was not graceful")
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            async def bind_server():
                return await serve(
                    self._handle_client,
                    self.host,
                    self.port,
                    origins=[
                        f"http://127.0.0.1:{PRESENTATION_PORT}",
                        f"http://localhost:{PRESENTATION_PORT}",
                    ],
                    max_size=32_768,
                    ping_interval=20,
                    ping_timeout=20,
                )

            self._server = self._loop.run_until_complete(bind_server())
        except Exception as error:
            self._startup_error = error
            self._ready.set()
            self._loop.close()
            return

        self._ready.set()
        self._loop.run_forever()
        self._loop.close()

    async def _handle_client(self, browser):
        if not SARVAM_API_KEY:
            await browser.send(json.dumps({"event": "error", "fatal": True, "message": "Sarvam speech recognition is not configured."}))
            return

        client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)
        try:
            async with client.speech_to_text_realtime_streaming.connect(
                language_code="auto",
                model=SARVAM_STT_MODEL,
                stream_type="fast",
                mode="transcribe",
                endpointing="vad",
                encoding="linear16",
                sample_rate="16000",
            ) as sarvam:
                async def send_audio():
                    async for raw_message in browser:
                        try:
                            message = json.loads(raw_message)
                        except (TypeError, json.JSONDecodeError):
                            continue
                        event = message.get("event")
                        if event == "audio_input":
                            audio = message.get("audio", "")
                            if not isinstance(audio, str) or len(audio) > 22_000:
                                continue
                            await sarvam.send_realtime_audio_input(RealtimeAudioInput(audio=audio))
                        elif event == "end":
                            await sarvam.send_realtime_end(RealtimeEnd())
                            return

                async def send_transcripts():
                    async for event in sarvam:
                        payload = {"event": getattr(event, "event", "")}
                        for field in ("text", "language", "language_confidence", "code", "message", "is_fatal"):
                            value = getattr(event, field, None)
                            if value is not None:
                                payload[field] = value
                        await browser.send(json.dumps(payload, ensure_ascii=False))
                        if payload["event"] == "session.end" or (payload["event"] == "error" and payload.get("is_fatal")):
                            return

                sender = asyncio.create_task(send_audio())
                receiver = asyncio.create_task(send_transcripts())
                done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
                if sender in done:
                    try:
                        await asyncio.wait_for(receiver, timeout=5)
                    except asyncio.TimeoutError:
                        pass
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        except ConnectionClosed:
            pass
        except Exception:
            LOGGER.exception("Sarvam realtime transcription connection failed")
            try:
                await browser.send(json.dumps({
                    "event": "error",
                    "fatal": True,
                    "message": "Sarvam live transcription could not connect. Restart Stick and try again.",
                }))
            except ConnectionClosed:
                pass
