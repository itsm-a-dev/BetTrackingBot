import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from rapidfuzz import process, fuzz

# Minimal team lists (extend as needed)
TEAM_MAP = {
    "NFL": ["Patriots","Dolphins","Cowboys","Eagles","Jets","Giants","Chiefs","49ers","Packers","Bills","Vikings","Falcons","Seahawks","Rams","Saints","Lions","Bears","Broncos","Chargers","Raiders","Texans","Jaguars","Commanders","Ravens","Browns","Steelers","Bengals","Titans","Colts","Buccaneers","Panthers","Cardinals"],
    "NBA": ["Lakers","Celtics","Heat","Warriors","Bucks","Knicks","Mavericks","Suns","Clippers","Nuggets","76ers","Raptors","Bulls","Hawks","Cavaliers","Grizzlies","Pelicans","Wolves","Kings","Thunder","Spurs","Pistons","Pacers","Magic","Wizards","Hornets","Jazz","Blazers","Rockets"],
    "MLB": ["Yankees","Dodgers","Astros","Braves","Mets","Red Sox","Cubs","Giants","Phillies","Padres","Rays","Blue Jays","Cardinals","Brewers","Twins","Rangers","Mariners","Guardians"],
    "NHL": ["Rangers","Bruins","Maple Leafs","Lightning","Golden Knights","Panthers","Avalanche","Oilers","Penguins","Capitals","Devils","Stars","Wild","Jets","Canucks","Flames","Kings","Sharks"],
}

# Prop categories to normalize
PROP_STATS = [
    "passing yards","rushing yards","receiving yards","receptions","attempts","completions","passing touchdowns","rushing touchdowns","receiving touchdowns","touchdowns","interceptions",
    "points","rebounds","assists","pra","threes","three pointers","three-point field goals",
    "shots on goal","saves","hits",
    "outs","strikeouts","hits allowed","earned runs",
    "anytime td","anytime touchdown","to score",
]

# Precompiled regexes
RE_AMERICAN_ODDS = re.compile(r"(?<!\d)([+-]\d{2,4})\b")       # -115, +105
RE_MONEY = re.compile(r"\$([\d,.]+)")
RE_STAKE = re.compile(r"(?:stake|risk|wager)\s*\$?([\d,.]+)", re.I)
RE_PAYOUT = re.compile(r"(?:payout|to\s*win)\s*\$?([\d,.]+)", re.I)
RE_OU = re.compile(r"\b(over|under)\s*([0-9]+(?:\.[0-9])?)\b", re.I)
RE_TEAM_SPREAD = re.compile(r"\b([A-Za-z .'-]+?)\s*([+-]\d+(?:\.\d)?)\b")
RE_VS = re.compile(r"\b([A-Za-z .'-]+)\s+@\s+([A-Za-z .'-]+)|\b([A-Za-z .'-]+)\s+vs\.?\s+([A-Za-z .'-]+)", re.I)

