"""The run save: engine round trips, determinism, envelope, atomic writes, migrations."""

from __future__ import annotations

import copy
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.engine.football_ai import FootballAIDifficulty
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
    for seed in range(200):
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
    for seed in range(64):
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
    assert controller.state.phase in (
        FootballRunPhase.FIRED, FootballRunPhase.ELIMINATED, FootballRunPhase.CHAMPION,
    )
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


def _continues_identically(controller: FootballGameController, seed: int, steps: int = 400) -> None:
    restored = FootballGameController.from_save_data(json.loads(json.dumps(controller.to_save_data())))
    original_choices, restored_choices = random.Random(seed), random.Random(seed)
    for _ in range(steps):
        assert _signature(restored) == _signature(controller)
        more = step(controller, original_choices)
        assert step(restored, restored_choices) is more
        if not more:
            break
    assert restored.to_save_data() == controller.to_save_data()


def _perk_state_reached(controller: FootballGameController) -> str | None:
    """'charge' when a perk charge or rest-of-drive effect is armed; 'green dog' mid-prompt."""
    from src.engine.football import FootballPlayerPerkKind as K
    from src.engine.football_perk_context import perk_history

    if controller.state.human_decision is FootballHumanDecision.GREEN_DOG:
        return "green dog"
    match = controller.state.match
    if not _match(controller) or match is None:
        return None
    history = perk_history(match)
    for side in (match.possession,):
        if history.deep_charge(side, armed_by_completion=False, whole_game=False) or (
            history.deep_charge(side, armed_by_completion=True, whole_game=True)
        ) or history.used(K.SCREEN_WALL, side, "drive") or history.used(
            K.CAPTAINS_ADJUSTMENT, side, "drive"
        ):
            return "charge"
    return None


def test_runs_with_perks_continue_identically_after_a_charge_and_mid_green_dog() -> None:
    found: set[str] = set()
    for seed in range(60):
        controller = new_controller(seed)
        rng = random.Random(seed)
        while step(controller, rng):
            reached = _perk_state_reached(controller)
            if reached is not None and reached not in found:
                found.add(reached)
                _continues_identically(controller, seed)
                break
        if found == {"charge", "green dog"}:
            break
    assert found == {"charge", "green dog"}


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

    def late(controller: FootballGameController) -> bool:
        return (
            _match(controller) and controller.state.game_number >= 9
            and controller.state.match.period >= 2
        )

    for seed in range(64):
        controller = new_controller(seed)
        rng = random.Random(seed)
        while not late(controller) and step(controller, rng):
            pass
        if late(controller):
            break
    assert late(controller)
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


def _mid_match_controller() -> FootballGameController:
    for seed in range(40):
        controller = new_controller(seed)
        rng = random.Random(seed)
        while step(controller, rng):
            if _match(controller) and controller._simulator._challenge_snapshot is not None:
                return controller
    raise AssertionError("No mid-match state with a Challenge snapshot was reached.")


def test_version_1_mid_match_save_migrates_to_version_2(tmp_path: Path) -> None:
    """A v1 save has no opening receiver or perk activations; both are derived."""
    controller = _mid_match_controller()
    expected = json.loads(json.dumps(controller.to_save_data()))
    old = copy.deepcopy(expected)
    simulator = old["simulator"]
    for match in (simulator["state"], simulator["challenge_snapshot"]):
        del match["opening_possession"]
    for event in simulator["state"]["match_events"]:
        event.pop("perk_activations", None)
        if "play_result" in event:
            event["play_result"].pop("perk_activations", None)
    _write_envelope(tmp_path / RUN_FILE_NAME, {"run": old}, 1)

    result = _store(tmp_path).load()

    assert result.status is LoadStatus.OK
    restored = result.controller.to_save_data()
    # The opening drive's offense received the opening kickoff (Team A in a run).
    assert restored["simulator"]["state"]["opening_possession"] == "team_a"
    assert restored["simulator"]["challenge_snapshot"]["opening_possession"] == "team_a"
    events = result.controller.state.match.match_events
    if not any(event.perk_activations for event in controller.state.match.match_events):
        assert restored == expected
    assert all(not event.perk_activations for event in events)


def test_version_1_payload_between_matches_migrates_unchanged() -> None:
    payload = {"run": {"simulator": None, "phase": "pre_match_shop"}}
    assert migrate_payload(payload, 1, to_version=2) == payload


def _reach_playoffs(predicate) -> tuple[FootballGameController, int]:
    """The first Easy run (by seed) that reaches a playoff state matching ``predicate``."""
    for seed in range(60):
        controller = new_controller(seed, FootballAIDifficulty.EASY)
        rng = random.Random(seed)
        while step(controller, rng):
            if controller.state.playoffs is not None and predicate(controller.state):
                return controller, seed
    pytest.fail("No seeded run reached the requested playoff state.")


