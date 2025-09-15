import re
from rapidfuzz import process, fuzz

TEAM_MAP = {
    "NFL": ["Cowboys","Eagles","Patriots","Jets","Giants","Chiefs","49ers","Packers"],
    "NBA": ["Lakers","Celtics","Heat","Warriors","Bucks","Knicks"],
    "MLB": ["Yankees","Dodgers","Astros","Braves","Mets"],
    "NHL": ["Rangers","Bruins","Maple Leafs","Lightning"]
}

def detect_league(text: str) -> str | None:
    t = text.lower()
    if "nfl" in t or "football" in t: return "NFL"
    if "nba" in t or "basketball" in t: return "NBA"
    if "mlb" in t or "baseball" in t: return "MLB"
    if "nhl" in t or "hockey" in t: return "NHL"
    return None

def extract_odds(text: str) -> int | None:
    m = re.search(r"([+-]\d{2,4})\b", text)
    return int(m.group(1)) if m else None

def extract_stake(text: str) -> float | None:
    m = re.search(r"(?:stake|risk|wager)\\s*\\$?([\\d,.]+)", text, re.I)
    if m:
        return float(m.group(1).replace(",",""))
    return None

def best_team_match(league: str, text: str) -> list[str]:
    teams = TEAM_MAP.get(league, [])
    found = process.extract(text, teams, scorer=fuzz.partial_ratio, limit=4)
    return [t for t,score,idx in found if score >= 70]
