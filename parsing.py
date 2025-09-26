import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Literal

from rapidfuzz import process, fuzz

from config import Config

logger = logging.getLogger("parsing")

LegType = Literal["moneyline", "spread", "total", "prop", "unknown"]

@dataclass
class ParsedLeg:
    league: str
    leg_type: LegType
    teams_or_player: str
    market: str
    odds: Optional[str] = None

@dataclass
class ParsedSlip:
    stake: Optional[float]
    payout: Optional[float]
    legs: List[ParsedLeg] = field(default_factory=list)
    raw_text: str = ""
    sportsbook_style: str = "Generic"


TEAM_CATALOGS: Dict[str, List[str]] = {}
PLAYER_CATALOGS: Dict[str, List[str]] = {}


async def refresh_dynamic_catalogs(config: Config):
    TEAM_CATALOGS.update({
        "NFL": ["Patriots", "Cowboys", "Eagles", "Dolphins", "Jaguars", "Bills", "Chiefs", "Jets"],
        "NBA": ["Lakers", "Celtics", "Heat", "Warriors", "Knicks"],
        "MLB": ["Yankees", "Dodgers", "Red Sox", "Mets", "Braves"],
        "NHL": ["Bruins", "Lightning", "Panthers", "Rangers", "Maple Leafs"],
        "Soccer": ["Arsenal", "Real Madrid", "Barcelona", "Inter", "Liverpool", "Man City"],
        "UFC": [],
    })
    PLAYER_CATALOGS.update({
        "NFL": ["Patrick Mahomes", "Tyreek Hill", "Jalen Hurts", "Josh Allen", "Trevor Lawrence"],
        "Soccer": ["Lionel Messi", "Erling Haaland", "Kylian Mbappe", "Mohamed Salah"],
        "UFC": ["Jon Jones", "Islam Makhachev", "Sean O'Malley"],
    })
    if config.debug_logging:
        logger.info("Dynamic catalogs refreshed.")


def _split_into_leg_blocks(text: str) -> List[str]:
    parts = [b.strip() for b in re.split(r"\n{2,}|-{3,}|_{3,}", text) if b.strip()]
    return parts


def _detect_league(block: str) -> str:
    for league, teams in TEAM_CATALOGS.items():
        match = process.extractOne(block, teams, scorer=fuzz.token_set_ratio)
        if match and match[1] >= 80:
            return league
    if re.search(r"\bNFL\b", block, re.I):
        return "NFL"
    if re.search(r"\bNBA\b", block, re.I):
        return "NBA"
    if re.search(r"\bMLB\b", block, re.I):
        return "MLB"
    if re.search(r"\bNHL\b", block, re.I):
        return "NHL"
    if re.search(r"\b(UFC|Fight|Bout)\b", block, re.I):
        return "UFC"
    if re.search(r"\b(EPL|LaLiga|Serie A|Bundesliga|MLS|UEFA)\b", block, re.I):
        return "Soccer"
    return "Unknown"


def _classify_leg(block: str) -> LegType:
    if re.search(r"\bML\b|\bmoneyline\b", block, re.I):
        return "moneyline"
    if re.search(r"\bspread\b|\b[-+]\d+(\.\d+)?\b", block, re.I) and re.search(r"\b(-|\+)\d", block):
        return "spread"
    if re.search(r"\b(total|over|under|o/u)\b", block, re.I):
        return "total"
    if re.search(r"\bprop\b|\bassists\b|\brebounds\b|\bpasses\b|\byards\b|\bshots\b|\bSOG\b", block, re.I):
        return "prop"
    return "unknown"


def _extract_odds(block: str) -> Optional[str]:
    m = re.search(r"([+-]\d{2,4})", block)
    return m.group(1) if m else None


def _extract_stake(text: str) -> Optional[float]:
    m = re.search(r"(stake|wager|risk)\s*[:$]?\s*([0-9]+(?:\.[0-9]{1,2})?)", text, re.I)
    return float(m.group(2)) if m else None


def _extract_payout(text: str) -> Optional[float]:
    m = re.search(r"(payout|to win|return)\s*[:$]?\s*([0-9]+(?:\.[0-9]{1,2})?)", text, re.I)
    return float(m.group(2)) if m else None


def parse_slip_text(text: str, min_conf: float, style: str = "Generic") -> ParsedSlip:
    blocks = _split_into_leg_blocks(text)
    legs: List[ParsedLeg] = []

    for b in blocks:
        league = _detect_league(b)
        leg_type = _classify_leg(b)
        odds = _extract_odds(b)

        teams_or_player = ""
        tm = re.search(r"([A-Za-z .'-]+)\s+(vs\.?|@)\s+([A-Za-z .'-]+)", b, re.I)
        if tm:
            teams_or_player = f"{tm.group(1).strip()} {tm.group(2).strip()} {tm.group(3).strip()}"
        else:
            pm = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", b)
            if pm:
                teams_or_player = pm[0]

        market = "Unknown"
        if leg_type == "moneyline":
            market = "ML"
        elif leg_type == "spread":
            spr = re.search(r"([-+]\d+(?:\.\d+)?)", b)
            market = f"Spread {spr.group(1)}" if spr else "Spread"
        elif leg_type == "total":
            tot = re.search(r"(O|U|Over|Under)\s*([0-9]+(?:\.[0-9]+)?)", b, re.I)
            market = f"Total {tot.group(1).upper()} {tot.group(2)}" if tot else "Total"
        elif leg_type == "prop":
            ou = re.search(r"(Over|Under)\s*\d+(?:\.\d+)?", b, re.I)
            market = f"Prop: {ou.group(0)}" if ou else "Prop: Custom"

        legs.append(ParsedLeg(
            league=league,
            leg_type=leg_type,
            teams_or_player=teams_or_player or "Unknown",
            market=market,
            odds=odds
        ))

    return ParsedSlip(
        stake=_extract_stake(text),
        payout=_extract_payout(text),
        legs=legs,
        raw_text=text,
        sportsbook_style=style
    )
