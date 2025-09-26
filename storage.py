import json
import logging
import os
from typing import Dict, Any

logger = logging.getLogger("storage")
DEFAULT_PATH = "tracked_bets.json"


def save_tracked_bets(bets: Dict[str, Any], path: str = DEFAULT_PATH) -> None:
    """Atomically save tracked bets to JSON."""
    try:
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(bets, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        logger.info(f"Saved {len(bets)} tracked bets to {path}.")
    except Exception as e:
        logger.exception(f"Failed to save tracked bets: {e}")


def load_tracked_bets(path: str = DEFAULT_PATH) -> Dict[str, Any]:
    """Load tracked bets from JSON, or return empty dict if missing/corrupt."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} tracked bets from {path}.")
        return data
    except FileNotFoundError:
        logger.warning("No tracked_bets.json found — starting empty.")
        return {}
    except Exception as e:
        logger.exception(f"Failed to load tracked bets: {e}")
        return {}
