# parsing.py
import re
from dataclasses import dataclass
from typing import Optional, List
from rapidfuzz import process, fuzz

# Extend these lists as needed
TEAM_MAP = {
    "NFL": [
        "Patriots","Dolphins","Cowboys","Eagles","Jets","Giants","Chiefs","49ers","Packers","Bills",
        "Vikings","Falcons","Seahawks","Rams","Saints","Lions","Bears","Broncos","Chargers","Raiders",
        "Texans","Jaguars","Commanders","Ravens","Browns","Steelers","Bengals","Titans","Colts",
        "Buccaneers","Panthers","Cardinals"
    ],
    "NBA": [
        "Lakers","Celtics","Heat","Warriors","Bucks","Knicks","Mavericks","Suns","Clippers","Nuggets",
        "76ers","Raptors","Bulls","Hawks","Cavaliers","Grizzlies","Pelicans","Wolves","Kings","Thunder",
        "Spurs","Pistons","Pacers","Magic","Wizards","Hornets","Jazz","Blazers","Rockets"
    ],
    "MLB": [
        "Yankees","Dodgers","Astros","Braves","Mets","Red Sox","Cubs","Giants","Phillies","Padres",
        "Rays","Blue Jays","Cardinals","Brewers","Twins","Rangers","Mariners","Guardians","Pirates",
        "Nationals","Athletics","Rockies","Diamondbacks","Tigers","Royals","Orioles","White Sox","Marlins","Angels"
    ],
    "NHL": [
        "Rangers","Bruins","Maple Leafs","Lightning","Golden Knights","Panthers","Avalanche","Oilers",
        "Penguins","Capitals","Devils","Stars","Wild","Jets","Canucks","Flames","Kings","Sharks",
        "Senators","Sabres","Predators","Hurricanes","Blue Jackets","Ducks","Coyotes","Flyers","Kraken","Islanders","Red Wings"
    ],
    # Treated as special cases via keywords rather than team matching
    "UFC": [],
    "SOCCER": []
}

PROP_STATS = [
    "passing yards","rushing yards","receiving yards","receptions","attempts","completions",
    "passing touchdowns","rushing touchdowns","receiving touchdowns","touchdowns","interceptions",
    "points","rebounds","assists","pra","threes","three pointers","three-point field goals",
    "shots on goal","saves","hits","total bases","strikeouts","earned runs","outs","hits allowed",
    "anytime td","anytime touchdown","to score","total rounds","total match points","total runs","total goals",
    "passing attempts","passing completions","sacks","tackles"
]

