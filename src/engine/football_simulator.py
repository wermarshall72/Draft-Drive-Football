"""Caller-driven interactive football match resolution.

All randomness belongs to one ``FootballMatchSimulator`` instance for the
entire match. Yardage, clock, fatigue, and probability constants are prototype
values, not real-world statistical data.
"""

from __future__ import annotations

import random
from dataclasses import replace
from math import isfinite
from numbers import Real

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballFourthDownAction,
    FootballMatchEvent,
    FootballMatchResult,
    FootballMatchState,
    FootballMatchStatus,
    FootballPlayResult,
    FootballPosition,
    FootballTeamSide,
    OffensivePlayAction,
)

REGULATION_PERIOD_SECONDS = 900
OVERTIME_PERIOD_SECONDS = 300
FIRST_DOWN_YARDS = 10.0
GOAL_LINE_YARDS = 100.0
FIELD_GOAL_DISTANCE_BUFFER = 10.0

# Prototype drive-resolution values; these are not real-world statistics.
FIELD_GOAL_SUCCESS_BASE = 0.86
FIELD_GOAL_SUCCESS_DROP_PER_TEN_YARDS = 0.065
FIELD_GOAL_SUCCESS_FLOOR = 0.18
FIELD_GOAL_POINTS = 3
TOUCHDOWN_POINTS = 7
SAFETY_POINTS = 2
RUN_PLAY_CLOCK_SECONDS = 18
COMPLETED_PASS_CLOCK_SECONDS = 18
INCOMPLETE_PASS_CLOCK_SECONDS = 5
TURNOVER_PLAY_CLOCK_SECONDS = 18
GO_FOR_IT_CLOCK_SECONDS = 18
PUNT_CLOCK_SECONDS = 18
FIELD_GOAL_CLOCK_SECONDS = 5
PUNT_NET_YARDS = 40.0
TOUCHBACK_START_YARDS = 25.0
GO_FOR_IT_GAIN_MIN_YARDS = 1.0
GO_FOR_IT_GAIN_MAX_YARDS = 4.0
GO_FOR_IT_MAX_YARDS = 20.0
MIN_PLAY_YARDAGE_SPREAD = 1.0
VOLATILITY_SPREAD_MULTIPLIER = 6.0
TURNOVER_LOSS_YARDS = -3.0
FATIGUE_RAMP_PLAYS = 30
MAX_FATIGUE_POWER_REDUCTION = 0.10
MATCHED_SCHEME_DEFENSE_MULTIPLIER = 1.12
MATCHED_SCHEME_OFFENSE_MULTIPLIER = 0.96
TURNOVER_BASE_PROBABILITY = 0.08
MATCHED_SCHEME_TURNOVER_BONUS = 0.06
PASS_INCOMPLETE_BASE_PROBABILITY = 0.22
MATCHED_SCHEME_INCOMPLETE_BONUS = 0.12
PASS_INTERCEPTION_PROBABILITY = 0.12
GO_FOR_IT_BASE_SUCCESS_PROBABILITY = 0.52
GO_FOR_IT_MAX_SUCCESS_PROBABILITY = 0.78

