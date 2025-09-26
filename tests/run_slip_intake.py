"""
Test harness for slip intake.
Usage:
    python tests/run_slip_intake.py <image_path>

This will:
- Load the image
- Run advanced OCR (YOLO/EasyOCR/Tesseract depending on config)
- Route text through format_router
- Parse into a ParsedSlip object
- Print structured output for diagnostics
"""

import asyncio
import sys
from pathlib import Path

from config import Config
from ocr_advanced import run_ocr
from format_router import route_text
from parsing import parse_slip_text


async def main(image_path: str):
    config = Config.from_env()
    img_bytes = Path(image_path).read_bytes()

    # Run OCR
    ocr_out = run_ocr(img_bytes, config)
    print("=== OCR TEXT ===")
    print(ocr_out["text"])

    # Route and normalize
    routed_text, style = route_text(ocr_out["text"], config)
    print("\n=== ROUTED TEXT (style: {}) ===".format(style))
    print(routed_text)

    # Parse into structured slip
    parsed = parse_slip_text(routed_text, config.ocr_confidence_threshold, style)

    print("\n=== PARSED SLIP ===")
    print(f"Stake: {parsed.stake}, Payout: {parsed.payout}, Style: {parsed.sportsbook_style}")
    for i, leg in enumerate(parsed.legs, start=1):
        print(f"Leg {i}: {leg.league} | {leg.leg_type} | {leg.teams_or_player} | {leg.market} | Odds: {leg.odds}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/run_slip_intake.py <image_path>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
