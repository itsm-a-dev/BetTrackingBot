import httpx
from typing import Optional, Dict, Any, List
from rapidfuzz import fuzz, process

ESPN_SCOREBOARD = {
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
}

async def fetch_scores(league: str) -> Dict[str, Any]:
    url = ESPN_SCOREBOARD.get(league)
    if not url:
        return {}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()

def find_game_id_for_teams(league: str, teams: List[str], scoreboard: Dict[str, Any]) -> Optional[str]:
    if not teams or len(teams) < 2:
        return None
    t1, t2 = teams[0], teams[1]
    best_id, best_score = None, 0
    for event in scoreboard.get("events", []):
        comp = event["competitions"][0]["competitors"]
        names = [c["team"]["displayName"] for c in comp]
        score = min(
            max(process.extractOne(t1, names)[1], 0),
            max(process.extractOne(t2, names)[1], 0),
        )
        if score > best_score:
            best_score = score
            best_id = event["id"]
    return best_id if best_score >= 70 else None

def extract_score_and_status(event: Dict[str, Any]) -> Dict[str, str]:
    comp = event["competitions"][0]["competitors"]
    score_str = " vs ".join([f"{c['team']['displayName']} {c['score']}" for c in comp])
    status = event["status"]["type"]["description"]
    return {"score": score_str, "status": status}

# Minimal player stat extraction per league/category. This is a best-effort heuristic.
def _nfl_player_stat(event: Dict[str, Any], player: str, stat: str) -> Optional[float]:
    # We map common NFL props
    stat = stat.lower()
    categories = {
        "passing yards": ["passing", "passYards", "yards", "YDS"],
        "rushing yards": ["rushing", "rushYards", "yards", "YDS"],
        "receiving yards": ["receiving", "recYards", "yards", "YDS"],
        "receptions": ["receptions", "REC"],
        "interceptions": ["interceptions", "INT"],
        "touchdowns": ["touchdowns","TD"],
        "anytime td": ["touchdowns","TD"],
        "anytime touchdown": ["touchdowns","TD"],
        "to score": ["touchdowns","TD"],
        "completions": ["completions","COMP"],
        "attempts": ["attempts","ATT"],
        "passing touchdowns": ["passTD","TD"],
    }
    wanted = categories.get(stat, [])
    # ESPN "boxscore" not on scoreboard; we estimate via competitor statistics if present
    comps = event["competitions"][0]["competitors"]
    # Try player name fuzzy match within roster if available (not always present on scoreboard)
    for c in comps:
        aths = c.get("athletes", [])
        if not aths: 
            continue
        best = process.extractOne(player, [a["athlete"]["displayName"] for a in aths])
        if not best or best[1] < 70:
            continue
        target = aths[best[2]]
        # Scan stats array
        stats = target.get("stats", [])
        # stats often like ["CMP/ATT 18/30", "YDS 225", "TD 2", "INT 1"]
        for s in stats:
            for key in wanted:
                if key.lower() in s.lower():
                    # Extract final number in string
                    nums = [n for n in s.replace(",", " ").split() if n.replace(".","",1).isdigit()]
                    if nums:
                        try:
                            return float(nums[-1])
                        except:
                            continue
    return None

def find_player_stat_for_leg(league: str, event: Dict[str, Any], player: str, stat: str) -> Optional[float]:
    league = league.upper()
    if league == "NFL":
        return _nfl_player_stat(event, player, stat)
    # TODO: NBA/MLB/NHL mappings — follow same pattern, parsing event competitors/athletes stats when present.
    return None
