"""Interactive football simulator for the redesign prototype.

The simulator accepts caller-supplied actions and keeps the match RNG bound to a
single match instance. The model types live in ``src.engine.football`` and state is
returned as a new ``FootballMatchState`` instance for each transition.
"""

from __future__ import annotations

import random
from dataclasses import replace

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballFourthDownAction,
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
FIELD_GOAL_SUCCESS_BASE = 0.86
FIELD_GOAL_SUCCESS_DROP_PER_TEN_YARDS = 0.065
FIELD_GOAL_SUCCESS_FLOOR = 0.18

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


def matchup_for_play(play: OffensivePlayAction):
    if play not in _PLAY_MATCHUPS:
        raise ValueError(f"Unsupported play: {play!r}")
    return _PLAY_MATCHUPS[play]


def field_goal_distance_for_position(field_position: float) -> float:
    return (GOAL_LINE_YARDS - field_position) + FIELD_GOAL_DISTANCE_BUFFER


def field_goal_success_probability(distance: float) -> float:
    return max(
        FIELD_GOAL_SUCCESS_FLOOR,
        FIELD_GOAL_SUCCESS_BASE - (max(0.0, distance) / 10.0) * FIELD_GOAL_SUCCESS_DROP_PER_TEN_YARDS,
    )


def _opponent(side: FootballTeamSide) -> FootballTeamSide:
    return FootballTeamSide.TEAM_B if side is FootballTeamSide.TEAM_A else FootballTeamSide.TEAM_A


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _drive_yards_remaining(position: float) -> float:
    return max(0.0, GOAL_LINE_YARDS - position)


def _scheme_matches_play(scheme: DefensiveSchemeAction | None, play: OffensivePlayAction) -> bool:
    return scheme is not None and scheme.value == play.value


def _complete_match(state: FootballMatchState) -> FootballMatchState:
    if state.team_a_score == state.team_b_score:
        raise ValueError("A completed match cannot end in a tie.")
    winner = FootballTeamSide.TEAM_A if state.team_a_score > state.team_b_score else FootballTeamSide.TEAM_B
    final_result = FootballMatchResult(
        team_a_score=state.team_a_score,
        team_b_score=state.team_b_score,
        winner=winner,
        completed=True,
    )
    return replace(
        state,
        status=FootballMatchStatus.COMPLETED,
        awaited_action=None,
        current_drive_defensive_scheme=None,
        final_result=final_result,
    )


def _advance_clock_period(
    state: FootballMatchState, rng: random.Random
) -> FootballMatchState:
    if state.status is FootballMatchStatus.COMPLETED or state.game_clock_seconds > 0:
        return state
    if state.period < 2:
        return replace(state, period=2, game_clock_seconds=REGULATION_PERIOD_SECONDS)
    if state.team_a_score != state.team_b_score:
        return _complete_match(state)
    if state.period == 2:
        return replace(
            state,
            period=3,
            game_clock_seconds=OVERTIME_PERIOD_SECONDS,
            down=1,
            yards_to_go=FIRST_DOWN_YARDS,
            offense_field_position=25.0,
            possession=rng.choice((FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B)),
            awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
            current_drive_defensive_scheme=None,
        )
    return replace(
        state,
        period=state.period + 1,
        game_clock_seconds=OVERTIME_PERIOD_SECONDS,
        down=1,
        yards_to_go=FIRST_DOWN_YARDS,
        offense_field_position=25.0,
        possession=rng.choice((FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B)),
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        current_drive_defensive_scheme=None,
    )


