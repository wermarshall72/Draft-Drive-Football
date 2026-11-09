import random
from dataclasses import dataclass, field, replace
from typing import Literal

Position = Literal["QB", "RB", "WR", "OLINE", "FRONT7", "SECONDARY"]

@dataclass
class Unit:
    name: str
    position: Position
    tier: int = 1  # 1 to 3 (Bronze, Silver, Gold like Super Auto Pets)
    power: float = 10.0  # Base stat for Tug-of-War clashes
    volatility: float = 0.2  # RNG variance factor (0.2 = +/- 20% swing on drives)
    synergy_tags: list[str] = field(default_factory=list) # e.g., ["Air_Raid", "Scrambler"]

@dataclass
class Coach:
    name: str
    off_scheme: str
    def_scheme: str
    off_modifier: float = 1.0  # e.g., 1.2 for +20% Offense
    def_modifier: float = 1.0  # e.g., 1.1 for +10% Defense

@dataclass
class SpecialTeams:
    name: str = "Special Teams"
    tier: int = 1
    momentum_swing_chance: float = 0.05 # 5% chance to randomly flip drive momentum
    field_goal_reliability: float = 0.80 # 80% chance to secure points on stalled drives

@dataclass
class Roster:
    player_name: str
    qb: Unit
    rb: Unit
    wr: Unit
    oline: Unit
    front7: Unit
    secondary: Unit
    coach: Coach
    special_teams: SpecialTeams

    def get_offensive_power(self) -> float:
        """Calculates raw offensive baseline before RNG."""
        base_off = sum(u.power for u in [self.qb, self.rb, self.wr, self.oline])
        return base_off * self.coach.off_modifier

    def get_defensive_power(self) -> float:
        """Calculates raw defensive baseline before RNG."""
        base_def = sum(u.power for u in [self.front7, self.secondary])
        return base_def * self.coach.def_modifier


COACH_ARCHETYPES = (
    Coach(
        name="Air Raid / Bend-Don't-Break",
        off_scheme="Air Raid",
        def_scheme="Bend-Don't-Break",
        off_modifier=1.2,
        def_modifier=0.9,
    ),
    Coach(
        name="Option / Pressure Defense",
        off_scheme="Option",
        def_scheme="Pressure Defense",
        off_modifier=1.1,
        def_modifier=1.1,
    ),
    Coach(
        name="Balanced",
        off_scheme="Balanced",
        def_scheme="Balanced",
    ),
    Coach(
        name="Ground-and-Pound / Shut Down",
        off_scheme="Ground-and-Pound",
        def_scheme="Shut Down",
        off_modifier=0.9,
        def_modifier=1.2,
    ),
    Coach(
        name="Spread / Aggressive",
        off_scheme="Spread",
        def_scheme="Aggressive",
        off_modifier=1.15,
        def_modifier=0.95,
    ),
)


def random_coach_options() -> list[Coach]:
    """Offer three distinct coach archetypes at the start of a run."""
    return [replace(coach) for coach in random.sample(COACH_ARCHETYPES, 3)]
