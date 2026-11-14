"""Framework-independent orchestration for an interactive football run."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballFourthDownAction,
    FootballMatchState,
    FootballMatchStatus,
    FootballPosition,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_coaches import FootballCoachPair
from src.engine.football_ai import FootballAI, FootballAIDifficulty
from src.engine.football_shop import (
    FootballShop,
    FootballShopCard,
    FootballShopSection,
    FootballShopState,
    FootballUpgrade,
)
from src.engine.football_simulator import FootballMatchSimulator
from src.engine.football_team_builder import (
    FootballPlayerCandidate,
    FootballTeamBuilder,
    FootballTeamBuilderState,
)


class FootballRunPhase(str, Enum):
    COACH_DRAFT = "coach_draft"
    PLAYER_DRAFT = "player_draft"
    PRE_MATCH_SHOP = "pre_match_shop"
    MATCH = "match"
    READY_FOR_NEXT_GAME = "ready_for_next_game"
    PLAYOFFS = "playoffs"
    FIRED = "fired"


class FootballHumanDecision(str, Enum):
    CHOOSE_COACH = "choose_coach"
    DRAFT_PLAYER = "draft_player"
    SHOP = "shop"
    OPEN_NEXT_SHOP = "open_next_shop"
    START_NEXT_GAME = "open_next_shop"
    OFFENSIVE_PLAY = "offensive_play"
    DEFENSIVE_SCHEME = "defensive_scheme"
    FOURTH_DOWN = "fourth_down"


@dataclass(frozen=True)
class FootballGameControllerState:
    """Immutable view of run progress and the data needed by a future UI."""

    phase: FootballRunPhase
    team_builder: FootballTeamBuilderState
    shop: FootballShopState | None
    match: FootballMatchState | None
    human_decision: FootballHumanDecision | None
    opponent_name: str
    opponent_difficulty: FootballAIDifficulty
    selected_coach_pair: FootballCoachPair | None
    game_number: int
    wins: int
    losses: int


class FootballGameController:
    """Coordinate drafting, recurring shops, local AI, and regular-season games.

    Each random stream has its own seed: builder, shop, AI, and match. Team A
    is always the human roster and Team B is always the local AI roster.
    """

    REGULAR_SEASON_GAMES = 10
    LOSSES_TO_BE_FIRED = 3
    OPENING_POSSESSION = FootballTeamSide.TEAM_A

    def __init__(
        self,
        team_name: str,
        *,
        difficulty: FootballAIDifficulty,
        builder_seed: int,
        shop_seed: int,
        ai_seed: int,
        match_seed: int,
        opponent_name: str = "Local AI",
        shop_catalogs: Mapping[
            FootballShopSection, tuple[FootballShopCard, ...]
        ] | None = None,
    ) -> None:
        if not isinstance(team_name, str) or not team_name.strip():
            raise ValueError("Team name must be a non-empty string.")
        if not isinstance(opponent_name, str) or not opponent_name.strip():
            raise ValueError("Opponent name must be a non-empty string.")
        if opponent_name.strip() == team_name.strip():
            raise ValueError("Opponent name must differ from the player's team name.")
        if not isinstance(difficulty, FootballAIDifficulty):
            raise ValueError("Difficulty must be a FootballAIDifficulty.")
        for seed_name, seed in (
            ("Builder", builder_seed),
            ("Shop", shop_seed),
            ("AI", ai_seed),
            ("Match", match_seed),
        ):
            if isinstance(seed, bool) or not isinstance(seed, int):
                raise ValueError(f"{seed_name} seed must be an integer.")

        self._builder = FootballTeamBuilder(team_name, builder_seed)
        self._shop_rng = random.Random(shop_seed)
        self._shop_catalogs = (
            {
                section: tuple(cards)
                for section, cards in shop_catalogs.items()
            }
            if shop_catalogs is not None
            else None
        )
        self._ai = FootballAI(
            FootballTeamSide.TEAM_B,
            difficulty,
            ai_seed,
            opponent_name,
        )
        self._match_seed_rng = random.Random(match_seed)
        self._difficulty = difficulty
        self._opponent_name = opponent_name
        self._shop: FootballShop | None = None
        self._simulator: FootballMatchSimulator | None = None
        self._phase = FootballRunPhase.COACH_DRAFT
        self._game_number = 1
        self._wins = 0
        self._losses = 0

    @property
    def state(self) -> FootballGameControllerState:
        match = self._simulator.state if self._simulator is not None else None
        return FootballGameControllerState(
            phase=self._phase,
            team_builder=self._builder.state,
            shop=self._shop.state if self._shop is not None else None,
            match=match,
            human_decision=self._human_decision(match),
            opponent_name=self._opponent_name,
            opponent_difficulty=self._difficulty,
            selected_coach_pair=self._builder.selected_coach_pair,
            game_number=self._game_number,
            wins=self._wins,
            losses=self._losses,
        )

    def choose_coach(self, choice: FootballCoachPair | int) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.COACH_DRAFT)
        self._builder.choose_coach(choice)
        self._phase = FootballRunPhase.PLAYER_DRAFT
        return self.state

    def choose_player(
        self,
        position: FootballPosition,
        choice: FootballPlayerCandidate | int,
    ) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.PLAYER_DRAFT)
        self._builder.choose_player(position, choice)
        if self._builder.completed:
            self._shop = FootballShop(
                self._builder.build_roster(),
                rng=self._shop_rng,
                catalogs=self._shop_catalogs,
                game_number=self._game_number,
            )
            self._phase = FootballRunPhase.PRE_MATCH_SHOP
        return self.state

    def buy_upgrade(
        self, upgrade: FootballUpgrade | int
    ) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.PRE_MATCH_SHOP)
        self._require_shop().buy_upgrade(upgrade)
        return self.state

    def buy_shop_card(
        self,
        section: FootballShopSection,
        card_id: str | int,
    ) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.PRE_MATCH_SHOP)
        self._require_shop().buy_card(section, card_id)
        return self.state

    def unlock_shop_slot(
        self,
        section: FootballShopSection,
        slot_number: int,
    ) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.PRE_MATCH_SHOP)
        self._require_shop().unlock_slot(section, slot_number)
        return self.state

    def move_to_next_day(self) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.PRE_MATCH_SHOP)
        self._require_shop().move_to_next_day()
        return self.state

    def finish_shop(self) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.PRE_MATCH_SHOP)
        self._require_shop().finish()
        self._start_match()
        return self.state

    def enter_next_shop(self) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.READY_FOR_NEXT_GAME)
        self._require_shop().open_next_visit(self._game_number + 1)
        self._game_number += 1
        self._phase = FootballRunPhase.PRE_MATCH_SHOP
        return self.state

    def start_next_game(self) -> FootballGameControllerState:
        """Compatibility alias; the next game now requires a fresh shop first."""
        return self.enter_next_shop()

    def choose_offensive_play(
        self, action: OffensivePlayAction
    ) -> FootballGameControllerState:
        if not isinstance(action, OffensivePlayAction):
            raise ValueError("Action must be an OffensivePlayAction.")
        self._require_decision(FootballHumanDecision.OFFENSIVE_PLAY)
        self._require_simulator().resolve_offensive_play(action)
        self._advance_match()
        return self.state

    def choose_defensive_scheme(
        self, action: DefensiveSchemeAction
    ) -> FootballGameControllerState:
        if not isinstance(action, DefensiveSchemeAction):
            raise ValueError("Action must be a DefensiveSchemeAction.")
        self._require_decision(FootballHumanDecision.DEFENSIVE_SCHEME)
        self._require_simulator().select_defensive_scheme(action)
        self._advance_match()
        return self.state

    def choose_fourth_down(
        self, action: FootballFourthDownAction
    ) -> FootballGameControllerState:
        if not isinstance(action, FootballFourthDownAction):
            raise ValueError("Action must be a FootballFourthDownAction.")
        self._require_decision(FootballHumanDecision.FOURTH_DOWN)
        self._require_simulator().resolve_fourth_down(action)
        self._advance_match()
        return self.state

    def _start_match(self) -> None:
        if (
            self._shop is None
            or not self._shop.finished
            or self._shop.game_number != self._game_number
        ):
            raise ValueError("The pre-match shop must be finished before a match.")
        opponent = self._ai.generate_opponent_roster()
        match_seed = self._match_seed_rng.getrandbits(64)
        match_state = FootballMatchState(
            team_a=self._shop.roster,
            team_b=opponent,
            random_seed=match_seed,
            team_a_score=0,
            team_b_score=0,
            possession=self.OPENING_POSSESSION,
            down=1,
            yards_to_go=10.0,
            offense_field_position=25.0,
            game_clock_seconds=900,
            period=1,
            awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        )
        self._simulator = FootballMatchSimulator(match_state)
        self._phase = FootballRunPhase.MATCH
        self._advance_match()

    def _advance_match(self) -> None:
        simulator = self._require_simulator()
        while simulator.state.status is FootballMatchStatus.IN_PROGRESS:
            if self._human_decision(simulator.state) is not None:
                return

            action = self._ai.choose_action(simulator.state)
            awaited = simulator.state.awaited_action
            if awaited is FootballAwaitedAction.DEFENSIVE_SCHEME:
                if not isinstance(action, DefensiveSchemeAction):
                    raise RuntimeError("AI returned an invalid defensive-scheme action.")
                simulator.select_defensive_scheme(action)
            elif awaited is FootballAwaitedAction.OFFENSIVE_PLAY:
                if not isinstance(action, OffensivePlayAction):
                    raise RuntimeError("AI returned an invalid offensive-play action.")
                simulator.resolve_offensive_play(action)
            elif awaited is FootballAwaitedAction.FOURTH_DOWN_DECISION:
                if not isinstance(action, FootballFourthDownAction):
                    raise RuntimeError("AI returned an invalid fourth-down action.")
                simulator.resolve_fourth_down(action)
            else:
                raise RuntimeError(
                    f"AI cannot act while awaiting {simulator.state.awaited_action!r}."
                )

        self._record_match_result(simulator.state)

    def _record_match_result(self, match: FootballMatchState) -> None:
        if self._phase is not FootballRunPhase.MATCH:
            raise RuntimeError("A match result can only be recorded during a match.")
        result = match.final_result
        if result is None or not result.completed or result.winner is None:
            raise RuntimeError("A completed match must include a decisive result.")
        if result.winner is FootballTeamSide.TEAM_A:
            self._wins += 1
        else:
            self._losses += 1

        if self._losses >= self.LOSSES_TO_BE_FIRED:
            self._phase = FootballRunPhase.FIRED
        elif self._game_number == self.REGULAR_SEASON_GAMES:
            self._phase = FootballRunPhase.PLAYOFFS
        else:
            self._phase = FootballRunPhase.READY_FOR_NEXT_GAME

    def _human_decision(
        self, match: FootballMatchState | None
    ) -> FootballHumanDecision | None:
        if self._phase is FootballRunPhase.COACH_DRAFT:
            return FootballHumanDecision.CHOOSE_COACH
        if self._phase is FootballRunPhase.PLAYER_DRAFT:
            return FootballHumanDecision.DRAFT_PLAYER
        if self._phase is FootballRunPhase.PRE_MATCH_SHOP:
            return FootballHumanDecision.SHOP
        if self._phase is FootballRunPhase.READY_FOR_NEXT_GAME:
            return FootballHumanDecision.OPEN_NEXT_SHOP
        if self._phase is not FootballRunPhase.MATCH or match is None:
            return None

        if match.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME:
            if match.possession is FootballTeamSide.TEAM_B:
                return FootballHumanDecision.DEFENSIVE_SCHEME
        elif match.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY:
            if match.possession is FootballTeamSide.TEAM_A:
                return FootballHumanDecision.OFFENSIVE_PLAY
        elif match.awaited_action is FootballAwaitedAction.FOURTH_DOWN_DECISION:
            if match.possession is FootballTeamSide.TEAM_A:
                return FootballHumanDecision.FOURTH_DOWN
        return None

    def _require_phase(self, expected: FootballRunPhase) -> None:
        if self._phase is not expected:
            raise ValueError(
                f"Action is not valid during the {self._phase.value} phase."
            )

    def _require_decision(self, expected: FootballHumanDecision) -> None:
        actual = self._human_decision(
            self._simulator.state if self._simulator is not None else None
        )
        if actual is not expected:
            raise ValueError(
                f"Human decision {expected.value!r} is not currently required."
            )

    def _require_shop(self) -> FootballShop:
        if self._shop is None:
            raise RuntimeError("The pre-match shop is unavailable.")
        return self._shop

    def _require_simulator(self) -> FootballMatchSimulator:
        if self._simulator is None:
            raise RuntimeError("The match simulator is unavailable.")
        return self._simulator
