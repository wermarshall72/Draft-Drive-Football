"""The run save: engine round trips, determinism, envelope, atomic writes, migrations."""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.engine.football_decks import BONUS_CARD_CATALOG
from src.engine.football_controller import (
    FootballGameController,
    FootballHumanDecision,
    FootballRunPhase,
)
from src.engine.save_data import UnsupportedSave
from src.persistence import migrations
from src.persistence.migrations import CURRENT_SCHEMA_VERSION, MIGRATIONS, migrate_payload
from src.persistence.run_save import (
    BACKUP_FILE_NAME,
    FORMAT,
    RUN_FILE_NAME,
    LoadStatus,
    RunSaveStore,
    SaveBlocked,
    canonical_json,
    decode_envelope,
    delete_run,
    encode_envelope,
    load_run,
    payload_checksum,
    save_run,
)
from tests.football_run_driver import new_controller, step

FIXED_TIME = datetime(2026, 11, 23, 18, 4, 5, tzinfo=timezone.utc)


def _round_trip(controller: FootballGameController) -> FootballGameController:
    data = controller.to_save_data()
    restored = FootballGameController.from_save_data(json.loads(json.dumps(data)))
    assert restored.to_save_data() == data
    assert restored.state == controller.state
    return restored


def _store(path: Path) -> RunSaveStore:
    return RunSaveStore(path, clock=lambda: FIXED_TIME)


# -- round trip at every phase -------------------------------------------------------


def _shop(controller: FootballGameController) -> bool:
    return controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP


def _match(controller: FootballGameController) -> bool:
    return controller.state.phase is FootballRunPhase.MATCH


def _decision(decision: FootballHumanDecision):
    return lambda controller: controller.state.human_decision is decision


PHASES = {
    "coach draft": _decision(FootballHumanDecision.CHOOSE_COACH),
    "mid player draft": lambda c: (
        c.state.phase is FootballRunPhase.PLAYER_DRAFT
        and 2 <= len(c.state.team_builder.selected_players) <= 6
    ),
    "shop with pending removal": lambda c: _shop(c) and c.state.shop.pending_removal is not None,
    "shop after Next Day": lambda c: _shop(c) and c.state.shop.day > 1,
    "shop with owned coach upgrades": lambda c: (
        _shop(c) and bool(c.state.shop.owned_coach_upgrades)
    ),
    "shop with bonus cards": lambda c: _shop(c) and any(
        card.card_id in BONUS_CARD_CATALOG for card in c.state.shop.offensive_deck
    ),
    "offensive play": _decision(FootballHumanDecision.OFFENSIVE_PLAY),
    "defensive scheme": _decision(FootballHumanDecision.DEFENSIVE_SCHEME),
    "fourth down": _decision(FootballHumanDecision.FOURTH_DOWN),
    "conversion": _decision(FootballHumanDecision.CONVERSION),
    "Challenge prompt": _decision(FootballHumanDecision.CHALLENGE),
    "touchdown Challenge available": lambda c: (
        c.state.human_decision is FootballHumanDecision.CONVERSION
        and c.state.challenge_available
    ),
    "enlarged hand": lambda c: _match(c) and (
        len(c.state.match.team_a_offense_deck.hand) > 3
        or len(c.state.match.team_a_defense_deck.hand) > 2
    ),
    "overtime": lambda c: _match(c) and c.state.match.period >= 3,
    "result screen": _decision(FootballHumanDecision.OPEN_NEXT_SHOP),
    "after a Bye Week": lambda c: _shop(c) and bool(c.state.skipped_games),
}


def test_round_trip_at_every_phase_and_decision() -> None:
    reached: dict[str, int] = {}
    for seed in range(16):
        controller = new_controller(seed)
        rng = random.Random(seed)
        while True:
            for name, predicate in PHASES.items():
                if name not in reached and predicate(controller):
                    restored = _round_trip(controller)
                    assert restored.state.human_decision is controller.state.human_decision
                    reached[name] = seed
            if not step(controller, rng):
                break
        if len(reached) == len(PHASES):
            break
    assert set(reached) == set(PHASES)


def test_round_trip_preserves_challenge_snapshot_and_rng_state() -> None:
    for seed in range(16):
        controller = new_controller(seed)
        rng = random.Random(seed)
        while step(controller, rng):
            if controller.state.human_decision is FootballHumanDecision.CHALLENGE:
                restored = _round_trip(controller)
                assert restored._simulator._challenge_snapshot == (
                    controller._simulator._challenge_snapshot
                )
                assert restored._simulator.rng.getstate() == controller._simulator.rng.getstate()
                return
    pytest.fail("No Challenge prompt was reached.")


