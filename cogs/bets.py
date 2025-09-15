import discord
from discord.ext import commands, tasks
from config import TRACK_CHANNEL_ID, CONFIDENCE_THRESHOLD
from ocr import ocr_image
from parsing import detect_league, extract_odds, extract_stake, best_team_match
from espn import fetch_scores, match_game


class Bets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tracked = {}  # message_id -> bet dict
        self.update_scores.start()

    def cog_unload(self):
        self.update_scores.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Triggered whenever a message is sent in the server."""
        # Ignore bot messages
        if message.author.bot:
            return

        # Debug log
        print(f"[DEBUG] Message from {message.author} in channel {message.channel.id} "
              f"with {len(message.attachments)} attachments")

        # Only process messages in the tracking channel with an attachment
        if message.channel.id != TRACK_CHANNEL_ID or not message.attachments:
            return

        # Read the first attachment
        try:
            img_bytes = await message.attachments[0].read()
        except Exception as e:
            print(f"[ERROR] Failed to read attachment: {e}")
            return

        # Run OCR
        try:
            text = ocr_image(img_bytes)
            print(f"[DEBUG] OCR output:\n{text}")
        except Exception as e:
            print(f"[ERROR] OCR failed: {e}")
            await message.channel.send("❌ Could not read that image. Try a clearer screenshot.")
            return

        # Parse fields
        try:
            league = detect_league(text) or "NFL"
        except Exception as e:
            print(f"[ERROR] detect_league failed: {e}")
            league = "NFL"

        try:
            odds = extract_odds(text)
        except Exception as e:
            print(f"[ERROR] extract_odds failed: {e}")
            odds = None

        try:
            stake = extract_stake(text)
        except Exception as e:
            print(f"[ERROR] extract_stake failed: {e}")
            stake = None

        try:
            teams = best_team_match(league, text)
        except Exception as e:
            print(f"[ERROR] best_team_match failed: {e}")
            teams = []

        print(f"[DEBUG] Parsed league={league}, odds={odds}, stake={stake}, teams={teams}")

        # Confidence check
        confidence = 0.95 if teams else 0.5
        if confidence < CONFIDENCE_THRESHOLD:
            await message.channel.send(
                f"{message.author.mention} ⚠️ Low confidence parse — please edit manually."
            )
            return

        # Build embed
        embed = discord.Embed(title="📄 Bet Recorded", color=discord.Color.green())
        embed.add_field(name="League", value=league, inline=True)
        embed.add_field(name="Teams", value=", ".join(teams) if teams else "Unknown", inline=True)
        embed.add_field(name="Odds", value=str(odds) if odds is not None else "Unknown", inline=True)
        embed.add_field(name="Stake", value=f"${stake}" if stake is not None else "Unknown", inline=True)
        embed.set_footer(text="Odds locked at capture")

        try:
            posted = await message.channel.send(embed=embed)
        except Exception as e:
            print(f"[ERROR] Failed to send embed: {e}")
            return

        # Track for live updates
        self.tracked[posted.id] = {
            "league": league,
            "teams": teams,
            "message": posted
        }

    @tasks.loop(seconds=60)
    async def update_scores(self):
        """Periodically update tracked bets with live scores."""
        for msg_id, bet in list(self.tracked.items()):
            try:
                scoreboard = await fetch_scores(bet["league"])
                game_id = match_game(bet["league"], bet["teams"], scoreboard)
                if not game_id:
                    continue

                for event in scoreboard.get("events", []):
                    if event["id"] == game_id:
                        comp = event["competitions"][0]["competitors"]
                        score_str = " vs ".join(
                            [f"{c['team']['displayName']} {c['score']}" for c in comp]
                        )
                        status = event["status"]["type"]["description"]

                        embed = bet["message"].embeds[0]
                        # Remove old score/status fields if they exist
                        embed.clear_fields()
                        embed.add_field(name="League", value=bet["league"], inline=True)
                        embed.add_field(name="Teams", value=", ".join(bet["teams"]), inline=True)
                        embed.add_field(name="Score", value=score_str, inline=False)
                        embed.add_field(name="Status", value=status, inline=False)

                        await bet["message"].edit(embed=embed)

                        if status.lower() == "final":
                            self.tracked.pop(msg_id, None)
            except Exception as e:
                print(f"[ERROR] update_scores failed for msg_id={msg_id}: {e}")

    @update_scores.before_loop
    async def before_update_scores(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Bets(bot))
