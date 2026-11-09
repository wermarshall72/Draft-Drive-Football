import random
from dataclasses import replace

from src.engine.units import Position, Roster, SpecialTeams, Unit

PortalCard = Unit | SpecialTeams


class Shop:
    """Transfer portal shop with a six-Day action-point budget."""

    DAYS_PER_SHOP = 6
    OPENING_AP = DAYS_PER_SHOP
    PORTAL_SIZE = 3
    OPENING_ORDER: tuple[Position, ...] = (
        "QB",
        "RB",
        "WR",
        "OLINE",
        "FRONT7",
        "SECONDARY",
    )
    UNIT_POOL: tuple[tuple[str, Position, float, float, float], ...] = (
        ("Pocket Passer", "QB", 12.4, 0.14, 0.90),
        ("Dual-Threat QB", "QB", 12.1, 0.20, 0.78),
        ("Game Manager", "QB", 11.7, 0.10, 0.92),
        ("Scrambler", "QB", 11.8, 0.28, 0.62),
        ("Improviser", "QB", 12.2, 0.30, 0.58),
        ("Rushing QB", "QB", 12.0, 0.26, 0.65),
        ("Power Back", "RB", 11.4, 0.24, 0.72),
        ("Receiving Back", "RB", 10.9, 0.18, 0.80),
        ("One-Cut Runner", "RB", 11.2, 0.12, 0.88),
        ("Speed Back", "RB", 10.7, 0.30, 0.56),
        ("Ball-Security Back", "RB", 10.8, 0.10, 0.94),
        ("Workhorse Back", "RB", 11.3, 0.19, 0.86),
        ("Deep Threat", "WR", 11.8, 0.30, 0.60),
        ("Possession Receiver", "WR", 11.5, 0.10, 0.91),
        ("Route Technician", "WR", 11.7, 0.16, 0.84),
        ("YAC Receiver", "WR", 11.4, 0.24, 0.70),
        ("Contested-Catch Target", "WR", 11.9, 0.28, 0.64),
        ("Slot Separator", "WR", 11.2, 0.12, 0.89),
        ("Pass Protector", "OLINE", 13.6, 0.10, 0.94),
        ("Run Blocker", "OLINE", 13.9, 0.24, 0.78),
        ("Zone-Mobility Lineman", "OLINE", 13.2, 0.22, 0.72),
        ("Mauler", "OLINE", 14.0, 0.30, 0.62),
        ("Anchor Tackle", "OLINE", 13.8, 0.12, 0.90),
        ("Balanced Lineman", "OLINE", 13.5, 0.18, 0.84),
        ("Edge Rusher", "FRONT7", 26.8, 0.30, 0.60),
        ("Run Stuffer", "FRONT7", 26.7, 0.12, 0.92),
        ("Blitzing Linebacker", "FRONT7", 25.8, 0.28, 0.64),
        ("Coverage Linebacker", "FRONT7", 25.3, 0.10, 0.90),
        ("Interior Disruptor", "FRONT7", 26.4, 0.23, 0.74),
        ("Balanced Front", "FRONT7", 26.0, 0.18, 0.82),
        ("Shutdown Corner", "SECONDARY", 23.8, 0.12, 0.92),
        ("Ball Hawk", "SECONDARY", 22.8, 0.30, 0.58),
        ("Press Corner", "SECONDARY", 23.4, 0.26, 0.68),
        ("Zone Safety", "SECONDARY", 23.0, 0.10, 0.94),
        ("Run-Support Safety", "SECONDARY", 22.9, 0.20, 0.80),
        ("Nickel Defender", "SECONDARY", 23.3, 0.17, 0.84),
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
        self.opening_picks = 0

    def roll_opening_offer(self, position: Position) -> list[Unit]:
        """Offer three random players for the next opening-draft position."""
        if self.opening_picks >= len(self.OPENING_ORDER):
            raise RuntimeError("The opening draft is complete.")
        expected_position = self.OPENING_ORDER[self.opening_picks]
        if position != expected_position:
            raise ValueError(f"The next opening pick must be for {expected_position}.")
        if self.days < 1:
            raise RuntimeError("Not enough Days to make an opening pick.")
        if self.portal:
            raise RuntimeError("Choose a card from the current opening offer first.")

        pool = [choice for choice in self.UNIT_POOL if choice[1] == position]
        self.portal = [
            Unit(
                name=name,
                position=card_position,
                power=power,
                volatility=volatility,
                stamina=stamina,
            )
            for name, card_position, power, volatility, stamina in random.sample(
                pool, self.PORTAL_SIZE
            )
        ]
        return [card for card in self.portal if isinstance(card, Unit)]

    def draft_opening_unit(self, unit: Unit) -> None:
        """Select one offered player and spend one opening Action Point."""
        if self.opening_picks >= len(self.OPENING_ORDER):
            raise RuntimeError("The opening draft is complete.")
        if not any(offered is unit for offered in self.portal):
            raise ValueError("Unit must be selected from the current opening offer.")
        if unit.position != self.OPENING_ORDER[self.opening_picks]:
            raise ValueError("Unit does not match the current opening position.")
        if self.days < 1:
            raise RuntimeError("Not enough Days to make an opening pick.")

        self._place_unit(unit)
        self.portal.clear()
        self.opening_picks += 1
        self.days -= 1

    def roll_portal(self) -> list[PortalCard]:
        """Spend one Day and offer three randomly selected cards."""
        if self.days < 1:
            raise RuntimeError("Not enough Days to roll the portal.")

        self.days -= 1
        pool: list[tuple[str, Position, float, float, float] | SpecialTeams] = [
            *self.UNIT_POOL,
            *self.SPECIAL_TEAMS_POOL,
        ]
        self.portal = []
        for choice in random.sample(pool, self.PORTAL_SIZE):
            if isinstance(choice, SpecialTeams):
                self.portal.append(replace(choice))
            else:
                name, position, power, volatility, stamina = choice
                self.portal.append(
                    Unit(
                        name=name,
                        position=position,
                        power=power,
                        volatility=volatility,
                        stamina=stamina,
                    )
                )
        return self.portal

    def draft_unit(self, unit: PortalCard) -> None:
        """Draft an offered card into its matching roster slot."""
        if not any(offered is unit for offered in self.portal):
            raise ValueError("Unit must be selected from the current portal.")

        if isinstance(unit, SpecialTeams):
            self.roster.special_teams = unit
            self.portal.remove(unit)
            return

        self._place_unit(unit)
        self.portal.remove(unit)

    def _place_unit(self, unit: Unit) -> None:
        slot = self.ROSTER_SLOTS.get(unit.position)
        if slot is None:
            raise ValueError(f"Unsupported roster position: {unit.position}")
        setattr(self.roster, slot, unit)