def test_ended_runs_round_trip_too() -> None:
    controller = new_controller(1)
    rng = random.Random(1)
    while step(controller, rng):
        pass
    assert controller.state.phase in (FootballRunPhase.FIRED, FootballRunPhase.PLAYOFFS)
    _round_trip(controller)


# -- determinism ---------------------------------------------------------------------


def _signature(controller: FootballGameController) -> tuple:
    state = controller.state
    return (
        state.phase, state.human_decision, state.game_number, state.wins, state.losses,
        state.match.match_events if state.match is not None else None,
    )


@pytest.mark.parametrize("seed", range(24))
def test_restored_run_continues_identically_to_the_original(seed: int) -> None:
    """Play N steps, save, load into a new controller, and continue both alike."""
    controller = new_controller(seed)
    rng = random.Random(seed * 7919)
    for _ in range(rng.randrange(20, 160)):
        if not step(controller, rng):
            break
    data = json.loads(json.dumps(controller.to_save_data()))
    restored = FootballGameController.from_save_data(data)

    original_choices = random.Random(seed)
    restored_choices = random.Random(seed)
    start_game = controller.state.game_number
    reached_next_shop = False
    for _ in range(5000):
        assert _signature(restored) == _signature(controller)
        if _shop(controller) and controller.state.game_number > start_game:
            reached_next_shop = True
        more = step(controller, original_choices)
        assert step(restored, restored_choices) is more
        if not more or (reached_next_shop and not _shop(controller)):
            break
    assert restored.to_save_data() == controller.to_save_data()
    assert restored.state == controller.state


def test_restored_run_through_the_file_store_continues_identically(tmp_path: Path) -> None:
    controller = new_controller(5)
    rng = random.Random(5)
    while not (_match(controller) and len(controller.state.match.match_events) > 40):
        assert step(controller, rng)
    store = _store(tmp_path)
    store.save(controller)
    result = RunSaveStore(tmp_path).load()
    assert result.status is LoadStatus.OK
    restored = result.controller
    first, second = random.Random(99), random.Random(99)
    while step(controller, first):
        assert step(restored, second)
    assert not step(restored, second)
    assert restored.to_save_data() == controller.to_save_data()


# -- envelope ------------------------------------------------------------------------


def _saved_controller(steps: int = 30, seed: int = 3) -> FootballGameController:
    controller = new_controller(seed)
    rng = random.Random(seed)
    for _ in range(steps):
        step(controller, rng)
    return controller


def test_envelope_fields_and_readable_payload(tmp_path: Path) -> None:
    controller = _saved_controller()
    _store(tmp_path).save(controller)
    text = (tmp_path / RUN_FILE_NAME).read_text(encoding="utf-8")
    envelope = json.loads(text)
    assert list(envelope) == [
        "format", "schema_version", "game_version", "saved_at", "checksum", "payload",
    ]
    assert envelope["format"] == FORMAT
    assert envelope["schema_version"] == CURRENT_SCHEMA_VERSION
    assert envelope["game_version"] == "0.1.0"
    assert envelope["saved_at"] == "2026-11-23T18:04:05Z"
    assert envelope["checksum"] == payload_checksum(envelope["payload"])
    assert envelope["payload"]["run"] == json.loads(json.dumps(controller.to_save_data()))
    assert text.count("\n") > 100  # indented for reading
    assert str(tmp_path) not in text and os.path.expanduser("~") not in text


def test_checksum_detects_a_single_changed_byte(tmp_path: Path) -> None:
    _store(tmp_path).save(_saved_controller())
    data = bytearray((tmp_path / RUN_FILE_NAME).read_bytes())
    position = data.index(b'"wins": 0') + len(b'"wins": ')
    data[position] = ord("7")  # still valid JSON, but altered
    with pytest.raises(Exception, match="checksum"):
        decode_envelope(bytes(data))


def test_a_changed_byte_with_a_backup_restores_the_backup(tmp_path: Path) -> None:
    store = _store(tmp_path)
    controller = _saved_controller(20)
    store.save(controller)
    previous = controller.to_save_data()
    step(controller, random.Random(1))
    store.save(controller)
    path = tmp_path / RUN_FILE_NAME
    data = bytearray(path.read_bytes())
    data[data.index(b'"losses": ') + len(b'"losses": ')] = ord("2")
    path.write_bytes(bytes(data))

    result = _store(tmp_path).load()

    assert result.status is LoadStatus.RESTORED_FROM_BACKUP
    assert result.controller.to_save_data() == previous
    assert not path.exists()
    assert [moved.name for moved in result.moved_aside] == [
        "run.damaged-20261123T180405Z.json"
    ]


