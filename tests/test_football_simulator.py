from dataclasses import replace
import random

import pytest

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCoach,
    FootballFourthDownAction,
    FootballMatchState,
    FootballMatchStatus,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_simulator import (
    FATIGUE_RAMP_PLAYS,
    MAX_FATIGUE_POWER_REDUCTION,
    FootballMatchSimulator,
    field_goal_distance_for_position,
    field_goal_success_probability,
    matchup_for_play,
)


class SequenceRNG(random.Random):
    def __init__(
        self,
        random_values: tuple[float, ...] = (),
        uniform_values: tuple[float, ...] = (),
        choice_value: FootballTeamSide = FootballTeamSide.TEAM_A,
    ):
        super().__init__(0)
        self.random_values = random_values
        self.uniform_values = uniform_values
        self.choice_value = choice_value
        self.random_calls = 0
        self.uniform_calls = 0
        self.choice_calls = 0

    def random(self) -> float:
        value = self.random_values[self.random_calls] if self.random_calls < len(self.random_values) else 0.99
        self.random_calls += 1
        return value

    def uniform(self, low: float, high: float) -> float:
        value = self.uniform_values[self.uniform_calls] if self.uniform_calls < len(self.uniform_values) else (low + high) / 2
        self.uniform_calls += 1
        return value

    def choice(self, values):
        self.choice_calls += 1
        return self.choice_value


def _roster(
    team_name: str,
    *,
    power: float = 10.0,
    stamina: float = 0.75,
) -> FootballRoster:
    players = {
        position: FootballPlayer(
            name=f"{team_name} {position.value}",
            position=position,
            power=power,
            volatility=0.2,
            stamina=stamina,
        )
        for position in FootballPosition
    }
    return FootballRoster(
        team_name=team_name,
        players=players,
        coach=FootballCoach(f"{team_name} Coach"),
        special_teams=FootballSpecialTeams(),
    )


def _match_state(**overrides) -> FootballMatchState:
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
    if "game_clock_seconds" not in overrides and values["period"] >= 3:
        values["game_clock_seconds"] = 300
    if values["awaited_action"] in (
        FootballAwaitedAction.OFFENSIVE_PLAY,
        FootballAwaitedAction.FOURTH_DOWN_DECISION,
    ):
        values.setdefault(
            "current_drive_defensive_scheme", DefensiveSchemeAction.DEEP_PASS
        )
    return FootballMatchState(**values)


def _sim_with_scheme(
    *,
    scheme: DefensiveSchemeAction = DefensiveSchemeAction.SHORT_PASS,
    rng: SequenceRNG | None = None,
    **state_overrides,
) -> FootballMatchSimulator:
    sim = FootballMatchSimulator(_match_state(**state_overrides))
    if rng is not None:
        sim.rng = rng
    sim.select_defensive_scheme(scheme)
    return sim


def test_all_six_play_matchups_use_the_required_positions():
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


@pytest.mark.parametrize("play", list(OffensivePlayAction))
def test_matching_scheme_changes_power_but_mismatching_scheme_does_not(play):
    matching = _sim_with_scheme(
        scheme=DefensiveSchemeAction(play.value),
        rng=SequenceRNG((0.99,), (0.0,)),
    )
    mismatching_scheme = next(
        scheme for scheme in DefensiveSchemeAction if scheme.value != play.value
    )
    mismatching = _sim_with_scheme(
        scheme=mismatching_scheme,
        rng=SequenceRNG((0.99,), (0.0,)),
    )

    matched_result = matching.resolve_offensive_play(play).match_events[-1].play_result
    mismatched_result = mismatching.resolve_offensive_play(play).match_events[-1].play_result
    assert matched_result is not None and mismatched_result is not None
    assert matched_result.offense_power == pytest.approx(19.2)
    assert matched_result.defense_power == pytest.approx(22.4)
    assert mismatched_result.offense_power == 20.0
    assert mismatched_result.defense_power == 20.0


def test_normal_run_and_completed_pass_advance_clock_and_down():
    run = _sim_with_scheme(rng=SequenceRNG((0.99,), (0.0,)))
    run_state = run.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert run_state.offense_field_position == 29.0
    assert run_state.down == 2
    assert run_state.yards_to_go == 6.0
    assert run_state.game_clock_seconds == 882

    pass_sim = _sim_with_scheme(rng=SequenceRNG((0.99,), (0.0,)))
    pass_state = pass_sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert pass_state.offense_field_position == 33.0
    assert pass_state.down == 2
    assert pass_state.game_clock_seconds == 882


