etTrackingBot 🏈🏀⚾🏒⚽🥊
A Discord bot that ingests screenshots of betting slips, parses them into structured bets, and tracks them live with ESPN scoreboards. Built with Python, OpenCV, Tesseract, YOLO/EasyOCR (optional), and discord.py..

✨ Features
OCR Pipeline

Baseline: Tesseract with preprocessing (grayscale, denoise, deskew, adaptive threshold).

Advanced: YOLOv8 region detection + EasyOCR fallback + multipass preprocessing.

Format Router

Normalizes sportsbook-specific quirks (FanDuel, DraftKings, Caesars, etc.).

Boosts segmentation for more accurate leg detection.

Parsing Engine

Splits slips into legs.

Detects league (NFL, NBA, MLB, NHL, Soccer, UFC).

Classifies bet type (moneyline, spread, total, prop).

Extracts odds, stake, payout.

Live Updates

Matches legs to ESPN events via fuzzy matching.

Updates scores and statuses in real time.

Hooks for player prop tracking.

Persistence

JSON (tracked_bets.json) for quick reloads.

SQLite (bets.db) for long-term storage and analytics.

Discord Commands

!listbets — show active bets.

!addbet — manually add a bet via JSON.

!removebet <id> — remove a tracked bet.

!train — upload labeled slips to improve OCR/detection.

🚀 Running Locally
Install dependencies

bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
Set environment variables Create a .env file (or export in shell):

env
BOT_TOKEN=your_discord_bot_token
CHANNEL_ID=123456789012345678
DEBUG_LOGGING=true
USE_YOLO=false
USE_EASYOCR=false
Run the bot

bash
python app.py
☁️ Deploying on Railway
Connect your GitHub repo to Railway.

Set environment variables in Railway’s dashboard:

BOT_TOKEN — your Discord bot token.

CHANNEL_ID — the Discord channel ID where slips are posted.

Optional flags: DEBUG_LOGGING, USE_YOLO, USE_EASYOCR.

Start command: Railway will run python app.py by default.

Railway automatically installs dependencies from requirements.txt.

🧪 Testing OCR + Parsing
Use the included test harness:

bash
python tests/run_slip_intake.py path/to/slip.png
This prints raw OCR text, routed/normalized text, and the structured ParsedSlip.

📂 Project Structure
Code
BetTrackingBot/
├── app.py              # Entrypoint
├── config.py           # Settings/env vars
├── ocr.py              # Baseline OCR
├── ocr_advanced.py     # YOLO/EasyOCR multipass OCR
├── format_router.py    # Normalize sportsbook formats
├── parsing.py          # Slip parsing & league detection
├── espn.py             # ESPN API integration
├── storage.py          # JSON persistence
├── db.py               # SQLite persistence
├── cogs/bets.py        # Discord cog with commands & loops
├── tests/run_slip_intake.py
├── requirements.txt
└── tracked_bets.json   # Auto-generated runtime file
⚙️ Future Enhancements
Full prop tracking via ESPN boxscore APIs.

Automated YOLO retraining from !train samples.

Richer embeds with per-leg live updates.