def test_truncated_file_falls_back_to_the_backup(tmp_path: Path) -> None:
    store = _store(tmp_path)
    controller = _saved_controller(20)
    store.save(controller)
    expected = controller.to_save_data()
    step(controller, random.Random(2))
    store.save(controller)
    path = tmp_path / RUN_FILE_NAME
    path.write_bytes(path.read_bytes()[:500])

    result = _store(tmp_path).load()

    assert result.status is LoadStatus.RESTORED_FROM_BACKUP
    assert result.message
    assert result.controller.to_save_data() == expected


def test_both_files_damaged_are_moved_aside_and_reported(tmp_path: Path) -> None:
    store = _store(tmp_path)
    controller = _saved_controller(20)
    store.save(controller)
    step(controller, random.Random(3))
    store.save(controller)
    (tmp_path / RUN_FILE_NAME).write_text("{not json", encoding="utf-8")
    (tmp_path / BACKUP_FILE_NAME).write_bytes(b"")

    result = _store(tmp_path).load()

    assert result.status is LoadStatus.DAMAGED and result.controller is None
    names = sorted(path.name for path in tmp_path.iterdir())
    assert names == [
        "run.backup.damaged-20261123T180405Z.json",
        "run.damaged-20261123T180405Z.json",
    ]
    assert (tmp_path / "run.damaged-20261123T180405Z.json").read_text() == "{not json"
    # A fresh run can save again afterwards.
    store.save(controller)
    assert (tmp_path / RUN_FILE_NAME).exists()


def test_missing_save_reports_none(tmp_path: Path) -> None:
    assert _store(tmp_path).load().status is LoadStatus.NONE
    assert load_run(tmp_path).status is LoadStatus.NONE


def test_save_rotates_the_previous_good_file_to_the_backup(tmp_path: Path) -> None:
    store = _store(tmp_path)
    controller = _saved_controller(10)
    store.save(controller)
    first = (tmp_path / RUN_FILE_NAME).read_bytes()
    step(controller, random.Random(4))
    store.save(controller)
    assert (tmp_path / BACKUP_FILE_NAME).read_bytes() == first
    assert decode_envelope((tmp_path / RUN_FILE_NAME).read_bytes())


def test_a_damaged_current_file_is_not_rotated_over_the_backup(tmp_path: Path) -> None:
    store = _store(tmp_path)
    controller = _saved_controller(10)
    store.save(controller)
    step(controller, random.Random(4))
    store.save(controller)
    good_backup = (tmp_path / BACKUP_FILE_NAME).read_bytes()
    (tmp_path / RUN_FILE_NAME).write_text("garbage", encoding="utf-8")
    _store(tmp_path).save(controller)
    assert (tmp_path / BACKUP_FILE_NAME).read_bytes() == good_backup


