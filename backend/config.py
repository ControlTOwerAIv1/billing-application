import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

def load_env():
    """Reads .env file and populates os.environ if present."""
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

load_env()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "orderbot.db"))
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

raw_model = os.getenv("LLM_MODEL", "gemini/gemini-3.5-flash-lite")
if raw_model.startswith("gemini-") and not raw_model.startswith("gemini/"):
    LLM_MODEL = f"gemini/{raw_model}"
else:
    LLM_MODEL = raw_model
