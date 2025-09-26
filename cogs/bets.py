import logging
from typing import Dict, Any
from datetime import datetime

import discord
from discord.ext import commands, tasks

from config import Config
from ocr_advanced import run_ocr
from format_router import route_text
from parsing import parse_slip_text
from storage import save_tracked_bets, load_tracked_bets
from espn import fetch_scoreboard, fuzzy_match_game, extract_live_score, extract_player_prop_status
from db import insert_bet, mark_settlement

logger = logging.getLogger("cog.bets")


class BetsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: Config = bot.config
        self.tracked: Dict[str, Any] = load_tracked_bets()
        self.scores_update_loop.start()
        self.props_update_loop.start()
        self.settlement_loop.start()

    def cog_unload(self):
        self.scores_update_loop.cancel()
        self.props_update_loop.cancel()
        self.settlement_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if self.config.channel_id and message.channel.id != self.config.channel_id:
            return
        if not message.attachments:
            return

        for att in message.attachments:
            if att.content_type and ("image" in att.content_type):
                await self._process_slip_image(message, att)

    async def _process_slip_image(self, message: discord.Message, attachment: discord.Attachment):
        try:
            img_bytes = await attachment.read()
            ocr_out = run_ocr(img_bytes, self.config)
            routed_text, style = route_text(ocr_out["text"], self.config)
            parsed = parse_slip_text(routed_text, self.config.ocr_confidence_threshold, style)

            bet_id = f"bet_{message.id}_{attachment.id}"
            bet_obj = {
                "user": str(message.author),
                "created_at": datetime.utcnow().isoformat(),
                "stake": parsed.stake,
                "payout": parsed.payout,
                "legs": [
                    {
                        "league": leg.league,
                        "type": leg.leg_type,
                        "teams_or_player": leg.teams_or_player,
                        "market": leg.market,
                        "odds": leg.odds,
                        "status": "pending",
                        "match": None,
                        "live": None,
                    } for leg in parsed.legs
                ],
                "raw_text": parsed.raw_text,
                "style": parsed.sportsbook_style,
                "regions": ocr_out.get("regions", []),
            }
            self.tracked[bet_id] = bet_obj
            save_tracked_bets(self.tracked)
            await insert_bet(bet_id, bet_obj)

            embed = discord.Embed(title="Bet tracked", color=0x00B2FF)
            embed.add_field(name="Stake", value=str(parsed.stake or "Unknown"), inline=True)
            embed.add_field(name="Payout", value=str(parsed.payout or "Unknown"), inline=True)
            for i, leg in enumerate(parsed.legs, start=1):
                embed.add_field(
                    name=f"Leg {i}",
                    value=f"{leg.league} | {leg.market}\n{leg.teams_or_player}\nOdds: {leg.odds or 'N/A'}",
                    inline=False
                )
            await message.reply(embed=embed)
        except Exception as e:
            logger.exception(f"OCR/parse failed: {e}")
            await message.reply("Failed to parse slip image. Please try a clearer screenshot or manual add via !addbet.")

    @commands.command(name="listbets")
    async def listbets(self, ctx: commands.Context):
        if not self.tracked:
            await ctx.reply("No active bets tracked.")
            return
        embed = discord.Embed(title="Tracked Bets", color=0x00B2FF)
        for bet_id, bet in list(self.tracked.items())[:10]:
            legs_desc = "\n".join([
                f"- {l['league']} | {l['market']} | {l['teams_or_player']} ({l.get('status','pending')})"
                for l in bet["legs"]
            ])
            embed.add_field(name=bet_id, value=legs_desc or "No legs", inline=False)
        await ctx.reply(embed=embed)

    @commands.command(name="addbet")
    async def addbet(self, ctx: commands.Context, *, json_payload: str):
        import json
        try:
            payload = json.loads(json_payload)
            bet_id = f"bet_{ctx.message.id}"
            self.tracked[bet_id] = payload
            save_tracked_bets(self.tracked)
            await insert_bet(bet_id, payload)
            await ctx.reply(f"Added bet {bet_id}.")
        except Exception as e:
            logger.exception(f"Manual add failed: {e}")
            await ctx.reply("Invalid JSON payload.")

    @commands.command(name="removebet")
    async def removebet(self, ctx: commands.Context, bet_id: str):
        if bet_id in self.tracked:
            del self.tracked[bet_id]
            save_tracked_bets(self.tracked)
            await ctx.reply(f"Removed {bet_id}.")
        else:
            await ctx.reply("Bet ID not found.")

    @tasks.loop(seconds=60.0)
    async def scores_update_loop(self):
        try:
            for bet_id, bet in self.tracked.items():
                for leg in bet["legs"]:
                    league = leg["league"]
                    if league in ("Unknown", "UFC"):
                        continue
                    try:
                        data = await fetch_scoreboard(self.config, league)
                        match = fuzzy_match_game(league, leg["teams_or_player"], data.get("events", []))
                        if match:
                            _, event = match
                            leg["match"] = {"id": event.get("id")}
                            leg["live"] = extract_live_score(event)
                    except Exception as e:
                        logger.debug(f"Scores update failed for {league}: {e}")
            save_tracked_bets(self.tracked)
        except Exception as e:
            logger.exception(f"Scores loop error: {e}")

    @tasks.loop(seconds=20.0)
    async def props_update_loop(self):
        try:
            for bet_id, bet in self.tracked.items():
                for leg in bet["legs"]:
                    if leg["type"] != "prop":
                        continue
                    league = leg["league"]
                    player = leg["teams_or_player"] if leg["teams_or_player"] != "Unknown" else ""
                    metric = leg["market"]
                    if leg.get("match") and player:
                        leg["prop_status"] = extract_player_prop_status(league, {}, player, metric)
            save_tracked_bets(self.tracked)
        except Exception as e:
            logger.exception(f"Props loop error: {e}")

    @tasks.loop(seconds=60.0)
    async def settlement_loop(self):
        try:
            for bet_id, bet in self.tracked.items():
                all_final = True
                for leg in bet["legs"]:
                    live = leg.get("live", "")
                    if not (isinstance(live, str) and "Final" in live):
                        all_final = False
                        break
                if all_final and bet.get("settlement") is None:
                    bet["settled_at"] = datetime.utcnow().isoformat()
                    bet["settlement"] = "unknown"
                    await mark_settlement(bet_id, "unknown")
            save_tracked_bets(self.tracked)
        except Exception as e:
            logger.exception(f"Settlement loop error: {e}")

    @scores_update_loop.before_loop
    async def before_scores_loop(self):
        await self.bot.wait_until_ready()

    @props_update_loop.before_loop
    async def before_props_loop(self):
        await self.bot.wait_until_ready()

    @settlement_loop.before_loop
    async def before_settlement_loop(self):
        await self.bot.wait_until_ready()
