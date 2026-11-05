import sqlite3
import json
import uuid
import os
from datetime import datetime
from dataclasses import asdict
from src.engine.units import Roster, Unit, Coach, SpecialTeams

DB_PATH = "data/cfb_battler.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS snapshots (
            id TEXT PRIMARY KEY,
            player_name TEXT,
            round_number INTEGER,
            wins INTEGER,
            losses INTEGER,
            coach_id TEXT,
            qb_data TEXT,
            rb_data TEXT,
            wr_data TEXT,
            oline_data TEXT,
            front7_data TEXT,
            secondary_data TEXT,
            st_data TEXT,
            created_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_snapshot(roster: Roster, round_number: int, wins: int, losses: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    snapshot_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    
    cursor.execute('''
        INSERT INTO snapshots (
            id, player_name, round_number, wins, losses, coach_id,
            qb_data, rb_data, wr_data, oline_data, front7_data, secondary_data, st_data,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        snapshot_id,
        roster.player_name,
        round_number,
        wins,
        losses,
        roster.coach.name, # Using name as coach_id for now
        json.dumps(asdict(roster.qb)),
        json.dumps(asdict(roster.rb)),
        json.dumps(asdict(roster.wr)),
        json.dumps(asdict(roster.oline)),
        json.dumps(asdict(roster.front7)),
        json.dumps(asdict(roster.secondary)),
        json.dumps(asdict(roster.special_teams)),
        created_at
    ))
    
    conn.commit()
    conn.close()
    return snapshot_id

def get_random_snapshot(round_number: int, exclude_id: str = None) -> Roster:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = "SELECT * FROM snapshots WHERE round_number = ?"
    params = [round_number]
    if exclude_id:
        query += " AND id != ?"
        params.append(exclude_id)
    
    query += " ORDER BY RANDOM() LIMIT 1"
    
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
        
    # Mapping row to Roster object (Assuming column order from CREATE TABLE)
    # id, player_name, round_number, wins, losses, coach_id, qb_data, rb_data, wr_data, oline_data, front7_data, secondary_data, st_data, created_at
    
    def load_unit(data_str):
        data = json.loads(data_str)
        return Unit(**data)

    def load_coach(coach_id):
        # This is a bit of a placeholder since we don't have a coach registry yet
        # For now, we'll just reconstruct a basic one or look it up if we had a registry
        return Coach(name=coach_id, off_scheme="Unknown", def_scheme="Unknown")

    def load_st(data_str):
        data = json.loads(data_str)
        return SpecialTeams(**data)

    return Roster(
        player_name=row[1],
        qb=load_unit(row[6]),
        rb=load_unit(row[7]),
        wr=load_unit(row[8]),
        oline=load_unit(row[9]),
        front7=load_unit(row[10]),
        secondary=load_unit(row[11]),
        coach=load_coach(row[5]),
        special_teams=load_st(row[12])
    )
