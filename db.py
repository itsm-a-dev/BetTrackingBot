import logging
import aiosqlite
from typing import List, Dict, Any

logger = logging.getLogger("db")

DB_PATH = "bets.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS bets (
    id TEXT PRIMARY KEY,
    user TEXT,
    created_at TEXT,
    stake REAL,
    payout REAL,
    settlement TEXT,
    settled_at TEXT
);

CREATE TABLE IF NOT EXISTS legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id TEXT,
    league TEXT,
    type TEXT,
    teams_or_player TEXT,
    market TEXT,
    odds TEXT,
    status TEXT,
    live TEXT,
    FOREIGN KEY(bet_id) REFERENCES bets(id)
);
"""


async def init_db(path: str = DB_PATH):
    async with aiosqlite.connect(path) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("Database initialized.")


async def insert_bet(bet_id: str, bet: Dict[str, Any], path: str = DB_PATH):
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO bets (id, user, created_at, stake, payout, settlement, settled_at) VALUES (?,?,?,?,?,?,?)",
            (
                bet_id,
                bet.get("user"),
                bet.get("created_at"),
                bet.get("stake"),
                bet.get("payout"),
                bet.get("settlement"),
                bet.get("settled_at"),
            ),
        )
        for leg in bet.get("legs", []):
            await db.execute(
                "INSERT INTO legs (bet_id, league, type, teams_or_player, market, odds, status, live) VALUES (?,?,?,?,?,?,?,?)",
                (
                    bet_id,
                    leg.get("league"),
                    leg.get("type"),
                    leg.get("teams_or_player"),
                    leg.get("market"),
                    leg.get("odds"),
                    leg.get("status"),
                    leg.get("live"),
                ),
            )
        await db.commit()
    logger.debug(f"Inserted bet {bet_id} with {len(bet.get('legs', []))} legs.")


async def get_active_bets(path: str = DB_PATH) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM bets WHERE settlement IS NULL")
        bets = await cursor.fetchall()
        out = []
        for b in bets:
            legs_cur = await db.execute("SELECT * FROM legs WHERE bet_id=?", (b["id"],))
            legs = await legs_cur.fetchall()
            out.append({"bet": dict(b), "legs": [dict(l) for l in legs]})
        return out


async def mark_settlement(bet_id: str, settlement: str, path: str = DB_PATH):
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "UPDATE bets SET settlement=?, settled_at=datetime('now') WHERE id=?",
            (settlement, bet_id),
        )
        await db.commit()
    logger.info(f"Bet {bet_id} settled as {settlement}.")