# Regex patterns
RE_AMERICAN_ODDS   = re.compile(r"(?<!\d)([+-]\d{2,4})\b")
RE_MONEY           = re.compile(r"\$([\d,.]+)")
RE_STAKE           = re.compile(r"(?:stake|risk|wager)\s*\$?([\d,.]+)", re.I)
RE_PAYOUT          = re.compile(r"(?:payout|to\s*win)\s*\$?([\d,.]+)", re.I)
RE_OU              = re.compile(r"\b(over|under)\s*([0-9]+(?:\.[0-9])?)\b", re.I)
RE_TEAM_SPREAD     = re.compile(r"\b([A-Za-z .'-]+?)\s*([+-]\d+(?:\.\d)?)\b")
RE_VS              = re.compile(r"\b([A-Za-z .'-]+)\s+@\s+([A-Za-z .'-]+)|\b([A-Za-z .'-]+)\s+vs\.?\s+([A-Za-z .'-]+)", re.I)
RE_PLAYER_STAT     = re.compile(r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z'.-]+)+)\s*[-–—:]\s*(?P<stat>[A-Za-z ]+)", re.I)
RE_LEG_START       = re.compile(r"^\s*(over|under|yes|no)\b|^\s*\d+\+|\bto\s+record\b|\banytime\s+td\b|\bto\s+score\b", re.I)
RE_WINNER_KEY      = re.compile(r"\b(to win|winner|moneyline|ml)\b", re.I)
RE_TOTAL_KEY       = re.compile(r"\b(total (?:runs|points|match points|goals|rounds))\b", re.I)
RE_UFC_MMA_KEY     = re.compile(r"\b(total rounds|winner)\b", re.I)

@dataclass
class Leg:
    type: str                       # 'prop' | 'total' | 'spread' | 'moneyline' | 'unknown'
    league: Optional[str] = None
    player: Optional[str] = None
    stat: Optional[str] = None
    side: Optional[str] = None      # 'over' | 'under' | 'yes' | 'no'
    line: Optional[float] = None
    target_text: Optional[str] = None
    team: Optional[str] = None
    game_teams: Optional[List[str]] = None
    raw_block: Optional[str] = None
    current_value: Optional[float] = None
    result: str = "pending"         # 'pending' | 'won' | 'lost' | 'push'

@dataclass
class ParsedSlip:
    bet_type: str                   # 'single' | 'parlay'
    league: Optional[str]
    odds: Optional[int]
    stake: Optional[float]
    payout: Optional[float]
    legs: List[Leg]

def best_team_match(league: str, text: str, limit=4, threshold=70) -> List[str]:
    teams = TEAM_MAP.get(league, [])
    if not teams:
        return []
    found = process.extract(text, teams, scorer=fuzz.partial_ratio, limit=limit)
    return [t for t, score, _ in found if score >= threshold]

def detect_league_from_text(text: str) -> Optional[str]:
    # Votes based on team name matches; also keyword nudges for UFC/SOCCER
    votes = {}
    lowered = text.lower()
    if RE_UFC_MMA_KEY.search(lowered) or "ufc" in lowered or "mma" in lowered:
        votes["UFC"] = votes.get("UFC", 0) + 2
    if "premier league" in lowered or "la liga" in lowered or "bundesliga" in lowered or "serie a" in lowered or "mls" in lowered:
        votes["SOCCER"] = votes.get("SOCCER", 0) + 2
    for lg in ("NFL","NBA","MLB","NHL"):
        matches = best_team_match(lg, text, limit=10, threshold=70)
        if matches:
            votes[lg] = votes.get(lg, 0) + len(matches)
    return max(votes, key=votes.get) if votes else None

def extract_odds(text: str) -> Optional[int]:
    m = RE_AMERICAN_ODDS.search(text)
    return int(m.group(1)) if m else None

def extract_stake(text: str) -> Optional[float]:
    m = RE_STAKE.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    m2 = RE_MONEY.search(text)
    if m2:
        return float(m2.group(1).replace(",", ""))
    return None

def extract_payout(text: str) -> Optional[float]:
    m = RE_PAYOUT.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None

def extract_game_teams_from_text(league: str, text: str) -> List[str]:
    # Try explicit "@/vs" first
    m = RE_VS.search(text)
    candidates: List[str] = []
    if m:
        parts = [p for p in m.groups() if p]
        for p in parts:
            matched = best_team_match(league, p, limit=1, threshold=60)
            if matched:
                candidates.append(matched[0])
    # Fallback to top fuzzy matches in body
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

def classify_line_block(block: str) -> Leg:
    league_guess = detect_league_from_text(block)
    pm = RE_PLAYER_STAT.search(block)
    ou = RE_OU.search(block)

    # 1) Player prop
    if pm:
        player = pm.group("name").strip()
        stat = normalize_stat(pm.group("stat"))
        side, line, tgt = None, None, None
        if ou:
            side = ou.group(1).lower()
            line = float(ou.group(2))
            tgt = f"{side} {line}"
        elif "anytime td" in block.lower() or "to score" in block.lower():
            tgt = "Yes" if "yes" in block.lower() else "No" if "no" in block.lower() else None
            side = tgt.lower() if tgt else None
            stat = "anytime td"
        leg = Leg(type="prop", league=league_guess, player=player, stat=stat, side=side, line=line, target_text=tgt, raw_block=block)

        # For props, try to infer teams from the whole block (often includes "Team @ Team")
        if league_guess in ("NFL","NBA","MLB","NHL"):
            leg.game_teams = extract_game_teams_from_text(league_guess, block)
        return leg

    # 2) Totals (non-player)
    if ou or RE_TOTAL_KEY.search(block):
        side_txt, line_val = None, None
        if ou:
            side_txt = ou.group(1).lower()
            line_val = float(ou.group(2))
        text_low = block.lower()
        # Some slips show "Over 0.5 Hits" without explicit "total"
        if not league_guess:
            league_guess = detect_league_from_text(block)
        return Leg(type="total", league=league_guess, side=side_txt, line=line_val, target_text=f"{side_txt or ''} {line_val or ''}".strip(), raw_block=block)

    # 3) Spread "Team -3.5" or "+7.5"
    sp = RE_TEAM_SPREAD.search(block)
    if sp:
        team_guess = sp.group(1).strip()
        # Avoid capturing generic words as team (e.g., "Under", "Over", "Yes") — safeguard:
        if team_guess.lower() in ("over","under","yes","no"):
            team_guess = ""
        try:
            line = float(sp.group(2))
        except Exception:
            line = None
        best = best_team_match(league_guess or "", team_guess, limit=1, threshold=60) if team_guess else []
        team = best[0] if best else (team_guess or None)
        return Leg(type="spread", league=league_guess, team=team, line=line, target_text=f"{team or ''} {line or ''}".strip(), raw_block=block)

    # 4) Moneyline / Winner
    if RE_WINNER_KEY.search(block):
        teams = best_team_match(league_guess or "", block, limit=2, threshold=75)
        team = teams[0] if teams else None
        return Leg(type="moneyline", league=league_guess, team=team, target_text=team or "ML", raw_block=block)

    # 5) Unknown — keep raw for debugging
    return Leg(type="unknown", league=league_guess, target_text=block.strip()[:80], raw_block=block)

def split_into_leg_blocks(text: str) -> List[str]:
    # Split on lines and group into candidate legs by triggers.
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

    # Only drop pure headers/footers; keep mixed lines
    cleaned: List[str] = []
    for b in blocks:
        low = b.lower()
        tokens = low.split()
        if len(tokens) <= 3 and any(k in low for k in ["parlay","sgp","sgpmax","wager","payout","odds","hard rock","sports bet","bet slip","profit boost","boosted"]):
            # Very short and clearly a header/footer — skip
            continue
        cleaned.append(b)
    return cleaned

def parse_slip(text: str) -> ParsedSlip:
    # Global metadata
    odds = extract_odds(text)
    stake = extract_stake(text)
    payout = extract_payout(text)

    # Blocks -> Legs
    blocks = split_into_leg_blocks(text)
    legs: List[Leg] = []
    for b in blocks:
        leg = classify_line_block(b)
        # Per-leg teams (use the per-leg league if available)
        if leg.league in ("NFL","NBA","MLB","NHL") and not leg.game_teams:
            leg.game_teams = extract_game_teams_from_text(leg.league, b)
        legs.append(leg)

    # Overall league hint: majority league among legs
    league_vote = {}
    for l in legs:
        if l.league:
            league_vote[l.league] = league_vote.get(l.league, 0) + 1
    overall_league = max(league_vote, key=league_vote.get) if league_vote else detect_league_from_text(text)

    bet_type = "parlay" if len(legs) > 1 else "single"
    return ParsedSlip(bet_type=bet_type, league=overall_league, odds=odds, stake=stake, payout=payout, legs=legs)