# Legs segmentation: lines that start with Over/Under/Yes/No or contain a player + stat phrase
RE_LEG_START = re.compile(r"^\s*(over|under|yes|no)\b|^\s*\d+\+|\bto\s+record\b|\banytime\s+td\b|\bto\s+score\b", re.I)
RE_PLAYER_STAT = re.compile(r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z'.-]+)+)\s*[-–—:]\s*(?P<stat>[A-Za-z ]+)", re.I)

@dataclass
class Leg:
    type: str                   # 'prop' | 'total' | 'spread' | 'moneyline' | 'unknown'
    # Prop fields
    player: Optional[str] = None
    stat: Optional[str] = None  # normalized stat name
    side: Optional[str] = None  # 'over' | 'under' | 'yes' | 'no'
    line: Optional[float] = None
    target_text: Optional[str] = None  # e.g., '175+' or 'Yes'
    # Team market fields
    team: Optional[str] = None
    # Live tracking fields
    game_teams: Optional[List[str]] = None
    current_value: Optional[float] = None
    result: str = "pending"     # 'pending' | 'won' | 'lost' | 'push'

@dataclass
class ParsedSlip:
    bet_type: str               # 'single' | 'parlay'
    league: str
    odds: Optional[int] = None
    stake: Optional[float] = None
    payout: Optional[float] = None
    legs: Optional[List[Leg]] = None


def detect_league(text: str) -> Optional[str]:
    t = text.lower()
    if "nfl" in t or "football" in t: return "NFL"
    if "nba" in t or "basketball" in t: return "NBA"
    if "mlb" in t or "baseball" in t: return "MLB"
    if "nhl" in t or "hockey" in t: return "NHL"
    return None


def extract_odds(text: str) -> Optional[int]:
    m = RE_AMERICAN_ODDS.search(text)
    return int(m.group(1)) if m else None


def extract_stake(text: str) -> Optional[float]:
    m = RE_STAKE.search(text)
    if m: return float(m.group(1).replace(",", ""))
    m2 = RE_MONEY.search(text)
    if m2: return float(m2.group(1).replace(",", ""))
    return None


def extract_payout(text: str) -> Optional[float]:
    m = RE_PAYOUT.search(text)
    if m: return float(m.group(1).replace(",", ""))
    return None


def best_team_match(league: str, text: str, limit: int = 4, threshold: int = 70) -> List[str]:
    teams = TEAM_MAP.get(league, [])
    found = process.extract(text, teams, scorer=fuzz.partial_ratio, limit=limit)
    return [t for t, score, _ in found if score >= threshold]


def extract_game_teams_from_text(league: str, text: str) -> List[str]:
    m = RE_VS.search(text)
    candidates: List[str] = []
    if m:
        parts = [p for p in m.groups() if p]
        for p in parts:
            matched = best_team_match(league, p, limit=1, threshold=60)
            if matched:
                candidates.append(matched[0])
    if len(candidates) < 2:
        pool = best_team_match(league, text, limit=6, threshold=65)
        seen = set()
        for t in pool:
            if t not in seen:
                candidates.append(t); seen.add(t)
            if len(candidates) == 2:
                break
    return candidates[:2]


def normalize_stat(stat: str) -> str:
    s = stat.lower().strip()
    for cat in PROP_STATS:
        if s in cat or cat in s:
            return cat
    return s


def classify_line_block(league: str, block: str) -> Leg:
    # Player prop?
    pm = RE_PLAYER_STAT.search(block)
    ou = RE_OU.search(block)
    if pm:
        player = pm.group("name").strip()
        stat = normalize_stat(pm.group("stat"))
        side = None
        line = None
        target_text = None
        if ou:
            side = ou.group(1).lower()
            line = float(ou.group(2))
            target_text = f"{side} {line}"
        else:
            # Yes/No props like Anytime TD
            if "anytime td" in block.lower() or "to score" in block.lower():
                target_text = "Yes" if "yes" in block.lower() else "No" if "no" in block.lower() else None
                side = "yes" if "yes" in block.lower() else "no" if "no" in block.lower() else None
                stat = "anytime td"
        return Leg(type="prop", player=player, stat=stat, side=side, line=line, target_text=target_text)

    # Totals (non-player)
    if ou:
        side = ou.group(1).lower()
        line = float(ou.group(2))
        return Leg(type="total", side=side, line=line, target_text=f"{side} {line}")

    # Spread "Team -3.5"
    sp = RE_TEAM_SPREAD.search(block)
    if sp:
        team_guess = sp.group(1).strip()
        line = float(sp.group(2))
        best = best_team_match(league, team_guess, limit=1, threshold=60)
        team = best[0] if best else team_guess
        return Leg(type="spread", team=team, line=line, target_text=f"{team} {line}")

    # ML hints
    if re.search(r"\b(to win|moneyline|ml)\b", block, re.I):
        teams = best_team_match(league, block, limit=2, threshold=75)
        team = teams[0] if teams else None
        return Leg(type="moneyline", team=team, target_text=team or "ML")

    return Leg(type="unknown", target_text=block.strip()[:60])


def split_into_leg_blocks(text: str) -> List[str]:
    # Split on lines; group consecutive lines that belong to the same leg
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    blocks: List[str] = []
    cur: List[str] = []
    for ln in lines:
        if RE_LEG_START.search(ln) and cur:
            blocks.append("\n".join(cur)); cur = [ln]
        else:
            cur.append(ln)
    if cur:
        blocks.append("\n".join(cur))
    # Heuristic: filter out obvious headers/footers
    cleaned = []
    for b in blocks:
        low = b.lower()
        if any(k in low for k in ["parlay", "sgp", "wager", "payout", "odds", "hard rock", "bet slip", "sports bet"]):
            continue
        cleaned.append(b)
    return cleaned


def parse_slip(text: str) -> ParsedSlip:
    league = detect_league(text) or "NFL"
    odds = extract_odds(text)
    stake = extract_stake(text)
    payout = extract_payout(text)

    blocks = split_into_leg_blocks(text)
    legs: List[Leg] = []
    for b in blocks:
        leg = classify_line_block(league, b)
        # Try to attach game teams for live tracking
        leg.game_teams = extract_game_teams_from_text(league, text)
        legs.append(leg)

    bet_type = "parlay" if len(legs) > 1 else "single"
    return ParsedSlip(bet_type=bet_type, league=league, odds=odds, stake=stake, payout=payout, legs=legs)


# Legacy exports used elsewhere
def classify_market(text: str, league: str) -> Dict[str, Any]:
    # Compatibility shim: returns a simplified single-leg dict if needed
    parsed = parse_slip(text)
    if not parsed.legs:
        return {"type": "unknown"}
    leg = parsed.legs[0]
    d = asdict(leg)
    d["league"] = parsed.league
    d["bet_type"] = parsed.bet_type
    return d
