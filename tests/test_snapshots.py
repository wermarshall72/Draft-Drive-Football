import json
import sqlite3
from pathlib import Path

from src.db.schema import get_random_snapshot, init_db, save_snapshot
from src.engine.units import Coach, SpecialTeams, Unit
from src.main import create_starter_team


def test_snapshot_round_trip_and_self_exclusion(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "snapshots.db"
    init_db(db_path)
    roster = create_starter_team(
        "Home Team",
        Coach(
            name="Air Raid",
            off_scheme="Air Raid",
            def_scheme="Zone",
            off_modifier=1.25,
            def_modifier=0.9,
            position_modifiers={"QB": 1.1, "WR": 1.2, "SECONDARY": 1.1},
            off_description="Favor QB and WR power.",
            def_description="Favor Secondary power.",
        ),
    )
    roster.qb = Unit(
        name="Custom QB",
        position="QB",
        tier=3,
        power=18.5,
        volatility=0.1,
        synergy_tags=["Air_Raid", "Scrambler"],
        description="Custom snapshot profile.",
    )
    roster.special_teams = SpecialTeams(
        name="Return Unit",
        tier=2,
        momentum_swing_chance=0.11,
        field_goal_reliability=0.91,
    )

    own_snapshot_id = save_snapshot(roster, 1, 2, 1, db_path=db_path)
    assert (
        get_random_snapshot(
            1,
            exclude_id=own_snapshot_id,
            exclude_player_name="Home Team",
            db_path=db_path,
        )
        is None
    )

    opponent = create_starter_team("Opponent")
    opponent_id = save_snapshot(opponent, 1, 3, 0, db_path=db_path)
    restored = get_random_snapshot(
        1,
        exclude_id=own_snapshot_id,
        exclude_player_name="home team",
        db_path=db_path,
    )

    assert restored is not None
    assert restored.player_name == "Opponent"
    assert restored.coach == opponent.coach
    assert restored.qb == opponent.qb
    assert opponent_id

    own_restored = get_random_snapshot(
        1,
        exclude_id=opponent_id,
        exclude_player_name="Opponent",
        db_path=db_path,
    )
    assert own_restored is not None
    assert own_restored.player_name == "Home Team"
    assert own_restored.coach == roster.coach
    assert own_restored.qb == roster.qb
    assert own_restored.special_teams == roster.special_teams


def test_snapshot_db_initializes_independent_of_working_directory(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "elsewhere" / "game.db"
    working_directory = tmp_path / "cwd"
    working_directory.mkdir()
    monkeypatch.chdir(working_directory)

    init_db(database)
    team = create_starter_team("Home Team")
    snapshot_id = save_snapshot(team, 1, 0, 0, db_path=database)

    assert database.exists()
    assert get_random_snapshot(
        1, exclude_id=snapshot_id, db_path=database
    ) is None


def test_legacy_snapshot_without_stamina_uses_default(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-snapshot.db"
    roster = create_starter_team("Legacy Team")
    save_snapshot(roster, 1, 0, 0, db_path=db_path)

    with sqlite3.connect(db_path) as connection:
        qb_data = json.loads(
            connection.execute(
                "SELECT qb_data FROM snapshots WHERE player_name = ?",
                ("Legacy Team",),
            ).fetchone()[0]
        )
        qb_data.pop("stamina")
        connection.execute(
            "UPDATE snapshots SET qb_data = ? WHERE player_name = ?",
            (json.dumps(qb_data), "Legacy Team"),
        )

    restored = get_random_snapshot(1, db_path=db_path)

    assert restored is not None
    assert restored.qb.stamina == 0.75


def test_legacy_coach_snapshot_uses_side_wide_modifiers(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-coach.db"
    roster = create_starter_team("Legacy Coach Team")
    snapshot_id = save_snapshot(roster, 1, 0, 0, db_path=db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE snapshots SET coach_data = ? WHERE id = ?",
            (
                json.dumps(
                    {
                        "name": "Legacy Coach",
                        "off_scheme": "Old Offense",
                        "def_scheme": "Old Defense",
                        "off_modifier": 1.25,
                        "def_modifier": 0.9,
                    }
                ),
                snapshot_id,
            ),
        )

    restored = get_random_snapshot(1, db_path=db_path)

    assert restored is not None
    assert restored.coach.position_modifiers == {}
    assert restored.coach.off_modifier == 1.25
    assert restored.coach.def_modifier == 0.9
    assert restored.get_offensive_power() == 50.0
    assert restored.get_defensive_power() == 36.0
