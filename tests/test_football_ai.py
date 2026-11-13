import random

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCoach,
    FootballFourthDownAction,
    FootballMatchState,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_ai import (
    FootballAI,
    FootballAIDifficulty,
    HARD_POWER_ADJUSTMENT,
)
from src.engine.football_simulator import FootballMatchSimulator


def _roster(
    team_name: str,
    *,
    default_power: float = 10.0,
    powers: dict[FootballPosition, float] | None = None,
) -> FootballRoster:
    power_by_position = powers or {}
    players = {
        position: FootballPlayer(
            name=f"{team_name} {position.value}",
            position=position,
            power=power_by_position.get(position, default_power),
            volatility=0.2,
            stamina=0.75,
        )
        for position in FootballPosition
    }
    return FootballRoster(
        team_name=team_name,
        players=players,
        coach=FootballCoach(f"{team_name} Coach"),
        special_teams=FootballSpecialTeams(f"{team_name} Special Teams"),
    )


def _state(**overrides: object) -> FootballMatchState:
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
    if values.get("awaited_action") in (
        FootballAwaitedAction.OFFENSIVE_PLAY,
        FootballAwaitedAction.FOURTH_DOWN_DECISION,
    ):
        values.setdefault(
            "current_drive_defensive_scheme", DefensiveSchemeAction.DEEP_PASS
        )
    return FootballMatchState(**values)  # type: ignore[arg-type]


def _ai(
    difficulty: FootballAIDifficulty,
    *,
    side: FootballTeamSide = FootballTeamSide.TEAM_A,
    seed: int = 17,
) -> FootballAI:
    return FootballAI(side, difficulty, seed, "Local Opponent")


@pytest.mark.parametrize(
    "difficulty",
    list(FootballAIDifficulty),
)
def test_generated_roster_is_complete_valid_and_keeps_non_player_slots_separate(
    difficulty: FootballAIDifficulty,
) -> None:
    roster = _ai(difficulty).generate_opponent_roster()

    assert set(roster.players) == set(FootballPosition)
    assert len(roster.players) == 8
    for position, player in roster.players.items():
        assert player.position is position
        assert 0.0 <= player.power <= 12.5
        assert 0.0 <= player.volatility <= 1.0
        assert 0.0 <= player.stamina <= 1.0
    assert isinstance(roster.coach, FootballCoach)
    assert isinstance(roster.special_teams, FootballSpecialTeams)
    assert roster.coach not in roster.players.values()
    assert roster.special_teams not in roster.players.values()


def test_roster_generation_is_reproducible_and_seeded_differently() -> None:
    first = _ai(FootballAIDifficulty.STANDARD, seed=121).generate_opponent_roster()
    replay = _ai(FootballAIDifficulty.STANDARD, seed=121).generate_opponent_roster()
    other_seed = _ai(FootballAIDifficulty.STANDARD, seed=122).generate_opponent_roster()

    assert first == replay
    assert first != other_seed


def test_difficulty_applies_only_the_documented_small_power_adjustment() -> None:
    rosters = {
        difficulty: _ai(difficulty, seed=7).generate_opponent_roster()
        for difficulty in FootballAIDifficulty
    }
    position = FootballPosition.QB

    assert (
        rosters[FootballAIDifficulty.HARD].players[position].power
        - rosters[FootballAIDifficulty.STANDARD].players[position].power
        == pytest.approx(HARD_POWER_ADJUSTMENT)
    )


@pytest.mark.parametrize(
    ("difficulty", "awaited_action", "possession", "down", "expected_types"),
    [
        (
            difficulty,
            FootballAwaitedAction.DEFENSIVE_SCHEME,
            FootballTeamSide.TEAM_B,
            1,
            DefensiveSchemeAction,
        )
        for difficulty in FootballAIDifficulty
    ]
    + [
        (
            difficulty,
            FootballAwaitedAction.OFFENSIVE_PLAY,
            FootballTeamSide.TEAM_A,
            2,
            OffensivePlayAction,
        )
        for difficulty in FootballAIDifficulty
    ]
    + [
        (
            difficulty,
            FootballAwaitedAction.FOURTH_DOWN_DECISION,
            FootballTeamSide.TEAM_A,
            4,
            FootballFourthDownAction,
        )
        for difficulty in FootballAIDifficulty
    ],
)
def test_each_difficulty_selects_only_supported_action_for_awaited_state(
    difficulty: FootballAIDifficulty,
    awaited_action: FootballAwaitedAction,
    possession: FootballTeamSide,
    down: int,
    expected_types: type,
) -> None:
    state = _state(
        awaited_action=awaited_action,
        possession=possession,
        down=down,
    )

    action = _ai(difficulty).choose_action(state)

    assert isinstance(action, expected_types)
    if isinstance(action, OffensivePlayAction):
        assert action in tuple(OffensivePlayAction)
    elif isinstance(action, DefensiveSchemeAction):
        assert action in tuple(DefensiveSchemeAction)
    else:
        assert action in tuple(FootballFourthDownAction)


