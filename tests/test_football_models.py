import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCoach,
    FootballMatchResult,
    FootballMatchState,
    FootballMatchStatus,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    FootballPlayResult,
    OffensivePlayAction,
)


def _roster(team_name: str = "Home") -> FootballRoster:
    players = {
        position: FootballPlayer(
            name=f"{team_name} {position.value}",
            position=position,
            power=10.0,
            volatility=0.2,
            stamina=0.75,
        )
        for position in FootballPosition
    }
    return FootballRoster(
        team_name=team_name,
        players=players,
        coach=FootballCoach(f"{team_name} Coach"),
        special_teams=FootballSpecialTeams(),
    )


def _match_state(**overrides: object) -> FootballMatchState:
    values: dict[str, object] = {
        "team_a": _roster("Home"),
        "team_b": _roster("Away"),
        "random_seed": 1234,
        "team_a_score": 0,
        "team_b_score": 0,
        "possession": FootballTeamSide.TEAM_A,
        "down": 1,
        "yards_to_go": 10.0,
        "offense_field_position": 25.0,
        "game_clock_seconds": 900,
        "period": 1,
    }
    values.update(overrides)
    return FootballMatchState(**values)  # type: ignore[arg-type]


def test_roster_requires_each_of_the_eight_player_positions_once() -> None:
    roster = _roster()
    expected = {
        "QB",
        "RB",
        "WR",
        "O_LINE",
        "D_LINE",
        "LINEBACKERS",
        "CORNERBACKS",
        "SAFETIES",
    }

    assert set(roster.players) == set(FootballPosition)
    assert {position.value for position in roster.players} == expected
    assert len(roster.players) == 8
    assert all(
        roster.players[position].position is position for position in FootballPosition
    )
    with pytest.raises(TypeError):
        roster.players[FootballPosition.QB] = roster.players[FootballPosition.RB]


def test_roster_rejects_missing_or_non_position_slots() -> None:
    roster = _roster()
    missing_player = dict(roster.players)
    del missing_player[FootballPosition.SAFETIES]
    with pytest.raises(ValueError, match="exactly one player"):
        FootballRoster("Incomplete", missing_player, roster.coach, roster.special_teams)

    invalid_slot = dict(roster.players)
    invalid_slot["KICKER"] = FootballPlayer(  # type: ignore[index]
        "Kicker", FootballPosition.SAFETIES, 10.0, 0.2, 0.75
    )
    with pytest.raises(ValueError, match="FootballPosition identifiers"):
        FootballRoster("Invalid", invalid_slot, roster.coach, roster.special_teams)


def test_roster_rejects_player_in_mismatched_position_slot() -> None:
    roster = _roster()
    players = dict(roster.players)
    players[FootballPosition.QB] = players[FootballPosition.RB]

    with pytest.raises(ValueError, match="QB slot cannot contain a RB player"):
        FootballRoster("Mismatched", players, roster.coach, roster.special_teams)


def test_coach_and_special_teams_are_separate_from_eight_players() -> None:
    roster = _roster()

    assert isinstance(roster.coach, FootballCoach)
    assert isinstance(roster.special_teams, FootballSpecialTeams)
    assert len(roster.players) == 8
    assert roster.coach not in roster.players.values()
    assert roster.special_teams not in roster.players.values()


@pytest.mark.parametrize("down", [0, 5, True])
def test_match_state_rejects_invalid_down(down: object) -> None:
    with pytest.raises(ValueError, match="Down must"):
        _match_state(down=down)


@pytest.mark.parametrize("distance", [0, -1, float("inf"), float("nan")])
def test_match_state_rejects_invalid_distance(distance: float) -> None:
    with pytest.raises(ValueError, match="Yards to go"):
        _match_state(yards_to_go=distance)


@pytest.mark.parametrize("clock", [-1, 1.5, True])
def test_match_state_rejects_invalid_clock(clock: object) -> None:
    with pytest.raises(ValueError, match="Game clock seconds"):
        _match_state(game_clock_seconds=clock)


@pytest.mark.parametrize("position", [-0.1, 100.1, float("nan")])
def test_match_state_rejects_invalid_field_position(position: float) -> None:
    with pytest.raises(ValueError, match="field position"):
        _match_state(offense_field_position=position)


def test_match_state_describes_field_position_and_keeps_match_seed() -> None:
    state = _match_state(
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        current_drive_defensive_scheme=DefensiveSchemeAction.ZONE_COVERAGE,
    )

    assert state.random_seed == 1234
    assert state.offense_field_position == 25.0
    assert state.current_drive_defensive_scheme is DefensiveSchemeAction.ZONE_COVERAGE


def test_action_and_result_models_accept_future_resolver_data() -> None:
    play_result = FootballPlayResult(
        offensive_play=OffensivePlayAction.SHORT_PASS,
        yards_gained=-2.0,
        clock_seconds_used=8,
        points_scored=0,
        turnover=True,
        possession_changed=True,
        defensive_scheme=DefensiveSchemeAction.BLITZ,
    )
    final_result = FootballMatchResult(
        team_a_score=7,
        team_b_score=3,
        winner=FootballTeamSide.TEAM_A,
        completed=True,
    )
    completed_state = _match_state(
        team_a_score=7,
        team_b_score=3,
        status=FootballMatchStatus.COMPLETED,
        final_result=final_result,
    )

    assert play_result.offensive_play is OffensivePlayAction.SHORT_PASS
    assert play_result.yards_gained == -2.0
    assert play_result.clock_seconds_used == 8
    assert play_result.turnover and play_result.possession_changed
    assert play_result.defensive_scheme is DefensiveSchemeAction.BLITZ
    assert completed_state.final_result is final_result


def test_match_completion_requires_a_completed_final_result() -> None:
    with pytest.raises(ValueError, match="completed final result"):
        _match_state(status=FootballMatchStatus.COMPLETED)

    incomplete_result = FootballMatchResult(0, 0, None, completed=False)
    with pytest.raises(ValueError, match="completed final result"):
        _match_state(
            status=FootballMatchStatus.COMPLETED,
            final_result=incomplete_result,
        )
    with pytest.raises(ValueError, match="cannot have a final result"):
        _match_state(final_result=FootballMatchResult(0, 0, None, completed=True))
    with pytest.raises(ValueError, match="scores must match"):
        _match_state(
            team_a_score=1,
            status=FootballMatchStatus.COMPLETED,
            final_result=FootballMatchResult(0, 0, None, completed=True),
        )