def test_incomplete_pass_is_lossless_and_uses_less_clock_than_a_completion():
    incomplete_sim = _sim_with_scheme(rng=SequenceRNG((0.0,), (0.0,)))
    before_position = incomplete_sim.state.offense_field_position
    incomplete = incomplete_sim.resolve_offensive_play(OffensivePlayAction.SHORT_PASS)
    incomplete_result = incomplete.match_events[-1].play_result
    assert incomplete_result is not None
    assert incomplete_result.incomplete
    assert incomplete_result.yards_gained == 0
    assert incomplete.offense_field_position == before_position
    assert incomplete.game_clock_seconds == 895
    assert incomplete.down == 2

    complete_sim = _sim_with_scheme(rng=SequenceRNG((0.99,), (0.0,)))
    completed = complete_sim.resolve_offensive_play(OffensivePlayAction.SHORT_PASS)
    assert completed.game_clock_seconds == 882


def test_first_down_and_goal_to_go_use_the_shorter_distance():
    first_down_sim = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (0.0,)),
        yards_to_go=3.0,
    )
    first_down = first_down_sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert first_down.down == 1
    assert first_down.offense_field_position == 33.0
    assert first_down.yards_to_go == 10.0

    goal_sim = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (-1.0,)),
        offense_field_position=97.0,
        yards_to_go=10.0,
    )
    goal_state = goal_sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert goal_state.team_a_score == 7
    assert goal_state.match_events[-1].points_scored == 7


def test_negative_yardage_increases_distance_and_turnover_flips_field_position():
    negative_sim = _sim_with_scheme(rng=SequenceRNG((0.99,), (-5.0,)))
    negative = negative_sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert negative.offense_field_position == 24.0
    assert negative.yards_to_go == 11.0
    assert negative.down == 2

    turnover_sim = _sim_with_scheme(
        scheme=DefensiveSchemeAction.RB_RUN,
        rng=SequenceRNG((0.25,), (0.0,)),
    )
    turnover = turnover_sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert turnover.match_events[-1].play_result.turnover
    assert turnover.possession is FootballTeamSide.TEAM_B
    assert turnover.offense_field_position == 78.0
    assert turnover.down == 1
    assert turnover.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    assert turnover.current_drive_defensive_scheme is None


def test_negative_yardage_from_goal_to_go_uses_actual_line_to_gain():
    sim = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (-8.0,)),
        offense_field_position=95.0,
        yards_to_go=10.0,
    )
    result = sim.resolve_offensive_play(OffensivePlayAction.PA_PASS)
    assert result.offense_field_position == 92.0
    assert result.yards_to_go == 8.0


def test_incomplete_play_at_goal_line_does_not_score_without_positive_gain():
    incomplete = _sim_with_scheme(
        scheme=DefensiveSchemeAction.SHORT_PASS,
        rng=SequenceRNG((0.0,), (0.0,)),
        offense_field_position=100.0,
    )
    incomplete_state = incomplete.resolve_offensive_play(OffensivePlayAction.SHORT_PASS)
    assert incomplete_state.team_a_score == 0
    assert incomplete_state.match_events[-1].play_result.incomplete

    completed = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (0.0,)),
        offense_field_position=100.0,
    )
    completed_state = completed.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert completed_state.team_a_score == 7


def test_safety_scores_two_and_gives_opponent_own_twenty_five():
    sim = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (-10.0,)),
        offense_field_position=2.0,
    )
    result = sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert result.team_b_score == 2
    assert result.possession is FootballTeamSide.TEAM_B
    assert result.offense_field_position == 25.0
    assert result.down == 1
    assert result.current_drive_defensive_scheme is None
    assert result.match_events[-1].scoring_team is FootballTeamSide.TEAM_B


def test_fourth_down_go_for_it_success_and_failure():
    success = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=2.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        )
    )
    success.rng = SequenceRNG((0.0,), (2.0,))
    continued = success.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    assert continued.possession is FootballTeamSide.TEAM_A
    assert continued.down == 1
    assert continued.offense_field_position == 29.0
    assert continued.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY

    failure = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=10.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
        )
    )
    failure.rng = SequenceRNG((0.99,))
    flipped = failure.resolve_fourth_down(FootballFourthDownAction.GO_FOR_IT)
    assert flipped.possession is FootballTeamSide.TEAM_B
    assert flipped.offense_field_position == 75.0
    assert flipped.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME
    assert flipped.current_drive_defensive_scheme is None