@pytest.mark.parametrize(
    ("awaited_action", "possession", "down"),
    [
        (FootballAwaitedAction.DEFENSIVE_SCHEME, FootballTeamSide.TEAM_A, 1),
        (FootballAwaitedAction.OFFENSIVE_PLAY, FootballTeamSide.TEAM_B, 2),
        (FootballAwaitedAction.FOURTH_DOWN_DECISION, FootballTeamSide.TEAM_B, 4),
    ],
)
def test_ai_rejects_actions_when_it_does_not_own_the_turn(
    awaited_action: FootballAwaitedAction,
    possession: FootballTeamSide,
    down: int,
) -> None:
    state = _state(
        awaited_action=awaited_action,
        possession=possession,
        down=down,
    )

    with pytest.raises(ValueError, match="AI cannot"):
        _ai(FootballAIDifficulty.STANDARD).choose_action(state)


def test_ai_rejects_missing_awaited_action() -> None:
    state = _state(
        awaited_action=None,
        possession=FootballTeamSide.TEAM_A,
        down=1,
    )

    with pytest.raises(ValueError):
        _ai(FootballAIDifficulty.STANDARD).choose_action(state)


def test_ai_choices_do_not_mutate_match_state_events_or_simulator_rng() -> None:
    state = _state(
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        possession=FootballTeamSide.TEAM_A,
        match_events=(),
    )
    simulator = FootballMatchSimulator(state)
    before_rng = simulator.rng.getstate()
    before_events = state.match_events

    action = _ai(FootballAIDifficulty.EASY).choose_action(state)

    assert isinstance(action, OffensivePlayAction)
    assert simulator.state is state
    assert simulator.state.match_events is before_events
    assert simulator.rng.getstate() == before_rng


def test_easy_decision_stream_replays_from_the_same_ai_seed() -> None:
    state = _state(
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        possession=FootballTeamSide.TEAM_A,
    )
    first = _ai(FootballAIDifficulty.EASY, seed=918)
    replay = _ai(FootballAIDifficulty.EASY, seed=918)

    assert [first.choose_action(state) for _ in range(12)] == [
        replay.choose_action(state) for _ in range(12)
    ]
    assert first._rng.getstate() == replay._rng.getstate()


def test_standard_fourth_down_policy_distinguishes_long_and_short_yardage() -> None:
    ai = _ai(FootballAIDifficulty.STANDARD)
    long_distance = _state(
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        down=4,
        yards_to_go=9.0,
        offense_field_position=25.0,
    )
    short_yardage = _state(
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        down=4,
        yards_to_go=1.0,
        offense_field_position=25.0,
    )

    assert ai.choose_action(long_distance) is FootballFourthDownAction.PUNT
    assert ai.choose_action(short_yardage) is FootballFourthDownAction.GO_FOR_IT


def test_easy_fourth_down_choices_exclude_out_of_range_field_goals() -> None:
    ai = _ai(FootballAIDifficulty.EASY)
    state = _state(
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        down=4,
        yards_to_go=4.0,
        offense_field_position=25.0,
    )

    assert {
        ai.choose_action(state) for _ in range(20)
    } <= {FootballFourthDownAction.GO_FOR_IT, FootballFourthDownAction.PUNT}


def test_ai_rejects_an_expired_period_clock() -> None:
    state = _state(
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        possession=FootballTeamSide.TEAM_A,
        game_clock_seconds=0,
    )

    with pytest.raises(ValueError, match="clock"):
        _ai(FootballAIDifficulty.STANDARD).choose_action(state)


def test_hard_offense_uses_the_simulator_matchup_strengths() -> None:
    strong_matchup = {
        FootballPosition.QB: 10.0,
        FootballPosition.RB: 10.0,
        FootballPosition.WR: 20.0,
        FootballPosition.O_LINE: 10.0,
        FootballPosition.D_LINE: 10.0,
        FootballPosition.LINEBACKERS: 10.0,
        FootballPosition.CORNERBACKS: 10.0,
        FootballPosition.SAFETIES: 10.0,
    }
    state = _state(
        team_a=_roster("Home", powers=strong_matchup),
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        possession=FootballTeamSide.TEAM_A,
        down=3,
        yards_to_go=8.0,
    )

    assert _ai(FootballAIDifficulty.HARD).choose_action(state) is OffensivePlayAction.DEEP_PASS


def test_ai_rejects_invalid_constructor_values() -> None:
    with pytest.raises(ValueError, match="team side"):
        FootballAI("team_a", FootballAIDifficulty.STANDARD, 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="difficulty"):
        FootballAI(FootballTeamSide.TEAM_A, "hard", 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="seed"):
        FootballAI(FootballTeamSide.TEAM_A, FootballAIDifficulty.STANDARD, True)


def test_easy_ai_random_stream_is_independent_from_match_simulator_stream() -> None:
    state = _state(
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        possession=FootballTeamSide.TEAM_B,
    )
    simulator = FootballMatchSimulator(state)
    ai = _ai(FootballAIDifficulty.EASY, seed=44)
    match_rng = random.Random(state.random_seed)

    ai.choose_action(state)

    assert simulator.rng.getstate() == match_rng.getstate()
