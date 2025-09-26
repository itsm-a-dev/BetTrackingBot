import asyncio
import logging

import discord
from discord.ext import commands

from config import Config
from parsing import refresh_dynamic_catalogs
from cogs.bets import BetsCog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("BetTrackingBot")


def create_bot(config: Config) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.config = config
    return bot


async def main():
    config = Config.from_env()
    bot = create_bot(config)

    @bot.event
    async def on_ready():
        logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
        logger.info("Refreshing dynamic catalogs...")
        try:
            await refresh_dynamic_catalogs(bot.config)
            logger.info("Catalogs refreshed.")
        except Exception as e:
            logger.exception(f"Failed to refresh catalogs: {e}")

    async def load_cogs():
        await bot.add_cog(BetsCog(bot))

    await load_cogs()
    await bot.start(config.bot_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
