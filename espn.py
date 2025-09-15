import httpx

ESPN_URLS = {
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"
}

async def fetch_scores(league: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(ESPN_URLS[league])
        return r.json()

def match_game(league: str, teams: list[str], scoreboard: dict):
    for event in scoreboard.get("events", []):
        comp = event["competitions"][0]["competitors"]
        names = [c["team"]["displayName"] for c in comp]
        if all(any(team.lower() in n.lower() for n in names) for team in teams):
            return event["id"]
    return None