def test_version_2_save_at_the_old_playoffs_marker_migrates_into_the_playoffs(
    tmp_path: Path,
) -> None:
    """A v2 run that ended at the playoffs marker resumes at game 10 with its bracket."""
    controller, _seed = _reach_playoffs(
        lambda state: state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
        and state.game_number == 10
    )
    expected = json.loads(json.dumps(controller.to_save_data()))
    old = copy.deepcopy(expected)
    del old["playoffs"], old["ai_teams"]
    old["opponent_name"] = "Local AI"
    old["phase"] = "playoffs"
    _write_envelope(tmp_path / RUN_FILE_NAME, {"run": old}, 2)

    result = _store(tmp_path).load()

    assert result.status is LoadStatus.OK
    restored = result.controller.to_save_data()
    # Version 4 gave the old run the fixed legacy AI-team draw; the bracket is
    # seeded from the AI seed alone, so only its AI teams differ.
    assert restored["ai_teams"] == [team_id for team_id, _ in migrations._V4_LEGACY_RUN_TEAMS[:20]]
    bracket, original = restored.pop("playoffs"), expected.pop("playoffs")
    assert {**bracket, "team_ids": None} == {**original, "team_ids": None}
    # The retained game-10 match now names its AI roster after the legacy rival.
    assert restored["simulator"]["state"]["team_b"]["team_name"] == (
        migrations._V4_LEGACY_RUN_TEAMS[9][1]
    )
    ignored = {"ai_teams": None, "simulator": None}
    assert {**restored, **ignored} == {**expected, **ignored}
    assert result.controller.state.human_decision is FootballHumanDecision.OPEN_NEXT_SHOP


def test_version_2_payload_gains_an_empty_bracket() -> None:
    payload = {"run": {"simulator": None, "phase": "pre_match_shop"}}
    assert migrate_payload(payload, 2, to_version=3) == {
        "run": {"simulator": None, "phase": "pre_match_shop", "playoffs": None},
    }


def test_a_run_in_the_playoffs_without_a_bracket_is_unsupported() -> None:
    controller, _seed = _reach_playoffs(lambda state: state.game_number == 11)
    data = json.loads(json.dumps(controller.to_save_data()))
    data["playoffs"] = None
    with pytest.raises(UnsupportedSave, match="bracket"):
        FootballGameController.from_save_data(data)


@pytest.mark.parametrize(
    "where",
    ("bracket", "quarterfinal shop", "semifinal match"),
)
def test_runs_continue_identically_from_the_playoffs(where: str) -> None:
    predicates = {
        "bracket": lambda state: state.phase is FootballRunPhase.READY_FOR_NEXT_GAME,
        "quarterfinal shop": lambda state: state.phase is FootballRunPhase.PRE_MATCH_SHOP
        and state.game_number == 11,
        "semifinal match": lambda state: state.phase is FootballRunPhase.MATCH
        and state.game_number == 12 and len(state.match.match_events) > 20,
    }
    controller, seed = _reach_playoffs(predicates[where])
    _round_trip(controller)
    _continues_identically(controller, seed, steps=3000)


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
    assert migrations.CURRENT_SCHEMA_VERSION == 5


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


def _half_limited_perk_fired_this_half(controller: FootballGameController):
    """The Bait & Jump or Keep Read kind that fired earlier in the match's current half."""
    from src.engine.football import FootballPlayerPerkKind as K, FootballTeamSide
    from src.engine.football_perk_context import perk_history

    match = controller.state.match
    if not _match(controller) or match is None:
        return None
    history = perk_history(match)
    for kind in (K.BAIT_AND_JUMP, K.KEEP_READ):
        if any(history.used(kind, side, "half") for side in FootballTeamSide):
            return kind
    return None


def test_runs_continue_identically_after_bait_and_jump_or_keep_read_fired_this_half() -> None:
    """Saved mid-half after a once-per-half perk fired, the restored run plays on alike."""
    found = set()
    for seed in range(400):
        controller = new_controller(seed)
        rng = random.Random(seed)
        while step(controller, rng):
            kind = _half_limited_perk_fired_this_half(controller)
            if kind is not None and kind not in found:
                found.add(kind)
                _continues_identically(controller, seed)
                break
        if len(found) == 2:
            break
    assert len(found) == 2, found


# -- version 4: AI team identities ----------------------------------------------------

_PLACEHOLDERS = tuple(migrations._V4_PLACEHOLDER_TEAMS)


