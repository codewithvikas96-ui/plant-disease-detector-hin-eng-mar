"""Paths, environment and constants shared by the whole backend.

Importing this module loads .env, so anything that reads the environment
(the Groq assistant, the rate limits) must import it first.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env")

# Knowledge that ships with the app (versioned in git).
DATA_DIR = BACKEND_DIR / "data"
REMEDIES_PATH = DATA_DIR / "remedies.json"
PRICES_PATH = DATA_DIR / "prices.json"
ORGANIC_PATH = DATA_DIR / "organic.json"

MODELS_DIR = BACKEND_DIR / "models"
MODEL_PATH = MODELS_DIR / "plant_disease_model.pt"

# State the server writes while running (git-ignored).
VAR_DIR = BACKEND_DIR / "var"
TTS_CACHE_DIR = VAR_DIR / "tts_cache"
SCANS_DB = VAR_DIR / "scans.db"

FRONTEND_DIR = ROOT_DIR / "frontend"

SUPPORTED_LANGUAGES = ("mr", "hi", "en")
LANG_PATTERN = "^(mr|hi|en)$"

# Below this top-1 probability we tell the farmer we are unsure rather than
# naming a disease. A wrong confident answer costs them a spray they did not need.
CONFIDENCE_THRESHOLD = 0.60

MAX_UPLOAD_BYTES = 12 * 1024 * 1024  # phone photos are ~2-5 MB; 12 MB is generous
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
MAX_AUDIO_BYTES = 5 * 1024 * 1024  # 30 s of opus is ~250 KB

AI_RATE_LIMIT_PER_MIN = int(os.environ.get("AI_RATE_LIMIT_PER_MIN", "20"))
REPORT_RATE_LIMIT_PER_MIN = 10

PORT = os.environ.get("PORT", "8000")
