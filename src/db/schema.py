import json
import os
import sqlite3
import uuid
from contextlib import closing
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TypeAlias

from src.engine.units import Coach, Roster, SpecialTeams, Unit

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "cfb_battler.db"
DatabasePath: TypeAlias = str | os.PathLike[str]


def _connect(db_path: DatabasePath) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def init_db(db_path: DatabasePath = DB_PATH) -> None:
    with closing(_connect(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY,
                player_name TEXT,
                round_number INTEGER,
                wins INTEGER,
                losses INTEGER,
                coach_id TEXT,
                coach_data TEXT,
                qb_data TEXT,
                rb_data TEXT,
                wr_data TEXT,
                oline_data TEXT,
                front7_data TEXT,
                secondary_data TEXT,
                st_data TEXT,
                created_at TIMESTAMP
            )
            """
        )
        columns = {
            row[1] for row in cursor.execute("PRAGMA table_info(snapshots)")
        }
        if "coach_data" not in columns:
            cursor.execute("ALTER TABLE snapshots ADD COLUMN coach_data TEXT")
        conn.commit()


def save_snapshot(
    roster: Roster,
    round_number: int,
    wins: int,
    losses: int,
    db_path: DatabasePath = DB_PATH,
) -> str:
    init_db(db_path)
    snapshot_id = str(uuid.uuid4())
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO snapshots (
                    id, player_name, round_number, wins, losses, coach_id,
                    coach_data, qb_data, rb_data, wr_data, oline_data,
                    front7_data, secondary_data, st_data, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    roster.player_name,
                    round_number,
                    wins,
                    losses,
                    roster.coach.name,
                    json.dumps(asdict(roster.coach)),
                    json.dumps(asdict(roster.qb)),
                    json.dumps(asdict(roster.rb)),
                    json.dumps(asdict(roster.wr)),
                    json.dumps(asdict(roster.oline)),
                    json.dumps(asdict(roster.front7)),
                    json.dumps(asdict(roster.secondary)),
                    json.dumps(asdict(roster.special_teams)),
                    datetime.now().isoformat(),
                ),
            )
    return snapshot_id


def get_random_snapshot(
    round_number: int,
    exclude_id: str | None = None,
    exclude_player_name: str | None = None,
    db_path: DatabasePath = DB_PATH,
) -> Roster | None:
    init_db(db_path)
    query = """
        SELECT player_name, coach_id, coach_data, qb_data, rb_data, wr_data,
               oline_data, front7_data, secondary_data, st_data
        FROM snapshots
        WHERE round_number = ?
    """
    params: list[str | int] = [round_number]
    if exclude_id:
        query += " AND id != ?"
        params.append(exclude_id)
    if exclude_player_name:
        query += " AND player_name COLLATE NOCASE != ?"
        params.append(exclude_player_name)
    query += " ORDER BY RANDOM() LIMIT 1"

    with closing(_connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(query, params).fetchone()
    if row is None:
        return None

    def load_unit(data: str) -> Unit:
        return Unit(**json.loads(data))

    if row["coach_data"]:
        coach = Coach(**json.loads(row["coach_data"]))
    else:
        coach = Coach(
            name=row["coach_id"],
            off_scheme="Unknown",
            def_scheme="Unknown",
        )

    return Roster(
        player_name=row["player_name"],
        qb=load_unit(row["qb_data"]),
        rb=load_unit(row["rb_data"]),
        wr=load_unit(row["wr_data"]),
        oline=load_unit(row["oline_data"]),
        front7=load_unit(row["front7_data"]),
        secondary=load_unit(row["secondary_data"]),
        coach=coach,
        special_teams=SpecialTeams(**json.loads(row["st_data"])),
    )
