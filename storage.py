import json
import sqlite3
from datetime import datetime
from typing import Optional

import pandas as pd

DB_FILE = "tournaments.db"


def get_connection():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            state_json TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS match_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            stage TEXT,
            round INTEGER,
            match_id TEXT,
            player1 TEXT,
            player2 TEXT,
            winner TEXT,
            loser TEXT,
            status TEXT,
            saved_at TEXT NOT NULL,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS placements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            place_num INTEGER,
            player_name TEXT,
            weight TEXT,
            faculty TEXT,
            saved_at TEXT NOT NULL,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
        )
    """)

    conn.commit()
    conn.close()


def upsert_tournament(
    tournament_id: Optional[int],
    category: str,
    status: str,
    state: dict,
    history_df: pd.DataFrame,
    placements_df: pd.DataFrame,
) -> int:
    conn = get_connection()
    cur = conn.cursor()

    now = datetime.now().isoformat()
    state_json = json.dumps(state, ensure_ascii=False)

    if tournament_id is None:
        cur.execute("""
            INSERT INTO tournaments (category, status, created_at, updated_at, state_json)
            VALUES (?, ?, ?, ?, ?)
        """, (category, status, now, now, state_json))
        tournament_id = cur.lastrowid
    else:
        cur.execute("""
            UPDATE tournaments
            SET category = ?, status = ?, updated_at = ?, state_json = ?
            WHERE id = ?
        """, (category, status, now, state_json, tournament_id))

        cur.execute("DELETE FROM match_history WHERE tournament_id = ?", (tournament_id,))
        cur.execute("DELETE FROM placements WHERE tournament_id = ?", (tournament_id,))

    if history_df is not None and not history_df.empty:
        rows = history_df.to_dict("records")
        for row in rows:
            cur.execute("""
                INSERT INTO match_history (
                    tournament_id, stage, round, match_id, player1, player2, winner, loser, status, saved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tournament_id,
                row.get("stage", ""),
                row.get("round", None),
                row.get("match_id", ""),
                row.get("player1", ""),
                row.get("player2", ""),
                row.get("winner", ""),
                row.get("loser", ""),
                row.get("status", ""),
                now
            ))

    if placements_df is not None and not placements_df.empty:
        rows = placements_df.to_dict("records")
        for row in rows:
            cur.execute("""
                INSERT INTO placements (
                    tournament_id, place_num, player_name, weight, faculty, saved_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                tournament_id,
                row.get("place", None),
                row.get("full_name", ""),
                str(row.get("weight", "")),
                row.get("faculty", ""),
                now
            ))

    conn.commit()
    conn.close()
    return tournament_id


def list_tournaments(category: Optional[str] = None):
    conn = get_connection()
    cur = conn.cursor()

    if category:
        cur.execute("""
            SELECT id, category, status, created_at, updated_at
            FROM tournaments
            WHERE category = ?
            ORDER BY id DESC
        """, (category,))
    else:
        cur.execute("""
            SELECT id, category, status, created_at, updated_at
            FROM tournaments
            ORDER BY id DESC
        """)

    rows = cur.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "category": row[1],
            "status": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }
        for row in rows
    ]


def load_tournament(tournament_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, category, status, created_at, updated_at, state_json
        FROM tournaments
        WHERE id = ?
    """, (tournament_id,))

    row = cur.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "id": row[0],
        "category": row[1],
        "status": row[2],
        "created_at": row[3],
        "updated_at": row[4],
        "state": json.loads(row[5]),
    }

def clear_all_tournaments():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM match_history")
    cur.execute("DELETE FROM placements")
    cur.execute("DELETE FROM tournaments")
    conn.commit()
    conn.close()