class FootballMatchSimulator:
    def __init__(self, match_state: FootballMatchState):
        if not isinstance(match_state, FootballMatchState):
            raise ValueError("Match state must be a FootballMatchState.")
        self.state = match_state
        self.rng = random.Random(match_state.random_seed)

    def select_defensive_scheme(self, scheme: DefensiveSchemeAction) -> FootballMatchState:
        if not isinstance(scheme, DefensiveSchemeAction):
            raise ValueError("Defense must be a DefensiveSchemeAction.")
        if self.state.status is FootballMatchStatus.COMPLETED:
            raise ValueError("A completed match cannot accept new actions.")
        if self.state.awaited_action is not FootballAwaitedAction.DEFENSIVE_SCHEME:
            raise ValueError("Defensive scheme selection is only legal at the start of a drive.")
        if self.state.current_drive_defensive_scheme is not None:
            raise ValueError("A defensive scheme cannot be replaced mid-drive.")
        self.state = replace(
            self.state,
            current_drive_defensive_scheme=scheme,
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        )
        return self.state

    def resolve_offensive_play(self, play: OffensivePlayAction) -> FootballMatchState:
        if not isinstance(play, OffensivePlayAction):
            raise ValueError("Offensive play must be an OffensivePlayAction.")
        if self.state.status is FootballMatchStatus.COMPLETED:
            raise ValueError("A completed match cannot accept new actions.")
        if self.state.awaited_action is not FootballAwaitedAction.OFFENSIVE_PLAY:
            raise ValueError("Offensive play is not currently legal.")
        if self.state.current_drive_defensive_scheme is None:
            raise ValueError("A defensive scheme must be chosen before the snap.")

        scheme = self.state.current_drive_defensive_scheme
        same_scheme = _scheme_matches_play(scheme, play)
        offense_roster = self.state.team_a if self.state.possession is FootballTeamSide.TEAM_A else self.state.team_b
        defense_roster = self.state.team_b if self.state.possession is FootballTeamSide.TEAM_A else self.state.team_a
        offense_slots, defense_slots = matchup_for_play(play)
        offense_players = [offense_roster.players[position] for position in offense_slots]
        defense_players = [defense_roster.players[position] for position in defense_slots]
        offense_power = sum(player.power for player in offense_players)
        defense_power = sum(player.power for player in defense_players)
        if same_scheme:
            defense_power *= 1.12
            offense_power *= 0.96

        base_gain = {
            OffensivePlayAction.RB_RUN: 4.0,
            OffensivePlayAction.SCREEN_PASS: 3.5,
            OffensivePlayAction.PA_PASS: 5.0,
            OffensivePlayAction.SHORT_PASS: 5.5,
            OffensivePlayAction.MEDIUM_PASS: 6.5,
            OffensivePlayAction.DEEP_PASS: 8.0,
        }[play]
        spread = max(1.0, (sum(p.volatility for p in offense_players) / len(offense_players) + sum(p.volatility for p in defense_players) / len(defense_players)) * 6.0)
        yards = base_gain + (offense_power - defense_power) * 0.5 + self.rng.uniform(-spread, spread)

        turnover = False
        incomplete = False
        if play in _PASS_PLAYS:
            roll = self.rng.random()
            threshold = 0.22 + (0.12 if same_scheme else 0.0)
            if roll < threshold:
                incomplete = True
                yards = -2.0
            elif roll < threshold + 0.12:
                turnover = True
                yards = -3.0
        else:
            roll = self.rng.random()
            if roll < 0.08 + (0.06 if same_scheme else 0.0):
                turnover = True
                yards = min(yards, 0.0)

        if incomplete:
            yards = -2.0

        if yards > 0 and self.state.offense_field_position >= GOAL_LINE_YARDS - 10.0:
            yards = max(yards, GOAL_LINE_YARDS - self.state.offense_field_position)

        new_position = self.state.offense_field_position + yards
        if new_position <= 0 and yards < 0:
            safety_team = _opponent(self.state.possession)
            next_scores = [self.state.team_a_score, self.state.team_b_score]
            if safety_team is FootballTeamSide.TEAM_A:
                next_scores[0] += 2
            else:
                next_scores[1] += 2
            next_state = replace(
                self.state,
                team_a_score=next_scores[0],
                team_b_score=next_scores[1],
                possession=safety_team,
                down=1,
                yards_to_go=FIRST_DOWN_YARDS,
                offense_field_position=25.0,
                game_clock_seconds=max(0, self.state.game_clock_seconds - 18),
                awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                current_drive_defensive_scheme=None,
            )
            self.state = _advance_clock_period(next_state, self.rng)
            return self.state

        if new_position >= GOAL_LINE_YARDS:
            score_team = self.state.possession
            next_team = _opponent(score_team)
            next_scores = [self.state.team_a_score, self.state.team_b_score]
            if score_team is FootballTeamSide.TEAM_A:
                next_scores[0] += 7
            else:
                next_scores[1] += 7
            next_state = replace(
                self.state,
                team_a_score=next_scores[0],
                team_b_score=next_scores[1],
                possession=next_team,
                down=1,
                yards_to_go=FIRST_DOWN_YARDS,
                offense_field_position=25.0,
                game_clock_seconds=max(0, self.state.game_clock_seconds - 26),
                awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                current_drive_defensive_scheme=None,
            )
            if next_state.period >= 3 and next_state.team_a_score != next_state.team_b_score:
                self.state = _complete_match(next_state)
                return self.state
            self.state = _advance_clock_period(next_state, self.rng)
            return self.state

        if turnover:
            receiver = _opponent(self.state.possession)
            field_position = _clamp(100.0 - new_position, 0.0, GOAL_LINE_YARDS)
            next_state = replace(
                self.state,
                possession=receiver,
                down=1,
                yards_to_go=FIRST_DOWN_YARDS,
                offense_field_position=field_position,
                game_clock_seconds=max(0, self.state.game_clock_seconds - 18),
                awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                current_drive_defensive_scheme=None,
            )
            self.state = _advance_clock_period(next_state, self.rng)
            return self.state

        if yards >= 0:
            if yards >= min(self.state.yards_to_go, FIRST_DOWN_YARDS):
                remaining_distance = _drive_yards_remaining(new_position)
                next_yards_to_go = FIRST_DOWN_YARDS if remaining_distance > FIRST_DOWN_YARDS else remaining_distance
                if next_yards_to_go <= 0:
                    next_yards_to_go = FIRST_DOWN_YARDS
                next_state = replace(
                    self.state,
                    down=1,
                    yards_to_go=next_yards_to_go,
                    offense_field_position=new_position,
                    game_clock_seconds=max(0, self.state.game_clock_seconds - 16),
                    current_drive_defensive_scheme=self.state.current_drive_defensive_scheme,
                    awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
                )
            else:
                new_down = self.state.down + 1
                remaining = max(0.0, self.state.yards_to_go - yards)
                if new_down >= 4:
                    await_action = FootballAwaitedAction.FOURTH_DOWN_DECISION
                    new_down = 4
                else:
                    await_action = FootballAwaitedAction.OFFENSIVE_PLAY
                next_state = replace(
                    self.state,
                    down=new_down,
                    yards_to_go=remaining,
                    offense_field_position=new_position,
                    game_clock_seconds=max(0, self.state.game_clock_seconds - 16),
                    current_drive_defensive_scheme=self.state.current_drive_defensive_scheme,
                    awaited_action=await_action,
                )
            self.state = _advance_clock_period(next_state, self.rng)
            return self.state

        remaining = self.state.yards_to_go - yards
        next_down = self.state.down + 1 if self.state.down < 4 else 4
        await_action = FootballAwaitedAction.OFFENSIVE_PLAY if next_down < 4 else FootballAwaitedAction.FOURTH_DOWN_DECISION
        next_state = replace(
            self.state,
            down=next_down,
            yards_to_go=remaining,
            offense_field_position=new_position,
            game_clock_seconds=max(0, self.state.game_clock_seconds - 16),
            current_drive_defensive_scheme=self.state.current_drive_defensive_scheme,
            awaited_action=await_action,
        )
        self.state = _advance_clock_period(next_state, self.rng)
        return self.state

    def resolve_fourth_down(self, decision: FootballFourthDownAction) -> FootballMatchState:
        if not isinstance(decision, FootballFourthDownAction):
            raise ValueError("Fourth-down decision must be a FootballFourthDownAction.")
        if self.state.status is FootballMatchStatus.COMPLETED:
            raise ValueError("A completed match cannot accept new actions.")
        if self.state.awaited_action is not FootballAwaitedAction.FOURTH_DOWN_DECISION:
            raise ValueError("Fourth-down decisions are only legal on fourth down.")
        if self.state.down != 4:
            raise ValueError("Fourth-down decisions are only legal on fourth down.")

        if decision is FootballFourthDownAction.GO_FOR_IT:
            if self.rng.random() < min(0.78, 0.52 + (self.state.yards_to_go / 12.0)):
                gain = min(self.state.yards_to_go + self.rng.uniform(1.0, 4.0), 20.0)
                new_position = _clamp(self.state.offense_field_position + gain, 0.0, GOAL_LINE_YARDS)
                remaining = _drive_yards_remaining(new_position)
                next_state = replace(
                    self.state,
                    offense_field_position=new_position,
                    down=1,
                    yards_to_go=FIRST_DOWN_YARDS if remaining >= FIRST_DOWN_YARDS else remaining,
                    game_clock_seconds=max(0, self.state.game_clock_seconds - 15),
                    current_drive_defensive_scheme=self.state.current_drive_defensive_scheme,
                    awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
                )
                self.state = _advance_clock_period(next_state, self.rng)
                return self.state

            failed_position = _clamp(self.state.offense_field_position + min(self.state.yards_to_go - 0.5, -1.0), 0.0, GOAL_LINE_YARDS)
            next_state = replace(
                self.state,
                possession=_opponent(self.state.possession),
                down=1,
                yards_to_go=FIRST_DOWN_YARDS,
                offense_field_position=100.0 - failed_position,
                game_clock_seconds=max(0, self.state.game_clock_seconds - 15),
                awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                current_drive_defensive_scheme=None,
            )
            self.state = _advance_clock_period(next_state, self.rng)
            return self.state

        if decision is FootballFourthDownAction.PUNT:
            next_state = replace(
                self.state,
                possession=_opponent(self.state.possession),
                down=1,
                yards_to_go=FIRST_DOWN_YARDS,
                offense_field_position=25.0,
                game_clock_seconds=max(0, self.state.game_clock_seconds - 18),
                awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                current_drive_defensive_scheme=None,
            )
            self.state = _advance_clock_period(next_state, self.rng)
            return self.state

        if decision is FootballFourthDownAction.FIELD_GOAL:
            distance = field_goal_distance_for_position(self.state.offense_field_position)
            chance = field_goal_success_probability(distance)
            if self.rng.random() < chance:
                next_scores = [self.state.team_a_score, self.state.team_b_score]
                if self.state.possession is FootballTeamSide.TEAM_A:
                    next_scores[0] += 3
                else:
                    next_scores[1] += 3
                next_state = replace(
                    self.state,
                    team_a_score=next_scores[0],
                    team_b_score=next_scores[1],
                    possession=_opponent(self.state.possession),
                    down=1,
                    yards_to_go=FIRST_DOWN_YARDS,
                    offense_field_position=25.0,
                    game_clock_seconds=max(0, self.state.game_clock_seconds - 20),
                    awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                    current_drive_defensive_scheme=None,
                )
                self.state = _advance_clock_period(next_state, self.rng)
                if self.state.status is FootballMatchStatus.COMPLETED:
                    return self.state
                return self.state

            next_state = replace(
                self.state,
                possession=_opponent(self.state.possession),
                down=1,
                yards_to_go=FIRST_DOWN_YARDS,
                offense_field_position=25.0,
                game_clock_seconds=max(0, self.state.game_clock_seconds - 18),
                awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
                current_drive_defensive_scheme=None,
            )
            self.state = _advance_clock_period(next_state, self.rng)
            return self.state

        raise ValueError(f"Unsupported fourth-down choice: {decision!r}")


def select_defensive_scheme(state: FootballMatchState, scheme: DefensiveSchemeAction) -> FootballMatchState:
    return FootballMatchSimulator(state).select_defensive_scheme(scheme)


def resolve_offensive_play(state: FootballMatchState, play: OffensivePlayAction) -> FootballMatchState:
    return FootballMatchSimulator(state).resolve_offensive_play(play)


def resolve_fourth_down(state: FootballMatchState, decision: FootballFourthDownAction) -> FootballMatchState:
    return FootballMatchSimulator(state).resolve_fourth_down(decision)
