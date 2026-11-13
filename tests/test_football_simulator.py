import random

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCoach,
    FootballMatchState,
    FootballMatchStatus,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football import FootballFourthDownAction
from src.engine.football_simulator import (
    FootballMatchSimulator,
    field_goal_distance_for_position,
    field_goal_success_probability,
    matchup_for_play,
    resolve_offensive_play,
    select_defensive_scheme,
)


class DeterministicRNG(random.Random):
    def __init__(self, *values: float):
        super().__init__(0)
        self._values = list(values)
        self._index = 0

    def random(self) -> float:
        if self._index >= len(self._values):
            return 0.0
        value = self._values[self._index]
        self._index += 1
        return value

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self.random()


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


def _match_state(**overrides):
    values = {
        "team_a": _roster("Home"),
        "team_b": _roster("Away"),
        "random_seed": 17,
        "team_a_score": 0,
        "team_b_score": 0,
        "possession": FootballTeamSide.TEAM_A,
        "down": 1,
        "yards_to_go": 10.0,
        "offense_field_position": 25.0,
        "game_clock_seconds": 900,
        "period": 1,
        "awaited_action": FootballAwaitedAction.DEFENSIVE_SCHEME,
    }
    values.update(overrides)
    return FootballMatchState(**values)


def test_matchup_players_use_the_exact_required_positions():
    expected = {
        OffensivePlayAction.RB_RUN: (
            (FootballPosition.O_LINE, FootballPosition.RB),
            (FootballPosition.D_LINE, FootballPosition.LINEBACKERS),
        ),
        OffensivePlayAction.SCREEN_PASS: (
            (FootballPosition.O_LINE, FootballPosition.WR),
            (FootballPosition.D_LINE, FootballPosition.CORNERBACKS),
        ),
        OffensivePlayAction.PA_PASS: (
            (FootballPosition.QB, FootballPosition.RB),
            (FootballPosition.SAFETIES, FootballPosition.LINEBACKERS),
        ),
        OffensivePlayAction.SHORT_PASS: (
            (FootballPosition.RB, FootballPosition.WR),
            (FootballPosition.LINEBACKERS, FootballPosition.CORNERBACKS),
        ),
        OffensivePlayAction.MEDIUM_PASS: (
            (FootballPosition.QB, FootballPosition.O_LINE),
            (FootballPosition.SAFETIES, FootballPosition.D_LINE),
        ),
        OffensivePlayAction.DEEP_PASS: (
            (FootballPosition.QB, FootballPosition.WR),
            (FootballPosition.SAFETIES, FootballPosition.CORNERBACKS),
        ),
    }
    for play, pairing in expected.items():
        assert matchup_for_play(play) == pairing


def test_scheme_selection_persists_for_the_drive():
    state = _match_state()
    state = select_defensive_scheme(state, DefensiveSchemeAction.RB_RUN)
    sim = FootballMatchSimulator(state)
    sim.rng = DeterministicRNG(0.10, 0.90)
    updated = sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)

    assert updated.current_drive_defensive_scheme is DefensiveSchemeAction.RB_RUN
    assert updated.awaited_action in {
        FootballAwaitedAction.OFFENSIVE_PLAY,
        FootballAwaitedAction.FOURTH_DOWN_DECISION,
    }


def test_incomplete_pass_and_first_down_reset():
    state = _match_state(
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        current_drive_defensive_scheme=None,
        offense_field_position=25.0,
    )
    state = select_defensive_scheme(state, DefensiveSchemeAction.PA_PASS)
    sim = FootballMatchSimulator(state)
    sim.rng = DeterministicRNG(0.05, 0.0, 0.0)
    updated = sim.resolve_offensive_play(OffensivePlayAction.PA_PASS)

    assert updated.offense_field_position < 25.0
    assert updated.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY
    assert updated.down == 2
    assert updated.yards_to_go > 0


def test_negative_yard_play_increases_yards_to_go():
    state = _match_state(
        down=1,
        yards_to_go=2.0,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        current_drive_defensive_scheme=DefensiveSchemeAction.PA_PASS,
    )
    sim = FootballMatchSimulator(state)
    sim.rng = DeterministicRNG(0.5, 0.0)

    updated = sim.resolve_offensive_play(OffensivePlayAction.PA_PASS)

    assert updated.down == 2
    assert updated.yards_to_go == 4.0
    assert updated.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY


def test_fourth_down_field_goal_distance_and_success():
    state = _match_state(
        down=4,
        yards_to_go=5.0,
        offense_field_position=45.0,
        game_clock_seconds=110,
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
    )
    distance = field_goal_distance_for_position(state.offense_field_position)
    assert distance == 65.0
    assert field_goal_success_probability(distance) > 0.18

    sim = FootballMatchSimulator(state)
    sim.rng = DeterministicRNG(0.0)
    updated = sim.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)

    assert updated.team_a_score == 3
    assert updated.possession is FootballTeamSide.TEAM_B
    assert updated.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME


def test_failed_fourth_down_go_for_it_changes_possession():
    state = _match_state(
        down=4,
        yards_to_go=4.0,
        offense_field_position=30.0,
        game_clock_seconds=90,
        awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
    )
    sim = FootballMatchSimulator(state)
    sim.rng = DeterministicRNG(0.99, 0.9)
    updated = sim.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)

    assert updated.possession is FootballTeamSide.TEAM_B
    assert updated.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    assert updated.offense_field_position == 71.0


def test_touchdown_and_safety_are_scored_correctly():
    touchdown = _match_state(
        offense_field_position=95.0,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
    )
    sim = FootballMatchSimulator(touchdown)
    sim.rng = DeterministicRNG(0.90, 0.90)
    scored = sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert scored.team_a_score == 7
    assert scored.possession is FootballTeamSide.TEAM_B

    safety = _match_state(
        offense_field_position=2.0,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        current_drive_defensive_scheme=DefensiveSchemeAction.PA_PASS,
        possession=FootballTeamSide.TEAM_A,
    )
    sim = FootballMatchSimulator(safety)
    sim.rng = DeterministicRNG(0.0)
    safe_result = sim.resolve_offensive_play(OffensivePlayAction.PA_PASS)
    assert safe_result.team_b_score == 2
    assert safe_result.possession is FootballTeamSide.TEAM_B
    assert safe_result.offense_field_position == 25.0


def test_regulation_clock_rolls_to_overtime_and_final_result_stays_consistent():
    state = _match_state(
        game_clock_seconds=5,
        period=2,
        team_a_score=0,
        team_b_score=0,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
    )
    sim = FootballMatchSimulator(state)
    sim.rng = DeterministicRNG(0.90, 0.90)
    updated = sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)

    assert updated.period == 3
    assert updated.game_clock_seconds == 300
    assert updated.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    assert updated.status is FootballMatchStatus.IN_PROGRESS
