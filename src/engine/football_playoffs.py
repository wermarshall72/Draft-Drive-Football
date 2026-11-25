"""The eight-team, single-elimination playoff bracket that follows the regular season.

The human team is seeded by regular-season losses (0 -> #1, 1 -> #2, 2 -> #3),
so a Bye Week never costs a seed. The other seven seeds are local AI teams with
placeholder names. Round 1 pairs 1v8, 4v5, 3v6, and 2v7; winners meet in bracket
order. The human's games are real matches (scheduled games 11-13); every other
game in a round is decided by the bracket's own seeded RNG once the human's game
in that round is recorded, so the bracket fills in round by round.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.engine.save_data import (
    UnsupportedSave,
    enum_value,
    items,
    optional,
    required,
    rng_from_data,
    rng_to_data,
)

REGULAR_SEASON_GAMES = 10
PLAYOFF_TEAMS = 8
PLAYOFF_ROUNDS = 3
FINAL_GAME_NUMBER = REGULAR_SEASON_GAMES + PLAYOFF_ROUNDS

# Each playoff round adds this much opponent player power (round 1: +0.25 ...
# championship: +0.75) and one more extra deck card than the difficulty's cap.
PLAYOFF_POWER_STEP = 0.25
PLAYOFF_EXTRA_CARDS_PER_ROUND = 1

# Round-1 pairings (higher seed first) in bracket order; winners of games
# (0, 1) and (2, 3) meet in the semifinals.
FIRST_ROUND_PAIRS: tuple[tuple[int, int], ...] = ((1, 8), (4, 5), (3, 6), (2, 7))

# Placeholder names for the seven AI playoff teams until local AI teams get
# their own identities.
PLAYOFF_TEAM_NAMES: tuple[str, ...] = (
    "Ridgeline", "Harbor City", "Prairie State", "Iron Valley", "Lakeshore",
    "Red Mesa", "Pine Hollow", "Summit Tech", "Bayou A&M", "Granite Falls",
    "Coastal State", "Northfield",
)

# AI-vs-AI games: the better seed wins 50% + 5% per seed of difference, at most 80%.
_SEED_EDGE = 0.05
_MAX_FAVORITE = 0.80
_LOSING_SCORES = (0, 3, 6, 7, 10, 13, 14, 17, 20, 21, 24, 27)
_MARGINS = (1, 2, 3, 3, 4, 6, 7, 7, 8, 10, 11, 14, 17, 21)
_SHUTOUT_MARGINS = tuple(margin for margin in _MARGINS if margin != 1)


class FootballPlayoffRound(int, Enum):
    QUARTERFINAL = 1
    SEMIFINAL = 2
    CHAMPIONSHIP = 3

    @property
    def label(self) -> str:
        return self.name.title()


def playoff_round_for_game(game_number: int) -> FootballPlayoffRound | None:
    """The playoff round of a scheduled game number, or None in the regular season."""
    offset = game_number - REGULAR_SEASON_GAMES
    if 1 <= offset <= PLAYOFF_ROUNDS:
        return FootballPlayoffRound(offset)
    return None


def game_label(game_number: int, *, padded: bool = True) -> str:
    """``GAME 07`` (``GAME 7`` unpadded) in the regular season, ``QUARTERFINAL`` etc. after."""
    playoff_round = playoff_round_for_game(game_number)
    if playoff_round is not None:
        return playoff_round.name
    return f"GAME {game_number:02d}" if padded else f"GAME {game_number}"


def human_seed_for_losses(losses: int) -> int:
    if isinstance(losses, bool) or not isinstance(losses, int) or not 0 <= losses <= 2:
        raise ValueError("A playoff team has 0-2 regular-season losses.")
    return losses + 1


@dataclass(frozen=True)
class FootballPlayoffTeam:
    seed: int
    name: str
    is_human: bool = False


@dataclass(frozen=True)
class FootballPlayoffGame:
    """One bracket game. ``winner_seed`` is None until it is decided."""

    playoff_round: FootballPlayoffRound
    slot: int
    high_seed: int
    low_seed: int
    winner_seed: int | None = None
    high_score: int | None = None
    low_score: int | None = None
    overtime: bool = False

    @property
    def decided(self) -> bool:
        return self.winner_seed is not None

    def has(self, seed: int) -> bool:
        return seed in (self.high_seed, self.low_seed)

    def opponent_of(self, seed: int) -> int:
        if seed == self.high_seed:
            return self.low_seed
        if seed == self.low_seed:
            return self.high_seed
        raise ValueError(f"Seed {seed} is not in this game.")

    def score_for(self, seed: int) -> int | None:
        return self.high_score if seed == self.high_seed else self.low_score


@dataclass(frozen=True)
class FootballPlayoffBracketState:
    """Immutable bracket view for the UI."""

    teams: tuple[FootballPlayoffTeam, ...]
    games: tuple[FootballPlayoffGame, ...]
    human_seed: int

    def team(self, seed: int) -> FootballPlayoffTeam:
        return self.teams[seed - 1]

    def round_games(self, playoff_round: FootballPlayoffRound) -> tuple[FootballPlayoffGame, ...]:
        return tuple(game for game in self.games if game.playoff_round is playoff_round)

    def human_game(self, playoff_round: FootballPlayoffRound) -> FootballPlayoffGame | None:
        return next(
            (game for game in self.round_games(playoff_round) if game.has(self.human_seed)),
            None,
        )

    @property
    def human_eliminated(self) -> bool:
        return any(
            game.decided and game.has(self.human_seed) and game.winner_seed != self.human_seed
            for game in self.games
        )

    @property
    def champion_seed(self) -> int | None:
        final = self.round_games(FootballPlayoffRound.CHAMPIONSHIP)
        return final[0].winner_seed if final else None

    @property
    def next_human_round(self) -> FootballPlayoffRound | None:
        """The round of the human's next undecided game, if any."""
        for playoff_round in FootballPlayoffRound:
            game = self.human_game(playoff_round)
            if game is not None and not game.decided:
                return playoff_round
        return None


