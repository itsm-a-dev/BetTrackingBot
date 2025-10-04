from dataclasses import dataclass

@dataclass
class ParsedSlip:
    bookmaker: str
    event: str
    odds: str
    stake: float
    legs: list
