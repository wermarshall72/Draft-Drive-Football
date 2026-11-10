from typing import Literal

from src.db.schema import DB_PATH, DatabasePath, get_random_snapshot, save_snapshot
from src.engine.shop import Shop
from src.engine.simulator import MatchResult, simulate_match
from src.engine.units import Coach, Roster, SpecialTeams, Unit

RunPhase = Literal["opening_draft", "regular_season", "playoffs", "won", "lost"]


class GameRun:
    """Tracks progression through a single roguelike run."""

    REGULAR_SEASON_GAMES = 10
    LOSSES_TO_BE_FIRED = 3
    PLAYOFF_ROUNDS = 3

    def __init__(
        self,
        roster: Roster,
        shop: Shop,
        db_path: DatabasePath = DB_PATH,
    ) -> None:
        self.roster = roster
        self.shop = shop
        self.db_path = db_path
        self.wins = 0
        self.losses = 0
        self.round_number = 1
        self.playoff_round = 0
        self.phase: RunPhase = "opening_draft"

    def start_regular_season(self) -> None:
        """Finish National Signing Day and prepare for the first game."""
        if self.phase != "opening_draft":
            raise RuntimeError("The regular season has already started.")
        self.phase = "regular_season"
        self.prep_phase()

    def prep_phase(self) -> None:
        """Restore the shop's action-point budget for the current match."""
        if self.phase not in ("regular_season", "playoffs"):
            raise RuntimeError("The shop is not available during this phase.")
        self.shop.has_future_shop = not (
            self.phase == "playoffs"
            and self.playoff_round >= self.PLAYOFF_ROUNDS
        )
        self.shop.prepare_next_shop()

    def combat_phase(self) -> MatchResult:
        """Play one regular-season or playoff match and advance the run."""
        if self.phase not in ("regular_season", "playoffs"):
            raise RuntimeError("The run is not ready for a match.")

        is_playoff = self.phase == "playoffs"
        match_round = (
            self.REGULAR_SEASON_GAMES + self.playoff_round
            if is_playoff
            else self.round_number
        )
        snapshot_id = save_snapshot(
            self.shop.effective_roster(include_match_effects=False),
            round_number=match_round,
            wins=self.wins,
            losses=self.losses,
            db_path=self.db_path,
        )
        opponent = get_random_snapshot(
            round_number=match_round,
            exclude_id=snapshot_id,
            exclude_player_name=self.roster.player_name,
            db_path=self.db_path,
        )
        if opponent is None:
            opponent = self._build_dummy_opponent(self.roster.player_name)

        match_roster = self.shop.effective_roster()
        result = simulate_match(match_roster, opponent)
        while result["winner"] == "Tie":
            result = simulate_match(match_roster, opponent)

        won_match = result["winner"] == self.roster.player_name
        self.shop.complete_match(won_match)
        if won_match:
            self.wins += 1
        else:
            self.losses += 1

        if is_playoff:
            self._advance_playoffs(won_match)
        else:
            self._advance_regular_season()
        return result

    def _advance_regular_season(self) -> None:
        if self.losses >= self.LOSSES_TO_BE_FIRED:
            self.phase = "lost"
        elif self.round_number == self.REGULAR_SEASON_GAMES:
            self.phase = "playoffs"
            self.playoff_round = 1
        else:
            self.round_number += 1

    def _advance_playoffs(self, won_match: bool) -> None:
        if not won_match:
            self.phase = "lost"
        elif self.playoff_round >= self.PLAYOFF_ROUNDS:
            self.phase = "won"
        else:
            self.playoff_round += 1

    def is_game_over(self) -> bool:
        """Report whether the run reached a final win or loss state."""
        return self.phase in ("won", "lost")

    @staticmethod
    def _build_dummy_opponent(player_name: str) -> Roster:
        opponent_name = "FCS Cupcake"
        while opponent_name == player_name:
            opponent_name += " CPU"
        return Roster(
            player_name=opponent_name,
            qb=Unit(name="Basic QB", position="QB", power=12.0),
            rb=Unit(name="Basic RB", position="RB", power=10.0),
            wr=Unit(name="Basic WR", position="WR", power=10.0),
            oline=Unit(name="Basic OLINE", position="OLINE", power=15.0),
            front7=Unit(name="Basic FRONT7", position="FRONT7", power=25.0),
            secondary=Unit(name="Basic SEC", position="SECONDARY", power=22.0),
            coach=Coach(
                name="Head Coach",
                off_scheme="Scheme",
                def_scheme="Scheme",
            ),
            special_teams=SpecialTeams(),
        )
