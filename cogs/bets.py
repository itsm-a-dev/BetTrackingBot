import discord
from discord.ext import commands, tasks
from typing import Dict, Any, List
from config import TRACK_CHANNEL_ID, CONFIDENCE_THRESHOLD
from ocr import ocr_image
from parsing import parse_slip, Leg
from espn import fetch_scores, find_game_id_for_teams, extract_score_and_status, find_player_stat_for_leg


class Bets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # tracked[msg_id] = { 'league', 'bet_type', 'odds', 'stake', 'payout', 'legs':[LegDict], 'game_ids': set(), 'message': Message }
        self.tracked: Dict[int, Dict[str, Any]] = {}
        self.update_scores.start()

    def cog_unload(self):
        self.update_scores.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id != TRACK_CHANNEL_ID or not message.attachments:
            return

        print(f"[DEBUG] Intake from {message.author} in {message.channel.id} with {len(message.attachments)} attachment(s)")

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
        print(f"[DEBUG] Parsed bet_type={parsed.bet_type} league={parsed.league} legs={len(parsed.legs or [])} odds={parsed.odds} stake={parsed.stake} payout={parsed.payout}")

        # Confidence heuristic
        legs_ok = parsed.legs and len(parsed.legs) > 0
        any_leg_informative = any(l.type != "unknown" for l in (parsed.legs or []))
        confidence = 0.9 if legs_ok and any_leg_informative else 0.5

        if confidence < CONFIDENCE_THRESHOLD:
            await message.channel.send(f"{message.author.mention} ⚠️ Low confidence parse — please edit manually.")
            return

        # Build embed
        title = "🎯 Parlay" if parsed.bet_type == "parlay" else "📄 Bet Recorded"
        embed = discord.Embed(title=title, color=discord.Color.blurple())
        embed.add_field(name="League", value=parsed.league, inline=True)
        if parsed.odds is not None:
            embed.add_field(name="Odds", value=str(parsed.odds), inline=True)
        if parsed.stake is not None:
            embed.add_field(name="Stake", value=f"${parsed.stake}", inline=True)
        if parsed.payout is not None:
            embed.add_field(name="Payout", value=f"${parsed.payout}", inline=True)

        # Legs summarization
        leg_lines: List[str] = []
        for idx, leg in enumerate(parsed.legs or [], start=1):
            if leg.type == "prop":
                detail = []
                if leg.side: detail.append(leg.side.upper())
                if leg.line is not None: detail.append(str(leg.line))
                tgt = " ".join(detail) if detail else (leg.target_text or "")
                leg_lines.append(f"{idx}. {leg.player} — {leg.stat.title()} {tgt}".strip())
            elif leg.type == "total":
                leg_lines.append(f"{idx}. Total — {leg.side.upper()} {leg.line}")
            elif leg.type == "spread":
                leg_lines.append(f"{idx}. Spread — {leg.team} {leg.line}")
            elif leg.type == "moneyline":
                leg_lines.append(f"{idx}. Moneyline — {leg.team or 'Unknown'}")
            else:
                leg_lines.append(f"{idx}. {leg.target_text or 'Unknown leg'}")
        embed.add_field(name="Legs", value="\n".join(leg_lines) if leg_lines else "—", inline=False)

        embed.set_footer(text="Odds locked at capture")
        try:
            posted = await message.channel.send(embed=embed)
        except Exception as e:
            print(f"[ERROR] Failed to send embed: {e}")
            return

        # Prepare tracking state
        state = {
            "league": parsed.league,
            "bet_type": parsed.bet_type,
            "odds": parsed.odds,
            "stake": parsed.stake,
            "payout": parsed.payout,
            "legs": [leg.__dict__ for leg in (parsed.legs or [])],  # serialize Leg dataclasses
            "message": posted,
        }

        self.tracked[posted.id] = state
        print(f"[DEBUG] Tracking message_id={posted.id} with {len(state['legs'])} legs")

    @tasks.loop(seconds=60)
    async def update_scores(self):
        for msg_id, bet in list(self.tracked.items()):
            try:
                league = bet["league"]
                scoreboard = await fetch_scores(league)
                events = scoreboard.get("events", [])

                # Try to attach game_id to legs lacking it, based on game_teams
                for leg in bet["legs"]:
                    if "game_id" in leg and leg["game_id"]:
                        continue
                    teams = leg.get("game_teams") or []
                    gid = find_game_id_for_teams(league, teams, scoreboard) if teams else None
                    leg["game_id"] = gid

                # Compute live info and settle legs where determinable
                final_flags = []
                for leg in bet["legs"]:
                    gid = leg.get("game_id")
                    # Find event
                    event = next((e for e in events if e["id"] == gid), None) if gid else None
                    # Update score/status block once per message, using first matched event
                    # We'll rebuild embed at the end

                    # For prop legs, try to fetch current stat value
                    if leg["type"] == "prop" and event:
                        current = find_player_stat_for_leg(league, event, leg.get("player") or "", leg.get("stat") or "")
                        if current is not None:
                            leg["current_value"] = current
                            # Settle condition (simple, can be extended per stat semantics)
                            if leg.get("stat") in ("anytime td","anytime touchdown","to score"):
                                # Treat any TD >= 1 as hit when final; if we see >=1 midgame we can mark provisional
                                pass  # keep pending until final unless you want early-hit semantics
                            else:
                                line = leg.get("line")
                                side = leg.get("side")
                                if line is not None and side in ("over","under"):
                                    if side == "over" and current > float(line):
                                        leg["result"] = "won" if event["status"]["type"]["description"].lower() == "final" else "pending"
                                    if side == "under" and current < float(line):
                                        leg["result"] = "won" if event["status"]["type"]["description"].lower() == "final" else "pending"
                    # For non-prop legs, we only settle at final by comparing score — omitted here for brevity

                    # Mark final flags if event is final
                    if event and event["status"]["type"]["description"].lower() == "final":
                        final_flags.append(True)

                # Rebuild embed with live info
                msg: discord.Message = bet["message"]
                old = msg.embeds[0] if msg.embeds else discord.Embed(title="Bet", color=discord.Color.blurple())
                new = discord.Embed(title=old.title, color=old.color)

                # Static fields
                new.add_field(name="League", value=bet["league"], inline=True)
                if bet.get("odds") is not None:
                    new.add_field(name="Odds", value=str(bet["odds"]), inline=True)
                if bet.get("stake") is not None:
                    new.add_field(name="Stake", value=f"${bet['stake']}", inline=True)
                if bet.get("payout") is not None:
                    new.add_field(name="Payout", value=f"${bet['payout']}", inline=True)

                # Legs with live values
                lines: List[str] = []
                for idx, leg in enumerate(bet["legs"], start=1):
                    if leg["type"] == "prop":
                        detail = []
                        if leg.get("side"): detail.append(leg["side"].upper())
                        if leg.get("line") is not None: detail.append(str(leg["line"]))
                        tgt = " ".join(detail) if detail else (leg.get("target_text") or "")
                        curr = f" — {leg['current_value']}" if leg.get("current_value") is not None else ""
                        res = f" ✅" if leg.get("result") == "won" else f" ❌" if leg.get("result") == "lost" else ""
                        lines.append(f"{idx}. {leg.get('player')} — {str(leg.get('stat')).title()} {tgt}{curr}{res}".strip())
                    elif leg["type"] == "total":
                        lines.append(f"{idx}. Total — {leg.get('side','').upper()} {leg.get('line')}")
                    elif leg["type"] == "spread":
                        lines.append(f"{idx}. Spread — {leg.get('team')} {leg.get('line')}")
                    elif leg["type"] == "moneyline":
                        lines.append(f"{idx}. Moneyline — {leg.get('team') or 'Unknown'}")
                    else:
                        lines.append(f"{idx}. {leg.get('target_text') or 'Unknown leg'}")
                new.add_field(name="Legs", value="\n".join(lines) if lines else "—", inline=False)

                # Add a single score/status block if we had any event
                first_event = None
                # Prefer the first leg with a game_id
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

                # Parlay settlement: if final and any leg is lost -> lost; if final and all legs won -> won
                finals = []
                for leg in bet["legs"]:
                    if not leg.get("game_id"):
                        continue
                    e = next((x for x in events if x["id"] == leg["game_id"]), None)
                    if not e: 
                        continue
                    finals.append(e["status"]["type"]["description"].lower() == "final")

                if finals and all(finals):
                    # Simple settlement rule: props marked 'won' count, anything else non-won => lost
                    all_won = all(l.get("result") == "won" or l["type"] != "prop" for l in bet["legs"])
                    # For non-prop legs, you can implement proper settlement by interpreting score vs line.

                    end_title = ("✅ Parlay WON" if all_won else "❌ Parlay LOST") if bet["bet_type"] == "parlay" else ("✅ Bet WON" if all_won else "❌ Bet LOST")
                    final_embed = discord.Embed(title=end_title, color=discord.Color.green() if all_won else discord.Color.red())
                    # Carry over fields
                    final_embed.add_field(name="League", value=bet["league"], inline=True)
                    if bet.get("odds") is not None:
                        final_embed.add_field(name="Odds", value=str(bet["odds"]), inline=True)
                    if bet.get("stake") is not None:
                        final_embed.add_field(name="Stake", value=f"${bet['stake']}", inline=True)
                    if bet.get("payout") is not None:
                        final_embed.add_field(name="Payout", value=f"${bet['payout']}", inline=True)
                    final_embed.add_field(name="Legs", value="\n".join(lines) if lines else "—", inline=False)
                    if first_event:
                        ss = extract_score_and_status(first_event)
                        final_embed.add_field(name="Final Score", value=ss["score"], inline=False)
                    final_embed.set_footer(text="Settled")
                    await msg.edit(embed=final_embed)
                    self.tracked.pop(msg_id, None)

            except Exception as e:
                print(f"[ERROR] update_scores failed for msg_id={msg_id}: {e}")

    @update_scores.before_loop
    async def before_update_scores(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Bets(bot))
