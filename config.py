import os
from dotenv import load_dotenv
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
POSTGRES_DSN = os.getenv("POSTGRES_DSN")
TRACK_CHANNEL_ID = int(os.getenv("TRACK_CHANNEL_ID", "0"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.9"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "/usr/bin/tesseract")
