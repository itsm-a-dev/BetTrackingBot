import os

BOT_TOKEN = os.getenv("DISCORD_TOKEN")  # Railway env var
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bets.db")
