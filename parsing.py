# parsing.py
import re
import asyncio
from dataclasses import dataclass
from typing import Optional, List, Dict
from rapidfuzz import process, fuzz
import httpx
import time

# ============================================================
# Dynamic team/player catalogs (autoload + periodic refresh)
# ============================================================

TEAM_MAP: Dict[str, List[str]] = {
    "NFL": [],
    "NBA": [],
    "MLB": [],
    "NHL": [],
    "SOCCER": [],  # aggregate across configured competitions
    "UFC": [],     # fighters (optional)
}

PLAYER_MAP: Dict[str, List[str]] = {
    "NFL": [],
    "NBA": [],
    "MLB": [],
    "NHL": [],
    "SOCCER": [],
    "UFC": [],
}

# Configure which leagues/competitions to fetch
ESPN_TEAM_ENDPOINTS: Dict[str, List[str]] = {
    "NFL": ["football/nfl"],
    "NBA": ["basketball/nba"],
    "MLB": ["baseball/mlb"],
    "NHL": ["hockey/nhl"],
    # Add more soccer comps as needed; eng.1=Premier League, esp.1=La Liga, ger.1=Bundesliga, ita.1=Serie A, usa.1=MLS
    "SOCCER": ["soccer/eng.1", "soccer/esp.1", "soccer/ger.1", "soccer/ita.1", "soccer/usa.1"],
    "UFC": ["mma/ufc"],  # fighters via athletes endpoint
}

# Refresh intervals (seconds)
CATALOG_REFRESH_INTERVAL = 24 * 60 * 60  # daily
HTTP_TIMEOUT = 15

_last_catalog_refresh = 0
_catalog_lock = asyncio.Lock()


async def _fetch_json(client: httpx.AsyncClient, url: str) -> Optional[Dict]:
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


async def _fetch_league_teams_and_players(league: str, sport_paths: List[str]) -> None:
    teams: List[str] = []
    players: List[str] = []

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for sport_path in sport_paths:
            # Teams endpoint
            team_url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/teams"
            data = await _fetch_json(client, team_url)
            if not data:
                continue

            team_entries = (
                data.get("sports", [{}])[0]
                .get("leagues", [{}])[0]
                .get("teams", [])
            )
            for entry in team_entries:
                t = entry.get("team") or {}
                if name := t.get("displayName"):
                    teams.append(name)

                # UFC and SOCCER may not have meaningful rosters here; handle by league
                if league == "UFC":
                    # Fighters are under athletes endpoint, not team rosters
                    continue

                # For team sports, attempt roster for players (optional but useful)
                team_id = t.get("id")
                if not team_id:
                    continue
                roster_url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/teams/{team_id}/roster"
                roster = await _fetch_json(client, roster_url)
                if not roster:
                    continue
                for group in roster.get("athletes", []):
                    for item in group.get("items", []):
                        athlete = item.get("athlete") or {}
                        if pname := athlete.get("displayName"):
                            players.append(pname)

            # UFC fighters (athletes) — league-wide list
            if league == "UFC":
                ath_url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/athletes"
                athletes = await _fetch_json(client, ath_url)
                # Structure varies; collect displayName defensively
                if athletes:
                    # Some responses have "athletes": [{"items":[{athlete:{displayName}}]}...]
                    for group in athletes.get("athletes", []):
                        for item in group.get("items", []):
                            athlete = item.get("athlete") or {}
                            if pname := athlete.get("displayName"):
                                players.append(pname)

    # Deduplicate and store
    TEAM_MAP[league] = sorted(set(teams))
    PLAYER_MAP[league] = sorted(set(players))
    print(f"[INIT] Catalog for {league}: {len(TEAM_MAP[league])} teams, {len(PLAYER_MAP[league])} players")


