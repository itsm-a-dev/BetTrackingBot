import discord
from discord.ext import commands, tasks
from config import TRACK_CHANNEL_ID, CONFIDENCE_THRESHOLD
from ocr import ocr_image
from parsing import (
    detect_league, extract_odds, extract_stake,
    extract_game_teams_from_text, classify_market
)
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
        if message.author.bot:
            return

        print(f"[DEBUG] Message from {message.author} in channel {message.channel.id} "
              f"with {len(message.attachments)} attachments")

        if message.channel.id != TRACK_CHANNEL_ID or not message.attachments:
            return

        # Read first attachment
        try:
            img_bytes = await message.attachments[0].read()
        except Exception as e:
            print(f"[ERROR] Failed to read attachment: {e}")
            return

        # OCR
        try:
            text = ocr_image(img_bytes)
            print(f"[DEBUG] OCR output:\n{text}")
        except Exception as e:
            print(f"[ERROR] OCR failed: {e}")
            await message.channel.send("❌ Could not read that image. Try a clearer screenshot.")
            return

        # Parse core fields
        league = detect_league(text) or "NFL"
        odds = extract_odds(text)
        stake = extract_stake(text)
        market = classify_market(text, league)

        # Teams for game matching:
        # - For props, try to pull teams from "@"/"vs".
        # - For team markets, infer from text.
        if market["type"] == "prop":
            teams = extract_game_teams_from_text(league, text)
        else:
            teams = extract_game_teams_from_text(league, text)

        print(f"[DEBUG] Parsed league={league}, odds={odds}, stake={stake}, market={market}, teams={teams}")

        # Confidence: require at least a recognizable market OR two teams
        confidence = 0.0
        if market["type"] == "prop" and market.get("player") and market.get("stat"):
            confidence = 0.95
        elif market["type"] in ("spread", "moneyline", "total"):
            confidence = 0.85
        elif len(teams) >= 2:
            confidence = 0.7
        else:
            confidence = 0.4

        if confidence < CONFIDENCE_THRESHOLD:
            await message.channel.send(
                f"{message.author.mention} ⚠️ Low confidence parse — please edit manually."
            )
            return

        # Build embed
        embed = discord.Embed(title="📄 Bet Recorded", color=discord.Color.green())
        embed.add_field(name="League", value=league, inline=True)

        # Market‑specific display
        if market["type"] == "prop":
            title = f"{market.get('player')} — {market.get('stat').title()}"
            detail = []
            if market.get("side"):
                detail.append(market["side"].upper())
            if market.get("line") is not None:
                detail.append(str(market["line"]))
            embed.add_field(name="Market", value="Player Prop", inline=True)
            embed.add_field(name="Selection", value=title, inline=False)
            if detail:
                embed.add_field(name="Prop Line", value=" ".join(detail), inline=True)
        elif market["type"] == "total":
            embed.add_field(name="Market", value="Total (O/U)", inline=True)
            embed.add_field(name="Selection", value=market["side"].upper(), inline=True)
            embed.add_field(name="Line", value=str(market["line"]), inline=True)
        elif market["type"] == "spread":
            embed.add_field(name="Market", value="Spread", inline=True)
            embed.add_field(name="Selection", value=market["team"], inline=True)
            embed.add_field(name="Line", value=str(market["line"]), inline=True)
        elif market["type"] == "moneyline":
            embed.add_field(name="Market", value="Moneyline", inline=True)
            embed.add_field(name="Selection", value=market.get("team") or "Unknown", inline=True)
        else:
            embed.add_field(name="Market", value="Unknown", inline=True)

        # Teams and finance details
        if teams:
            embed.add_field(name="Game", value=" @ ".join(teams) if len(teams) == 2 else ", ".join(teams), inline=False)
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
            "market": market,
            "message": posted,
        }

    @tasks.loop(seconds=60)
    async def update_scores(self):
        """Periodically update tracked bets with live scores."""
        for msg_id, bet in list(self.tracked.items()):
            try:
                if len(bet["teams"]) < 2:
                    # Can't match a game reliably without both teams; skip live updates
                    continue

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
                        # Rebuild core fields while preserving market display
                        new_embed = discord.Embed(title=embed.title, color=embed.color)
                        for f in embed.fields:
                            # Keep non-live fields (Market, Selection, Line, Odds, Stake)
                            if f.name in ("League", "Market", "Selection", "Line", "Prop Line", "Odds", "Stake", "Game"):
                                new_embed.add_field(name=f.name, value=f.value, inline=f.inline)
                        new_embed.add_field(name="Score", value=score_str, inline=False)
                        new_embed.add_field(name="Status", value=status, inline=False)
                        new_embed.set_footer(text=embed.footer.text if embed.footer else "")

                        await bet["message"].edit(embed=new_embed)

                        if status.lower() == "final":
                            self.tracked.pop(msg_id, None)
            except Exception as e:
                print(f"[ERROR] update_scores failed for msg_id={msg_id}: {e}")

    @update_scores.before_loop
    async def before_update_scores(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Bets(bot))