def _as_version_3(data: dict) -> dict:
    """A current payload rewritten the way version 3 saved it.

    The run gets ``opponent_name`` instead of ``ai_teams``; a bracket lists
    names (the AI seeds take placeholder names in seed order); a live match's AI
    roster carries the old name ("Local AI", or the placeholder in the playoffs).
    """
    old = copy.deepcopy(data)
    del old["ai_teams"]
    old["opponent_name"] = "Local AI"
    bracket = old.get("playoffs")
    placeholder_of: dict[int, str] = {}
    if bracket is not None:
        names = []
        for seed, team_id in enumerate(bracket.pop("team_ids"), start=1):
            if team_id is None:
                names.append(bracket["human_name"])
            else:
                placeholder_of[seed] = _PLACEHOLDERS[len(placeholder_of)]
                names.append(placeholder_of[seed])
        del bracket["human_name"]
        bracket["teams"] = names
    simulator = old.get("simulator")
    if simulator is not None:
        old_name = "Local AI"
        if old["game_number"] > 10:
            game = next(
                game for game in bracket["games"]
                if game["round"] == old["game_number"] - 10
                and bracket["human_seed"] in (game["high_seed"], game["low_seed"])
            )
            other = game["low_seed"] if game["high_seed"] == bracket["human_seed"] else game["high_seed"]
            old_name = placeholder_of[other]
        for match in (simulator["state"], simulator.get("challenge_snapshot")):
            if match and "team_b" in match:
                migrations._rename_team_b(match, old_name)
    return old


def test_version_3_mid_match_save_meets_its_legacy_rival(tmp_path: Path) -> None:
    controller = _mid_match_controller()
    game = controller.state.game_number
    old = _as_version_3(json.loads(json.dumps(controller.to_save_data())))
    assert old["simulator"]["state"]["team_b"]["team_name"] == "Local AI"
    _write_envelope(tmp_path / RUN_FILE_NAME, {"run": old}, 3)

    result = _store(tmp_path).load()

    assert result.status is LoadStatus.OK
    restored = result.controller
    legacy = [team_id for team_id, _name in migrations._V4_LEGACY_RUN_TEAMS[:20]]
    assert list(restored._ai_teams) == legacy
    rival = restored.state.opponent_team
    assert rival.team_id == legacy[game - 1]
    roster = restored.state.match.team_b
    assert roster.team_name == rival.name
    assert roster.special_teams.name == f"{rival.name} Special Teams"
    assert all(player.name.startswith(f"{rival.name} ") for player in roster.players.values())
    assert "opponent_name" not in restored.to_save_data()
    rng = random.Random(1)
    for _ in range(50):
        step(restored, rng)


def test_version_3_playoff_save_maps_placeholders_to_catalog_teams(tmp_path: Path) -> None:
    controller, _seed = _reach_playoffs(
        lambda state: state.phase is FootballRunPhase.MATCH and state.game_number == 12
    )
    old = _as_version_3(json.loads(json.dumps(controller.to_save_data())))
    placeholders = [name for name in old["playoffs"]["teams"] if name in _PLACEHOLDERS]
    _write_envelope(tmp_path / RUN_FILE_NAME, {"run": old}, 3)

    result = _store(tmp_path).load()

    assert result.status is LoadStatus.OK
    state = result.controller.state
    ai_names = [team.name for team in state.playoffs.teams if not team.is_human]
    assert ai_names == [migrations._V4_PLACEHOLDER_TEAMS[name][1] for name in placeholders]
    assert state.match.team_b.team_name == state.opponent_team.name
    assert state.opponent_team.name in ai_names


def test_version_3_migration_avoids_the_human_team_name() -> None:
    # Ridgeline would become the Bighorns, so the spare takes its place.
    payload = {"run": {
        "builder": {"team_name": "Bighorns"}, "opponent_name": "Local AI",
        "game_number": 1, "simulator": None,
        "playoffs": {"human_seed": 1, "games": [], "teams": [
            "Bighorns", "Ridgeline", "Harbor City", "Prairie State", "Iron Valley",
            "Lakeshore", "Red Mesa", "Pine Hollow",
        ]},
    }}
    run = migrate_payload(payload, 3)["run"]
    assert run["ai_teams"] == [team for team, _ in migrations._V4_LEGACY_RUN_TEAMS[:20]]
    assert run["playoffs"]["human_name"] == "Bighorns"
    assert run["playoffs"]["team_ids"][:2] == [None, migrations._V4_PLACEHOLDER_SPARE[0]]
    renamed = migrate_payload({"run": {**payload["run"], "builder": {"team_name": "wolves"},
                                       "playoffs": None}}, 3)["run"]
    assert "wolves" not in renamed["ai_teams"] and len(renamed["ai_teams"]) == 20
    with pytest.raises(UnsupportedSave, match="Unknown playoff team"):
        bad = copy.deepcopy(payload)
        bad["run"]["playoffs"]["teams"][3] = "Local AI"
        migrate_payload(bad, 3)
