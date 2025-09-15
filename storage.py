# storage.py
import json
import os

TRACKED_FILE = "tracked_bets.json"

def save_tracked(tracked: dict):
    try:
        with open(TRACKED_FILE, "w", encoding="utf-8") as f:
            json.dump(tracked, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed to save tracked bets: {e}")

def load_tracked() -> dict:
    if not os.path.exists(TRACKED_FILE):
        return {}
    try:
        with open(TRACKED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load tracked bets: {e}")
        return {}
