from models.bet import ParsedSlip

def parse_slip(img_bytes):
    # TODO: plug in OCR / parsing here
    # Stub returns dummy bet
    return ParsedSlip(
        bookmaker="DraftKings",
        event="Lakers vs Celtics",
        odds="-110",
        stake=50.0,
        legs=[{"team": "Lakers", "type": "ML"}]
    )
