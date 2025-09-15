import discord, asyncio
from discord.ext import commands, tasks
from ocr import ocr_image
from parsing import detect_league, extract_odds, extract_stake, best_team_match
from espn import fetch_scores, match_game
from config import TRACK_CHANNEL_ID, CONFIDENCE_THRESHOLD

class Bets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracked = {}  # message_id -> bet dict
        self.update_scores.start()

    def cog_unload(self):
        self.update_scores.cancel()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.channel.id != TRACK_CHANNEL_ID or not message.attachments:
            return

        img_bytes = await message.attachments[0].read()
        text = ocr_image(img_bytes)

        league = detect_league(text) or "NFL"
        odds = extract_odds(text) or -110
        stake = extract_stake(text) or 0
        teams = best_team_match(league, text)

        confidence = 0.95 if teams else 0.5

        if confidence < CONFIDENCE_THRESHOLD:
            await message.channel.send(f"{message.author.mention} low confidence parse, please edit manually.")
            # TODO: implement modal for edit
            return

        embed = discord.Embed(title="Bet Recorded", color=discord.Color.green())
        embed.add_field(name="League", value=league)
        embed.add_field(name="Teams", value=", ".join(teams))
        embed.add_field(name="Odds", value=str(odds))
        embed.add_field(name="Stake", value=f"${stake}")
        embed.set_footer(text="Odds locked at capture")

        posted = await message.channel.send(embed=embed)
        self.tracked[posted.id] = {
            "league": league,
            "teams": teams,
            "message": posted
        }

    @tasks.loop(seconds=60)
    async def update_scores(self):
        for msg_id, bet in list(self.tracked.items()):
            scoreboard = await fetch_scores(bet["league"])
            game_id = match_game(bet["league"], bet["teams"], scoreboard)
            if not game_id:
                continue
            for event in scoreboard["events"]:
                if event["id"] == game_id:
                    comp = event["competitions"][0]["competitors"]
                    score_str = " vs ".join([f"{c['team']['displayName']} {c['score']}" for c in comp])
                    status = event["status"]["type"]["description"]
                    embed = bet["message"].embeds[0]
                    embed.add_field(name="Score", value=score_str, inline=False)
                    embed.add_field(name="Status", value=status, inline=False)
                    await bet["message"].edit(embed=embed)
                    if status.lower() == "final":
                        self.tracked.pop(msg_id, None)

    @update_scores.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Bets(bot))