def test_delete_removes_the_save_and_its_backup(tmp_path: Path) -> None:
    controller = _saved_controller(10)
    save_run(controller, tmp_path)
    save_run(controller, tmp_path)
    assert (tmp_path / BACKUP_FILE_NAME).exists()
    delete_run(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_save_is_well_under_fifty_milliseconds_late_in_a_match(tmp_path: Path) -> None:
    import time

    controller = new_controller(19)
    rng = random.Random(19)
    while not (
        _match(controller) and controller.state.game_number >= 9
        and controller.state.match.period >= 2
    ):
        assert step(controller, rng)
    store = _store(tmp_path)
    durations = []
    for _ in range(10):
        started = time.perf_counter()
        store.save(controller)
        durations.append(time.perf_counter() - started)
    assert sorted(durations)[5] < 0.05


# -- atomic write --------------------------------------------------------------------


def test_failed_replace_leaves_the_save_and_backup_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    controller = _saved_controller(10)
    store.save(controller)
    step(controller, random.Random(5))
    store.save(controller)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    step(controller, random.Random(6))

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk full"):
        store.save(controller)
    monkeypatch.undo()

    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


# -- migrations ----------------------------------------------------------------------


def _write_envelope(path: Path, payload: dict, version: int) -> None:
    envelope = json.loads(encode_envelope(payload, FIXED_TIME))
    envelope["schema_version"] = version
    path.write_text(json.dumps(envelope), encoding="utf-8")


def test_every_older_schema_version_has_a_registered_step() -> None:
    assert all(version in MIGRATIONS for version in range(1, CURRENT_SCHEMA_VERSION))


def test_migration_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Template for future migrations: write an old-format save, load it upgraded.

    A real migration test should load a checked-in fixture saved by the old
    build instead of building the old payload by hand.
    """
    controller = _saved_controller(25)
    expected = json.loads(json.dumps(controller.to_save_data()))
    # A pretend "version 0" payload that called the run "season".
    old_payload = {"season": expected}

    def zero_to_one(payload: dict) -> dict:
        return {"run": payload.pop("season")}

    monkeypatch.setitem(MIGRATIONS, 0, zero_to_one)
    _write_envelope(tmp_path / RUN_FILE_NAME, old_payload, 0)

    result = _store(tmp_path).load()

    assert result.status is LoadStatus.OK
    assert result.controller.to_save_data() == expected


def test_migrations_apply_in_order_without_changing_the_input() -> None:
    steps = {
        0: lambda payload: {**payload, "log": payload["log"] + ["0->1"]},
        1: lambda payload: {**payload, "log": payload["log"] + ["1->2"]},
    }
    original = {"log": []}
    assert migrate_payload(original, 0, to_version=2, migrations=steps) == {
        "log": ["0->1", "1->2"]
    }
    assert original == {"log": []}
    with pytest.raises(UnsupportedSave, match="too old"):
        migrate_payload(original, 0, to_version=3, migrations=steps)


def test_newer_schema_version_is_reported_and_never_overwritten(tmp_path: Path) -> None:
    controller = _saved_controller(10)
    path = tmp_path / RUN_FILE_NAME
    _write_envelope(path, {"run": controller.to_save_data()}, CURRENT_SCHEMA_VERSION + 1)
    original = path.read_bytes()

    store = _store(tmp_path)
    result = store.load()

    assert result.status is LoadStatus.UNSUPPORTED_VERSION and result.blocked
    assert "newer version" in result.message
    with pytest.raises(SaveBlocked):
        store.save(controller)
    # A store that never loaded it refuses as well.
    with pytest.raises(SaveBlocked):
        _store(tmp_path).save(controller)
    assert path.read_bytes() == original
    assert not (tmp_path / BACKUP_FILE_NAME).exists()

    moved = store.abandon()
    assert [item.name for item in moved] == ["run.abandoned-20261123T180405Z.json"]
    assert moved[0].read_bytes() == original
    store.save(controller)
    assert path.exists()


def test_unknown_card_id_is_an_unsupported_save(tmp_path: Path) -> None:
    controller = _saved_controller(30)
    payload = {"run": json.loads(json.dumps(controller.to_save_data()))}
    payload["run"]["shop"]["offensive_deck"][0][1] = "mystery_play"
    _write_envelope(tmp_path / RUN_FILE_NAME, payload, CURRENT_SCHEMA_VERSION)
    with pytest.raises(UnsupportedSave, match="mystery_play"):
        FootballGameController.from_save_data(payload["run"])

    store = _store(tmp_path)
    result = store.load()

    assert result.status is LoadStatus.UNSUPPORTED and result.blocked
    assert "mystery_play" in result.message
    with pytest.raises(SaveBlocked):
        store.save(controller)


@pytest.mark.parametrize(
    ("path", "value", "fragment"),
    [
        (("builder", "selected_coach_pair"), ["no_such_coach", "run_stop"], "coach pair"),
        (("phase",), "season_ten", "run phase"),
        (("shop", "owned_coach_upgrades"), ["retired-upgrade"], "coach_upgrades card"),
        (("builder", "rng"), [3, [1, 2], None], "draft RNG"),
    ],
)
def test_unknown_ids_and_bad_shapes_raise_unsupported_save(path, value, fragment) -> None:
    data = json.loads(json.dumps(_saved_controller(30).to_save_data()))
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(UnsupportedSave, match=fragment):
        FootballGameController.from_save_data(data)


def test_canonical_checksum_ignores_formatting() -> None:
    payload = {"b": [1, 2], "a": {"z": 1.5, "y": "é"}}
    assert canonical_json(payload) == '{"a":{"y":"é","z":1.5},"b":[1,2]}'.encode()
    assert migrations.CURRENT_SCHEMA_VERSION == 1


def test_persistence_package_does_not_import_pygame() -> None:
    import subprocess
    import sys

    code = (
        "import sys; import src.persistence, src.persistence.run_save, src.profile; "
        "print('pygame' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.stdout.strip() == "False"
