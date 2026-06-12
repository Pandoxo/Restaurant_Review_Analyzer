"""
Configuration module — loads environment variables and defines project constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "reviews.db"

# ── API Keys ───────────────────────────────────────────────────
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
OUTSCRAPER_API_KEY = os.getenv("OUTSCRAPER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ── LLM Backend ────────────────────────────────────────────────
# "gemini" = Google Gemini API (free tier, no GPU needed)
# "ollama" = Local Ollama (requires GPU)
LLM_BACKEND = os.getenv("LLM_BACKEND", "gemini")

# Ollama settings (only used if LLM_BACKEND=ollama)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Gemini settings (only used if LLM_BACKEND=gemini)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_DELAY_SECONDS = float(os.getenv("GEMINI_DELAY_SECONDS", "0.3"))

# ── Search Parameters ─────────────────────────────────────────
CITY = "Poznań"
SEARCH_QUERY = "restaurants in Poznań"
MAX_RESTAURANTS = 10
MAX_REVIEWS_PER_RESTAURANT = 1500  # safety cap

# ── Analysis Thresholds ───────────────────────────────────────
# Suspicion scoring weights
WEIGHT_STAFF_NAME_ONLY = 0.30
WEIGHT_IN_BURST = 0.25
WEIGHT_SHALLOW_REVIEW = 0.20
WEIGHT_LOW_REVIEWER_HISTORY = 0.15
WEIGHT_GENERIC_LANGUAGE = 0.10

# A review is flagged if its suspicion score exceeds this
SUSPICION_THRESHOLD = 0.60

# A restaurant is flagged if this % of its reviews are suspicious
RESTAURANT_FLAG_THRESHOLD = 0.10  # 10%

# Burst detection: sliding window size in days, and minimum reviews
# to consider a window a "burst"
BURST_WINDOW_DAYS = 14
BURST_MIN_REVIEWS = 5
