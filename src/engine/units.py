import random
from dataclasses import dataclass, field, replace
from itertools import product
from typing import Literal

Position = Literal["QB", "RB", "WR", "OLINE", "FRONT7", "SECONDARY"]

@dataclass
class Unit:
    name: str
    position: Position
    tier: int = 1  # 1 to 3 (Bronze, Silver, Gold like Super Auto Pets)
    power: float = 10.0  # Base stat for Tug-of-War clashes
    volatility: float = 0.2  # RNG variance factor (0.2 = +/- 20% swing on drives)
    stamina: float = 0.75  # 0 to 1; higher stamina reduces late-game fatigue
    synergy_tags: list[str] = field(default_factory=list) # e.g., ["Air_Raid", "Scrambler"]
    description: str = ""

@dataclass
class Coach:
    name: str
    off_scheme: str
    def_scheme: str
    off_modifier: float = 1.0
    def_modifier: float = 1.0
    position_modifiers: dict[Position, float] = field(default_factory=dict)
    off_description: str = ""
    def_description: str = ""

    def modifier_for(self, position: Position) -> float:
        """Return a position multiplier, falling back to legacy side-wide values."""
        if self.position_modifiers:
            return self.position_modifiers.get(position, 1.0)
        if position in ("QB", "RB", "WR", "OLINE"):
            return self.off_modifier
        return self.def_modifier

@dataclass
class SpecialTeams:
    name: str = "Special Teams"
    tier: int = 1
    momentum_swing_chance: float = 0.05 # 5% chance to randomly flip drive momentum
    field_goal_reliability: float = 0.80
    momentum_swing_magnitude: float = 15.0
    opponent_swing_reduction: float = 0.0

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
    match_drive_count: int = 10
    match_fatigue_limit: float = 0.10

    def get_offensive_power(self) -> float:
        """Calculates raw offensive baseline before RNG."""
        return sum(
            unit.power * self.coach.modifier_for(unit.position)
            for unit in self.get_offensive_units()
        )

    def get_defensive_power(self) -> float:
        """Calculates raw defensive baseline before RNG."""
        return sum(
            unit.power * self.coach.modifier_for(unit.position)
            for unit in self.get_defensive_units()
        )

    def get_offensive_units(self) -> tuple[Unit, ...]:
        return self.qb, self.rb, self.wr, self.oline

    def get_defensive_units(self) -> tuple[Unit, ...]:
        return self.front7, self.secondary


def create_starter_team(name: str, coach: Coach | None = None) -> Roster:
    return Roster(
        player_name=name,
        qb=Unit(name="Walk-on QB", position="QB", power=10.0),
        rb=Unit(name="Walk-on RB", position="RB", power=10.0),
        wr=Unit(name="Walk-on WR", position="WR", power=10.0),
        oline=Unit(name="Walk-on O-Line", position="OLINE", power=10.0),
        front7=Unit(name="Walk-on Front 7", position="FRONT7", power=20.0),
        secondary=Unit(name="Walk-on Secondary", position="SECONDARY", power=20.0),
        coach=coach
        or Coach(
            name="Balanced",
            off_scheme="Balanced",
            def_scheme="Balanced",
        ),
        special_teams=SpecialTeams(),
    )


@dataclass(frozen=True)
class CoachStyle:
    name: str
    description: str
    position_modifiers: dict[Position, float]


OFFENSIVE_STYLES = (
    CoachStyle(
        "Air Raid",
        "Favor QB and WR power over RB power.",
        {"QB": 1.1, "WR": 1.1, "RB": 0.9},
    ),
    CoachStyle(
        "Ground-and-Pound",
        "Boost RB power while reducing WR power.",
        {"RB": 1.2, "WR": 0.8},
    ),
    CoachStyle(
        "Option",
        "Boost QB and RB power at the expense of WR power.",
        {"QB": 1.1, "RB": 1.1, "WR": 0.8},
    ),
    CoachStyle("Balanced", "No position-specific power changes.", {}),
    CoachStyle(
        "Spread",
        "Favor WR and O-Line power over RB power.",
        {"WR": 1.1, "OLINE": 1.1, "RB": 0.9},
    ),
)

DEFENSIVE_STYLES = (
    CoachStyle(
        "Bend-Don't-Break",
        "Lean on Secondary power while giving up Front 7 power.",
        {"FRONT7": 0.8, "SECONDARY": 1.2},
    ),
    CoachStyle(
        "Pressure Defense",
        "Boost Front 7 power while reducing Secondary power.",
        {"FRONT7": 1.2, "SECONDARY": 0.8},
    ),
    CoachStyle("Balanced", "No position-specific power changes.", {}),
    CoachStyle(
        "Shut Down",
        "Favor Secondary power over Front 7 power.",
        {"FRONT7": 0.9, "SECONDARY": 1.1},
    ),
    CoachStyle(
        "Aggressive",
        "Favor Front 7 power over Secondary power.",
        {"FRONT7": 1.1, "SECONDARY": 0.9},
    ),
)

COACH_PAIRINGS = tuple(
    Coach(
        name=f"{offense.name} / {defense.name}",
        off_scheme=offense.name,
        def_scheme=defense.name,
        position_modifiers={
            **offense.position_modifiers,
            **defense.position_modifiers,
        },
        off_description=offense.description,
        def_description=defense.description,
    )
    for offense, defense in product(OFFENSIVE_STYLES, DEFENSIVE_STYLES)
)


def random_coach_options() -> list[Coach]:
    """Offer three distinct coach archetypes at the start of a run."""
    return [
        replace(coach, position_modifiers=dict(coach.position_modifiers))
        for coach in random.sample(COACH_PAIRINGS, 3)
    ]
