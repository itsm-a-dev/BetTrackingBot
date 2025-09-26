import logging
from typing import Dict, Any, Optional, List, Tuple

import httpx
from rapidfuzz import process, fuzz

from config import Config

logger = logging.getLogger("espn")

LEAGUE_ENDPOINTS = {
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "Soccer": "https://site.api.espn.com/apis/site/v2/sports/soccer/{comp}/scoreboard",
}


async def fetch_scoreboard(config: Config, league: str) -> Dict[str, Any]:
    """Fetch ESPN scoreboard JSON for a given league."""
    url = LEAGUE_ENDPOINTS.get(league)
    if not url:
        return {"events": []}

    if league == "Soccer":
        all_data = {"events": []}
        async with httpx.AsyncClient(timeout=config.http_timeout) as client:
            for comp in config.soccer_competitions:
                try:
                    r = await client.get(url.format(comp=comp))
                    r.raise_for_status()
                    data = r.json()
                    all_data["events"].extend(data.get("events", []))
                except Exception as e:
                    logger.debug(f"Soccer fetch failed for {comp}: {e}")
        return all_data

    async with httpx.AsyncClient(timeout=config.http_timeout) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def fuzzy_match_game(league: str, teams_str: str, events: List[Dict[str, Any]]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Fuzzy match a slip's team string to an ESPN event."""
    if not teams_str or not events:
        return None

    candidates = []
    for ev in events:
        comps = ev.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue
        home = competitors[0].get("team", {}).get("displayName", "")
        away = competitors[1].get("team", {}).get("displayName", "")
        s = f"{away} @ {home}"
        candidates.append((ev.get("id"), s, ev))

    match = process.extractOne(teams_str, [c[1] for c in candidates], scorer=fuzz.token_set_ratio)
    if match and match[1] >= 80:
        idx = match[2]
        return candidates[idx][0], candidates[idx][2]
    return None


def extract_live_score(event: Dict[str, Any]) -> str:
    """Return a human-readable live score string from an ESPN event."""
    comps = event.get("competitions", [])
    if not comps:
        return "No data"
    comp = comps[0]
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return "No data"
    home = competitors[0]
    away = competitors[1]
    status = comp.get("status", {}).get("type", {}).get("description", "")
    return f"{away.get('team', {}).get('displayName', '')} {away.get('score', '')} - {home.get('team', {}).get('displayName', '')} {home.get('score', '')} | {status}"


def extract_player_prop_status(league: str, event: Dict[str, Any], player_name: str, metric: str) -> str:
    """Stub for per-league player prop extraction."""
    if league == "NFL":
        return f"NFL prop tracking not fully implemented for {player_name} ({metric})."
    if league == "Soccer":
        return f"Soccer prop tracking not fully implemented for {player_name} ({metric})."
    if league == "UFC":
        return f"UFC prop tracking not fully implemented for {player_name} ({metric})."
    return f"{league} prop tracking not implemented."
