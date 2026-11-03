from dataclasses import dataclass, field
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
