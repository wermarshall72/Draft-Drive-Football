"""Validated player-type catalog and shared partnership contribution rules."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Mapping

from src.engine.football import FootballPlayer, FootballPlayerPerkKind, FootballPosition

# The uniform stats every player had before save format 5 (old saves keep them);
# still the neutral reference for hand-built test rosters.
PLAYER_BASE_POWER = 50.0
PLAYER_BASE_VOLATILITY = 0.10
PLAYER_BASE_STAMINA = 0.50
# Each drafted prospect rolls uniformly over whole steps around its type's base.
POWER_SPREAD = 2  # power points
VOLATILITY_SPREAD_PCT = 1  # percentage points
STAMINA_SPREAD_PCT = 3  # percentage points
MIN_VOLATILITY_PCT = 1
MAX_STAMINA_PCT = 100
BASIC_BASE_STATS = (46, 12, 45)  # power, volatility %, stamina %
PARTNERSHIP_BONUS = 0.10
MAX_COMBINED_PLAYER_MODIFIER = 1.30

OFFENSIVE_POSITIONS = (
    FootballPosition.QB,
    FootballPosition.RB,
    FootballPosition.WR,
    FootballPosition.O_LINE,
)
DEFENSIVE_POSITIONS = (
    FootballPosition.D_LINE,
    FootballPosition.LINEBACKERS,
    FootballPosition.CORNERBACKS,
    FootballPosition.SAFETIES,
)
_POSITIONS_BY_SIDE = (OFFENSIVE_POSITIONS, DEFENSIVE_POSITIONS)


class FootballPerkLimit(str, Enum):
    """How often a perk may fire for its team."""

    EVERY = "every"  # every qualifying snap, attempt, or drive
    DRIVE = "drive"  # once per drive (yours or the rival's)
    HALF = "half"  # once per half; overtime is one half
    GAME = "game"
    CHARGE = "charge"  # one stored effect waiting for a later play


class FootballPerkEffectType(str, Enum):
    STATS = "stats"
    CARDS = "cards"
    YARDS = "yards"  # yards, clock, field position, and kick range
    TURNOVERS = "turnovers"  # incompletion/INT odds, rerolls, big plays, blocks


@dataclass(frozen=True)
class FootballPlayerPerk:
    """A specialist's executable perk: a typed kind plus its tuning values.

    The simulator reads ``values`` by name; all wording is generated from the
    same values in ``src/ui/football_player_perks.py``.
    """

    kind: FootballPlayerPerkKind
    name: str
    limit: FootballPerkLimit
    effect_type: FootballPerkEffectType
    partner_required: bool = False
    values: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FootballPlayerPerkKind):
            raise ValueError("Player perk kind must be a FootballPlayerPerkKind.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Player perk names must be non-empty.")
        if not isinstance(self.limit, FootballPerkLimit):
            raise ValueError("Player perk limit must be a FootballPerkLimit.")
        if not isinstance(self.effect_type, FootballPerkEffectType):
            raise ValueError("Player perk effect type must be a FootballPerkEffectType.")
        if not isinstance(self.partner_required, bool):
            raise ValueError("Player perk partner requirement must be a boolean.")
        if not isinstance(self.values, Mapping) or any(
            not isinstance(key, str)
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            for key, value in self.values.items()
        ):
            raise ValueError("Player perk values must map names to finite numbers.")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def value(self, key: str) -> float:
        return self.values[key]


@dataclass(frozen=True)
class FootballPlayerType:
    """Immutable identity and display metadata for one player archetype."""

    type_id: str
    position: FootballPosition
    name: str
    partner_position: FootballPosition | None
    perk: FootballPlayerPerk | None
    base_power: int  # a whole number
    base_volatility_pct: int  # a whole percent
    base_stamina_pct: int  # a whole percent

    @property
    def base_volatility(self) -> float:
        return self.base_volatility_pct / 100

    @property
    def base_stamina(self) -> float:
        return self.base_stamina_pct / 100

    def __post_init__(self) -> None:
        if not isinstance(self.type_id, str) or not self.type_id.strip():
            raise ValueError("Player type identifier must be non-empty.")
        for value, label, low, high in (
            (self.base_power, "base power", POWER_SPREAD, 1000),
            (self.base_volatility_pct, "base volatility", MIN_VOLATILITY_PCT, 100),
            (self.base_stamina_pct, "base stamina", 0, MAX_STAMINA_PCT),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"Player type {label} must be a whole number in range.")
        if not isinstance(self.position, FootballPosition):
            raise ValueError("Player type position must be a FootballPosition.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Player type name must be non-empty.")
        if self.partner_position is not None:
            if not isinstance(self.partner_position, FootballPosition):
                raise ValueError("Partner must be a FootballPosition or None.")
            if self.partner_position is self.position:
                raise ValueError("A player type cannot partner with its own position.")
            if not any(
                self.position in side and self.partner_position in side
                for side in _POSITIONS_BY_SIDE
            ):
                raise ValueError("Player type partners must be on the same side.")
        if self.partner_position is None:
            if self.perk is not None:
                raise ValueError("Basic player types cannot have perks.")
        elif not isinstance(self.perk, FootballPlayerPerk):
            raise ValueError("Specialist player types require a typed perk.")


def _specialist(
    type_id: str,
    position: FootballPosition,
    partner: FootballPosition,
    name: str,
    kind: FootballPlayerPerkKind,
    perk_name: str,
    limit: FootballPerkLimit,
    effect_type: FootballPerkEffectType,
    partner_required: bool = False,
    **values: float,
) -> FootballPlayerType:
    power, volatility, stamina = _SPECIALIST_BASE_STATS[type_id]
    return FootballPlayerType(
        type_id,
        position,
        name,
        partner,
        FootballPlayerPerk(kind, perk_name, limit, effect_type, partner_required, values),
        power,
        volatility,
        stamina,
    )


# Base stats per specialist: power, volatility %, stamina % (see "Player type
# stats" in docs/player-perks-proposal.md). Power or big-play types run high
# power and volatility with less stamina; steady technicians keep volatility
# low; workhorses carry stamina; the rest are balanced.
_SPECIALIST_BASE_STATS: Mapping[str, tuple[int, int, int]] = MappingProxyType({
    "qb_rb_mesh_reader": (52, 9, 56),
    "qb_rb_option_ledger": (51, 8, 55),
    "qb_wr_boundary_captain": (52, 10, 60),
    "qb_wr_vertical_architect": (58, 14, 48),
    "qb_oline_pocket_anchor": (53, 7, 52),
    "qb_oline_silent_count": (52, 7, 54),
    "rb_qb_checkdown_back": (50, 8, 58),
    "rb_qb_option_keeper": (53, 11, 54),
    "rb_wr_orbit_runner": (57, 15, 52),
    "rb_wr_slot_outlet": (50, 8, 56),
    "rb_oline_gap_runner": (59, 14, 44),
    "rb_oline_pull_guard_back": (55, 10, 52),
    "wr_qb_route_technician": (51, 7, 55),
    "wr_qb_vertical_threat": (58, 15, 48),
    "wr_rb_screen_outlet": (52, 8, 56),
    "wr_rb_motion_receiver": (54, 10, 55),
    "wr_oline_boundary_route": (56, 12, 50),
    "wr_oline_release_specialist": (53, 9, 57),
    "oline_qb_pass_set_guard": (52, 7, 55),
    "oline_qb_pocket_tempo": (51, 8, 58),
    "oline_rb_drive_blocker": (54, 10, 60),
    "oline_rb_pull_guard": (58, 13, 48),
    "oline_wr_screen_setter": (52, 9, 55),
    "oline_wr_space_creator": (55, 11, 52),
    "dline_lb_a_gap_plug": (57, 9, 46),
    "dline_lb_edge_setter": (55, 10, 54),
    "dline_cb_contain_end": (52, 7, 55),
    "dline_cb_rush_contain": (54, 11, 54),
    "dline_s_interior_rusher": (58, 13, 46),
    "dline_s_stunt_tackle": (56, 14, 50),
    "lb_dline_front_fit_back": (54, 10, 56),
    "lb_dline_run_fit_captain": (54, 9, 54),
    "lb_cb_nickel_rover": (51, 8, 58),
    "lb_cb_hook_curl_reader": (50, 7, 56),
    "lb_s_robber_backer": (53, 11, 56),
    "lb_s_green_dog_blitzer": (58, 15, 50),
    "cb_dline_edge_corner": (52, 8, 56),
    "cb_dline_force_corner": (55, 10, 52),
    "cb_lb_nickel_matcher": (53, 9, 55),
    "cb_lb_underneath_bracket": (51, 7, 54),
    "cb_s_deep_half_corner": (54, 8, 50),
    "cb_s_trail_corner": (57, 15, 50),
    "s_dline_post_safety": (51, 7, 55),
    "s_dline_blitz_safety": (58, 14, 48),
    "s_lb_box_safety": (57, 11, 50),
    "s_lb_robber_safety": (54, 12, 52),
    "s_cb_boundary_safety": (52, 9, 58),
    "s_cb_range_safety": (53, 8, 54),
})


_QB, _RB, _WR, _OL = (
    FootballPosition.QB, FootballPosition.RB, FootballPosition.WR, FootballPosition.O_LINE,
)
_DL, _LB, _CB, _S = (
    FootballPosition.D_LINE, FootballPosition.LINEBACKERS,
    FootballPosition.CORNERBACKS, FootballPosition.SAFETIES,
)
_K = FootballPlayerPerkKind
_EVERY, _DRIVE, _HALF, _GAME, _CHARGE = (
    FootballPerkLimit.EVERY, FootballPerkLimit.DRIVE, FootballPerkLimit.HALF,
    FootballPerkLimit.GAME, FootballPerkLimit.CHARGE,
)
_STATS, _CARDS, _YARDS, _TURNOVERS = (
    FootballPerkEffectType.STATS, FootballPerkEffectType.CARDS,
    FootballPerkEffectType.YARDS, FootballPerkEffectType.TURNOVERS,
)

# Values are the approved starting numbers (docs/player-perks-proposal.md §3).
_SPECIALISTS = (
    _specialist("qb_rb_mesh_reader", _QB, _RB, "Mesh Reader", _K.MESH_READ, "Mesh Read", _DRIVE, _CARDS, True, cards=1),
    _specialist("qb_rb_option_ledger", _QB, _RB, "Option Ledger", _K.OPTION_LEDGER, "Option Ledger", _GAME, _CARDS, families=4, cards=2),
    _specialist("qb_wr_boundary_captain", _QB, _WR, "Boundary Captain", _K.HURRY_UP_CAPTAIN, "Hurry-Up Captain", _EVERY, _YARDS, window_seconds=180, seconds=8),
    _specialist("qb_wr_vertical_architect", _QB, _WR, "Vertical Architect", _K.SHOT_SETUP, "Shot Setup", _CHARGE, _TURNOVERS, True, incompletion=-0.12),
    _specialist("qb_oline_pocket_anchor", _QB, _OL, "Pocket Anchor", _K.POCKET_PRESENCE, "Pocket Presence", _EVERY, _STATS, from_snap=5, power=5),
    _specialist("qb_oline_silent_count", _QB, _OL, "Silent-Count Caller", _K.SILENT_COUNT, "Silent Count", _HALF, _STATS),
    _specialist("rb_qb_checkdown_back", _RB, _QB, "Checkdown Back", _K.CHECKDOWN, "Checkdown", _EVERY, _YARDS, True, yards=2),
    _specialist("rb_qb_option_keeper", _RB, _QB, "Option Keeper", _K.KEEP_READ, "Keep Read", _HALF, _TURNOVERS, True),
    _specialist("rb_wr_orbit_runner", _RB, _WR, "Orbit Runner", _K.ORBIT_BREAKAWAY, "Orbit Breakaway", _HALF, _TURNOVERS, True, chance=0.25, yards=8),
    _specialist("rb_wr_slot_outlet", _RB, _WR, "Slot Outlet", _K.OUTLET_REPEAT, "Outlet Repeat", _DRIVE, _CARDS, True),
    _specialist("rb_oline_gap_runner", _RB, _OL, "Gap Runner", _K.DOWNHILL, "Downhill", _EVERY, _YARDS, True, yards=1, run_yards=2),
    _specialist("rb_oline_pull_guard_back", _RB, _OL, "Pull-Guard Back", _K.FALL_FORWARD, "Fall Forward", _DRIVE, _YARDS, True, yards=1),
    _specialist("wr_qb_route_technician", _WR, _QB, "Route Technician", _K.HOT_ROUTE, "Hot Route", _DRIVE, _CARDS),
    _specialist("wr_qb_vertical_threat", _WR, _QB, "Field Stretcher", _K.CONTESTED_CATCH, "Contested Catch", _GAME, _TURNOVERS, True),
    _specialist("wr_rb_screen_outlet", _WR, _RB, "Chain Mover", _K.MOVE_THE_STICKS, "Move the Sticks", _HALF, _YARDS, True, yards=2),
    _specialist("wr_rb_motion_receiver", _WR, _RB, "Motion Receiver", _K.MOTION_JUMP, "Motion Jump", _DRIVE, _STATS, power=8),
    _specialist("wr_oline_boundary_route", _WR, _OL, "Boundary Route", _K.PYLON_REACH, "Pylon Reach", _GAME, _YARDS, yards=5),
    _specialist("wr_oline_release_specialist", _WR, _OL, "Release Specialist", _K.RELEASE_READ, "Release Read", _DRIVE, _CARDS, True, yards=8),
    _specialist("oline_qb_pass_set_guard", _OL, _QB, "Pass-Set Guard", _K.PASS_PRO, "Pass Pro", _GAME, _TURNOVERS, True),
    _specialist("oline_qb_pocket_tempo", _OL, _QB, "Pocket Tempo", _K.TEMPO_READ, "Tempo Read", _DRIVE, _CARDS, True, cards=1),
    _specialist("oline_rb_drive_blocker", _OL, _RB, "Drive Blocker", _K.FOUR_MINUTE_DRILL, "Four-Minute Drill", _EVERY, _YARDS, True, seconds=10),
    _specialist("oline_rb_pull_guard", _OL, _RB, "Pull Guard", _K.PULL_LEAD, "Pull Lead", _EVERY, _STATS, distance=3, power=10),
    _specialist("oline_wr_screen_setter", _OL, _WR, "Screen Setter", _K.SCREEN_WALL, "Screen Wall", _DRIVE, _STATS, True, power=8),
    _specialist("oline_wr_space_creator", _OL, _WR, "Space Creator", _K.BREATHING_ROOM, "Breathing Room", _EVERY, _YARDS, threshold=20, yards=5),
    _specialist("dline_lb_a_gap_plug", _DL, _LB, "A-Gap Plug", _K.HOLD_THE_FRONT, "Hold the Front", _DRIVE, _CARDS, True),
    _specialist("dline_lb_edge_setter", _DL, _LB, "Edge Setter", _K.EDGE_SET, "Edge Set", _DRIVE, _STATS, power=8),
    _specialist("dline_cb_contain_end", _DL, _CB, "Contain End", _K.CONTAIN, "Contain", _EVERY, _YARDS, cap=6),
    _specialist("dline_cb_rush_contain", _DL, _CB, "Rush Contain", _K.COLLAPSE, "Collapse", _DRIVE, _CARDS),
    _specialist("dline_s_interior_rusher", _DL, _S, "Interior Rusher", _K.KICK_RUSH, "Kick Rush", _EVERY, _TURNOVERS, block=0.08),
    _specialist("dline_s_stunt_tackle", _DL, _S, "Stunt Tackle", _K.STUNT_SACK, "Stunt Sack", _DRIVE, _YARDS, yards=5),
    _specialist("lb_dline_front_fit_back", _LB, _DL, "Front-Fit Back", _K.FIT_AND_SHED, "Fit & Shed", _DRIVE, _CARDS, yards=2, cards=1),
    _specialist("lb_dline_run_fit_captain", _LB, _DL, "Run-Fit Captain", _K.CAPTAINS_ADJUSTMENT, "Captain's Adjustment", _DRIVE, _STATS, power=8),
    _specialist("lb_cb_nickel_rover", _LB, _CB, "Nickel Rover", _K.HOLD_THE_LINE, "Hold the Line", _HALF, _YARDS, margin=2, short=0.5),
    _specialist("lb_cb_hook_curl_reader", _LB, _CB, "Hook-Curl Reader", _K.READ_KEYS, "Read Keys", _EVERY, _CARDS),
    _specialist("lb_s_robber_backer", _LB, _S, "Robber Backer", _K.SHORT_FIELD, "Short Field", _EVERY, _YARDS, yards=5),
    _specialist("lb_s_green_dog_blitzer", _LB, _S, "Green-Dog Blitzer", _K.GREEN_DOG, "Green Dog", _GAME, _CARDS),
    _specialist("cb_dline_edge_corner", _CB, _DL, "Edge Corner", _K.KEEP_IT_INBOUNDS, "Keep It Inbounds", _EVERY, _YARDS, seconds=6),
    _specialist("cb_dline_force_corner", _CB, _DL, "Force Corner", _K.FORCE_AND_FOLD, "Force & Fold", _EVERY, _STATS, True),
    _specialist("cb_lb_nickel_matcher", _CB, _LB, "Nickel Matcher", _K.NICKEL_LOCK, "Nickel Lock", _EVERY, _STATS, power=8),
    _specialist("cb_lb_underneath_bracket", _CB, _LB, "Underneath Bracket", _K.BRACKET, "Bracket", _GAME, _CARDS),
    _specialist("cb_s_deep_half_corner", _CB, _S, "Deep-Half Corner", _K.DEEP_LOCK, "Deep Lock", _EVERY, _YARDS, True, cap=10),
    _specialist("cb_s_trail_corner", _CB, _S, "Trail Corner", _K.BAIT_AND_JUMP, "Bait & Jump", _HALF, _TURNOVERS, interception=0.08),
    _specialist("s_dline_post_safety", _S, _DL, "Post Safety", _K.LAST_LINE, "Last Line", _GAME, _YARDS, distance=5),
    _specialist("s_dline_blitz_safety", _S, _DL, "Blitz Safety", _K.SAFETY_BLITZ, "Safety Blitz", _EVERY, _TURNOVERS, True, incompletion=0.10, yards=2),
    _specialist("s_lb_box_safety", _S, _LB, "Box Safety", _K.DOWNHILL_FILL, "Downhill Fill", _EVERY, _STATS, power=10),
    _specialist("s_lb_robber_safety", _S, _LB, "Robber Safety", _K.TIP_DRILL, "Tip Drill", _GAME, _TURNOVERS),
    _specialist("s_cb_boundary_safety", _S, _CB, "Boundary Safety", _K.SUDDEN_CHANGE, "Sudden Change", _EVERY, _CARDS, cards=1),
    _specialist("s_cb_range_safety", _S, _CB, "Range Safety", _K.RANGE_DENIAL, "Range Denial", _EVERY, _YARDS, yards=7),
)

_BASIC_DISPLAY_NAMES = {
    FootballPosition.QB: "Basic QB",
    FootballPosition.RB: "Basic RB",
    FootballPosition.WR: "Basic WR",
    FootballPosition.O_LINE: "Basic O-Line",
    FootballPosition.D_LINE: "Basic D-Line",
    FootballPosition.LINEBACKERS: "Basic Linebackers",
    FootballPosition.CORNERBACKS: "Basic Cornerbacks",
    FootballPosition.SAFETIES: "Basic Safeties",
}

BASIC_PLAYER_TYPES = tuple(
    FootballPlayerType(
        f"basic_{position.value.lower()}", position, _BASIC_DISPLAY_NAMES[position], None, None,
        *BASIC_BASE_STATS,
    )
    for position in FootballPosition
)

PLAYER_TYPES = _SPECIALISTS + BASIC_PLAYER_TYPES
PLAYER_TYPES_BY_ID: Mapping[str, FootballPlayerType] = MappingProxyType(
    {player_type.type_id: player_type for player_type in PLAYER_TYPES}
)
PLAYER_TYPES_BY_POSITION: Mapping[
    FootballPosition, tuple[FootballPlayerType, ...]
] = MappingProxyType(
    {
        position: tuple(
            player_type
            for player_type in PLAYER_TYPES
            if player_type.position is position
        )
        for position in FootballPosition
    }
)


def _validate_catalog() -> None:
    if len(_SPECIALISTS) != 48 or len(BASIC_PLAYER_TYPES) != 8:
        raise RuntimeError("The player catalog must contain 48 specialists and 8 basics.")
    if len(PLAYER_TYPES_BY_ID) != len(PLAYER_TYPES):
        raise RuntimeError("Player type identifiers must be unique.")

    for position, player_types in PLAYER_TYPES_BY_POSITION.items():
        specialists = tuple(item for item in player_types if item.partner_position)
        basics = tuple(item for item in player_types if item.partner_position is None)
        if len(specialists) != 6 or len(basics) != 1:
            raise RuntimeError(f"{position.value} must have six specialists and one basic.")
        expected_partners = next(
            side for side in _POSITIONS_BY_SIDE if position in side
        )
        if any(
            sum(item.partner_position is partner for item in specialists) != 2
            for partner in expected_partners
            if partner is not position
        ):
            raise RuntimeError(f"{position.value} must have two specialists per partner.")

    for positions in _POSITIONS_BY_SIDE:
        perks = [
            item.perk
            for item in _SPECIALISTS
            if item.position in positions and item.perk is not None
        ]
        if len({perk.name for perk in perks}) != len(perks):
            raise RuntimeError("Specialist perk names must be unique within each side.")
    kinds = [item.perk.kind for item in _SPECIALISTS if item.perk is not None]
    if len(set(kinds)) != len(kinds) or set(kinds) != set(FootballPlayerPerkKind):
        raise RuntimeError("Every player perk kind must belong to exactly one specialist.")
    if set(_SPECIALIST_BASE_STATS) != {item.type_id for item in _SPECIALISTS}:
        raise RuntimeError("Every specialist needs base stats, and only specialists.")

    # Basic is the weakest overall even with the spread: the worst roll of any
    # specialist must still beat the best roll of its position's Basic.
    for position, player_types in PLAYER_TYPES_BY_POSITION.items():
        basic = next(item for item in player_types if item.partner_position is None)
        best_basic = prospect_score_range(basic)[1]
        for item in player_types:
            if item.partner_position is not None and prospect_score_range(item)[0] <= best_basic:
                raise RuntimeError(
                    f"{item.name} can roll below the best {basic.name}; Basic must be "
                    "the weakest overall."
                )


def prospect_score(power: float, volatility: float, stamina: float) -> float:
    """Overall strength, used only to check that Basic is weakest (never shown)."""
    return power + 40 * stamina - 100 * volatility


def _spread_bounds(base: int, spread: int, low: int, high: int) -> tuple[int, int]:
    return max(low, base - spread), min(high, base + spread)


def prospect_score_range(player_type: FootballPlayerType) -> tuple[float, float]:
    """(worst, best) score a prospect of this type can roll, clamps included."""
    power = _spread_bounds(player_type.base_power, POWER_SPREAD, 0, 1000)
    volatility = _spread_bounds(
        player_type.base_volatility_pct, VOLATILITY_SPREAD_PCT, MIN_VOLATILITY_PCT, 100
    )
    stamina = _spread_bounds(player_type.base_stamina_pct, STAMINA_SPREAD_PCT, 0, MAX_STAMINA_PCT)
    return (
        prospect_score(power[0], volatility[1] / 100, stamina[0] / 100),
        prospect_score(power[1], volatility[0] / 100, stamina[1] / 100),
    )


_validate_catalog()


PLAYER_TYPES_BY_PERK: Mapping[FootballPlayerPerkKind, FootballPlayerType] = MappingProxyType(
    {item.perk.kind: item for item in _SPECIALISTS if item.perk is not None}
)


def player_perk(kind: FootballPlayerPerkKind) -> FootballPlayerPerk:
    perk = PLAYER_TYPES_BY_PERK[kind].perk
    assert perk is not None
    return perk


def player_type_for_id(type_id: str) -> FootballPlayerType:
    try:
        return PLAYER_TYPES_BY_ID[type_id]
    except (KeyError, TypeError) as error:
        raise ValueError(f"Unknown player type identifier: {type_id!r}.") from error


def player_types_for_position(
    position: FootballPosition,
) -> tuple[FootballPlayerType, ...]:
    if not isinstance(position, FootballPosition):
        raise ValueError("Position must be a FootballPosition.")
    return PLAYER_TYPES_BY_POSITION[position]


def player_type_offer(
    position: FootballPosition, rng: random.Random
) -> tuple[FootballPlayerType, FootballPlayerType, FootballPlayerType]:
    """Three different types, drawn with equal odds from the position's seven
    options (six specialists and Basic), in random order."""
    if not isinstance(position, FootballPosition):
        raise ValueError("Position must be a FootballPosition.")
    if not isinstance(rng, random.Random):
        raise ValueError("Offer generation requires a random.Random instance.")
    first, second, third = rng.sample(player_types_for_position(position), 3)
    return first, second, third


def roll_prospect(
    player_type: FootballPlayerType,
    rng: random.Random,
    *,
    name: str | None = None,
    power_adjustment: float = 0.0,
) -> FootballPlayer:
    """A prospect of ``player_type`` with its seeded spread around the type's base.

    Power moves up to ``POWER_SPREAD`` whole points, volatility and stamina up to
    their whole-percent spreads (volatility stays at least 1%, stamina at most
    100%). ``power_adjustment`` (AI difficulty) is added after the roll.
    """
    if not isinstance(rng, random.Random):
        raise ValueError("Prospect rolls require a random.Random instance.")
    power = player_type.base_power + rng.randint(-POWER_SPREAD, POWER_SPREAD)
    volatility = max(
        MIN_VOLATILITY_PCT,
        player_type.base_volatility_pct + rng.randint(-VOLATILITY_SPREAD_PCT, VOLATILITY_SPREAD_PCT),
    )
    stamina = min(
        MAX_STAMINA_PCT,
        max(0, player_type.base_stamina_pct + rng.randint(-STAMINA_SPREAD_PCT, STAMINA_SPREAD_PCT)),
    )
    return player_from_type(
        player_type, name=name, power=float(power) + power_adjustment,
        volatility=volatility / 100, stamina=stamina / 100,
    )


def player_from_type(
    player_type: FootballPlayerType,
    *,
    name: str | None = None,
    power: float | None = None,
    volatility: float | None = None,
    stamina: float | None = None,
) -> FootballPlayer:
    """A player of ``player_type``; stats left out are the type's base stats."""
    if player_type_for_id(player_type.type_id) is not player_type:
        raise ValueError("Player type must belong to the validated catalog.")
    return FootballPlayer(
        name=player_type.name if name is None else name,
        position=player_type.position,
        power=float(player_type.base_power) if power is None else power,
        volatility=player_type.base_volatility if volatility is None else volatility,
        stamina=player_type.base_stamina if stamina is None else stamina,
        player_type_id=player_type.type_id,
    )


def player_contribution_modifier(
    player: FootballPlayer,
    contributing_players: tuple[FootballPlayer, ...],
    coach_modifier: float,
) -> float:
    """Add coach and independent partnership bonuses, with an upper-only cap."""
    if isinstance(coach_modifier, bool) or not isinstance(coach_modifier, (int, float)):
        raise ValueError("Coach modifier must be numeric.")
    if not isfinite(coach_modifier):
        raise ValueError("Coach modifier must be finite.")
    player_type = (
        player_type_for_id(player.player_type_id)
        if player.player_type_id is not None
        else None
    )
    has_partner = (
        player_type is not None
        and player_type.partner_position is not None
        and any(
            other is not player
            and other.position is player_type.partner_position
            for other in contributing_players
        )
    )
    partnership_bonus = PARTNERSHIP_BONUS if has_partner else 0.0
    return min(
        MAX_COMBINED_PLAYER_MODIFIER,
        1.0 + coach_modifier + partnership_bonus,
    )


def coached_player_power(player: FootballPlayer, coach_modifier: float) -> float:
    """Power with only the coach position modifier (no partnership, fatigue, or scheme)."""
    return player.power * player_contribution_modifier(player, (player,), coach_modifier)
