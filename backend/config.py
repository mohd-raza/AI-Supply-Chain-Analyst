import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level above backend/)
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Azure OpenAI — support both AZURE_OPENAI_KEY and AZURE_OPENAI_API_KEY
AZURE_OPENAI_API_KEY: str = (
    os.getenv("AZURE_OPENAI_API_KEY")
    or os.getenv("AZURE_OPENAI_KEY")
    or ""
)
AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.2")
AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
REASONING_EFFORT: str = os.getenv("REASONING_EFFORT", "xhigh")

# Paths
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "chainmind.db"
ML_DIR = BASE_DIR / "ml"
COST_MODEL_PATH = ML_DIR / "cost_model.pkl"
TRANSIT_MODEL_PATH = ML_DIR / "transit_model.pkl"

# App settings
APP_TITLE = "ChainMind — Supply Chain Optimizer"
APP_VERSION = "1.0.0"
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
]

def validate_config() -> list[str]:
    """Return list of missing required config values."""
    missing = []
    if not AZURE_OPENAI_API_KEY:
        missing.append("AZURE_OPENAI_KEY / AZURE_OPENAI_API_KEY")
    if not AZURE_OPENAI_ENDPOINT:
        missing.append("AZURE_OPENAI_ENDPOINT")
    return missing