def test_punt_uses_forty_yard_net_and_touchback_at_end_zone():
    normal = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=4.0,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    punted = normal.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert punted.possession is FootballTeamSide.TEAM_B
    assert punted.offense_field_position == 35.0
    assert punted.down == 1
    assert punted.current_drive_defensive_scheme is None

    touchback = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=4.0,
            offense_field_position=60.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    touchback_state = touchback.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert touchback_state.possession is FootballTeamSide.TEAM_B
    assert touchback_state.offense_field_position == 25.0


def test_field_goal_distance_is_goal_distance_plus_ten_and_made_or_missed():
    position = 45.0
    distance = field_goal_distance_for_position(position)
    assert distance == 100.0 - position + 10.0
    assert distance == 65.0
    assert field_goal_success_probability(distance) > 0.18

    made = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=5.0,
            offense_field_position=position,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    made.rng = SequenceRNG((0.0,))
    made_state = made.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    assert made_state.team_a_score == 3
    assert made_state.possession is FootballTeamSide.TEAM_B
    assert made_state.offense_field_position == 25.0
    assert made_state.match_events[-1].field_goal_distance == 65.0

    missed = FootballMatchSimulator(
        _match_state(
            down=4,
            yards_to_go=5.0,
            offense_field_position=45.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    missed.rng = SequenceRNG((0.99,))
    missed_state = missed.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    assert missed_state.team_a_score == 0
    assert missed_state.possession is FootballTeamSide.TEAM_B
    assert missed_state.offense_field_position == 55.0


def test_scheme_is_fixed_for_drive_and_cleared_on_all_possession_changes():
    sim = _sim_with_scheme(rng=SequenceRNG((0.99,), (0.0,)))
    original = sim.state
    with pytest.raises(ValueError, match="cannot be replaced mid-drive"):
        sim.select_defensive_scheme(DefensiveSchemeAction.RB_RUN)
    assert sim.state is original

    play_turnover = _sim_with_scheme(rng=SequenceRNG((0.25,), (0.0,)))
    turned = play_turnover.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
    assert turned.current_drive_defensive_scheme is None

    for action, expected_position in (
        (FootballFourthDownAction.PUNT, 35.0),
        (FootballFourthDownAction.FIELD_GOAL, 75.0),
        (FootballFourthDownAction.GO_FOR_IT, 75.0),
    ):
        sim = FootballMatchSimulator(
            _match_state(
                down=4,
                offense_field_position=25.0,
                awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
                current_drive_defensive_scheme=DefensiveSchemeAction.RB_RUN,
            )
        )
        sim.rng = SequenceRNG(
            (0.99,) if action is not FootballFourthDownAction.FIELD_GOAL else (0.99,)
        )
        changed = sim.resolve_fourth_down(action)
        assert changed.possession is FootballTeamSide.TEAM_B
        assert changed.offense_field_position == expected_position
        assert changed.current_drive_defensive_scheme is None


def test_clock_is_capped_and_first_period_expiry_preserves_drive_state():
    capped = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (0.0,)),
        game_clock_seconds=4,
    )
    capped_state = capped.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    result = capped_state.match_events[-1].play_result
    assert result.clock_seconds_used == 4
    assert capped_state.period == 2
    assert capped_state.game_clock_seconds == 900
    assert capped_state.possession is FootballTeamSide.TEAM_A
    assert capped_state.down == 2
    assert capped_state.offense_field_position == 29.0
    assert capped_state.current_drive_defensive_scheme is DefensiveSchemeAction.SHORT_PASS


def test_special_teams_clock_is_capped_and_field_goal_at_expiry_completes():
    punt = FootballMatchSimulator(
        _match_state(
            down=4,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            game_clock_seconds=3,
        )
    )
    punt_state = punt.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert punt_state.period == 2
    assert punt_state.game_clock_seconds == 900
    assert punt_state.match_events[-1].clock_seconds_used == 3

    field_goal = FootballMatchSimulator(
        _match_state(
            period=2,
            down=4,
            offense_field_position=45.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
            game_clock_seconds=4,
        )
    )
    field_goal.rng = SequenceRNG((0.0,))
    completed = field_goal.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    assert completed.status is FootballMatchStatus.COMPLETED
    assert completed.team_a_score == 3
    assert completed.match_events[-1].clock_seconds_used == 4
    assert completed.final_result.team_a_score == completed.team_a_score
    assert completed.final_result.winner is FootballTeamSide.TEAM_A


