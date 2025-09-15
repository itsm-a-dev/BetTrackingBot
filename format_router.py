# format_router.py
import re
from typing import Literal

Sportsbook = Literal["hardrock", "draftkings", "fanduel", "betmgm", "caesars", "generic"]

HARDROCK_HINTS = [
    r"\bHARD\s*ROCK\b", r"\bHARD\s*ROCK\s*BET\b", r"\bSGP(?:MAX)?\b", r"\bCASH\s*OUT\b",
    r"\bMY\s*BETS\b", r"\bPAID\b", r"\bWAGER\b", r"\bPAYOUT\b", r"\bID:\b"
]
DK_HINTS = [r"\bDRAFT\s*KINGS\b", r"\bDK\b", r"\bSAME\s*GAME\s*PARLAY\b"]
FD_HINTS = [r"\bFAN\s*DUEL\b", r"\bFD\b", r"\bSAME\s*GAME\s*PARLAY\b", r"\bODDS BOOST\b"]
MGM_HINTS = [r"\bBET\s*MGM\b", r"\bMGM\b"]
CAESARS_HINTS = [r"\bCAESARS\b", r"\bCEASARS\b", r"\bEMPEROR\b"]

def _has_any(text: str, patterns) -> bool:
    T = text.upper()
    return any(re.search(p, T) for p in patterns)

def detect_format(ocr_text: str) -> Sportsbook:
    if _has_any(ocr_text, HARDROCK_HINTS):
        return "hardrock"
    if _has_any(ocr_text, DK_HINTS):
        return "draftkings"
    if _has_any(ocr_text, FD_HINTS):
        return "fanduel"
    if _has_any(ocr_text, MGM_HINTS):
        return "betmgm"
    if _has_any(ocr_text, CAESARS_HINTS):
        return "caesars"
    return "generic"

# Router (example – wire to your existing parsers)
def parse_by_format(ocr_text: str):
    fmt = detect_format(ocr_text)
    if fmt == "hardrock":
        from parsers.hardrock import parse as hardrock_parse
        return hardrock_parse(ocr_text)
    # elif fmt == "draftkings": ...
    # elif fmt == "fanduel": ...
    # elif fmt == "betmgm": ...
    # elif fmt == "caesars": ...
    else:
        from parsing import parse_slip as generic_parse
        return generic_parse(ocr_text)
