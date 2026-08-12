"""Start the browser WebRTC communication layer."""

import logging
import signal
import sys

from communication.server import start_communication_server
from config import OPENAI_API_KEY, PRESENTATION_PORT
from session_manager import SessionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger(__name__)


def main() -> None:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to .env before starting the application.")
    session_manager = SessionManager()
    server = start_communication_server(session_manager, host="127.0.0.1", port=PRESENTATION_PORT, block=False)

    def shutdown(_signum=None, _frame=None):
        LOGGER.info("Shutting down Stick presentation server")
        session_manager.shutdown_all()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    LOGGER.info("Stick presentation server ready on port %s", PRESENTATION_PORT)
    server.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"Cannot start realtime presentation: {error}")
    except KeyboardInterrupt:
        print("Realtime presentation stopped.")
