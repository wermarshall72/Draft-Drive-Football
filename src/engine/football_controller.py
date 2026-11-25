"""Framework-independent orchestration for an interactive football run."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from src.engine.football import (
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballDeckState,
    FootballCoachUpgradeKind,
    FootballConversionAction,
    FootballFourthDownAction,
    FootballMatchState,
    FootballMatchStatus,
    FootballPlayer,
    FootballPosition,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_coaches import FootballCoachPair
from src.engine.football_appearance import FootballPlayerAppearance, POSITION_ART
from src.engine.football_ai import FootballAI, FootballAIDifficulty
from src.engine.football_shop import (
    FootballShop,
    FootballShopCard,
    FootballShopSection,
    FootballShopState,
    FootballUpgrade,
)
from src.engine.football_simulator import (
    FootballMatchSimulator,
    REGULATION_PERIOD_SECONDS,
)
from src.engine.save_data import (
    UnsupportedSave,
    build,
    enum_value,
    required,
    items,
    optional,
    rng_from_data,
    rng_to_data,
)
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
    OFFENSIVE_PLAY = "offensive_play"
    DEFENSIVE_SCHEME = "defensive_scheme"
    FOURTH_DOWN = "fourth_down"
    CONVERSION = "conversion"
    CHALLENGE = "challenge"
    GREEN_DOG = "green_dog"


class FootballSeasonOutcome(str, Enum):
    WIN = "W"
    LOSS = "L"
    BYE = "BYE"


@dataclass(frozen=True)
class FootballSeasonGame:
    """Read-only record of one scheduled game: a played result or a Bye Week skip."""

    game_number: int
    outcome: FootballSeasonOutcome
    team_score: int | None = None
    opponent_score: int | None = None
    overtime: bool = False


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
    games_played: int = 0
    skipped_games: tuple[int, ...] = ()
    transition_message: str | None = None
    player_appearances: Mapping[FootballPosition, FootballPlayerAppearance] = field(
        default_factory=lambda: MappingProxyType({})
    )
    drafted_players: Mapping[FootballPosition, FootballPlayer] = field(
        default_factory=lambda: MappingProxyType({})
    )
    challenge_available: bool = False
    season_history: tuple[FootballSeasonGame, ...] = ()


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
        self._games_played = 0
        self._skipped_games: list[int] = []
        self._season_history: list[FootballSeasonGame] = []
        self._transition_message: str | None = None
        self._challenge_prompt = False
        self._player_appearances: dict[FootballPosition, FootballPlayerAppearance] = {}
        self._drafted_players: dict[FootballPosition, FootballPlayer] = {}

    # -- save data -------------------------------------------------------------
    # Saved: every attribute set in ``__init__`` and the shop and simulator once
    # they exist, including all random streams (builder, shared shop RNG, AI,
    # match-seed stream, and the simulator's play and deck RNGs), so a restored
    # run continues exactly like an uninterrupted one. Rebuilt: the shop
    # catalogs, which come from the current game (or ``shop_catalogs``). The
    # team name is the builder's; difficulty and opponent name are the AI's.

    def to_save_data(self) -> dict[str, Any]:
        return {
            "builder": self._builder.to_save_data(),
            "shop_rng": rng_to_data(self._shop_rng),
            "ai": self._ai.to_save_data(),
            "match_seed_rng": rng_to_data(self._match_seed_rng),
            "difficulty": self._difficulty.value,
            "opponent_name": self._opponent_name,
            "shop": (
                self._shop.to_save_data(include_rng=False)
                if self._shop is not None else None
            ),
            "simulator": (
                self._simulator.to_save_data() if self._simulator is not None else None
            ),
            "phase": self._phase.value,
            "game_number": self._game_number,
            "wins": self._wins,
            "losses": self._losses,
            "games_played": self._games_played,
            "skipped_games": list(self._skipped_games),
            "season_history": [
                _season_game_to_save_data(game) for game in self._season_history
            ],
            "transition_message": self._transition_message,
            "challenge_prompt": self._challenge_prompt,
            "player_appearances": [
                _appearance_to_save_data(position, appearance)
                for position, appearance in self._player_appearances.items()
            ],
            "drafted_players": [
                player.to_save_data() for player in self._drafted_players.values()
            ],
        }

    @classmethod
    def from_save_data(
        cls,
        data: Any,
        *,
        shop_catalogs: Mapping[
            FootballShopSection, tuple[FootballShopCard, ...]
        ] | None = None,
    ) -> "FootballGameController":
        """Rebuild a run from ``to_save_data``; raises ``UnsupportedSave`` if it can't."""
        what = "Run"
        controller = cls.__new__(cls)
        controller._builder = FootballTeamBuilder.from_save_data(
            required(data, "builder", dict, what)
        )
        controller._shop_rng = rng_from_data(required(data, "shop_rng", list, what), "shop RNG")
        controller._shop_catalogs = (
            {section: tuple(cards) for section, cards in shop_catalogs.items()}
            if shop_catalogs is not None
            else None
        )
        controller._ai = FootballAI.from_save_data(required(data, "ai", dict, what))
        controller._match_seed_rng = rng_from_data(
            required(data, "match_seed_rng", list, what), "match-seed RNG"
        )
        controller._difficulty = enum_value(
            FootballAIDifficulty, required(data, "difficulty", str, what), "difficulty"
        )
        controller._opponent_name = required(data, "opponent_name", str, what)
        shop = optional(data, "shop", dict, what)
        controller._shop = (
            FootballShop.from_save_data(
                shop, rng=controller._shop_rng, catalogs=controller._shop_catalogs
            )
            if shop is not None else None
        )
        simulator = optional(data, "simulator", dict, what)
        controller._simulator = (
            FootballMatchSimulator.from_save_data(simulator) if simulator is not None else None
        )
        controller._phase = enum_value(
            FootballRunPhase, required(data, "phase", str, what), "run phase"
        )
        controller._game_number = required(data, "game_number", int, what)
        controller._wins = required(data, "wins", int, what)
        controller._losses = required(data, "losses", int, what)
        controller._games_played = required(data, "games_played", int, what)
        skipped = items(required(data, "skipped_games", list, what), "Skipped games")
        if any(isinstance(game, bool) or not isinstance(game, int) for game in skipped):
            raise UnsupportedSave("Skipped games must be game numbers.")
        controller._skipped_games = list(skipped)
        controller._season_history = [
            _season_game_from_save_data(item)
            for item in items(required(data, "season_history", list, what), "Season history")
        ]
        controller._transition_message = optional(data, "transition_message", str, what)
        controller._challenge_prompt = required(data, "challenge_prompt", bool, what)
        controller._player_appearances = dict(
            _appearance_from_save_data(item)
            for item in items(
                required(data, "player_appearances", list, what), "Player appearances"
            )
        )
        drafted = [
            FootballPlayer.from_save_data(item)
            for item in items(required(data, "drafted_players", list, what), "Drafted players")
        ]
        controller._drafted_players = {player.position: player for player in drafted}
        if controller._phase in (
            FootballRunPhase.PRE_MATCH_SHOP, FootballRunPhase.READY_FOR_NEXT_GAME,
        ) and controller._shop is None:
            raise UnsupportedSave("A run past the draft must have a shop.")
        if controller._phase is FootballRunPhase.MATCH and controller._simulator is None:
            raise UnsupportedSave("A run in a match must have a match.")
        return controller

    @property
    def team_name(self) -> str:
        return self._builder.team_name

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
            games_played=self._games_played,
            skipped_games=tuple(self._skipped_games),
            transition_message=self._transition_message,
            player_appearances=MappingProxyType(dict(self._player_appearances)),
            drafted_players=MappingProxyType(dict(self._drafted_players)),
            challenge_available=(
                self._simulator.available_challenge_copy_id is not None
                if self._simulator is not None
                else False
            ),
            season_history=tuple(self._season_history),
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
        *,
        appearance: FootballPlayerAppearance | None = None,
    ) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.PLAYER_DRAFT)
        if appearance is not None:
            if not isinstance(appearance, FootballPlayerAppearance):
                raise ValueError("Appearance must be a FootballPlayerAppearance.")
            if not isinstance(position, FootballPosition) or appearance.asset_key != POSITION_ART[position]:
                raise ValueError("Appearance artwork must match the draft position.")
        player = self._builder.choose_player(position, choice)
        self._drafted_players[position] = player
        if appearance is not None:
            self._player_appearances[position] = appearance
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
        shop = self._require_shop()
        owned_before = {
            card.card_id for card in shop.state.owned_coach_upgrades
        }
        shop.buy_card(section, card_id)
        newly_owned = next(
            (
                card
                for card in shop.state.owned_coach_upgrades
                if card.card_id not in owned_before
            ),
            None,
        )
        if (
            newly_owned is not None
            and newly_owned.coach_upgrade_effect is not None
            and newly_owned.coach_upgrade_effect.kind
            is FootballCoachUpgradeKind.BYE_WEEK
        ):
            self._apply_bye_week()
        return self.state

    def remove_owned_card(self, copy_id: str) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.PRE_MATCH_SHOP)
        self._require_shop().remove_owned_card(copy_id)
        return self.state

    def cancel_card_removal(self) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.PRE_MATCH_SHOP)
        self._require_shop().cancel_card_removal()
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
        self._transition_message = None
        return self.state

    def enter_next_shop(self) -> FootballGameControllerState:
        self._require_phase(FootballRunPhase.READY_FOR_NEXT_GAME)
        self._require_shop().open_next_visit(self._game_number + 1)
        self._game_number += 1
        self._phase = FootballRunPhase.PRE_MATCH_SHOP
        return self.state

    def choose_offensive_play(
        self, action: OffensivePlayAction | str | None
    ) -> FootballGameControllerState:
        if (
            action is not None
            and not isinstance(action, OffensivePlayAction)
            and type(action) is not str
        ):
            raise ValueError("Action must be an OffensivePlayAction or card copy id.")
        self._require_decision(FootballHumanDecision.OFFENSIVE_PLAY)
        simulator = self._require_simulator()
        simulator.resolve_offensive_play(action)
        last_event = simulator.state.match_events[-1]
        result = last_event.play_result
        if (
            result is not None
            and (result.turnover or result.turnover_on_downs)
            and simulator.available_challenge_copy_id is not None
        ):
            self._challenge_prompt = True
            return self.state
        self._advance_match()
        return self.state

    def respond_to_challenge(self, accept: bool) -> FootballGameControllerState:
        if not isinstance(accept, bool):
            raise ValueError("Challenge response must be a boolean.")
        self._require_decision(FootballHumanDecision.CHALLENGE)
        simulator = self._require_simulator()
        if accept:
            copy_id = simulator.available_challenge_copy_id
            if copy_id is None:
                raise RuntimeError("The available Challenge card is no longer in hand.")
            simulator.resolve_bonus_card(copy_id)
        else:
            simulator.decline_challenge()
        self._challenge_prompt = False
        self._advance_match()
        return self.state

    def challenge_touchdown(self) -> FootballGameControllerState:
        self._require_decision(FootballHumanDecision.CONVERSION)
        simulator = self._require_simulator()
        copy_id = simulator.available_challenge_copy_id
        if copy_id is None:
            raise ValueError("No Challenge card is available for this conversion.")
        simulator.resolve_bonus_card(copy_id)
        self._advance_match()
        return self.state

    def choose_defensive_scheme(
        self, action: DefensiveSchemeAction | str | None
    ) -> FootballGameControllerState:
        if (
            action is not None
            and not isinstance(action, DefensiveSchemeAction)
            and type(action) is not str
        ):
            raise ValueError("Action must be a DefensiveSchemeAction or card copy id.")
        self._require_decision(FootballHumanDecision.DEFENSIVE_SCHEME)
        self._require_simulator().select_defensive_scheme(action)
        self._advance_match()
        return self.state

    def respond_to_green_dog(
        self, selection: str | DefensiveSchemeAction | None
    ) -> FootballGameControllerState:
        """Swap the active scheme for a hand scheme (copy id or scheme), or decline (None)."""
        if (
            selection is not None
            and not isinstance(selection, DefensiveSchemeAction)
            and type(selection) is not str
        ):
            raise ValueError("Green Dog selection must be a scheme card copy id, scheme, or None.")
        self._require_decision(FootballHumanDecision.GREEN_DOG)
        self._require_simulator().resolve_green_dog(selection)
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

    def choose_conversion(
        self,
        action: FootballConversionAction,
        play: OffensivePlayAction | str | None = None,
    ) -> FootballGameControllerState:
        if not isinstance(action, FootballConversionAction):
            raise ValueError("Action must be a FootballConversionAction.")
        if (
            play is not None
            and not isinstance(play, OffensivePlayAction)
            and type(play) is not str
        ):
            raise ValueError("Play must be an OffensivePlayAction or card copy id.")
        self._require_decision(FootballHumanDecision.CONVERSION)
        self._require_simulator().resolve_conversion(action, play)
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
        opponent_offense, opponent_defense = self._ai.generate_opponent_decks(
            self._game_number,
            opponent,
        )
        match_seed = self._match_seed_rng.getrandbits(64)
        match_state = FootballMatchState(
            team_a=self._shop.match_roster(),
            team_b=opponent,
            random_seed=match_seed,
            team_a_score=0,
            team_b_score=0,
            possession=self.OPENING_POSSESSION,
            down=1,
            yards_to_go=10.0,
            offense_field_position=25.0,
            game_clock_seconds=REGULATION_PERIOD_SECONDS,
            period=1,
            awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
            opening_possession=self.OPENING_POSSESSION,
            team_a_offense_deck=FootballDeckState(self._require_shop().offensive_deck),
            team_a_defense_deck=FootballDeckState(self._require_shop().defensive_deck),
            team_b_offense_deck=FootballDeckState(opponent_offense),
            team_b_defense_deck=FootballDeckState(opponent_defense),
            team_a_coach_upgrades=tuple(
                card.coach_upgrade_effect
                for card in self._require_shop().state.owned_coach_upgrades
                if card.coach_upgrade_effect is not None
            ),
        )
        self._simulator = FootballMatchSimulator(match_state)
        self._challenge_prompt = False
        self._phase = FootballRunPhase.MATCH
        self._advance_match()

    def _advance_match(self) -> None:
        simulator = self._require_simulator()
        while simulator.state.status is FootballMatchStatus.IN_PROGRESS:
            if self._human_decision(simulator.state) is not None:
                return

            awaited = simulator.state.awaited_action
            if awaited is FootballAwaitedAction.GREEN_DOG_DECISION:
                simulator.resolve_green_dog(self._ai.choose_green_dog(simulator.state))
                continue
            action = self._ai.choose_action(simulator.state)
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
            elif awaited is FootballAwaitedAction.CONVERSION:
                if not isinstance(action, FootballConversionAction):
                    raise RuntimeError("AI returned an invalid conversion action.")
                play = (
                    self._ai.choose_conversion_card(simulator.state)
                    if action is FootballConversionAction.TWO_POINT
                    else None
                )
                simulator.resolve_conversion(action, play)
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
        self._require_shop().complete_match()
        if result.winner is FootballTeamSide.TEAM_A:
            self._wins += 1
        else:
            self._losses += 1
        self._games_played += 1
        self._season_history.append(
            FootballSeasonGame(
                self._game_number,
                FootballSeasonOutcome.WIN
                if result.winner is FootballTeamSide.TEAM_A
                else FootballSeasonOutcome.LOSS,
                result.team_a_score,
                result.team_b_score,
                overtime=match.period > 2,
            )
        )

        if self._losses >= self.LOSSES_TO_BE_FIRED:
            self._phase = FootballRunPhase.FIRED
        elif self._game_number == self.REGULAR_SEASON_GAMES:
            self._phase = FootballRunPhase.PLAYOFFS
        else:
            self._phase = FootballRunPhase.READY_FOR_NEXT_GAME

    def _apply_bye_week(self) -> None:
        scheduled_game = self._game_number
        shop = self._require_shop()
        if not shop.finished:
            raise RuntimeError("Bye Week must finish the current shop before advancing.")
        if scheduled_game in self._skipped_games:
            raise RuntimeError("A scheduled game cannot be skipped twice.")
        self._skipped_games.append(scheduled_game)
        self._season_history.append(
            FootballSeasonGame(scheduled_game, FootballSeasonOutcome.BYE)
        )
        if scheduled_game == self.REGULAR_SEASON_GAMES:
            self._phase = FootballRunPhase.PLAYOFFS
            self._transition_message = (
                "Bye Week skipped scheduled game 10 without a match result. "
                "The regular season is complete; you reached the playoffs marker. "
                "No playoff games are available yet."
            )
            return

        next_game = scheduled_game + 1
        shop.open_next_visit(next_game)
        self._game_number = next_game
        self._phase = FootballRunPhase.PRE_MATCH_SHOP
        self._transition_message = (
            f"Bye Week skipped scheduled game {scheduled_game} without a win or "
            f"loss. Next up: the shop before scheduled game {next_game}."
        )

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
        if self._challenge_prompt:
            return FootballHumanDecision.CHALLENGE

        if match.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME:
            if match.possession is FootballTeamSide.TEAM_B:
                return FootballHumanDecision.DEFENSIVE_SCHEME
        elif match.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY:
            if match.possession is FootballTeamSide.TEAM_A:
                return FootballHumanDecision.OFFENSIVE_PLAY
        elif match.awaited_action is FootballAwaitedAction.FOURTH_DOWN_DECISION:
            if match.possession is FootballTeamSide.TEAM_A:
                return FootballHumanDecision.FOURTH_DOWN
        elif match.awaited_action is FootballAwaitedAction.CONVERSION:
            if match.possession is FootballTeamSide.TEAM_A:
                return FootballHumanDecision.CONVERSION
        elif match.awaited_action is FootballAwaitedAction.GREEN_DOG_DECISION:
            if match.possession is FootballTeamSide.TEAM_B:
                return FootballHumanDecision.GREEN_DOG
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


