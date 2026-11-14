"""Seeded, framework-independent opening roster draft for interactive football."""

from __future__ import annotations

import random
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from src.engine.football import (
    FootballCoach,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
)
from src.engine.football_coaches import COACH_PAIR_OFFERS, FootballCoachPair
from src.engine.football_player_catalog import player_from_type, player_type_offer

PLAYER_DRAFT_ORDER = (
    FootballPosition.QB,
    FootballPosition.RB,
    FootballPosition.WR,
    FootballPosition.O_LINE,
    FootballPosition.D_LINE,
    FootballPosition.LINEBACKERS,
    FootballPosition.CORNERBACKS,
    FootballPosition.SAFETIES,
)

@dataclass(frozen=True)
class FootballPlayerCandidate:
    """An offered player plus a description limited to its simulated stats."""

    player: FootballPlayer
    description: str

    @property
    def name(self) -> str:
        return self.player.name

    @property
    def position(self) -> FootballPosition:
        return self.player.position


@dataclass(frozen=True)
class FootballTeamBuilderState:
    """Immutable view of the current coach/player choice and draft progress."""

    coach_offer: tuple[FootballCoachPair, ...]
    selected_coach_pair: FootballCoachPair | None
    required_position: FootballPosition | None
    current_offer: tuple[FootballCoachPair | FootballPlayerCandidate, ...]
    selected_players: Mapping[FootballPosition, FootballPlayer]
    completed: bool


class FootballTeamBuilder:
    """Draft a paired coaching staff and one player for each position."""

    def __init__(
        self,
        team_name: str,
        seed: int,
        special_teams: FootballSpecialTeams | None = None,
    ) -> None:
        if not isinstance(team_name, str) or not team_name.strip():
            raise ValueError("Team name must be a non-empty string.")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("Builder seed must be an integer.")
        if special_teams is not None and not isinstance(
            special_teams, FootballSpecialTeams
        ):
            raise ValueError("Special teams must be a FootballSpecialTeams object.")

        self.team_name = team_name
        self.seed = seed
        self._special_teams = (
            special_teams if special_teams is not None else FootballSpecialTeams()
        )
        self._rng = random.Random(seed)
        self._coach_offer = tuple(self._rng.sample(COACH_PAIR_OFFERS, 3))
        self._selected_coach_pair: FootballCoachPair | None = None
        self._selected_players: dict[FootballPosition, FootballPlayer] = {}
        self._required_position: FootballPosition | None = None
        self._current_offer: tuple[
            FootballCoachPair | FootballPlayerCandidate, ...
        ] = self._coach_offer
        self._roster: FootballRoster | None = None

    @property
    def coach_offer(self) -> tuple[FootballCoachPair, ...]:
        return self._coach_offer

    @property
    def selected_coach_pair(self) -> FootballCoachPair | None:
        return self._selected_coach_pair

    @property
    def required_position(self) -> FootballPosition | None:
        return self._required_position

    @property
    def current_offer(self) -> tuple[FootballCoachPair | FootballPlayerCandidate, ...]:
        return self._current_offer

    @property
    def completed(self) -> bool:
        return self._roster is not None

    @property
    def state(self) -> FootballTeamBuilderState:
        return FootballTeamBuilderState(
            coach_offer=self.coach_offer,
            selected_coach_pair=self._selected_coach_pair,
            required_position=self._required_position,
            current_offer=self._current_offer,
            selected_players=MappingProxyType(dict(self._selected_players)),
            completed=self.completed,
        )

    def choose_coach(self, choice: FootballCoachPair | int) -> FootballCoachPair:
        self._require_active()
        if self._selected_coach_pair is not None:
            raise ValueError("A coach has already been selected.")
        selected = self._offered_choice(choice, FootballCoachPair, self._current_offer)
        if not isinstance(selected, FootballCoachPair):
            raise ValueError("Current coach offer contains an invalid item.")
        coach_pair = selected
        self._selected_coach_pair = coach_pair
        self._required_position = PLAYER_DRAFT_ORDER[0]
        self._current_offer = self._player_offer(self._required_position)
        return coach_pair

    def choose_player(
        self, position: FootballPosition, choice: FootballPlayerCandidate | int
    ) -> FootballPlayer:
        self._require_active()
        if self._selected_coach_pair is None:
            raise ValueError("Choose a coach before drafting players.")
        if not isinstance(position, FootballPosition):
            raise ValueError("Draft position must be a FootballPosition.")
        if position is not self._required_position:
            raise ValueError(
                f"The next required position is {self._required_position.value}."
            )

        selected = self._offered_choice(
            choice, FootballPlayerCandidate, self._current_offer
        )
        if not isinstance(selected, FootballPlayerCandidate):
            raise ValueError("Current player offer contains an invalid item.")
        player = selected.player
        if player.position is not position:
            raise ValueError(f"Offered player must play {position.value}.")

        self._selected_players[position] = player
        next_index = len(self._selected_players)
        if next_index == len(PLAYER_DRAFT_ORDER):
            self._required_position = None
            self._current_offer = ()
            self._roster = FootballRoster(
                team_name=self.team_name,
                players=self._selected_players,
                coach=FootballCoach(
                    f"{self._selected_coach_pair.offense.name} / "
                    f"{self._selected_coach_pair.defense.name}"
                ),
                special_teams=self._special_teams,
                coach_assignment=self._selected_coach_pair.assignment,
            )
        else:
            self._required_position = PLAYER_DRAFT_ORDER[next_index]
            self._current_offer = self._player_offer(self._required_position)
        return player

    def build_roster(self) -> FootballRoster:
        if self._roster is None:
            raise ValueError("The roster is not complete.")
        return self._roster

    def _player_offer(
        self, position: FootballPosition
    ) -> tuple[FootballPlayerCandidate, ...]:
        return tuple(
            FootballPlayerCandidate(
                player=player_from_type(player_type),
                description=(
                    "No partner, partnership bonus, or perk."
                    if player_type.partner_position is None
                    else (
                        f"Partners with {player_type.partner_position.value}; "
                        f"+10% contribution when paired. Perk is planned and inactive."
                    )
                ),
            )
            for player_type in player_type_offer(position, self._rng)
        )

    @staticmethod
    def _offered_choice(
        choice: FootballCoachPair | FootballPlayerCandidate | int,
        expected_type: type[FootballCoachPair] | type[FootballPlayerCandidate],
        offer: tuple[FootballCoachPair | FootballPlayerCandidate, ...],
    ) -> FootballCoachPair | FootballPlayerCandidate:
        if isinstance(choice, bool):
            raise ValueError("Choice must be an offered item or a valid offer index.")
        if isinstance(choice, int):
            if not 0 <= choice < len(offer):
                raise ValueError("Offer index is out of range.")
            selected = offer[choice]
        elif isinstance(choice, expected_type):
            selected = next((item for item in offer if item is choice), None)
            if selected is None:
                raise ValueError("Choice was not included in the current offer.")
        else:
            raise ValueError("Choice must be an offered item or a valid offer index.")
        if not isinstance(selected, expected_type):
            raise ValueError("Choice has the wrong type for the current offer.")
        return selected

    def _require_active(self) -> None:
        if self.completed:
            raise ValueError("The team-building flow is already complete.")
