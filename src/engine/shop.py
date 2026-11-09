import random
from dataclasses import replace

from src.engine.units import Position, Roster, SpecialTeams, Unit

PortalCard = Unit | SpecialTeams


class Shop:
    """Transfer portal shop with a six-Day action-point budget."""

    DAYS_PER_SHOP = 6
    OPENING_AP = DAYS_PER_SHOP
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
    SPECIAL_TEAMS_POOL = (
        SpecialTeams(
            name="Return Specialists",
            momentum_swing_chance=0.10,
            field_goal_reliability=0.80,
        ),
        SpecialTeams(
            name="Coverage Unit",
            momentum_swing_chance=0.03,
        ),
        SpecialTeams(
            name="Field Position Unit",
            momentum_swing_chance=0.07,
            field_goal_reliability=0.88,
        ),
    )
    ROSTER_SLOTS = {
        "QB": "qb",
        "RB": "rb",
        "WR": "wr",
        "OLINE": "oline",
        "FRONT7": "front7",
        "SECONDARY": "secondary",
    }

    def __init__(self, roster: Roster, days: int = DAYS_PER_SHOP) -> None:
        if days < 0:
            raise ValueError("Days cannot be negative.")
        self.roster = roster
        self.days = days
        self.portal: list[PortalCard] = []

    def roll_portal(self) -> list[PortalCard]:
        """Spend one Day and offer three randomly selected cards."""
        if self.days < 1:
            raise RuntimeError("Not enough Days to roll the portal.")

        self.days -= 1
        pool: list[tuple[str, Position, float] | SpecialTeams] = [
            *self.UNIT_POOL,
            *self.SPECIAL_TEAMS_POOL,
        ]
        self.portal = []
        for choice in random.sample(pool, self.PORTAL_SIZE):
            if isinstance(choice, SpecialTeams):
                self.portal.append(replace(choice))
            else:
                name, position, power = choice
                self.portal.append(Unit(name=name, position=position, power=power))
        return self.portal

    def draft_unit(self, unit: PortalCard) -> None:
        """Draft an offered card into its matching roster slot."""
        if not any(offered is unit for offered in self.portal):
            raise ValueError("Unit must be selected from the current portal.")

        if isinstance(unit, SpecialTeams):
            self.roster.special_teams = unit
            self.portal.remove(unit)
            return

        slot = self.ROSTER_SLOTS.get(unit.position)
        if slot is None:
            raise ValueError(f"Unsupported roster position: {unit.position}")

        setattr(self.roster, slot, unit)
        self.portal.remove(unit)
