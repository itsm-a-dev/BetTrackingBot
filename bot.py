import discord
from discord.ext import commands
import os
from config import BOT_TOKEN

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Load cogs
async def load_cogs():
    await bot.load_extension("cogs.bets")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

async def main():
    await load_cogs()
    await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