_PLAY_MATCHUPS = {
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

_PASS_PLAYS = {
    OffensivePlayAction.SCREEN_PASS,
    OffensivePlayAction.PA_PASS,
    OffensivePlayAction.SHORT_PASS,
    OffensivePlayAction.MEDIUM_PASS,
    OffensivePlayAction.DEEP_PASS,
}

_BASE_YARDAGE = {
    OffensivePlayAction.RB_RUN: 4.0,
    OffensivePlayAction.SCREEN_PASS: 3.5,
    OffensivePlayAction.PA_PASS: 5.0,
    OffensivePlayAction.SHORT_PASS: 5.5,
    OffensivePlayAction.MEDIUM_PASS: 6.5,
    OffensivePlayAction.DEEP_PASS: 8.0,
}


def matchup_for_play(play: OffensivePlayAction) -> tuple[tuple[FootballPosition, ...], tuple[FootballPosition, ...]]:
    if not isinstance(play, OffensivePlayAction) or play not in _PLAY_MATCHUPS:
        raise ValueError(f"Unsupported play: {play!r}")
    return _PLAY_MATCHUPS[play]


def field_goal_distance_for_position(field_position: float) -> float:
    if (
        isinstance(field_position, bool)
        or not isinstance(field_position, Real)
        or not isfinite(field_position)
    ):
        raise ValueError("Field position must be a finite number from 0 to 100.")
    if not 0 <= field_position <= GOAL_LINE_YARDS:
        raise ValueError("Field position must be between 0 and 100.")
    return (GOAL_LINE_YARDS - field_position) + FIELD_GOAL_DISTANCE_BUFFER


def field_goal_success_probability(distance: float) -> float:
    if (
        isinstance(distance, bool)
        or not isinstance(distance, Real)
        or not isfinite(distance)
        or distance < 0
    ):
        raise ValueError("Field-goal distance must be a non-negative number.")
    return max(
        FIELD_GOAL_SUCCESS_FLOOR,
        FIELD_GOAL_SUCCESS_BASE
        - (distance / 10.0) * FIELD_GOAL_SUCCESS_DROP_PER_TEN_YARDS,
    )


def _opponent(side: FootballTeamSide) -> FootballTeamSide:
    return (
        FootballTeamSide.TEAM_B
        if side is FootballTeamSide.TEAM_A
        else FootballTeamSide.TEAM_A
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _drive_yards_remaining(position: float) -> float:
    return max(0.0, GOAL_LINE_YARDS - position)


def _scheme_matches_play(
    scheme: DefensiveSchemeAction | None, play: OffensivePlayAction
) -> bool:
    return scheme is not None and scheme.value == play.value


def _complete_match(state: FootballMatchState) -> FootballMatchState:
    if state.team_a_score == state.team_b_score:
        raise ValueError("A completed match cannot end in a tie.")
    winner = (
        FootballTeamSide.TEAM_A
        if state.team_a_score > state.team_b_score
        else FootballTeamSide.TEAM_B
    )
    return replace(
        state,
        status=FootballMatchStatus.COMPLETED,
        awaited_action=None,
        current_drive_defensive_scheme=None,
        final_result=FootballMatchResult(
            team_a_score=state.team_a_score,
            team_b_score=state.team_b_score,
            winner=winner,
            completed=True,
        ),
    )


def _advance_period_if_expired(
    state: FootballMatchState, rng: random.Random
) -> FootballMatchState:
    if state.status is FootballMatchStatus.COMPLETED or state.game_clock_seconds > 0:
        return state
    if state.period == 1:
        return replace(
            state,
            period=2,
            game_clock_seconds=REGULATION_PERIOD_SECONDS,
        )
    if state.period == 2 and state.team_a_score != state.team_b_score:
        return _complete_match(state)
    if state.period >= 2:
        return replace(
            state,
            period=state.period + 1,
            game_clock_seconds=OVERTIME_PERIOD_SECONDS,
            down=1,
            yards_to_go=FIRST_DOWN_YARDS,
            offense_field_position=TOUCHBACK_START_YARDS,
            possession=rng.choice((FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B)),
            awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
            current_drive_defensive_scheme=None,
        )
    raise ValueError(f"Unsupported match period: {state.period}")


def _after_possession_change(
    state: FootballMatchState,
    *,
    possession: FootballTeamSide,
    field_position: float,
    clock_cost: int,
) -> FootballMatchState:
    return replace(
        state,
        possession=possession,
        down=1,
        yards_to_go=FIRST_DOWN_YARDS,
        offense_field_position=_clamp(field_position, 0.0, GOAL_LINE_YARDS),
        game_clock_seconds=max(0, state.game_clock_seconds - clock_cost),
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        current_drive_defensive_scheme=None,
    )


def _record_event(
    state: FootballMatchState,
    *,
    action: OffensivePlayAction | DefensiveSchemeAction | FootballFourthDownAction,
    play_result: FootballPlayResult | None = None,
    points_scored: int = 0,
    scoring_team: FootballTeamSide | None = None,
    field_goal_distance: float | None = None,
    clock_seconds_used: int = 0,
) -> FootballMatchState:
    event = FootballMatchEvent(
        sequence=len(state.match_events) + 1,
        action=action,
        team_a_score=state.team_a_score,
        team_b_score=state.team_b_score,
        possession=state.possession,
        offense_field_position=state.offense_field_position,
        down=state.down,
        yards_to_go=state.yards_to_go,
        game_clock_seconds=state.game_clock_seconds,
        period=state.period,
        status=state.status,
        clock_seconds_used=clock_seconds_used,
        play_result=play_result,
        points_scored=points_scored,
        scoring_team=scoring_team,
        field_goal_distance=field_goal_distance,
    )
    events = state.match_events + (event,)
    first = events[0]
    score_a = first.team_a_score - (
        first.points_scored if first.scoring_team is FootballTeamSide.TEAM_A else 0
    )
    score_b = first.team_b_score - (
        first.points_scored if first.scoring_team is FootballTeamSide.TEAM_B else 0
    )
    for recorded_event in events:
        score_a += (
            recorded_event.points_scored
            if recorded_event.scoring_team is FootballTeamSide.TEAM_A
            else 0
        )
        score_b += (
            recorded_event.points_scored
            if recorded_event.scoring_team is FootballTeamSide.TEAM_B
            else 0
        )
        if (recorded_event.team_a_score, recorded_event.team_b_score) != (
            score_a,
            score_b,
        ):
            raise ValueError("Match event scores do not reconcile with scoring events.")
    if (state.team_a_score, state.team_b_score) != (score_a, score_b):
        raise ValueError("Match state scores do not match the recorded event history.")
    return replace(state, match_events=events)


def _add_score(
    state: FootballMatchState, team: FootballTeamSide, points: int
) -> FootballMatchState:
    return replace(
        state,
        team_a_score=state.team_a_score + (points if team is FootballTeamSide.TEAM_A else 0),
        team_b_score=state.team_b_score + (points if team is FootballTeamSide.TEAM_B else 0),
    )


class FootballMatchSimulator:
    """Resolve caller-provided match actions against a persistent seeded RNG."""

    def __init__(self, match_state: FootballMatchState):
        if not isinstance(match_state, FootballMatchState):
            raise ValueError("Match state must be a FootballMatchState.")
        if (
            match_state.status is FootballMatchStatus.IN_PROGRESS
            and match_state.game_clock_seconds == 0
        ):
            raise ValueError("An in-progress match cannot start with an expired period clock.")
        if (
            match_state.status is FootballMatchStatus.IN_PROGRESS
            and match_state.period >= 3
            and match_state.team_a_score != match_state.team_b_score
        ):
            raise ValueError("An in-progress overtime match must start tied.")
        self.state = match_state
        self.rng = random.Random(match_state.random_seed)

    def _require_action(self, expected: FootballAwaitedAction) -> None:
        if self.state.status is FootballMatchStatus.COMPLETED:
            raise ValueError("A completed match cannot accept new actions.")
        if self.state.awaited_action is not expected:
            raise ValueError(f"Action is not legal while awaiting {self.state.awaited_action!r}.")
        if self.state.game_clock_seconds == 0:
            raise ValueError("No action is legal after the period clock has expired.")

    def select_defensive_scheme(
        self, scheme: DefensiveSchemeAction
    ) -> FootballMatchState:
        if not isinstance(scheme, DefensiveSchemeAction):
            raise ValueError("Defense must be a DefensiveSchemeAction.")
        if self.state.current_drive_defensive_scheme is not None:
            raise ValueError("A defensive scheme cannot be replaced mid-drive.")
        self._require_action(FootballAwaitedAction.DEFENSIVE_SCHEME)
        updated = replace(
            self.state,
            current_drive_defensive_scheme=scheme,
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        )
        self.state = _record_event(updated, action=scheme)
        return self.state

    def _adjusted_power(self, player_power: float, stamina: float, prior_plays: int) -> float:
        """Linearly reduce low-stamina power by at most 10% over 30 snaps."""
        ramp = min(prior_plays / FATIGUE_RAMP_PLAYS, 1.0)
        reduction = ramp * MAX_FATIGUE_POWER_REDUCTION * (1.0 - stamina)
        return player_power * (1.0 - reduction)

    def resolve_offensive_play(self, play: OffensivePlayAction) -> FootballMatchState:
        if not isinstance(play, OffensivePlayAction):
            raise ValueError("Offensive play must be an OffensivePlayAction.")
        self._require_action(FootballAwaitedAction.OFFENSIVE_PLAY)
        scheme = self.state.current_drive_defensive_scheme
        if scheme is None:
            raise ValueError("A defensive scheme must be chosen before the snap.")

        offense_roster = (
            self.state.team_a
            if self.state.possession is FootballTeamSide.TEAM_A
            else self.state.team_b
        )
        defense_roster = (
            self.state.team_b
            if self.state.possession is FootballTeamSide.TEAM_A
            else self.state.team_a
        )
        offense_slots, defense_slots = matchup_for_play(play)
        offense_players = [offense_roster.players[position] for position in offense_slots]
        defense_players = [defense_roster.players[position] for position in defense_slots]
        prior_plays = sum(
            event.play_result is not None for event in self.state.match_events
        )
        offense_power = sum(
            self._adjusted_power(player.power, player.stamina, prior_plays)
            for player in offense_players
        )
        defense_power = sum(
            self._adjusted_power(player.power, player.stamina, prior_plays)
            for player in defense_players
        )
        same_scheme = _scheme_matches_play(scheme, play)
        if same_scheme:
            defense_power *= MATCHED_SCHEME_DEFENSE_MULTIPLIER
            offense_power *= MATCHED_SCHEME_OFFENSE_MULTIPLIER

        spread = max(
            MIN_PLAY_YARDAGE_SPREAD,
            (
                sum(player.volatility for player in offense_players)
                / len(offense_players)
                + sum(player.volatility for player in defense_players)
                / len(defense_players)
            )
            * VOLATILITY_SPREAD_MULTIPLIER,
        )
        yards = _BASE_YARDAGE[play] + (offense_power - defense_power) * 0.5
        yards += self.rng.uniform(-spread, spread)
        turnover = False
        incomplete = False
        if play in _PASS_PLAYS:
            roll = self.rng.random()
            incomplete_threshold = PASS_INCOMPLETE_BASE_PROBABILITY + (
                MATCHED_SCHEME_INCOMPLETE_BONUS if same_scheme else 0.0
            )
            if roll < incomplete_threshold:
                incomplete = True
                yards = 0.0
            elif roll < incomplete_threshold + PASS_INTERCEPTION_PROBABILITY:
                turnover = True
                yards = TURNOVER_LOSS_YARDS
        elif self.rng.random() < TURNOVER_BASE_PROBABILITY + (
            MATCHED_SCHEME_TURNOVER_BONUS if same_scheme else 0.0
        ):
            turnover = True
            yards = min(yards, 0.0)

        clock_cost = (
            INCOMPLETE_PASS_CLOCK_SECONDS
            if incomplete
            else TURNOVER_PLAY_CLOCK_SECONDS
            if turnover
            else RUN_PLAY_CLOCK_SECONDS
            if play is OffensivePlayAction.RB_RUN
            else COMPLETED_PASS_CLOCK_SECONDS
        )
        positive_gain = yards > 0
        if positive_gain:
            yards = min(yards, _drive_yards_remaining(self.state.offense_field_position))
        new_position = self.state.offense_field_position + yards
        if new_position <= 0 and yards < 0:
            scoring_team = _opponent(self.state.possession)
            scored = _add_score(self.state, scoring_team, SAFETY_POINTS)
            next_state = _after_possession_change(
                scored,
                possession=scoring_team,
                field_position=TOUCHBACK_START_YARDS,
                clock_cost=clock_cost,
            )
            next_state = self._finish_action(next_state, points=SAFETY_POINTS)
            result = FootballPlayResult(
                play,
                yards,
                min(self.state.game_clock_seconds, clock_cost),
                points_scored=SAFETY_POINTS,
                turnover=turnover,
                possession_changed=True,
                defensive_scheme=scheme,
                incomplete=incomplete,
                offense_power=offense_power,
                defense_power=defense_power,
            )
            self.state = _record_event(
                next_state,
                action=play,
                play_result=result,
                points_scored=SAFETY_POINTS,
                scoring_team=scoring_team,
                clock_seconds_used=result.clock_seconds_used,
            )
            return self.state

        if new_position >= GOAL_LINE_YARDS and positive_gain:
            scoring_team = self.state.possession
            scored = _add_score(self.state, scoring_team, TOUCHDOWN_POINTS)
            next_state = _after_possession_change(
                scored,
                possession=_opponent(scoring_team),
                field_position=TOUCHBACK_START_YARDS,
                clock_cost=clock_cost,
            )
            next_state = self._finish_action(next_state, points=TOUCHDOWN_POINTS)
            result = FootballPlayResult(
                play,
                yards,
                min(self.state.game_clock_seconds, clock_cost),
                points_scored=TOUCHDOWN_POINTS,
                turnover=False,
                possession_changed=True,
                defensive_scheme=scheme,
                incomplete=incomplete,
                offense_power=offense_power,
                defense_power=defense_power,
            )
            self.state = _record_event(
                next_state,
                action=play,
                play_result=result,
                points_scored=TOUCHDOWN_POINTS,
                scoring_team=scoring_team,
                clock_seconds_used=result.clock_seconds_used,
            )
            return self.state

        if turnover:
            next_state = _after_possession_change(
                self.state,
                possession=_opponent(self.state.possession),
                field_position=100.0 - new_position,
                clock_cost=clock_cost,
            )
        else:
            line_to_gain = min(
                self.state.yards_to_go,
                FIRST_DOWN_YARDS,
                _drive_yards_remaining(self.state.offense_field_position),
            )
            line_to_gain = max(0.1, line_to_gain)
            first_down = yards >= line_to_gain
            remaining_goal_distance = _drive_yards_remaining(new_position)
            if first_down:
                next_down = 1
                next_yards_to_go = min(FIRST_DOWN_YARDS, remaining_goal_distance)
                if next_yards_to_go <= 0:
                    next_yards_to_go = FIRST_DOWN_YARDS
                awaited = FootballAwaitedAction.OFFENSIVE_PLAY
            else:
                next_down = min(self.state.down + 1, 4)
                next_yards_to_go = max(0.1, line_to_gain - yards)
                awaited = (
                    FootballAwaitedAction.FOURTH_DOWN_DECISION
                    if next_down == 4
                    else FootballAwaitedAction.OFFENSIVE_PLAY
                )
            next_state = replace(
                self.state,
                down=next_down,
                yards_to_go=next_yards_to_go,
                offense_field_position=new_position,
                game_clock_seconds=max(0, self.state.game_clock_seconds - clock_cost),
                awaited_action=awaited,
            )

        result = FootballPlayResult(
            offensive_play=play,
            yards_gained=yards,
            clock_seconds_used=min(self.state.game_clock_seconds, clock_cost),
            points_scored=0,
            turnover=turnover,
            possession_changed=turnover,
            defensive_scheme=scheme,
            incomplete=incomplete,
            offense_power=offense_power,
            defense_power=defense_power,
        )
        next_state = self._finish_action(next_state)
        self.state = _record_event(
            next_state,
            action=play,
            play_result=result,
            clock_seconds_used=result.clock_seconds_used,
        )
        return self.state

    def _finish_action(
        self,
        state: FootballMatchState,
        *,
        points: int = 0,
    ) -> FootballMatchState:
        if points and state.period >= 3:
            return _complete_match(state)
        return _advance_period_if_expired(state, self.rng)

    def resolve_fourth_down(
        self, decision: FootballFourthDownAction
    ) -> FootballMatchState:
        if not isinstance(decision, FootballFourthDownAction):
            raise ValueError("Fourth-down decision must be a FootballFourthDownAction.")
        self._require_action(FootballAwaitedAction.FOURTH_DOWN_DECISION)
        if self.state.down != 4:
            raise ValueError("Fourth-down decisions are only legal on fourth down.")

        state = self.state
        points = 0
        scoring_team = None
        distance = None
        clock_cost = 0
        if decision is FootballFourthDownAction.GO_FOR_IT:
            clock_cost = GO_FOR_IT_CLOCK_SECONDS
            yards_to_gain = min(
                state.yards_to_go,
                FIRST_DOWN_YARDS,
                _drive_yards_remaining(state.offense_field_position),
            )
            probability = min(
                GO_FOR_IT_MAX_SUCCESS_PROBABILITY,
                GO_FOR_IT_BASE_SUCCESS_PROBABILITY + yards_to_gain / 12.0,
            )
            if self.rng.random() < probability:
                gain = min(
                    yards_to_gain
                    + self.rng.uniform(
                        GO_FOR_IT_GAIN_MIN_YARDS, GO_FOR_IT_GAIN_MAX_YARDS
                    ),
                    GO_FOR_IT_MAX_YARDS,
                    _drive_yards_remaining(state.offense_field_position),
                )
                new_position = state.offense_field_position + gain
                if new_position >= GOAL_LINE_YARDS:
                    scoring_team = state.possession
                    points = 7
                    state = _add_score(state, scoring_team, points)
                    state = _after_possession_change(
                        state,
                        possession=_opponent(scoring_team),
                        field_position=TOUCHBACK_START_YARDS,
                        clock_cost=GO_FOR_IT_CLOCK_SECONDS,
                    )
                else:
                    state = replace(
                        state,
                        down=1,
                        yards_to_go=min(
                            FIRST_DOWN_YARDS,
                            _drive_yards_remaining(new_position),
                        ),
                        offense_field_position=new_position,
                        game_clock_seconds=max(
                            0, state.game_clock_seconds - GO_FOR_IT_CLOCK_SECONDS
                        ),
                        awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
                    )
            else:
                state = _after_possession_change(
                    state,
                    possession=_opponent(state.possession),
                    field_position=100.0 - state.offense_field_position,
                    clock_cost=GO_FOR_IT_CLOCK_SECONDS,
                )
        elif decision is FootballFourthDownAction.PUNT:
            clock_cost = PUNT_CLOCK_SECONDS
            punt_end_position = state.offense_field_position + PUNT_NET_YARDS
            receiving_position = (
                TOUCHBACK_START_YARDS
                if punt_end_position >= GOAL_LINE_YARDS
                else 100.0 - punt_end_position
            )
            state = _after_possession_change(
                state,
                possession=_opponent(state.possession),
                field_position=receiving_position,
                clock_cost=PUNT_CLOCK_SECONDS,
            )
        elif decision is FootballFourthDownAction.FIELD_GOAL:
            clock_cost = FIELD_GOAL_CLOCK_SECONDS
            distance = field_goal_distance_for_position(state.offense_field_position)
            if self.rng.random() < field_goal_success_probability(distance):
                scoring_team = state.possession
                points = FIELD_GOAL_POINTS
                state = _add_score(state, scoring_team, points)
                state = _after_possession_change(
                    state,
                    possession=_opponent(scoring_team),
                    field_position=TOUCHBACK_START_YARDS,
                    clock_cost=FIELD_GOAL_CLOCK_SECONDS,
                )
            else:
                state = _after_possession_change(
                    state,
                    possession=_opponent(state.possession),
                    field_position=100.0 - state.offense_field_position,
                    clock_cost=FIELD_GOAL_CLOCK_SECONDS,
                )

        if points and state.period >= 3:
            state = _complete_match(state)
        else:
            state = _advance_period_if_expired(state, self.rng)
        self.state = _record_event(
            state,
            action=decision,
            points_scored=points,
            scoring_team=scoring_team,
            field_goal_distance=distance,
            clock_seconds_used=min(self.state.game_clock_seconds, clock_cost),
        )
        return self.state