def _season_game_to_save_data(game: FootballSeasonGame) -> dict[str, Any]:
    data: dict[str, Any] = {"game_number": game.game_number, "outcome": game.outcome.value}
    if game.outcome is not FootballSeasonOutcome.BYE:
        data.update(
            team_score=game.team_score,
            opponent_score=game.opponent_score,
            overtime=game.overtime,
        )
    return data


def _season_game_from_save_data(data: Any) -> FootballSeasonGame:
    what = "Season game"
    return FootballSeasonGame(
        game_number=required(data, "game_number", int, what),
        outcome=enum_value(
            FootballSeasonOutcome, required(data, "outcome", str, what), "season outcome"
        ),
        team_score=optional(data, "team_score", int, what),
        opponent_score=optional(data, "opponent_score", int, what),
        overtime=optional(data, "overtime", bool, what, False),
    )


def _appearance_to_save_data(
    position: FootballPosition, appearance: FootballPlayerAppearance
) -> dict[str, Any]:
    return {
        "position": position.value,
        "asset_key": appearance.asset_key,
        "skin": list(appearance.skin),
        "primary": list(appearance.primary),
        "secondary": list(appearance.secondary),
    }


def _appearance_from_save_data(
    data: Any,
) -> tuple[FootballPosition, FootballPlayerAppearance]:
    what = "Player appearance"
    position = enum_value(FootballPosition, required(data, "position", str, what), "position")

    def color(key: str) -> tuple[int, ...]:
        return tuple(items(required(data, key, list, what), f"Appearance {key}"))

    appearance = build("player appearance", lambda: FootballPlayerAppearance(
        asset_key=required(data, "asset_key", str, what),
        skin=color("skin"),
        primary=color("primary"),
        secondary=color("secondary"),
    ))
    if appearance.asset_key != POSITION_ART[position]:
        raise UnsupportedSave("Appearance artwork must match its position.")
    return position, appearance
