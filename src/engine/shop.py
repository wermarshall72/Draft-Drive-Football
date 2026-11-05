import random

from src.engine.units import Position, Roster, Unit


class Shop:
    """Transfer portal shop with a six-Day action-point budget."""

    DAYS_PER_SHOP = 6
    PORTAL_SIZE = 3
    UNIT_POOL: tuple[tuple[str, Position, float], ...] = (
        ("Pocket Passer", "QB", 12.0),
        ("Dual-Threat QB", "QB", 11.0),
        ("Power Back", "RB", 12.0),
        ("Receiving Back", "RB", 10.0),
        ("Deep Threat", "WR", 12.0),
        ("Possession Receiver", "WR", 11.0),
        ("Pass Protector", "OLINE", 13.0),
        ("Run Blocker", "OLINE", 14.0),
        ("Edge Rusher", "FRONT7", 25.0),
        ("Run Stuffer", "FRONT7", 27.0),
        ("Ball Hawk", "SECONDARY", 22.0),
        ("Shutdown Corner", "SECONDARY", 24.0),
    )
    ROSTER_SLOTS = {
        "QB": "qb",
        "RB": "rb",
        "WR": "wr",
        "OLINE": "oline",
        "FRONT7": "front7",
        "SECONDARY": "secondary",
    }

    def __init__(self, roster: Roster) -> None:
        self.roster = roster
        self.days = self.DAYS_PER_SHOP
        self.portal: list[Unit] = []

    def roll_portal(self) -> list[Unit]:
        """Spend one Day and offer three randomly selected units."""
        if self.days < 1:
            raise RuntimeError("Not enough Days to roll the portal.")

        self.days -= 1
        self.portal = [
            Unit(name=name, position=position, power=power)
            for name, position, power in random.sample(
                self.UNIT_POOL, self.PORTAL_SIZE
            )
        ]
        return self.portal

    def draft_unit(self, unit: Unit) -> None:
        """Replace the matching roster position with an offered portal unit."""
        if not any(offered is unit for offered in self.portal):
            raise ValueError("Unit must be selected from the current portal.")

        slot = self.ROSTER_SLOTS.get(unit.position)
        if slot is None:
            raise ValueError(f"Unsupported roster position: {unit.position}")

        setattr(self.roster, slot, unit)
        self.portal.remove(unit)
