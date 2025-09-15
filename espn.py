# espn.py
import httpx
from typing import Optional, Dict, Any, List
from rapidfuzz import process

# ESPN scoreboard endpoints by league
ESPN_SCOREBOARD = {
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    # Example soccer competition: Premier League (eng.1)
    "SOCCER": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
    "UFC": "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard",
}

async def fetch_scores(league: str) -> Dict[str, Any]:
    """Fetch the ESPN scoreboard JSON for a given league."""
    url = ESPN_SCOREBOARD.get(league)
    if not url:
        return {}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()

def find_game_id_for_teams(league: str, teams: List[str], scoreboard: Dict[str, Any]) -> Optional[str]:
    """Match a pair of team names to a game ID in the scoreboard."""
    if not teams or len(teams) < 2:
        return None
    t1, t2 = teams[0], teams[1]
    best_id, best_score = None, 0
    for event in scoreboard.get("events", []):
        comp = event["competitions"][0]["competitors"]
        names = [c["team"]["displayName"] for c in comp]
        score = min(
            process.extractOne(t1, names)[1] if process.extractOne(t1, names) else 0,
            process.extractOne(t2, names)[1] if process.extractOne(t2, names) else 0,
        )
        if score > best_score:
            best_score = score
            best_id = event["id"]
    return best_id if best_score >= 70 else None

def extract_score_and_status(event: Dict[str, Any]) -> Dict[str, str]:
    """Return a dict with 'score' and 'status' strings for a given event."""
    comp = event["competitions"][0]["competitors"]
    score_str = " vs ".join([f"{c['team']['displayName']} {c['score']}" for c in comp])
    status = event["status"]["type"]["description"]
    return {"score": score_str, "status": status}

# --- Player stat extraction hooks ---

def _nfl_player_stat(event: Dict[str, Any], player: str, stat: str) -> Optional[float]:
    stat = stat.lower()
    categories = {
        "passing yards": ["yds"],
        "rushing yards": ["yds"],
        "receiving yards": ["yds"],
        "receptions": ["rec"],
        "interceptions": ["int"],
        "touchdowns": ["td"],
        "anytime td": ["td"],
        "completions": ["comp"],
        "attempts": ["att"],
        "passing touchdowns": ["td"],
    }
    wanted = categories.get(stat, [])
    comps = event["competitions"][0]["competitors"]
    for c in comps:
        aths = c.get("athletes", [])
        if not aths:
            continue
        best = process.extractOne(player, [a["athlete"]["displayName"] for a in aths])
        if not best or best[1] < 70:
            continue
        target = aths[best[2]]
        stats = target.get("stats", [])
        for s in stats:
            for key in wanted:
                if key.lower() in s.lower():
                    nums = [n for n in s.replace(",", " ").split() if n.replace(".","",1).isdigit()]
                    if nums:
                        return float(nums[-1])
    return None

def _soccer_player_stat(event: Dict[str, Any], player: str, stat: str) -> Optional[float]:
    stat = stat.lower()
    categories = {
        "goals": ["goals"],
        "assists": ["assists"],
        "shots on target": ["shotsOnTarget"],
        "saves": ["goalkeeperSaves"],
        "yellow card": ["yellowCards"],
        "red card": ["redCards"],
    }
    wanted = categories.get(stat, [])
    comps = event["competitions"][0]["competitors"]
    for c in comps:
        aths = c.get("athletes", [])
        if not aths:
            continue
        best = process.extractOne(player, [a["athlete"]["displayName"] for a in aths])
        if not best or best[1] < 70:
            continue
        target = aths[best[2]]
        stats = target.get("stats", [])
        for s in stats:
            for key in wanted:
                if key.lower() in s.lower():
                    nums = [n for n in s.replace(",", " ").split() if n.replace(".","",1).isdigit()]
                    if nums:
                        return float(nums[-1])
    return None

def _ufc_fight_stat(event: Dict[str, Any], fighter: str, stat: str) -> Optional[float]:
    stat = stat.lower()
    categories = {
        "total rounds": ["rounds"],
        "significant strikes": ["sigStrikes"],
        "takedowns": ["takedowns"],
        "submission attempts": ["submissionAttempts"],
        "knockdowns": ["knockdowns"],
    }
    wanted = categories.get(stat, [])
    comps = event["competitions"][0]["competitors"]
    for c in comps:
        if fighter.lower() in c.get("athlete", {}).get("displayName", "").lower():
            stats = c.get("statistics", [])
            for s in stats:
                for key in wanted:
                    if key.lower() in s.lower():
                        nums = [n for n in s.replace(",", " ").split() if n.replace(".","",1).isdigit()]
                        if nums:
                            return float(nums[-1])
    return None

def find_player_stat_for_leg(league: str, event: Dict[str, Any], player: str, stat: str) -> Optional[float]:
    league = league.upper()
    if league == "NFL":
        return _nfl_player_stat(event, player, stat)
    if league == "SOCCER":
        return _soccer_player_stat(event, player, stat)
    if league == "UFC":
        return _ufc_fight_stat(event, player, stat)
    # TODO: Add NBA, MLB, NHL stat extraction
    return None
