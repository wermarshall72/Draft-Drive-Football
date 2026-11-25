"""AI team identities: the catalog, each run's draw, and how the run uses it."""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path

import pytest

from src.engine.football_ai import FootballAI, FootballAIDifficulty
from src.engine.football import FootballTeamSide
from src.engine.football_ai_teams import (
    AI_TEAM_CATALOG,
    AI_TEAMS_BY_ID,
    RUN_AI_TEAMS,
    SCHEDULED_AI_TEAMS,
    draw_run_ai_teams,
    eligible_ai_teams,
    playoff_pool,
    validate_run_ai_teams,
)
from src.engine.football_controller import (
    FootballGameController,
    FootballRunPhase,
    FootballSeasonOutcome,
)
from src.engine.football_playoffs import PLAYOFF_EXTRA_CARDS_PER_ROUND, FootballPlayoffRound
from src.engine.save_data import UnsupportedSave
from src.profile import COLOR_BY_ID, validate_team_name
from tests.football_run_driver import new_controller, step

DOC = Path(__file__).resolve().parents[1] / "docs" / "ai-team-names.md"


# -- catalog -------------------------------------------------------------------------


def test_catalog_has_100_distinct_valid_teams() -> None:
    assert len(AI_TEAM_CATALOG) == 100
    assert len(AI_TEAMS_BY_ID) == 100
    assert len({team.name.casefold() for team in AI_TEAM_CATALOG}) == 100
    assert len({team.abbreviation for team in AI_TEAM_CATALOG}) == 100
    pairs = {(team.primary_color_id, team.secondary_color_id) for team in AI_TEAM_CATALOG}
    assert len(pairs) == 100
    for team in AI_TEAM_CATALOG:
        assert team.team_id == team.name.lower().replace(" ", "-")
        assert validate_team_name(team.name) == team.name and len(team.name) <= 16
        assert re.fullmatch(r"[A-Z][a-z]+( [A-Z][a-z]+)?", team.name), team.name
        assert re.fullmatch(r"[A-Z]{2,4}", team.abbreviation), team.abbreviation
        assert team.primary_color_id in COLOR_BY_ID and team.secondary_color_id in COLOR_BY_ID
        assert team.primary_color_id != team.secondary_color_id
        assert team.name.casefold() != "owls"
    primaries = Counter(team.primary_color_id for team in AI_TEAM_CATALOG)
    assert set(primaries) == set(COLOR_BY_ID)
    assert max(primaries.values()) <= 6


