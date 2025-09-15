# cogs/bets.py
import discord
from discord.ext import commands, tasks
from config import TRACK_CHANNEL_ID, CONFIDENCE_THRESHOLD
from ocr import ocr_image
from parsing import parse_slip
from espn import fetch_scores, find_game_id_for_teams, extract_score_and_status, find_player_stat_for_leg

class Bets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # tracked[msg_id] = { 'league', 'bet_type', 'odds', 'stake', 'payout', 'legs':[LegDict], 'message': Message }
        self.tracked = {}
        self.update_scores.start()
        self.update_props.start()

    def cog_unload(self):
        self.update_scores.cancel()
        self.update_props.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != TRACK_CHANNEL_ID or not message.attachments:
            return

        try:
            img_bytes = await message.attachments[0].read()
        except Exception as e:
            print(f"[ERROR] Reading attachment failed: {e}")
            return

        try:
            text = ocr_image(img_bytes)
            print(f"[DEBUG] OCR length={len(text)}")
        except Exception as e:
            print(f"[ERROR] OCR failed: {e}")
            await message.channel.send("❌ Could not read that image. Try a clearer screenshot.")
            return

        parsed = parse_slip(text)
        print(f"[DEBUG] Parsed bet_type={parsed.bet_type} league={parsed.league} legs={len(parsed.legs)} odds={parsed.odds} stake={parsed.stake} payout={parsed.payout}")

        confidence = 0.9 if parsed.legs and any(l.type != "unknown" for l in parsed.legs) else 0.5
        if confidence < CONFIDENCE_THRESHOLD:
            await message.channel.send(f"{message.author.mention} ⚠️ Low confidence parse — please edit manually.")
            return

        embed = discord.Embed(
            title="🎯 Parlay" if parsed.bet_type == "parlay" else "📄 Bet Recorded",
            color=discord.Color.blurple()
        )
        embed.add_field(name="League", value=parsed.league or "Mixed", inline=True)
        if parsed.odds is not None:
            embed.add_field(name="Odds", value=str(parsed.odds), inline=True)
        if parsed.stake is not None:
            embed.add_field(name="Stake", value=f"${parsed.stake}", inline=True)
        if parsed.payout is not None:
            embed.add_field(name="Payout", value=f"${parsed.payout}", inline=True)

        lines = []
        for idx, leg in enumerate(parsed.legs, start=1):
            if leg.type == "prop":
                detail = []
                if leg.side: detail.append(leg.side.upper())
                if leg.line is not None: detail.append(str(leg.line))
                tgt = " ".join(detail) if detail else (leg.target_text or "")
                lines.append(f"{idx}. {leg.player} — {leg.stat.title()} {tgt}".strip())
            elif leg.type == "total":
                lines.append(f"{idx}. Total — {leg.side.upper() if leg.side else ''} {leg.line or ''}".strip())
            elif leg.type == "spread":
                lines.append(f"{idx}. Spread — {leg.team} {leg.line}")
            elif leg.type == "moneyline":
                lines.append(f"{idx}. Moneyline — {leg.team or 'Unknown'}")
            else:
                lines.append(f"{idx}. {leg.target_text or 'Unknown leg'}")
        embed.add_field(name="Legs", value="\n".join(lines) if lines else "—", inline=False)
        embed.set_footer(text="Odds locked at capture")

        try:
            posted = await message.channel.send(embed=embed)
        except Exception as e:
            print(f"[ERROR] Failed to send embed: {e}")
            return

        self.tracked[posted.id] = {
            "league": parsed.league,
            "bet_type": parsed.bet_type,
            "odds": parsed.odds,
            "stake": parsed.stake,
            "payout": parsed.payout,
            "legs": [leg.__dict__ for leg in parsed.legs],
            "message": posted,
        }
        print(f"[DEBUG] Tracking message_id={posted.id} with {len(parsed.legs)} legs")

    @tasks.loop(seconds=60)
    async def update_scores(self):
        for msg_id, bet in list(self.tracked.items()):
            try:
                if all(l["type"] == "prop" for l in bet["legs"]):
                    continue
                league = bet["league"]
                scoreboard = await fetch_scores(league)
                events = scoreboard.get("events", [])
                for leg in bet["legs"]:
                    if not leg.get("game_id") and leg.get("game_teams"):
                        gid = find_game_id_for_teams(leg["league"] or league, leg["game_teams"], scoreboard)
                        if gid:
                            leg["game_id"] = gid
                msg: discord.Message = bet["message"]
                new = discord.Embed(title=msg.embeds[0].title, color=msg.embeds[0].color)
                new.add_field(name="League", value=bet["league"] or "Mixed", inline=True)
                if bet.get("odds") is not None:
                    new.add_field(name="Odds", value=str(bet["odds"]), inline=True)
                if bet.get("stake") is not None:
                    new.add_field(name="Stake", value=f"${bet['stake']}", inline=True)
                if bet.get("payout") is not None:
                    new.add_field(name="Payout", value=f"${bet['payout']}", inline=True)
                lines = []
                for idx, leg in enumerate(bet["legs"], start=1):
                    if leg["type"] == "prop":
                        detail = []
                        if leg.get("side"): detail.append(leg["side"].upper())
                        if leg.get("line") is not None: detail.append(str(leg["line"]))
                        tgt = " ".join(detail) if detail else (leg.get("target_text") or "")
                        lines.append(f"{idx}. {leg.get('player')} — {str(leg.get('stat')).title()} {tgt}".strip())
                    elif leg["type"] == "total":
                        lines.append(f"{idx}. Total — {leg.get('side','').upper()} {leg.get('line')}")
                    elif leg["type"] == "spread":
                        lines.append(f"{idx}. Spread — {leg.get('team')} {leg.get('line')}")
                    elif leg["type"] == "moneyline":
                        lines.append(f"{idx}. Moneyline — {leg.get('team') or 'Unknown'}")
                    else:
                        lines.append(f"{idx}. {leg.get('target_text') or 'Unknown leg'}")
                new.add_field(name="Legs", value="\n".join(lines) if lines else "—", inline=False)
                first_event = None
                for leg in bet["legs"]:
                    if leg.get("game_id"):
                        first_event = next((e for e in events if e["id"] == leg["game_id"]), None)
                        if first_event:
                            break
                if first_event:
                    ss = extract_score_and_status(first_event)
                    new.add_field(name="Score", value=ss["score"], inline=False)
                    new.add_field(name="Status", value=ss["status"], inline=False)
                new.set_footer(text="Odds locked at capture")
                await msg.edit(embed=new)
            except Exception as e:
                print(f"[ERROR] update_scores failed for msg_id={msg_id}: {e}")
                
    @tasks.loop(seconds=20)
    async def update_props(self):
        """Update prop legs more frequently."""
        for msg_id, bet in list(self.tracked.items()):
            try:
                prop_legs = [l for l in bet["legs"] if l["type"] == "prop"]
                if not prop_legs:
                    continue

                for leg in prop_legs:
                    league = leg.get("league") or bet["league"]
                    if not league or not leg.get("game_teams"):
                        continue

                    scoreboard = await fetch_scores(league)
                    gid = leg.get("game_id") or find_game_id_for_teams(league, leg["game_teams"], scoreboard)
                    if not gid:
                        continue
                    leg["game_id"] = gid

                    event = next((e for e in scoreboard.get("events", []) if e["id"] == gid), None)
                    if not event:
                        continue

                    current = find_player_stat_for_leg(league, event, leg.get("player") or "", leg.get("stat") or "")
                    if current is not None:
                        leg["current_value"] = current
                        status = event["status"]["type"]["description"].lower()
                        if status == "final":
                            if leg.get("side") == "over" and current > float(leg.get("line", 0)):
                                leg["result"] = "won"
                            elif leg.get("side") == "under" and current < float(leg.get("line", 0)):
                                leg["result"] = "won"
                            else:
                                leg["result"] = "lost"

                # Optional: settle bet if all legs final
                if all(l.get("result") in ("won", "lost") for l in bet["legs"]):
                    all_won = all(l["result"] == "won" for l in bet["legs"])
                    end_title = ("✅ Parlay WON" if all_won else "❌ Parlay LOST") if bet["bet_type"] == "parlay" else ("✅ Bet WON" if all_won else "❌ Bet LOST")
                    final_embed = discord.Embed(title=end_title, color=discord.Color.green() if all_won else discord.Color.red())
                    final_embed.add_field(name="League", value=bet["league"] or "Mixed", inline=True)
                    if bet.get("odds") is not None:
                        final_embed.add_field(name="Odds", value=str(bet["odds"]), inline=True)
                    if bet.get("stake") is not None:
                        final_embed.add_field(name="Stake", value=f"${bet['stake']}", inline=True)
                    if bet.get("payout") is not None:
                        final_embed.add_field(name="Payout", value=f"${bet['payout']}", inline=True)

                    # Legs summary with results
                    lines = []
                    for idx, leg in enumerate(bet["legs"], start=1):
                        res_icon = "✅" if leg.get("result") == "won" else "❌"
                        if leg["type"] == "prop":
                            detail = []
                            if leg.get("side"): detail.append(leg["side"].upper())
                            if leg.get("line") is not None: detail.append(str(leg["line"]))
                            tgt = " ".join(detail) if detail else (leg.get("target_text") or "")
                            curr_val = f" ({leg.get('current_value')})" if leg.get("current_value") is not None else ""
                            lines.append(f"{idx}. {leg.get('player')} — {str(leg.get('stat')).title()} {tgt}{curr_val} {res_icon}".strip())
                        elif leg["type"] == "total":
                            lines.append(f"{idx}. Total — {leg.get('side','').upper()} {leg.get('line')} {res_icon}")
                        elif leg["type"] == "spread":
                            lines.append(f"{idx}. Spread — {leg.get('team')} {leg.get('line')} {res_icon}")
                        elif leg["type"] == "moneyline":
                            lines.append(f"{idx}. Moneyline — {leg.get('team') or 'Unknown'} {res_icon}")
                        else:
                            lines.append(f"{idx}. {leg.get('target_text') or 'Unknown leg'} {res_icon}")
                    final_embed.add_field(name="Legs", value="\n".join(lines) if lines else "—", inline=False)
                    final_embed.set_footer(text="Settled")
                    await bet["message"].edit(embed=final_embed)
                    self.tracked.pop(msg_id, None)

            except Exception as e:
                print(f"[ERROR] update_props failed for msg_id={msg_id}: {e}")

    @update_scores.before_loop
    @update_props.before_loop
    async def before_loops(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Bets(bot))

@commands.command(name="listbets")
async def list_bets(self, ctx):
    """List all currently tracked bets."""
    if not self.tracked:
        await ctx.send("No active bets.")
        return
    lines = []
    for mid, bet in self.tracked.items():
        lines.append(f"**{bet['bet_type']}** {bet.get('league') or 'Mixed'} — {len(bet['legs'])} legs")
    await ctx.send("\n".join(lines))

@commands.command(name="addbet")
async def add_bet(self, ctx, *, description: str):
    """Manually add a bet description (no OCR)."""
    # Minimal example: just store text
    self.tracked[f"manual-{len(self.tracked)+1}"] = {
        "league": None,
        "bet_type": "manual",
        "odds": None,
        "stake": None,
        "payout": None,
        "legs": [{"type": "manual", "target_text": description}],
        "message": None
    }
    save_tracked(self.tracked)
    await ctx.send(f"Added manual bet: {description}")

@commands.command(name="removebet")
async def remove_bet(self, ctx, bet_id: str):
    """Remove a bet by ID."""
    if bet_id in self.tracked:
        self.tracked.pop(bet_id)
        save_tracked(self.tracked)
        await ctx.send(f"Removed bet {bet_id}")
    else:
        await ctx.send(f"No bet found with ID {bet_id}")


