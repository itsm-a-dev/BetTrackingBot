import discord
from discord.ext import commands
from services import slip_processor, storage

class Bets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addbet")
    async def add_bet(self, ctx):
        if not ctx.message.attachments:
            await ctx.send("❌ Please upload a bet slip image with your command.")
            return

        attachment = ctx.message.attachments[0]
        img_bytes = await attachment.read()

        parsed_slip = slip_processor.parse_slip(img_bytes)

        embed = discord.Embed(title="Confirm Bet", description="Here’s what I read from your slip:")
        embed.add_field(name="Book", value=parsed_slip.bookmaker, inline=True)
        embed.add_field(name="Stake", value=parsed_slip.stake, inline=True)
        embed.add_field(name="Odds", value=parsed_slip.odds, inline=True)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Bets(bot))