async def refresh_catalogs(force: bool = False) -> None:
    global _last_catalog_refresh
    async with _catalog_lock:
        now = time.time()
        if not force and (now - _last_catalog_refresh) < CATALOG_REFRESH_INTERVAL:
            return
        tasks = [
            _fetch_league_teams_and_players(league, paths)
            for league, paths in ESPN_TEAM_ENDPOINTS.items()
        ]
        await asyncio.gather(*tasks)
        _last_catalog_refresh = now
        print("[INIT] Dynamic TEAM_MAP and PLAYER_MAP refreshed")


def _schedule_background_refresh() -> None:
    async def _loop():
        while True:
            try:
                await refresh_catalogs(force=True)
            except Exception as e:
                print(f"[WARN] Catalog refresh error: {e}")
            await asyncio.sleep(CATALOG_REFRESH_INTERVAL)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_loop())
        else:
            loop.create_task(_loop())
    except Exception:
        pass


# Initialize at import time, non-blocking
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(refresh_catalogs(force=True))
    else:
        loop.run_until_complete(refresh_catalogs(force=True))
    _schedule_background_refresh()
except Exception as e:
    print(f"[WARN] Initial catalog load failed: {e}")


# ============================================================
# Parsing logic
# ============================================================

PROP_STATS = [
    # Core
    "passing yards","rushing yards","receiving yards","receptions","attempts","completions",
    "passing touchdowns","rushing touchdowns","receiving touchdowns","touchdowns","interceptions",
    "points","rebounds","assists","pra","threes","three pointers","three-point field goals",
    "shots on goal","saves","hits","total bases","strikeouts","earned runs","outs","hits allowed",
    "anytime td","anytime touchdown","to score","total rounds","total match points","total runs","total goals",
    "passing attempts","passing completions","sacks","tackles",
    # Soccer-specific
    "goals","assists","shots","shots on target","clean sheet","yellow card","red card","btts","both teams to score",
    "win to nil","draw no bet","double chance",
    # UFC/MMA-specific
    "significant strikes","takedowns","submission attempts","knockdowns","method of victory"
]

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
RE_UFC_MMA_KEY     = re.compile(r"\b(total rounds|winner|method of victory|ko/tko|submission|decision)\b", re.I)
RE_SOCCER_KEY      = re.compile(r"\b(btts|both teams to score|win to nil|draw no bet|double chance)\b", re.I)

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


def best_player_match(league: str, text: str, limit=4, threshold=75) -> List[str]:
    players = PLAYER_MAP.get(league, [])
    if not players:
        return []
    found = process.extract(text, players, scorer=fuzz.partial_ratio, limit=limit)
    return [p for p, score, _ in found if score >= threshold]


def detect_league_from_text(text: str) -> Optional[str]:
    votes: Dict[str, int] = {}
    lowered = text.lower()

    # Keyword nudges
    if RE_UFC_MMA_KEY.search(lowered) or "ufc" in lowered or "mma" in lowered:
        votes["UFC"] = votes.get("UFC", 0) + 3
    if RE_SOCCER_KEY.search(lowered) or any(k in lowered for k in ["premier league","la liga","bundesliga","serie a","mls","champions league"]):
        votes["SOCCER"] = votes.get("SOCCER", 0) + 2

    # Team matches
    for lg in ("NFL","NBA","MLB","NHL","SOCCER"):
        matches = best_team_match(lg, text, limit=10, threshold=70)
        if matches:
            votes[lg] = votes.get(lg, 0) + len(matches)

    # Player matches can be strong signals for props
    for lg in ("NFL","NBA","MLB","NHL","SOCCER","UFC"):
        pm = best_player_match(lg, text, limit=5, threshold=78)
        if pm:
            votes[lg] = votes.get(lg, 0) + len(pm) + 1  # small bonus

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


