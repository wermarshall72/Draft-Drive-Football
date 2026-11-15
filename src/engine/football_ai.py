"""Deterministic local opponent generation and action selection."""

from __future__ import annotations

import random
from enum import Enum

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardCopy,
    FootballDeckState,
    FootballConversionAction,
    FootballCoach,
    FootballFourthDownAction,
    FootballMatchState,
    FootballMatchStatus,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
    FootballTeamSide,
    OffensivePlayAction,
    matchup_for_scheme,
)
from src.engine.football_coaches import COACH_PAIR_OFFERS
from src.engine.football_player_catalog import (
    PLAYER_BASE_POWER,
    PLAYER_BASE_STAMINA,
    PLAYER_BASE_VOLATILITY,
    player_from_type,
    player_type_offer,
)
from src.engine.football_simulator import (
    calculate_match_play_estimate,
    field_goal_distance_for_position,
    field_goal_success_probability,
)
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
    starting_defensive_deck,
    starting_offensive_deck,
)
from src.engine.football_coaches import coaches_for_assignment
from src.engine.football_player_catalog import player_contribution_modifier


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
        """Create a catalog-based roster with the existing difficulty offset.

        Easy, Standard, and Hard apply named offsets of -0.5, 0, and +0.5.
        """
        power_adjustment = {
            FootballAIDifficulty.EASY: EASY_POWER_ADJUSTMENT,
            FootballAIDifficulty.STANDARD: STANDARD_POWER_ADJUSTMENT,
            FootballAIDifficulty.HARD: HARD_POWER_ADJUSTMENT,
        }[self.difficulty]
        coach_pair = self._rng.choice(COACH_PAIR_OFFERS)
        players = {}
        for position in FootballPosition:
            offer = player_type_offer(position, self._rng)
            selected_type = self._rng.choice(offer)
            players[position] = player_from_type(
                selected_type,
                name=f"{self.team_name} {selected_type.name}",
                power=PLAYER_BASE_POWER + power_adjustment,
                volatility=PLAYER_BASE_VOLATILITY,
                stamina=PLAYER_BASE_STAMINA,
            )
        return FootballRoster(
            team_name=self.team_name,
            players=players,
            coach=FootballCoach(
                f"{coach_pair.offense.name} / {coach_pair.defense.name}"
            ),
            special_teams=FootballSpecialTeams(f"{self.team_name} Special Teams"),
            coach_assignment=coach_pair.assignment,
        )

    def generate_opponent_decks(
        self, game_number: int, roster: FootballRoster
    ) -> tuple[tuple[FootballCardCopy, ...], tuple[FootballCardCopy, ...]]:
        """Return deterministic run decks using an RNG separate from AI decisions."""
        if isinstance(game_number, bool) or not isinstance(game_number, int) or game_number < 1:
            raise ValueError("AI deck game number must be a positive integer.")
        if not isinstance(roster, FootballRoster):
            raise ValueError("AI deck generation requires a FootballRoster.")
        rng = random.Random(self.seed ^ (game_number * 0x9E3779B1))
        extra_count = min(
            {
                FootballAIDifficulty.EASY: 2,
                FootballAIDifficulty.STANDARD: 3,
                FootballAIDifficulty.HARD: 4,
            }[self.difficulty],
            1 + (game_number - 1) // 3,
        )
        offense, defense = coaches_for_assignment(roster.coach_assignment)
        offense_cards = list(starting_offensive_deck(f"ai:{game_number}"))
        defense_cards = list(starting_defensive_deck(f"ai:{game_number}"))

        def weighted_choice(definitions, *, is_offense: bool):
            scored = []
            for definition in definitions:
                positions = definition.contributors
                players = tuple(roster.players[position] for position in positions)
                coach = offense if is_offense else defense
                strength = sum(
                    player.power
                    * player_contribution_modifier(
                        player,
                        players,
                        coach.position_modifiers[player.position]
                        if coach is not None
                        else 0.0,
                    )
                    for player in players
                )
                scored.append((strength, definition))
            scored.sort(key=lambda item: item[0], reverse=True)
            pool_size = (
                len(scored)
                if self.difficulty is FootballAIDifficulty.EASY
                else min(5, len(scored))
                if self.difficulty is FootballAIDifficulty.STANDARD
                else min(3, len(scored))
            )
            return rng.choice(scored[:pool_size])[1]

        for index in range(extra_count):
            play = weighted_choice(
                tuple(OFFENSIVE_PLAY_CATALOG.values()),
                is_offense=True,
            )
            scheme = weighted_choice(
                tuple(DEFENSIVE_SCHEME_CATALOG.values()),
                is_offense=False,
            )
            offense_cards.append(
                FootballCardCopy(
                    f"ai:{game_number}:offense:purchased:{index + 1}",
                    play.card_id,
                )
            )
            defense_cards.append(
                FootballCardCopy(
                    f"ai:{game_number}:defense:purchased:{index + 1}",
                    scheme.card_id,
                )
            )
        return tuple(offense_cards), tuple(defense_cards)

    def choose_action(
        self, state: FootballMatchState
    ) -> (
        DefensiveSchemeAction
        | OffensivePlayAction
        | FootballFourthDownAction
        | FootballConversionAction
    ):
        """Select an action for this AI without changing the supplied match state."""
        if not isinstance(state, FootballMatchState):
            raise ValueError("AI action selection requires a FootballMatchState.")
        if (
            state.status is not FootballMatchStatus.IN_PROGRESS
            or (
                state.game_clock_seconds == 0
                and state.awaited_action is not FootballAwaitedAction.CONVERSION
            )
        ):
            raise ValueError("AI cannot act after the match or period clock has ended.")

        awaited_action = state.awaited_action
        if awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME:
            if state.possession is self.team_side:
                raise ValueError("AI cannot choose a defensive scheme while on offense.")
            schemes = self._hand_schemes(state)
            if not schemes:
                return DefensiveSchemeAction.RB_RUN
            if self.difficulty is FootballAIDifficulty.EASY:
                return self._rng.choice(schemes)
            return self._choose_defensive_scheme(state, schemes)

        if awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY:
            if state.possession is not self.team_side:
                raise ValueError("AI cannot choose an offensive play while on defense.")
            plays = self._hand_plays(state)
            if not plays:
                return OffensivePlayAction.RB_RUN
            if self.difficulty is FootballAIDifficulty.EASY:
                return self._rng.choice(plays)
            return self._choose_offensive_play(state, plays)

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

        if awaited_action is FootballAwaitedAction.CONVERSION:
            if state.possession is not self.team_side:
                raise ValueError("AI cannot choose a conversion for the other team.")
            margin = self._score_margin(state)
            if state.period >= 2 and margin in (-2, -1):
                return FootballConversionAction.TWO_POINT
            return FootballConversionAction.EXTRA_POINT

        raise ValueError(f"AI cannot act while awaiting {awaited_action!r}.")

    def _hand_plays(self, state: FootballMatchState) -> tuple[OffensivePlayAction, ...]:
        deck = self._deck_for_state(state, offensive=True)
        return tuple(OFFENSIVE_PLAY_CATALOG[card.card_id].action for card in deck.hand)

    def _hand_schemes(self, state: FootballMatchState) -> tuple[DefensiveSchemeAction, ...]:
        deck = self._deck_for_state(state, offensive=False)
        return tuple(DEFENSIVE_SCHEME_CATALOG[card.card_id].action for card in deck.hand)

    def choose_conversion_card(self, state: FootballMatchState) -> str | None:
        if (
            state.awaited_action is not FootballAwaitedAction.CONVERSION
            or state.conversion_team is not self.team_side
            or state.possession is not self.team_side
        ):
            raise ValueError("AI can choose a card only for its own conversion.")
        deck = self._deck_for_state(state, offensive=True)
        if not deck.hand:
            return None
        plays = tuple(OFFENSIVE_PLAY_CATALOG[card.card_id].action for card in deck.hand)
        play = (
            self._rng.choice(plays)
            if self.difficulty is FootballAIDifficulty.EASY
            else self._choose_offensive_play(state, plays)
        )
        return next(
            card.copy_id
            for card in deck.hand
            if OFFENSIVE_PLAY_CATALOG[card.card_id].action is play
        )

    def _deck_for_state(
        self, state: FootballMatchState, *, offensive: bool
    ) -> FootballDeckState:
        group = "offense" if offensive else "defense"
        deck = getattr(state, f"{self.team_side.value}_{group}_deck")
        if not isinstance(deck, FootballDeckState):
            raise ValueError("AI requires initialized match decks.")
        return deck

    def _choose_offensive_play(
        self,
        state: FootballMatchState,
        plays: tuple[OffensivePlayAction, ...],
    ) -> OffensivePlayAction:
        if self.difficulty is FootballAIDifficulty.HARD:
            return max(
                plays,
                key=lambda play: self._hard_play_score(state, play),
            )
        return max(
            plays,
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
            OffensivePlayAction.QB_SNEAK: 1.0,
            OffensivePlayAction.JET_SWEEP: 0.9,
            OffensivePlayAction.QUICK_OUT: 0.6,
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
        scheme = state.current_drive_defensive_scheme
        if scheme is None:
            raise ValueError("Hard offensive evaluation requires the active defensive scheme.")
        estimate = calculate_match_play_estimate(
            state,
            play,
            scheme=scheme,
            offense_side=self.team_side,
            is_conversion=(
                state.awaited_action is FootballAwaitedAction.CONVERSION
            ),
        )
        probability = estimate.first_down_probability(state.yards_to_go)
        return (
            self._situational_play_score(state, play)
            + 1.2 * estimate.expected_yards
            + 8.0 * probability
            - 12.0 * estimate.turnover_probability
        )

    def _choose_defensive_scheme(
        self,
        state: FootballMatchState,
        schemes: tuple[DefensiveSchemeAction, ...],
    ) -> DefensiveSchemeAction:
        if self.difficulty is FootballAIDifficulty.STANDARD:
            return max(
                schemes,
                key=lambda scheme: self._likely_offensive_play_score(state, scheme),
            )

        offense = self._roster_for_side(state, self._opponent(self.team_side))
        defense = self._roster_for_side(state, self.team_side)
        return max(
            schemes,
            key=lambda scheme: self._hard_defensive_scheme_score(
                state, scheme, offense, defense
            ),
        )

    def _likely_offensive_play_score(
        self, state: FootballMatchState, scheme: DefensiveSchemeAction
    ) -> float:
        _, counters = matchup_for_scheme(scheme)
        if scheme not in tuple(DefensiveSchemeAction)[:6]:
            return max(
                self._situational_play_score(state, play) for play in counters
            )
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
        _, counters = matchup_for_scheme(scheme)
        if not counters:
            return self._likely_offensive_play_score(state, scheme)
        play = max(
            counters,
            key=lambda action: self._situational_play_score(state, action),
        )
        estimate = calculate_match_play_estimate(
            state,
            play,
            scheme=scheme,
            offense_side=self._opponent(self.team_side),
        )
        return (
            self._likely_offensive_play_score(state, scheme)
            - 1.2 * estimate.expected_yards
            - 8.0 * estimate.first_down_probability(state.yards_to_go)
            + 12.0 * estimate.turnover_probability
        )

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
