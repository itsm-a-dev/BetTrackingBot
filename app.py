import discord
from discord.ext import commands
import asyncio
from config import DISCORD_TOKEN

# Intents: we need message content for OCR intake
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

class BetBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Load our bets cog
        await self.load_extension("cogs.bets")
        # Sync slash commands if we add them later
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s).")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

    async def on_ready(self):
        print(f"✅ Logged in as {self.user} (ID: {self.user.id})")
        print("------")

def main():
    bot = BetBot()
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