def classify_line_block(block: str) -> Leg:
    league_guess = detect_league_from_text(block)
    pm = RE_PLAYER_STAT.search(block)
    ou = RE_OU.search(block)

    # 1) Player prop
    if pm:
        player_text = pm.group("name").strip()
        # If we can match a known player in any league, prefer that league
        best_league = league_guess
        best_score = 0
        for lg in PLAYER_MAP.keys():
            cand = best_player_match(lg, player_text, limit=1, threshold=70)
            if cand:
                # slight boost if league already guessed by teams/keywords
                score = 2 if lg == league_guess else 1
                if score > best_score:
                    best_score, best_league = score, lg
        league_guess = best_league or league_guess

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

        leg = Leg(
            type="prop",
            league=league_guess,
            player=player_text,
            stat=stat,
            side=side,
            line=line,
            target_text=tgt,
            raw_block=block
        )

        if league_guess in ("NFL","NBA","MLB","NHL","SOCCER"):
            leg.game_teams = extract_game_teams_from_text(league_guess, block)
        return leg

    # 2) Totals (non-player) and sport‑agnostic totals
    if ou or RE_TOTAL_KEY.search(block):
        side_txt, line_val = (ou.group(1).lower(), float(ou.group(2))) if ou else (None, None)
        return Leg(
            type="total",
            league=league_guess,
            side=side_txt,
            line=line_val,
            target_text=f"{side_txt or ''} {line_val or ''}".strip(),
            raw_block=block
        )

    # 3) Spread "Team -3.5" or "+7.5"
    sp = RE_TEAM_SPREAD.search(block)
    if sp:
        team_guess = sp.group(1).strip()
        if team_guess.lower() in ("over","under","yes","no"):
            team_guess = ""
        try:
            line = float(sp.group(2))
        except Exception:
            line = None
        best = best_team_match(league_guess or "", team_guess, limit=1, threshold=60) if team_guess else []
        team = best[0] if best else (team_guess or None)
        return Leg(
            type="spread",
            league=league_guess,
            team=team,
            line=line,
            target_text=f"{team or ''} {line or ''}".strip(),
            raw_block=block
        )

    # 4) Moneyline / Winner
    if RE_WINNER_KEY.search(block):
        teams = best_team_match(league_guess or "", block, limit=2, threshold=75)
        team = teams[0] if teams else None
        return Leg(type="moneyline", league=league_guess, team=team, target_text=team or "ML", raw_block=block)

    # 5) Unknown — keep raw for debugging
    return Leg(type="unknown", league=league_guess, target_text=block.strip()[:80], raw_block=block)


def split_into_leg_blocks(text: str) -> List[str]:
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

    cleaned: List[str] = []
    for b in blocks:
        low = b.lower()
        tokens = low.split()
        # Only drop very short pure headers/footers; keep mixed lines
        if len(tokens) <= 3 and any(k in low for k in [
            "parlay","sgp","sgpmax","wager","payout","odds","hard rock","sports bet","bet slip","profit boost","boosted"
        ]):
            continue
        cleaned.append(b)
    return cleaned


def parse_slip(text: str) -> ParsedSlip:
    odds = extract_odds(text)
    stake = extract_stake(text)
    payout = extract_payout(text)

    blocks = split_into_leg_blocks(text)
    legs: List[Leg] = []
    for b in blocks:
        leg = classify_line_block(b)
        if leg.league in ("NFL","NBA","MLB","NHL","SOCCER") and not leg.game_teams:
            leg.game_teams = extract_game_teams_from_text(leg.league, b)
        legs.append(leg)

    # Majority league across legs (for top-level display only)
    league_vote: Dict[str, int] = {}
    for l in legs:
        if l.league:
            league_vote[l.league] = league_vote.get(l.league, 0) + 1
    overall_league = max(league_vote, key=league_vote.get) if league_vote else detect_league_from_text(text)

    bet_type = "parlay" if len(legs) > 1 else "single"
    return ParsedSlip(bet_type=bet_type, league=overall_league, odds=odds, stake=stake, payout=payout, legs=legs)
