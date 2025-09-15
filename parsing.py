import re
from rapidfuzz import process, fuzz

# Minimal team lists (extend as needed)
TEAM_MAP = {
    "NFL": ["Patriots", "Dolphins", "Cowboys", "Eagles", "Jets", "Giants", "Chiefs", "49ers", "Packers", "Bills"],
    "NBA": ["Lakers", "Celtics", "Heat", "Warriors", "Bucks", "Knicks", "Mavericks", "Suns"],
    "MLB": ["Yankees", "Dodgers", "Astros", "Braves", "Mets"],
    "NHL": ["Rangers", "Bruins", "Maple Leafs", "Lightning", "Golden Knights"],
}

# Common prop stat categories and aliases
PROP_STATS = [
    "passing yards", "rushing yards", "receiving yards", "receptions", "attempts",
    "completions", "touchdowns", "interceptions",
    "points", "rebounds", "assists", "pra", "threes", "three pointers",
    "shots on goal", "saves", "hits",
    "outs", "strikeouts", "hits allowed", "earned runs",
]

# Precompiled regexes
RE_AMERICAN_ODDS = re.compile(r"(?<!\d)([+-]\d{2,4})\b")  # -115, +105
RE_ML_HINT = re.compile(r"\b(to win|moneyline|ml)\b", re.I)
RE_OU = re.compile(r"\b(over|under)\s*([0-9]+(?:\.[0-9])?)\b", re.I)
RE_SPREAD = re.compile(r"\b([A-Za-z .'-]+?)\s*([+-]\d+(?:\.\d)?)\b")  # Team -3.5
RE_DOLLAR = re.compile(r"\$([\d,.]+)")
RE_STAKE = re.compile(r"(?:stake|risk|wager)\s*\$?([\d,.]+)", re.I)
RE_PLAYER_LINE = re.compile(
    r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z'.-]+)+)\s*[-–—:]\s*(?P<stat>[A-Za-z ]+)",
    re.I,
)  # "Drake Maye - Passing Yards"
RE_VS = re.compile(r"\b([A-Za-z .'-]+)\s+@\s+([A-Za-z .'-]+)|\b([A-Za-z .'-]+)\s+vs\.?\s+([A-Za-z .'-]+)", re.I)


def detect_league(text: str) -> str | None:
    t = text.lower()
    if "nfl" in t or "football" in t: return "NFL"
    if "nba" in t or "basketball" in t: return "NBA"
    if "mlb" in t or "baseball" in t: return "MLB"
    if "nhl" in t or "hockey" in t: return "NHL"
    return None


def extract_odds(text: str) -> int | None:
    m = RE_AMERICAN_ODDS.search(text)
    return int(m.group(1)) if m else None


def extract_stake(text: str) -> float | None:
    m = RE_STAKE.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    m2 = RE_DOLLAR.search(text)
    if m2:
        return float(m2.group(1).replace(",", ""))
    return None


def best_team_match(league: str, text: str, limit: int = 4, threshold: int = 70) -> list[str]:
    teams = TEAM_MAP.get(league, [])
    found = process.extract(text, teams, scorer=fuzz.partial_ratio, limit=limit)
    return [t for t, score, _ in found if score >= threshold]


def extract_game_teams_from_text(league: str, text: str) -> list[str]:
    # Try to read "Patriots @ Dolphins" or "Patriots vs Dolphins"
    m = RE_VS.search(text)
    candidates = []
    if m:
        parts = [p for p in m.groups() if p]
        for p in parts:
            matched = best_team_match(league, p, limit=1, threshold=60)
            if matched:
                candidates.append(matched[0])
    # Fallback: fuzzy scan entire text
    if len(candidates) < 2:
        pool = best_team_match(league, text, limit=6, threshold=65)
        # Deduplicate while keeping order
        seen = set()
        for t in pool:
            if t not in seen:
                candidates.append(t)
                seen.add(t)
            if len(candidates) == 2:
                break
    return candidates[:2]


def detect_player_prop(text: str) -> dict | None:
    # Look for "Name - Stat" and OU value
    m = RE_PLAYER_LINE.search(text)
    if not m:
        return None
    name = m.group("name").strip()
    stat = m.group("stat").strip().lower()

    # Normalize stat with our list if possible
    def norm_stat(s: str) -> str:
        s = s.lower().strip()
        for cat in PROP_STATS:
            if s in cat or cat in s:
                return cat
        return s

    stat = norm_stat(stat)

    ou = RE_OU.search(text)
    side, line = (None, None)
    if ou:
        side = ou.group(1).lower()
        line = float(ou.group(2))

    return {
        "market": "prop",
        "player": name,
        "stat": stat,
        "side": side,   # over/under or None
        "line": line,   # float or None
    }


def classify_market(text: str, league: str) -> dict:
    """
    Returns a dict describing the market:
    - For props: {type:'prop', player, stat, side, line}
    - For totals: {type:'total', side, line}
    - For spread: {type:'spread', team, line}
    - For moneyline: {type:'moneyline', team}
    """
    # 1) Player prop?
    prop = detect_player_prop(text)
    if prop:
        return {"type": "prop", **prop}

    t = text.lower()

    # 2) Total (Over/Under)
    ou = RE_OU.search(text)
    if ou:
        return {
            "type": "total",
            "side": ou.group(1).lower(),
            "line": float(ou.group(2)),
        }

    # 3) Spread "Team -3.5"
    sp = RE_SPREAD.search(text)
    if sp:
        team = sp.group(1).strip()
        line = float(sp.group(2))
        # Tighten team guess with fuzzy
        best = best_team_match(league, team, limit=1, threshold=60)
        team = best[0] if best else team
        return {"type": "spread", "team": team, "line": line}

    # 4) Moneyline hints ("to win", "ML")
    if RE_ML_HINT.search(text):
        # try to pick a single team (first mentioned)
        teams = extract_game_teams_from_text(league, text)
        sel = teams[0] if teams else None
        return {"type": "moneyline", "team": sel}

    # 5) Fallback: if exactly one strong team found, assume ML
    teams = best_team_match(league, text, limit=2, threshold=80)
    if len(teams) == 1:
        return {"type": "moneyline", "team": teams[0]}

    # Unknown
    return {"type": "unknown"}
