"""Deterministic local opponent generation and action selection."""

from __future__ import annotations

import random
from enum import Enum

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
    field_goal_distance_for_position,
    field_goal_success_probability,
    matchup_for_play,
)


class FootballAIDifficulty(str, Enum):
    EASY = "easy"
    STANDARD = "standard"
    HARD = "hard"


# Small additive power offsets applied after generating each player's base power.
EASY_POWER_ADJUSTMENT = -0.5
STANDARD_POWER_ADJUSTMENT = 0.0
HARD_POWER_ADJUSTMENT = 0.5

AI_MIN_FIELD_GOAL_SUCCESS_PROBABILITY = 0.5
LATE_GAME_SECONDS = 120

_PLAY_ACTIONS = tuple(OffensivePlayAction)
_SCHEME_ACTIONS = tuple(DefensiveSchemeAction)


class FootballAI:
    """One local AI identity with a persistent, explicitly seeded random stream.

    Generate a roster once per AI instance before asking for Easy choices if
    identical action sequences across instances are required. The stream is
    never shared with or re-seeded from a match simulator.
    """

    def __init__(
        self,
        team_side: FootballTeamSide,
        difficulty: FootballAIDifficulty,
        seed: int,
        team_name: str = "Local AI",
    ) -> None:
        if not isinstance(team_side, FootballTeamSide):
            raise ValueError("AI team side must be a FootballTeamSide.")
        if not isinstance(difficulty, FootballAIDifficulty):
            raise ValueError("AI difficulty must be a FootballAIDifficulty.")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("AI seed must be an integer.")
        if not isinstance(team_name, str) or not team_name.strip():
            raise ValueError("AI team name must be a non-empty string.")

        self.team_side = team_side
        self.difficulty = difficulty
        self.seed = seed
        self.team_name = team_name
        self._rng = random.Random(seed)

    def generate_opponent_roster(self) -> FootballRoster:
        """Create a complete roster with base power 8-12 and a difficulty offset.

        Easy, Standard, and Hard apply named offsets of -0.5, 0, and +0.5.
        """
        power_adjustment = {
            FootballAIDifficulty.EASY: EASY_POWER_ADJUSTMENT,
            FootballAIDifficulty.STANDARD: STANDARD_POWER_ADJUSTMENT,
            FootballAIDifficulty.HARD: HARD_POWER_ADJUSTMENT,
        }[self.difficulty]
        players = {
            position: FootballPlayer(
                name=f"{self.team_name} {position.value}",
                position=position,
                power=self._rng.uniform(8.0, 12.0) + power_adjustment,
                volatility=self._rng.uniform(0.1, 0.4),
                stamina=self._rng.uniform(0.65, 1.0),
            )
            for position in FootballPosition
        }
        return FootballRoster(
            team_name=self.team_name,
            players=players,
            coach=FootballCoach(f"{self.team_name} Coach"),
            special_teams=FootballSpecialTeams(f"{self.team_name} Special Teams"),
        )

    def choose_action(
        self, state: FootballMatchState
    ) -> DefensiveSchemeAction | OffensivePlayAction | FootballFourthDownAction:
        """Select an action for this AI without changing the supplied match state."""
        if not isinstance(state, FootballMatchState):
            raise ValueError("AI action selection requires a FootballMatchState.")
        if (
            state.status is not FootballMatchStatus.IN_PROGRESS
            or state.game_clock_seconds == 0
        ):
            raise ValueError("AI cannot act after the match or period clock has ended.")

        awaited_action = state.awaited_action
        if awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME:
            if state.possession is self.team_side:
                raise ValueError("AI cannot choose a defensive scheme while on offense.")
            if self.difficulty is FootballAIDifficulty.EASY:
                return self._rng.choice(_SCHEME_ACTIONS)
            return self._choose_defensive_scheme(state)

        if awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY:
            if state.possession is not self.team_side:
                raise ValueError("AI cannot choose an offensive play while on defense.")
            if self.difficulty is FootballAIDifficulty.EASY:
                return self._rng.choice(_PLAY_ACTIONS)
            return self._choose_offensive_play(state)

        if awaited_action is FootballAwaitedAction.FOURTH_DOWN_DECISION:
            if state.possession is not self.team_side:
                raise ValueError("AI cannot make a fourth-down decision while on defense.")
            if state.down != 4:
                raise ValueError("A fourth-down decision must be awaited on fourth down.")
            if self.difficulty is FootballAIDifficulty.EASY:
                actions = [FootballFourthDownAction.GO_FOR_IT, FootballFourthDownAction.PUNT]
                distance = field_goal_distance_for_position(
                    state.offense_field_position
                )
                if (
                    field_goal_success_probability(distance)
                    >= AI_MIN_FIELD_GOAL_SUCCESS_PROBABILITY
                ):
                    actions.append(FootballFourthDownAction.FIELD_GOAL)
                return self._rng.choice(actions)
            return self._choose_fourth_down(state)

        raise ValueError(f"AI cannot act while awaiting {awaited_action!r}.")

    def _choose_offensive_play(self, state: FootballMatchState) -> OffensivePlayAction:
        if self.difficulty is FootballAIDifficulty.HARD:
            return max(
                _PLAY_ACTIONS,
                key=lambda play: self._hard_play_score(state, play),
            )
        return max(
            _PLAY_ACTIONS,
            key=lambda play: self._situational_play_score(state, play),
        )

    def _situational_play_score(
        self, state: FootballMatchState, play: OffensivePlayAction
    ) -> float:
        scores = {
            OffensivePlayAction.RB_RUN: 1.0,
            OffensivePlayAction.SCREEN_PASS: 0.4,
            OffensivePlayAction.PA_PASS: 0.2,
            OffensivePlayAction.SHORT_PASS: 0.8,
            OffensivePlayAction.MEDIUM_PASS: 0.3,
            OffensivePlayAction.DEEP_PASS: 0.1,
        }
        if state.yards_to_go >= 8:
            scores[OffensivePlayAction.MEDIUM_PASS] += 1.4
            scores[OffensivePlayAction.DEEP_PASS] += 1.2
            scores[OffensivePlayAction.RB_RUN] -= 0.8
        elif state.yards_to_go <= 2:
            scores[OffensivePlayAction.RB_RUN] += 1.0
            scores[OffensivePlayAction.SHORT_PASS] += 0.5
            scores[OffensivePlayAction.DEEP_PASS] -= 1.0

        if state.down >= 3 and state.yards_to_go >= 6:
            scores[OffensivePlayAction.MEDIUM_PASS] += 0.8
            scores[OffensivePlayAction.DEEP_PASS] += 0.8
        if 100.0 - state.offense_field_position <= 10:
            scores[OffensivePlayAction.RB_RUN] += 0.8
            scores[OffensivePlayAction.SCREEN_PASS] += 0.4
            scores[OffensivePlayAction.DEEP_PASS] -= 0.8

        score_margin = self._score_margin(state)
        if self._is_late_game(state) and score_margin < 0:
            scores[OffensivePlayAction.DEEP_PASS] += 1.8
            scores[OffensivePlayAction.MEDIUM_PASS] += 1.0
        elif self._is_late_game(state) and score_margin > 0:
            scores[OffensivePlayAction.RB_RUN] += 1.0
            scores[OffensivePlayAction.DEEP_PASS] -= 0.8
        return scores[play]

    def _hard_play_score(
        self, state: FootballMatchState, play: OffensivePlayAction
    ) -> float:
        offense = self._roster_for_side(state, self.team_side)
        defense = self._roster_for_side(state, self._opponent(self.team_side))
        offensive_positions, defensive_positions = matchup_for_play(play)
        offense_power = sum(offense.players[position].power for position in offensive_positions)
        defense_power = sum(defense.players[position].power for position in defensive_positions)
        matchup_edge = (offense_power - defense_power) / max(
            1.0, offense_power + defense_power
        )
        return self._situational_play_score(state, play) + 5.0 * matchup_edge

    def _choose_defensive_scheme(self, state: FootballMatchState) -> DefensiveSchemeAction:
        if self.difficulty is FootballAIDifficulty.STANDARD:
            return max(
                _SCHEME_ACTIONS,
                key=lambda scheme: self._likely_offensive_play_score(state, scheme),
            )

        offense = self._roster_for_side(state, self._opponent(self.team_side))
        defense = self._roster_for_side(state, self.team_side)
        return max(
            _SCHEME_ACTIONS,
            key=lambda scheme: self._hard_defensive_scheme_score(
                state, scheme, offense, defense
            ),
        )

    def _likely_offensive_play_score(
        self, state: FootballMatchState, scheme: DefensiveSchemeAction
    ) -> float:
        # A scheme counters the play with the same enum value in the simulator.
        score = 1.0
        if state.yards_to_go <= 2:
            score += 1.8 if scheme in (
                DefensiveSchemeAction.RB_RUN,
                DefensiveSchemeAction.SHORT_PASS,
            ) else 0.0
        elif state.yards_to_go >= 8:
            score += 1.5 if scheme in (
                DefensiveSchemeAction.MEDIUM_PASS,
                DefensiveSchemeAction.DEEP_PASS,
            ) else 0.0
        if state.down >= 3 and state.yards_to_go >= 6:
            score += 1.2 if scheme in (
                DefensiveSchemeAction.MEDIUM_PASS,
                DefensiveSchemeAction.DEEP_PASS,
            ) else 0.0
        if 100.0 - state.offense_field_position <= 10:
            score += 1.0 if scheme in (
                DefensiveSchemeAction.RB_RUN,
                DefensiveSchemeAction.SCREEN_PASS,
            ) else 0.0
        return score

    def _hard_defensive_scheme_score(
        self,
        state: FootballMatchState,
        scheme: DefensiveSchemeAction,
        offense: FootballRoster,
        defense: FootballRoster,
    ) -> float:
        play = OffensivePlayAction(scheme.value)
        offensive_positions, defensive_positions = matchup_for_play(play)
        offense_power = sum(offense.players[position].power for position in offensive_positions)
        defense_power = sum(defense.players[position].power for position in defensive_positions)
        matchup_edge = (offense_power - defense_power) / max(
            1.0, offense_power + defense_power
        )
        return self._likely_offensive_play_score(state, scheme) + 5.0 * matchup_edge

    def _choose_fourth_down(
        self, state: FootballMatchState
    ) -> FootballFourthDownAction:
        field_goal_distance = field_goal_distance_for_position(
            state.offense_field_position
        )
        field_goal_is_reliable = (
            field_goal_success_probability(field_goal_distance)
            >= AI_MIN_FIELD_GOAL_SUCCESS_PROBABILITY
        )
        score_margin = self._score_margin(state)
        late = self._is_late_game(state)

        if late and score_margin < 0:
            if score_margin >= -3 and field_goal_is_reliable:
                return FootballFourthDownAction.FIELD_GOAL
            return FootballFourthDownAction.GO_FOR_IT
        if state.yards_to_go <= 2:
            return FootballFourthDownAction.GO_FOR_IT
        if (
            field_goal_is_reliable
            and state.yards_to_go >= 3
            and score_margin <= 3
        ):
            return FootballFourthDownAction.FIELD_GOAL
        if state.offense_field_position < 55.0:
            return FootballFourthDownAction.PUNT
        return FootballFourthDownAction.GO_FOR_IT

    @staticmethod
    def _roster_for_side(
        state: FootballMatchState, side: FootballTeamSide
    ) -> FootballRoster:
        return state.team_a if side is FootballTeamSide.TEAM_A else state.team_b

    @staticmethod
    def _opponent(side: FootballTeamSide) -> FootballTeamSide:
        return (
            FootballTeamSide.TEAM_B
            if side is FootballTeamSide.TEAM_A
            else FootballTeamSide.TEAM_A
        )

    def _score_margin(self, state: FootballMatchState) -> int:
        if self.team_side is FootballTeamSide.TEAM_A:
            return state.team_a_score - state.team_b_score
        return state.team_b_score - state.team_a_score

    @staticmethod
    def _is_late_game(state: FootballMatchState) -> bool:
        return state.period >= 3 or (
            state.period == 2 and state.game_clock_seconds <= LATE_GAME_SECONDS
        )