class FootballPlayoffBracket:
    """Mutable bracket owned by the controller; see the module docstring."""

    def __init__(self, human_name: str, losses: int, rng: random.Random) -> None:
        if not isinstance(human_name, str) or not human_name.strip():
            raise ValueError("The human team needs a name.")
        self._rng = rng
        self._human_seed = human_seed_for_losses(losses)
        pool = [
            name for name in PLAYOFF_TEAM_NAMES
            if name.casefold() != human_name.strip().casefold()
        ]
        names = self._rng.sample(pool, PLAYOFF_TEAMS - 1)
        teams = []
        for seed in range(1, PLAYOFF_TEAMS + 1):
            if seed == self._human_seed:
                teams.append(FootballPlayoffTeam(seed, human_name, is_human=True))
            else:
                teams.append(FootballPlayoffTeam(seed, names.pop(0)))
        self._teams = tuple(teams)
        self._games = [
            FootballPlayoffGame(FootballPlayoffRound.QUARTERFINAL, slot, high, low)
            for slot, (high, low) in enumerate(FIRST_ROUND_PAIRS)
        ]

    # -- save data -------------------------------------------------------------
    # Saved: the RNG state, human seed, teams, and every game. Nothing is rebuilt.

    def to_save_data(self) -> dict[str, Any]:
        return {
            "rng": rng_to_data(self._rng),
            "human_seed": self._human_seed,
            "teams": [team.name for team in self._teams],
            "games": [_game_to_save_data(game) for game in self._games],
        }

    @classmethod
    def from_save_data(cls, data: Any) -> "FootballPlayoffBracket":
        what = "Playoff bracket"
        bracket = cls.__new__(cls)
        bracket._rng = rng_from_data(required(data, "rng", list, what), "playoff RNG")
        bracket._human_seed = required(data, "human_seed", int, what)
        names = items(required(data, "teams", list, what), "Playoff teams")
        if len(names) != PLAYOFF_TEAMS or not all(
            isinstance(name, str) and name for name in names
        ):
            raise UnsupportedSave("A playoff bracket has eight named teams.")
        if not 1 <= bracket._human_seed <= PLAYOFF_TEAMS:
            raise UnsupportedSave("The human playoff seed is out of range.")
        bracket._teams = tuple(
            FootballPlayoffTeam(seed, name, is_human=seed == bracket._human_seed)
            for seed, name in enumerate(names, start=1)
        )
        bracket._games = [
            _game_from_save_data(item)
            for item in items(required(data, "games", list, what), "Playoff games")
        ]
        return bracket

    # -- queries ---------------------------------------------------------------

    @property
    def state(self) -> FootballPlayoffBracketState:
        return FootballPlayoffBracketState(self._teams, tuple(self._games), self._human_seed)

    def human_opponent(self, playoff_round: FootballPlayoffRound) -> FootballPlayoffTeam:
        game = self.state.human_game(playoff_round)
        if game is None or game.decided:
            raise ValueError(f"The human team has no {playoff_round.label} game to play.")
        return self._teams[game.opponent_of(self._human_seed) - 1]

    # -- results ---------------------------------------------------------------

    def record_human_result(
        self,
        playoff_round: FootballPlayoffRound,
        human_score: int,
        opponent_score: int,
        *,
        overtime: bool = False,
    ) -> None:
        """Record the human's game, decide the round's other games, and pair the next round."""
        if human_score == opponent_score:
            raise ValueError("A playoff game must have a winner.")
        game = self.state.human_game(playoff_round)
        if game is None or game.decided:
            raise ValueError(f"The human team has no {playoff_round.label} game to record.")
        opponent = game.opponent_of(self._human_seed)
        winner = self._human_seed if human_score > opponent_score else opponent
        self._replace(game, _decide(game, winner, {self._human_seed: human_score,
                                                  opponent: opponent_score}, overtime))
        for other in self.state.round_games(playoff_round):
            if not other.decided:
                self._replace(other, self._simulate(other))
        self._pair_next_round(playoff_round)

    def _simulate(self, game: FootballPlayoffGame) -> FootballPlayoffGame:
        favorite = min(_MAX_FAVORITE, 0.5 + _SEED_EDGE * (game.low_seed - game.high_seed))
        winner = game.high_seed if self._rng.random() < favorite else game.low_seed
        loser_score = self._rng.choice(_LOSING_SCORES)
        # No team scores exactly 1: a shutout needs a margin of at least 2.
        margins = _MARGINS if loser_score else _SHUTOUT_MARGINS
        winner_score = loser_score + self._rng.choice(margins)
        loser = game.opponent_of(winner)
        return _decide(game, winner, {winner: winner_score, loser: loser_score}, False)

    def _pair_next_round(self, playoff_round: FootballPlayoffRound) -> None:
        if playoff_round is FootballPlayoffRound.CHAMPIONSHIP:
            return
        finished = self.state.round_games(playoff_round)
        next_round = FootballPlayoffRound(playoff_round + 1)
        for slot in range(len(finished) // 2):
            first = finished[2 * slot].winner_seed
            second = finished[2 * slot + 1].winner_seed
            assert first is not None and second is not None
            high, low = sorted((first, second))
            self._games.append(FootballPlayoffGame(next_round, slot, high, low))

    def _replace(self, old: FootballPlayoffGame, new: FootballPlayoffGame) -> None:
        self._games[self._games.index(old)] = new


def _decide(
    game: FootballPlayoffGame, winner: int, scores: dict[int, int], overtime: bool
) -> FootballPlayoffGame:
    return FootballPlayoffGame(
        game.playoff_round, game.slot, game.high_seed, game.low_seed,
        winner_seed=winner,
        high_score=scores[game.high_seed],
        low_score=scores[game.low_seed],
        overtime=overtime,
    )


def _game_to_save_data(game: FootballPlayoffGame) -> dict[str, Any]:
    data: dict[str, Any] = {
        "round": game.playoff_round.value,
        "slot": game.slot,
        "high_seed": game.high_seed,
        "low_seed": game.low_seed,
    }
    if game.decided:
        data.update(
            winner_seed=game.winner_seed,
            high_score=game.high_score,
            low_score=game.low_score,
            overtime=game.overtime,
        )
    return data


def _game_from_save_data(data: Any) -> FootballPlayoffGame:
    what = "Playoff game"
    game = FootballPlayoffGame(
        enum_value(FootballPlayoffRound, required(data, "round", int, what), "playoff round"),
        required(data, "slot", int, what),
        required(data, "high_seed", int, what),
        required(data, "low_seed", int, what),
        winner_seed=optional(data, "winner_seed", int, what),
        high_score=optional(data, "high_score", int, what),
        low_score=optional(data, "low_score", int, what),
        overtime=optional(data, "overtime", bool, what, False),
    )
    seeds = (game.high_seed, game.low_seed)
    if not all(1 <= seed <= PLAYOFF_TEAMS for seed in seeds) or game.high_seed == game.low_seed:
        raise UnsupportedSave("A playoff game has two different seeds.")
    if game.winner_seed is not None and game.winner_seed not in seeds:
        raise UnsupportedSave("A playoff winner must have played the game.")
    return game
