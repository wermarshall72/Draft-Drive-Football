from src.db.schema import get_random_snapshot, save_snapshot
from src.engine.shop import Shop
from src.engine.simulator import simulate_match
from src.engine.units import Coach, Roster, SpecialTeams, Unit


class GameRun:
    """Tracks progression through a single roguelike run."""

    WINS_TO_WIN = 10
    LOSSES_TO_BE_FIRED = 5

    def __init__(self, roster: Roster, shop: Shop) -> None:
        self.roster = roster
        self.shop = shop
        self.wins = 0
        self.losses = 0
        self.round_number = 1

    def prep_phase(self) -> None:
        """Restore the shop's action-point budget for the new week."""
        self.shop.days = self.shop.DAYS_PER_SHOP

    def combat_phase(self) -> dict[str, object]:
        """Save the current team, play its round, and record the result."""
        snapshot_id = save_snapshot(
            self.roster,
            round_number=self.round_number,
            wins=self.wins,
            losses=self.losses,
        )
        opponent = get_random_snapshot(
            round_number=self.round_number,
            exclude_id=snapshot_id,
        )
        if opponent is None:
            opponent = self._build_dummy_opponent()

        result = simulate_match(self.roster, opponent)
        if result["winner"] == self.roster.player_name:
            self.wins += 1
        elif result["winner"] == opponent.player_name:
            self.losses += 1

        self.round_number += 1
        return result

    def is_game_over(self) -> bool:
        """Report whether the run has reached its win or loss limit."""
        if self.wins >= self.WINS_TO_WIN:
            print("Championship! You won the run.")
            return True
        if self.losses >= self.LOSSES_TO_BE_FIRED:
            print("Fired! Your run is over.")
            return True
        return False

    @staticmethod
    def _build_dummy_opponent() -> Roster:
        return Roster(
            player_name="FCS Cupcake",
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
