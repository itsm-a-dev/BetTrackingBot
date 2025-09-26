import re
from typing import Tuple
from config import Config


def normalize_headers_footers(text: str) -> str:
    # Remove common headers/footers, noisy lines, bet IDs, timestamps that break segmentation.
    patterns = [
        r"(?i)bet id[:#]\s*\w+",
        r"(?i)transaction[:#]\s*\w+",
        r"(?i)placed on[:]\s*.*",
        r"(?i)customer[:]\s*.*",
        r"(?i)^page \d+ of \d+$",
        r"(?i)^screenshot.*$",
    ]
    cleaned = []
    for line in text.splitlines():
        if any(re.search(p, line) for p in patterns):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def detect_sportsbook_style(text: str, hints: list) -> str:
    for h in hints:
        if re.search(rf"\b{re.escape(h)}\b", text, re.I):
            return h
    # Heuristics: DK slips often show "Leg x", FD shows "Parlay" headers, Caesars shows "Wager/To Win"
    if re.search(r"(?i)\bleg\s+\d+\b", text):
        return "DraftKings-ish"
    if re.search(r"(?i)\bparlay\b", text):
        return "FanDuel-ish"
    if re.search(r"(?i)\bwager\b.*\bto win\b", text):
        return "Caesars-ish"
    return "Generic"


def boost_leg_segmentation(text: str, style: str) -> str:
    # Insert extra newlines between common segment markers to improve block splitting.
    augmented = text
    augmented = re.sub(r"(?i)(leg\s+\d+)", r"\n\1\n", augmented)
    augmented = re.sub(r"(?i)(wager|stake|risk)\s*[:$]?\s*[0-9]+(?:\.[0-9]{1,2})?", r"\n\1\n", augmented)
    augmented = re.sub(r"(?i)(to win|payout|return)\s*[:$]?\s*[0-9]+(?:\.[0-9]{1,2})?", r"\n\1\n", augmented)
    augmented = re.sub(r"(?i)(over|under|total|spread|moneyline|ml)\b", r"\n\1\n", augmented)
    return augmented


def route_text(text: str, config: Config) -> Tuple[str, str]:
    # Normalize (optional), detect sportsbook style, boost segmentation.
    cleaned = normalize_headers_footers(text) if config.router_enable_normalization else text
    style = detect_sportsbook_style(cleaned, config.router_sportsbook_hints)
    boosted = boost_leg_segmentation(cleaned, style)
    return boosted, style
