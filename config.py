import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

DEEPSEEK_API_KEY = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
CF_WORKER_URL = (os.getenv("CF_WORKER_URL") or "").strip().rstrip("/")
POLLINATIONS_API_KEY = (os.getenv("POLLINATIONS_API_KEY") or "").strip()
DATABASE_URL = os.getenv("DATABASE_URL")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
LLM_RETRY_BACKOFF_SECONDS = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "0.5"))
DATABASE_TIMEOUT_SECONDS = int(os.getenv("DATABASE_TIMEOUT_SECONDS", "8"))
PRESENTATION_PORT = int(os.getenv("PRESENTATION_PORT", "8001"))
PRESENTATION_LANGUAGE = os.getenv("PRESENTATION_LANGUAGE", "en").strip().lower() or "en"
PPT_MASTER_ROOT = os.getenv("PPT_MASTER_ROOT", "")
PPT_MASTER_WORKSPACE = os.getenv("PPT_MASTER_WORKSPACE", "")
PRESENTATION_ARTIFACT_DIR = Path(os.getenv("PRESENTATION_ARTIFACT_DIR", str(Path(__file__).with_name("artifacts"))))
GENERATION_MAX_CORRECTIONS = int(os.getenv("GENERATION_MAX_CORRECTIONS", "1"))
GENERATION_DEBOUNCE_SECONDS = float(os.getenv("GENERATION_DEBOUNCE_SECONDS", "0.5"))
MIN_NEW_SCENE_SECONDS = float(os.getenv("MIN_NEW_SCENE_SECONDS", "6"))
# Gemini multimedia (optional; used for image fallback and video narration/TTS)
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash")
SARVAM_API_KEY = (os.getenv("SARVAM_API_KEY") or "").strip()
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v4-flash").strip()
SARVAM_TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "").strip()
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v4").strip()
SARVAM_STT_WS_PORT = int(os.getenv("SARVAM_STT_WS_PORT", "8765"))

MEDIA_MAX_CONCURRENCY = int(os.getenv("MEDIA_MAX_CONCURRENCY", "4"))
MEDIA_TIMEOUT_SECONDS = float(os.getenv("MEDIA_TIMEOUT_SECONDS", "60"))
MEDIA_RETRIES = int(os.getenv("MEDIA_RETRIES", "2"))
MEDIA_RETRY_BACKOFF_SECONDS = float(os.getenv("MEDIA_RETRY_BACKOFF_SECONDS", "0.75"))

VIDEO_ENABLED = os.getenv("VIDEO_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
VIDEO_OUTPUT_FORMAT = os.getenv("VIDEO_OUTPUT_FORMAT", "mp4")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")

TTS_VOICE = os.getenv("TTS_VOICE", "Kore")
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.0"))
