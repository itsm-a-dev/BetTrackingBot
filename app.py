# app.py
import asyncio
import logging
import discord
from discord.ext import commands

from config import DISCORD_TOKEN
from parsing import refresh_catalogs  # dynamic team/player catalogs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("betbot")

class BetBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # needed to read slip messages
        intents.guilds = True
        intents.members = False
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Ensure dynamic catalogs are fresh on startup
        try:
            await refresh_catalogs(force=True)
            logger.info("Dynamic team/player catalogs refreshed")
        except Exception as e:
            logger.warning(f"Catalog refresh failed on startup: {e}")

        # Load cogs
        try:
            await self.load_extension("cogs.bets")
            logger.info("Loaded cog: cogs.bets")
        except Exception as e:
            logger.exception(f"Failed to load cogs.bets: {e}")
            raise

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("------ Bot is ready ------")

def main():
    bot = BetBot()
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.exception(f"Bot crashed: {e}")

if __name__ == "__main__":
    main()
