"""Step-by-step upgrades of older run-save payloads.

Each entry in ``MIGRATIONS`` upgrades a payload from ``schema_version`` N to
N + 1 and works only on plain dicts (never on engine objects, which change
over time). To change the save format:

1. Bump ``CURRENT_SCHEMA_VERSION``.
2. Register ``MIGRATIONS[old] = _migrate_old_to_new`` that rewrites the old
   payload into the new shape (e.g. map a retired card ID to its replacement).
3. Add a fixture-based test next to ``test_migration_template`` in
   ``tests/test_run_save.py``.

A migration may raise ``UnsupportedSave`` when an old save cannot be carried
forward; the player is then offered to abandon it.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, MutableMapping
from typing import Any

from src.engine.save_data import UnsupportedSave

CURRENT_SCHEMA_VERSION = 4

Migration = Callable[[dict[str, Any]], dict[str, Any]]


def _opening_possession(match: dict[str, Any]) -> str:
    """The opening receiver: the first event's possession (the opening drive's offense)."""
    events = match.get("match_events")
    if isinstance(events, list) and events and isinstance(events[0], dict):
        possession = events[0].get("possession")
        if isinstance(possession, str):
            return possession
    possession = match.get("possession")
    return possession if isinstance(possession, str) else "team_a"


def _migrate_1_to_2(payload: dict[str, Any]) -> dict[str, Any]:
    """Player perks became active (version 2).

    Match states gain ``opening_possession`` (the team that received the opening
    kickoff and so kicks to start period 2). Events and play results gain
    ``perk_activations``, which is omitted while empty, so old histories need no
    change: they simply recorded no activations.
    """
    run = payload.get("run")
    simulator = run.get("simulator") if isinstance(run, dict) else None
    if not isinstance(simulator, dict):
        return payload
    state = simulator.get("state")
    if isinstance(state, dict):
        state.setdefault("opening_possession", _opening_possession(state))
        snapshot = simulator.get("challenge_snapshot")
        if isinstance(snapshot, dict):
            # A snapshot may store only its history length; its opening receiver
            # is the live match's.
            snapshot.setdefault("opening_possession", state["opening_possession"])
    return payload


def _migrate_2_to_3(payload: dict[str, Any]) -> dict[str, Any]:
    """Playoff games arrived (version 3).

    Runs gain ``playoffs`` (the bracket, null until the regular season ends).
    The old ended ``playoffs`` phase, reached by finishing or skipping game 10,
    becomes ``ready_for_next_game`` at game 10; loading seeds its bracket.
    """
    run = payload.get("run")
    if not isinstance(run, dict):
        return payload
    run.setdefault("playoffs", None)
    if run.get("phase") == "playoffs":
        run["phase"] = "ready_for_next_game"
    return payload


# Version 4 tables. They are frozen copies of catalog ids and names (never
# looked up in the live catalog) so this step keeps working as the game changes.
# Runs saved before AI teams existed get this fixed draw: 20 teams, skipping one
# named like the human team (the 21st is the spare).
_V4_LEGACY_RUN_TEAMS: tuple[tuple[str, str], ...] = (
    ("wildcats", "Wildcats"), ("hawks", "Hawks"), ("tigers", "Tigers"),
    ("falcons", "Falcons"), ("cougars", "Cougars"), ("sharks", "Sharks"),
    ("knights", "Knights"), ("panthers", "Panthers"), ("embers", "Embers"),
    ("griffins", "Griffins"), ("hornets", "Hornets"), ("foxes", "Foxes"),
    ("dragons", "Dragons"), ("stallions", "Stallions"), ("typhoons", "Typhoons"),
    ("wolves", "Wolves"), ("cardinals", "Cardinals"), ("otters", "Otters"),
    ("pioneers", "Pioneers"), ("vipers", "Vipers"), ("kestrels", "Kestrels"),
)
# Each old placeholder playoff name becomes a catalog team; the spare replaces
# one that is named like the human team.
_V4_PLACEHOLDER_TEAMS: dict[str, tuple[str, str]] = {
    "Ridgeline": ("bighorns", "Bighorns"),
    "Harbor City": ("navigators", "Navigators"),
    "Prairie State": ("bison", "Bison"),
    "Iron Valley": ("anvils", "Anvils"),
    "Lakeshore": ("herons", "Herons"),
    "Red Mesa": ("scorpions", "Scorpions"),
    "Pine Hollow": ("lumberjacks", "Lumberjacks"),
    "Summit Tech": ("yetis", "Yetis"),
    "Bayou A&M": ("crocodiles", "Crocodiles"),
    "Granite Falls": ("golems", "Golems"),
    "Coastal State": ("ospreys", "Ospreys"),
    "Northfield": ("blizzards", "Blizzards"),
}
_V4_PLACEHOLDER_SPARE = ("comets", "Comets")


def _rename_team_b(match: Any, new_name: str) -> None:
    """Give a saved match's AI roster (team, players, special teams) its new name."""
    roster = match.get("team_b") if isinstance(match, dict) else None
    if not isinstance(roster, dict):
        return
    old_name = roster.get("team_name")
    if not isinstance(old_name, str) or old_name == new_name:
        return
    roster["team_name"] = new_name

    def renamed(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(f"{old_name} "):
            return f"{new_name} {value[len(old_name) + 1:]}"
        return value

    roster["special_teams"] = renamed(roster.get("special_teams"))
    for player in roster.get("players") or ():
        if isinstance(player, dict):
            player["name"] = renamed(player.get("name"))


def _migrate_3_to_4(payload: dict[str, Any]) -> dict[str, Any]:
    """AI opponents gained catalog identities (version 4).

    Runs drop ``opponent_name`` and gain ``ai_teams`` (ten scheduled rivals,
    then ten playoff reserves); older runs get a fixed draw. A bracket's
    placeholder names become catalog ids (``team_ids``, None at the human seed)
    plus ``human_name``. A match in progress renames its AI roster to the
    current opponent.
    """
    run = payload.get("run")
    if not isinstance(run, dict) or "ai_teams" in run:
        # Already in the version 4 shape (only possible for a hand-built payload).
        return payload
    builder = run.get("builder")
    human = builder.get("team_name") if isinstance(builder, dict) else None
    if not isinstance(human, str) or not human.strip():
        raise UnsupportedSave("The saved run has no team name.")
    folded = human.strip().casefold()
    run.pop("opponent_name", None)
    schedule = [team for team in _V4_LEGACY_RUN_TEAMS if team[1].casefold() != folded][:20]
    run["ai_teams"] = [team_id for team_id, _name in schedule]
    current_name = None
    game_number = run.get("game_number")
    if isinstance(game_number, int) and 1 <= game_number <= 10:
        current_name = schedule[game_number - 1][1]

    bracket = run.get("playoffs")
    if isinstance(bracket, dict):
        names = bracket.pop("teams", None)
        human_seed = bracket.get("human_seed")
        if not isinstance(names, list) or not isinstance(human_seed, int) or not (
            1 <= human_seed <= len(names)
        ):
            raise UnsupportedSave("The saved playoff bracket is malformed.")
        bracket["human_name"] = names[human_seed - 1]
        teams: list[tuple[str, str] | None] = []
        for seed, name in enumerate(names, start=1):
            if seed == human_seed:
                teams.append(None)
                continue
            if name not in _V4_PLACEHOLDER_TEAMS:
                raise UnsupportedSave(f"Unknown playoff team: {name!r}.")
            team = _V4_PLACEHOLDER_TEAMS[name]
            teams.append(_V4_PLACEHOLDER_SPARE if team[1].casefold() == folded else team)
        bracket["team_ids"] = [team[0] if team is not None else None for team in teams]
        if isinstance(game_number, int) and game_number > 10:
            for game in bracket.get("games") or ():
                if (
                    isinstance(game, dict) and game.get("round") == game_number - 10
                    and human_seed in (game.get("high_seed"), game.get("low_seed"))
                ):
                    other = game["low_seed"] if game["high_seed"] == human_seed else game["high_seed"]
                    if isinstance(other, int) and 1 <= other <= len(teams) and teams[other - 1]:
                        current_name = teams[other - 1][1]

    simulator = run.get("simulator")
    if isinstance(simulator, dict) and current_name is not None:
        _rename_team_b(simulator.get("state"), current_name)
        _rename_team_b(simulator.get("challenge_snapshot"), current_name)
    return payload


# schema_version N -> function returning the payload at N + 1.
MIGRATIONS: MutableMapping[int, Migration] = {
    1: _migrate_1_to_2, 2: _migrate_2_to_3, 3: _migrate_3_to_4,
}


class NewerSaveVersion(UnsupportedSave):
    """The save was written by a newer build (for example via Steam Cloud)."""


def migrate_payload(
    payload: dict[str, Any],
    from_version: int,
    *,
    to_version: int = CURRENT_SCHEMA_VERSION,
    migrations: MutableMapping[int, Migration] | None = None,
) -> dict[str, Any]:
    """Upgrade ``payload`` to ``to_version``; the input is never modified."""
    registry = MIGRATIONS if migrations is None else migrations
    if isinstance(from_version, bool) or not isinstance(from_version, int):
        raise UnsupportedSave("The save has no valid schema version.")
    if from_version > to_version:
        raise NewerSaveVersion(
            f"Saved by a newer version of the game (save format {from_version}, "
            f"this build reads up to {to_version})."
        )
    upgraded = copy.deepcopy(payload) if from_version < to_version else payload
    for version in range(from_version, to_version):
        step = registry.get(version)
        if step is None:
            raise UnsupportedSave(
                f"Save format {from_version} is too old to upgrade (no step from {version})."
            )
        upgraded = step(upgraded)
        if not isinstance(upgraded, dict):
            raise UnsupportedSave(f"Upgrading save format {version} failed.")
    return upgraded