def test_regulation_completes_at_expiry_and_tied_regulation_starts_overtime():
    ahead = FootballMatchSimulator(
        _match_state(
            team_a_score=3,
            team_b_score=0,
            period=2,
            game_clock_seconds=4,
            down=4,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    done = ahead.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert done.status is FootballMatchStatus.COMPLETED
    assert done.final_result.winner is FootballTeamSide.TEAM_A

    tied = FootballMatchSimulator(
        _match_state(
            period=2,
            game_clock_seconds=4,
            down=4,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    tied.rng = SequenceRNG(choice_value=FootballTeamSide.TEAM_B)
    overtime = tied.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert overtime.period == 3
    assert overtime.game_clock_seconds == 300
    assert overtime.possession is FootballTeamSide.TEAM_B
    assert overtime.offense_field_position == 25.0
    assert overtime.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME


@pytest.mark.parametrize(
    ("period", "play", "uniform"),
    [
        (3, OffensivePlayAction.RB_RUN, 1.0),
        (3, OffensivePlayAction.DEEP_PASS, 0.0),
    ],
)
def test_overtime_first_touchdown_ends_match(period, play, uniform):
    sim = _sim_with_scheme(
        scheme=DefensiveSchemeAction.DEEP_PASS,
        rng=SequenceRNG((0.99,), (uniform,)),
        period=period,
        offense_field_position=97.0,
    )
    result = sim.resolve_offensive_play(play)
    assert result.status is FootballMatchStatus.COMPLETED
    assert result.final_result.winner is FootballTeamSide.TEAM_A


def test_overtime_first_field_goal_and_safety_end_match():
    field_goal = FootballMatchSimulator(
        _match_state(
            period=3,
            down=4,
            offense_field_position=90.0,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    field_goal.rng = SequenceRNG((0.0,))
    fg_state = field_goal.resolve_fourth_down(FootballFourthDownAction.FIELD_GOAL)
    assert fg_state.status is FootballMatchStatus.COMPLETED
    assert fg_state.final_result.winner is FootballTeamSide.TEAM_A

    safety = _sim_with_scheme(
        scheme=DefensiveSchemeAction.RB_RUN,
        rng=SequenceRNG((0.99,), (-10.0,)),
        period=3,
        offense_field_position=2.0,
    )
    safety_state = safety.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert safety_state.status is FootballMatchStatus.COMPLETED
    assert safety_state.final_result.winner is FootballTeamSide.TEAM_B


def test_tied_overtime_expiry_starts_another_overtime_iteratively():
    sim = FootballMatchSimulator(
        _match_state(
            period=3,
            game_clock_seconds=4,
            down=4,
            awaited_action=FootballAwaitedAction.FOURTH_DOWN_DECISION,
        )
    )
    rng = SequenceRNG(choice_value=FootballTeamSide.TEAM_A)
    sim.rng = rng
    next_period = sim.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert next_period.period == 4
    assert next_period.game_clock_seconds == 300
    assert next_period.possession is FootballTeamSide.TEAM_A
    assert rng.choice_calls == 1


def test_scoring_play_at_regulation_expiry_keeps_score_and_completes_match():
    sim = _sim_with_scheme(
        rng=SequenceRNG((0.99,), (0.0,)),
        period=2,
        game_clock_seconds=4,
        offense_field_position=97.0,
    )
    result = sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert result.status is FootballMatchStatus.COMPLETED
    assert result.team_a_score == 7
    assert result.match_events[-1].status is FootballMatchStatus.COMPLETED


def test_event_history_is_immutable_ordered_and_reconciles_scores_and_result():
    sim = _sim_with_scheme(
        scheme=DefensiveSchemeAction.DEEP_PASS,
        rng=SequenceRNG((0.99,), (0.0,)),
        period=3,
        offense_field_position=97.0,
    )
    scored = sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert tuple(event.sequence for event in scored.match_events) == (1, 2)
    assert scored.match_events[0].action is DefensiveSchemeAction.DEEP_PASS
    assert scored.match_events[1].action is OffensivePlayAction.RB_RUN
    assert sum(
        event.points_scored
        for event in scored.match_events
        if event.scoring_team is FootballTeamSide.TEAM_A
    ) == scored.team_a_score
    assert sum(
        event.points_scored
        for event in scored.match_events
        if event.scoring_team is FootballTeamSide.TEAM_B
    ) == scored.team_b_score
    assert scored.final_result is not None
    assert (
        scored.final_result.team_a_score,
        scored.final_result.team_b_score,
        scored.final_result.winner,
    ) == (
        scored.team_a_score,
        scored.team_b_score,
        FootballTeamSide.TEAM_A,
    )
    with pytest.raises(AttributeError):
        scored.match_events[0].points_scored = 10


def test_stamina_fatigue_is_deterministic_bounded_and_affects_later_power():
    low_stamina_players = dict(_roster("Home", stamina=0.0).players)
    high_stamina_players = dict(_roster("Away", stamina=1.0).players)
    state = _match_state(
        team_a=FootballRoster("Home", low_stamina_players, _roster("Home").coach, FootballSpecialTeams()),
        team_b=FootballRoster("Away", high_stamina_players, _roster("Away").coach, FootballSpecialTeams()),
    )
    sim = FootballMatchSimulator(state)
    sim.select_defensive_scheme(DefensiveSchemeAction.DEEP_PASS)
    rng = SequenceRNG((0.99,) * (FATIGUE_RAMP_PLAYS + 2), (0.0,) * (FATIGUE_RAMP_PLAYS + 2))
    sim.rng = rng
    first_power = sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS).match_events[-1].play_result.offense_power
    for _ in range(FATIGUE_RAMP_PLAYS - 1):
        sim.state = replace(
            sim.state,
            down=1,
            yards_to_go=1.0,
            offense_field_position=25.0,
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        )
        sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    sim.state = replace(
        sim.state,
        down=1,
        yards_to_go=1.0,
        offense_field_position=25.0,
        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
    )
    later_power = sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS).match_events[-1].play_result.offense_power
    assert later_power < first_power
    assert later_power >= first_power * (1.0 - MAX_FATIGUE_POWER_REDUCTION)
    assert later_power == pytest.approx(17.28)


def test_seeded_match_instance_replays_identical_actions_and_advances_one_rng():
    def play_sequence():
        sim = FootballMatchSimulator(_match_state(random_seed=291))
        sim.select_defensive_scheme(DefensiveSchemeAction.DEEP_PASS)
        sim.resolve_offensive_play(OffensivePlayAction.RB_RUN)
        sim.resolve_offensive_play(OffensivePlayAction.DEEP_PASS)
        return sim.state

    assert play_sequence() == play_sequence()

    stream = _sim_with_scheme(rng=SequenceRNG((0.99, 0.99), (0.0, 0.0)))
    stream.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert stream.rng.random_calls == 1
    stream.resolve_offensive_play(OffensivePlayAction.RB_RUN)
    assert stream.rng.random_calls == 2


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda sim: sim.resolve_offensive_play(OffensivePlayAction.RB_RUN), "awaiting"),
        (lambda sim: sim.resolve_fourth_down(FootballFourthDownAction.PUNT), "awaiting"),
        (lambda sim: sim.select_defensive_scheme("bad"), "DefensiveSchemeAction"),
        (lambda sim: sim.resolve_offensive_play("bad"), "OffensivePlayAction"),
        (lambda sim: sim.resolve_fourth_down("bad"), "FootballFourthDownAction"),
    ],
)
def test_invalid_or_unawaited_actions_do_not_change_state_or_rng(operation, message):
    sim = FootballMatchSimulator(_match_state())
    before_state = sim.state
    before_rng = sim.rng.getstate()
    with pytest.raises(ValueError, match=message):
        operation(sim)
    assert sim.state is before_state
    assert sim.rng.getstate() == before_rng


def test_invalid_fourth_down_call_preserves_state_and_rng():
    sim = FootballMatchSimulator(
        _match_state(down=3, awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY)
    )
    before = sim.state
    rng_state = sim.rng.getstate()
    with pytest.raises(ValueError, match="awaiting"):
        sim.resolve_fourth_down(FootballFourthDownAction.PUNT)
    assert sim.state is before
    assert sim.rng.getstate() == rng_state


def test_illegal_fourth_down_state_and_invalid_matchup_are_rejected():
    with pytest.raises(ValueError, match="fourth down"):
        FootballMatchState(
            **{
                "team_a": _roster("Home"),
                "team_b": _roster("Away"),
                "random_seed": 1,
                "team_a_score": 0,
                "team_b_score": 0,
                "possession": FootballTeamSide.TEAM_A,
                "down": 3,
                "yards_to_go": 10.0,
                "offense_field_position": 25.0,
                "game_clock_seconds": 900,
                "period": 1,
                "awaited_action": FootballAwaitedAction.FOURTH_DOWN_DECISION,
                "current_drive_defensive_scheme": DefensiveSchemeAction.RB_RUN,
            }
        )
    with pytest.raises(ValueError, match="Unsupported play"):
        matchup_for_play("not-a-play")


def test_expired_clock_and_non_tied_overtime_cannot_start_a_simulator():
    with pytest.raises(ValueError, match="expired period clock"):
        FootballMatchSimulator(_match_state(game_clock_seconds=0))
    with pytest.raises(ValueError, match="must start tied"):
        FootballMatchSimulator(
            _match_state(
                period=3,
                team_a_score=3,
                game_clock_seconds=300,
            )
        )
