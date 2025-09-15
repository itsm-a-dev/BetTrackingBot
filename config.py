# config.py
import os

def _get_env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except Exception:
        return default

def _get_env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default

# Discord
TRACK_CHANNEL_ID = _get_env_int("TRACK_CHANNEL_ID", 0)  # set in env
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# Parsing confidence gate (0-1)
CONFIDENCE_THRESHOLD = _get_env_float("CONFIDENCE_THRESHOLD", 0.75)

# Update intervals (seconds)
SCORES_UPDATE_INTERVAL = _get_env_int("SCORES_UPDATE_INTERVAL", 60)   # team scores
PROPS_UPDATE_INTERVAL  = _get_env_int("PROPS_UPDATE_INTERVAL", 20)   # props refresh faster

# Debug flags
DEBUG_MODE = os.getenv("DEBUG_MODE", "0") == "1"
OCR_DEBUG  = os.getenv("OCR_DEBUG", "0") == "1"

# Optional: ESPN fetch timeouts
HTTP_TIMEOUT_SECONDS = _get_env_int("HTTP_TIMEOUT_SECONDS", 15)

# Optional: Catalog refresh frequency (seconds) for dynamic team/player maps
CATALOG_REFRESH_INTERVAL = _get_env_int("CATALOG_REFRESH_INTERVAL", 24 * 60 * 60)

# Optional: Control which soccer competitions to aggregate in parsing.py
SOCCER_COMPETITIONS = os.getenv("SOCCER_COMPETITIONS", "soccer/eng.1,soccer/esp.1,soccer/ger.1,soccer/ita.1,soccer/usa.1").split(",")