def test_catalog_matches_the_reviewed_list() -> None:
    rows = re.findall(
        r"^\| \d+ \| ([^|]+?) \| ([A-Z]+) \| `([a-z-]+)` \| `([a-z-]+)` \|$",
        DOC.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    assert rows == [
        (team.name, team.abbreviation, team.primary_color_id, team.secondary_color_id)
        for team in AI_TEAM_CATALOG
    ]


# -- run draw ------------------------------------------------------------------------


def test_run_draw_is_deterministic_distinct_and_skips_clashes() -> None:
    for seed in range(50):
        drawn = draw_run_ai_teams(random.Random(seed), "Herons", "teal")
        assert drawn == draw_run_ai_teams(random.Random(seed), "Herons", "teal")
        teams = validate_run_ai_teams(drawn)
        assert len(set(drawn)) == RUN_AI_TEAMS
        assert all(team.name != "Herons" and team.primary_color_id != "teal" for team in teams)
    eligible = eligible_ai_teams("  herons ", "teal")
    teal = sum(team.primary_color_id == "teal" for team in AI_TEAM_CATALOG)
    # Herons is lavender, so the name rule removes it on top of the teal teams.
    assert len(eligible) == 100 - teal - 1
    assert "herons" not in {team.team_id for team in eligible}


def test_saved_draws_must_be_twenty_distinct_known_teams() -> None:
    drawn = list(draw_run_ai_teams(random.Random(3), "Owls"))
    with pytest.raises(UnsupportedSave, match="Unknown AI team"):
        validate_run_ai_teams([*drawn[:-1], "local-ai"])
    with pytest.raises(UnsupportedSave, match="20 distinct"):
        validate_run_ai_teams(drawn[:-1])
    with pytest.raises(UnsupportedSave, match="20 distinct"):
        validate_run_ai_teams([*drawn[:-1], drawn[0]])


def test_playoff_pool_is_played_rivals_plus_reserves() -> None:
    drawn = draw_run_ai_teams(random.Random(9), "Owls")
    pool = playoff_pool(drawn, [1, 2, 4, 3, 10])
    assert pool == (drawn[0], drawn[1], drawn[2], drawn[3], drawn[9], *drawn[10:])
    with pytest.raises(ValueError):
        playoff_pool(drawn, [11])


# -- the run -------------------------------------------------------------------------


def _controller(name: str = "Owls", color: str | None = None) -> FootballGameController:
    return FootballGameController(
        name, difficulty=FootballAIDifficulty.STANDARD,
        builder_seed=1, shop_seed=2, ai_seed=3, match_seed=4,
        team_primary_color_id=color,
    )


def test_the_draw_uses_its_own_stream_and_respects_the_human_team() -> None:
    first, second = _controller(), _controller()
    assert first.state.regular_season_teams == second.state.regular_season_teams
    assert first._ai.to_save_data() == second._ai.to_save_data()
    assert first._ai.to_save_data() == FootballAI(FootballTeamSide.TEAM_B,
                                                  FootballAIDifficulty.STANDARD, 3).to_save_data()
    rival = first.state.regular_season_teams[0]
    renamed = _controller(rival.name, rival.primary_color_id)
    teams = validate_run_ai_teams(renamed._ai_teams)
    assert all(team.name != rival.name for team in teams)
    assert all(team.primary_color_id != rival.primary_color_id for team in teams)


def test_every_regular_season_game_faces_its_scheduled_rival() -> None:
    controller = new_controller(5)
    schedule = controller.state.regular_season_teams
    assert len(schedule) == SCHEDULED_AI_TEAMS == len(set(schedule))
    rng = random.Random(5)
    faced: dict[int, str] = {}
    while step(controller, rng):
        state = controller.state
        if state.phase is FootballRunPhase.PRE_MATCH_SHOP and state.game_number <= 10:
            assert state.opponent_team is schedule[state.game_number - 1]
        if state.phase is FootballRunPhase.MATCH and state.game_number <= 10:
            assert state.opponent_team is schedule[state.game_number - 1]
            assert state.opponent_name == state.opponent_team.name
            faced[state.game_number] = state.match.team_b.team_name
            assert all(player.name.startswith(f"{state.opponent_name} ")
                       for player in state.match.team_b.players.values())
    assert faced and all(name == schedule[game - 1].name for game, name in faced.items())


def test_playoff_fields_mix_rematches_and_new_teams() -> None:
    rematches = fresh = brackets = 0
    for seed in range(60):
        controller = new_controller(seed, FootballAIDifficulty.EASY)
        rng = random.Random(seed)
        while controller.state.playoffs is None and step(controller, rng):
            pass
        state = controller.state
        if state.playoffs is None:
            continue
        brackets += 1
        played = {
            state.regular_season_teams[game.game_number - 1].team_id
            for game in state.season_history if game.outcome is not FootballSeasonOutcome.BYE
        }
        reserves = set(controller._ai_teams[SCHEDULED_AI_TEAMS:])
        ids = [team.ai_team.team_id for team in state.playoffs.teams if team.ai_team is not None]
        assert len(set(ids)) == 7 and set(ids) <= played | reserves
        rematches += sum(team_id in played for team_id in ids)
        fresh += sum(team_id in reserves for team_id in ids)
        if brackets >= 4:
            break
    assert brackets >= 4 and rematches and fresh


def test_a_playoff_rematch_never_reuses_a_regular_season_deck() -> None:
    """Playoff decks carry one more card per round than any regular-season deck."""
    for difficulty in FootballAIDifficulty:
        ai = FootballAI(FootballTeamSide.TEAM_B, difficulty, 11)
        roster = ai.generate_opponent_roster(team_name="Herons")
        regular = [ai.generate_opponent_decks(game, roster) for game in range(1, 11)]
        largest = max(len(offense) for offense, _defense in regular)
        for playoff_round in FootballPlayoffRound:
            offense, defense = ai.generate_opponent_decks(
                10 + playoff_round.value, roster,
                bonus_cards=PLAYOFF_EXTRA_CARDS_PER_ROUND * playoff_round.value,
            )
            assert len(offense) == len(defense) > largest
            for old_offense, old_defense in regular:
                assert [card.card_id for card in offense] != [c.card_id for c in old_offense]
                assert [card.card_id for card in defense] != [c.card_id for c in old_defense]


def test_the_draw_survives_a_save_round_trip() -> None:
    controller = new_controller(8)
    data = json.loads(json.dumps(controller.to_save_data()))
    assert data["ai_teams"] == list(controller._ai_teams) and "opponent_name" not in data
    restored = FootballGameController.from_save_data(data)
    assert restored.state.regular_season_teams == controller.state.regular_season_teams
    data["ai_teams"][4] = "local-ai"
    with pytest.raises(UnsupportedSave, match="Unknown AI team"):
        FootballGameController.from_save_data(data)
