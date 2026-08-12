"""Small reliability helpers shared by component-specific failure boundaries."""

import logging
import time

from config import LLM_MAX_RETRIES, LLM_RETRY_BACKOFF_SECONDS

LOGGER = logging.getLogger(__name__)


def is_retryable(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return True
    name = type(error).__name__.lower()
    return any(word in name for word in ("timeout", "connection", "rate", "serviceunavailable", "internalserver"))


def retry_call(operation, component: str, correlation_id: str = "-"):
    """Bounded exponential retry; invalid outputs are deliberately not retried."""
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            return operation()
        except Exception as error:
            if not is_retryable(error) or attempt == LLM_MAX_RETRIES:
                raise
            LOGGER.warning("[%s] %s retry %s/%s after transient failure", correlation_id, component, attempt + 1, LLM_MAX_RETRIES)
            time.sleep(LLM_RETRY_BACKOFF_SECONDS * (2 ** attempt))


def failure(component: str, message: str, retryable: bool = False) -> dict:
    return {"success": False, "error": {"type": component, "message": message, "retryable": retryable}}
