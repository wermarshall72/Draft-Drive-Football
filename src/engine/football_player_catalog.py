"""Validated player-type catalog and shared partnership contribution rules."""

from __future__ import annotations

import random
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Mapping

from src.engine.football import FootballPlayer, FootballPosition

PLAYER_BASE_POWER = 50.0
PLAYER_BASE_VOLATILITY = 0.10
PLAYER_BASE_STAMINA = 0.50
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


@dataclass(frozen=True)
class FootballPlayerPerk:
    """Descriptive future perk; it has no executable gameplay behavior."""

    name: str
    trigger: str
    effect: str
    duration: str
    reset: str
    dependency: str = (
        "Requires future player-perk execution and temporary-effect tracking."
    )

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.name,
                self.trigger,
                self.effect,
                self.duration,
                self.reset,
                self.dependency,
            )
        ):
            raise ValueError("Player perk descriptions must be non-empty.")

    @property
    def display_text(self) -> str:
        return (
            f"{self.name}. Trigger: {self.trigger} Effect: {self.effect} "
            f"Duration: {self.duration} Reset: {self.reset} "
            f"Dependency: {self.dependency}"
        )


@dataclass(frozen=True)
class FootballPlayerType:
    """Immutable identity and display metadata for one player archetype."""

    type_id: str
    position: FootballPosition
    name: str
    partner_position: FootballPosition | None
    perk: FootballPlayerPerk | None

    def __post_init__(self) -> None:
        if not isinstance(self.type_id, str) or not self.type_id.strip():
            raise ValueError("Player type identifier must be non-empty.")
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
            raise ValueError("Specialist player types require a descriptive perk.")


def _specialist(
    type_id: str,
    position: FootballPosition,
    partner: FootballPosition,
    name: str,
    perk_name: str,
    trigger: str,
    effect: str,
    duration: str,
    reset: str,
) -> FootballPlayerType:
    return FootballPlayerType(
        type_id,
        position,
        name,
        partner,
        FootballPlayerPerk(perk_name, trigger, effect, duration, reset),
    )


_SPECIALISTS = (
    _specialist("qb_rb_mesh_reader", FootballPosition.QB, FootballPosition.RB, "Mesh Reader", "Mesh Reclaim", "a QB+RB PA Pass is completed", "the next play featuring that RB gets +2 power", "one play", "each offensive drive"),
    _specialist("qb_rb_option_ledger", FootballPosition.QB, FootballPosition.RB, "Option Ledger", "Option Ledger", "the QB participates in three different play types in a drive", "+1 QB power per different play type on the team's next drive", "one drive", "each game"),
    _specialist("qb_wr_boundary_captain", FootballPosition.QB, FootballPosition.WR, "Boundary Captain", "Boundary Hold", "a QB+WR play gains at least 15 yards", "reduce the WR's volatility by 0.05", "rest of game", "once per game"),
    _specialist("qb_wr_vertical_architect", FootballPosition.QB, FootballPosition.WR, "Vertical Architect", "Route Map", "a QB+WR play converts on third down", "+2 QB power on the next play featuring the QB", "one play", "each half"),
    _specialist("qb_oline_pocket_anchor", FootballPosition.QB, FootballPosition.O_LINE, "Pocket Anchor", "Pocket Archive", "the QB participates in four plays in one drive without a turnover", "+3 QB power on the next drive", "one drive", "each game"),
    _specialist("qb_oline_silent_count", FootballPosition.QB, FootballPosition.O_LINE, "Silent-Count Caller", "Silent Count", "a QB+O-line play is used on fourth down", "the QB's stamina is treated as 0.1 higher for that play", "one play", "each game"),
    _specialist("rb_qb_checkdown_back", FootballPosition.RB, FootballPosition.QB, "Checkdown Back", "Checkdown Cache", "a QB+RB play gains at least 8 yards", "+2 RB power on the next play featuring the RB", "one play", "each drive"),
    _specialist("rb_qb_option_keeper", FootballPosition.RB, FootballPosition.QB, "Option Keeper", "Keep Read", "the offense completes a drive with at least two QB+RB plays", "+0.05 RB stamina", "rest of game", "once per game"),
    _specialist("rb_wr_orbit_runner", FootballPosition.RB, FootballPosition.WR, "Orbit Runner", "Orbit Return", "an RB+WR play converts on third down", "the next offensive drive starts with +1 yard of field position", "until next drive starts", "each half"),
    _specialist("rb_wr_slot_outlet", FootballPosition.RB, FootballPosition.WR, "Slot Outlet", "Slot Leak", "an RB+WR play is called on second down", "+2 RB power on that play if the offense is behind", "one play", "each drive"),
    _specialist("rb_oline_gap_runner", FootballPosition.RB, FootballPosition.O_LINE, "Gap Runner", "Cutback Draft", "the RB participates in three plays in one drive", "+2 RB power on the next drive", "one drive", "each game"),
    _specialist("rb_oline_pull_guard_back", FootballPosition.RB, FootballPosition.O_LINE, "Pull-Guard Back", "Pull-Guard Reserve", "an RB Run gains positive yards after halftime", "+0.05 RB stamina", "rest of game", "once per game"),
    _specialist("wr_qb_route_technician", FootballPosition.WR, FootballPosition.QB, "Route Technician", "Hot Route", "a QB+WR pass gains at least 10 yards", "+2 WR power on the next QB+WR play", "one play", "each drive"),
    _specialist("wr_qb_vertical_threat", FootballPosition.WR, FootballPosition.QB, "Vertical Threat", "Back-Shoulder Recall", "the team completes a QB+WR pass in the opponent's half", "reduce the QB's volatility by 0.05", "rest of game", "once per game"),
    _specialist("wr_rb_screen_outlet", FootballPosition.WR, FootballPosition.RB, "Screen Outlet", "Motion Swap", "an RB+WR play earns a first down", "+2 WR power on the next play featuring the WR", "one play", "each drive"),
    _specialist("wr_rb_motion_receiver", FootballPosition.WR, FootballPosition.RB, "Motion Receiver", "Check Release", "the WR participates in plays on consecutive downs", "+0.05 WR stamina", "rest of game", "once per half"),
    _specialist("wr_oline_boundary_route", FootballPosition.WR, FootballPosition.O_LINE, "Boundary Route", "Screen Set", "a QB+WR play is called immediately after an O-line+WR Screen Pass", "+3 WR power on that QB+WR play", "one play", "each drive"),
    _specialist("wr_oline_release_specialist", FootballPosition.WR, FootballPosition.O_LINE, "Release Specialist", "Screen Scout", "the offense uses an O-line+WR Screen Pass on first down", "+2 WR power on the next play if it is also a pass", "one play", "each game"),
    _specialist("oline_qb_pass_set_guard", FootballPosition.O_LINE, FootballPosition.QB, "Pass-Set Guard", "Pass-Set Reserve", "a QB+O-line play is called on third down", "reduce the QB's volatility by 0.05 for that play", "one play", "each drive"),
    _specialist("oline_qb_pocket_tempo", FootballPosition.O_LINE, FootballPosition.QB, "Pocket Tempo", "Pocket Tempo", "the QB gains a first down on a play involving the O-line", "+2 O-line power on the next play featuring the O-line", "one play", "each half"),
    _specialist("oline_rb_drive_blocker", FootballPosition.O_LINE, FootballPosition.RB, "Drive Blocker", "Double-Team Index", "the offense calls two RB Runs in a row", "+2 O-line power on the next play involving the O-line", "one play", "each drive"),
    _specialist("oline_rb_pull_guard", FootballPosition.O_LINE, FootballPosition.RB, "Pull Guard", "Pull-Guard Pivot", "an RB Run gains at least 5 yards", "+0.05 RB stamina", "rest of game", "once per game"),
    _specialist("oline_wr_screen_setter", FootballPosition.O_LINE, FootballPosition.WR, "Screen Setter", "Screen Wall", "an O-line+WR Screen Pass gains positive yards", "+2 O-line power on the next offensive play", "one play", "each drive"),
    _specialist("oline_wr_space_creator", FootballPosition.O_LINE, FootballPosition.WR, "Space Creator", "Wide-Lane Queue", "an O-line+WR play converts on third down", "add +1 yard to the next play's result", "one play", "each half"),
    _specialist("dline_lb_a_gap_plug", FootballPosition.D_LINE, FootballPosition.LINEBACKERS, "A-Gap Plug", "Box Reset", "the opponent runs an RB Run against the RB Run scheme", "+2 D-line power on the defense's next snap", "one snap", "each drive"),
    _specialist("dline_lb_edge_setter", FootballPosition.D_LINE, FootballPosition.LINEBACKERS, "Edge Setter", "Front Forecast", "the D-line contributes to two consecutive defensive snaps", "+0.05 D-line stamina", "rest of game", "once per half"),
    _specialist("dline_cb_contain_end", FootballPosition.D_LINE, FootballPosition.CORNERBACKS, "Contain End", "Screen Exchange", "the opponent calls a Screen Pass against the Screen Pass scheme", "+2 D-line power on the next defensive snap", "one snap", "each drive"),
    _specialist("dline_cb_rush_contain", FootballPosition.D_LINE, FootballPosition.CORNERBACKS, "Rush Contain", "Boundary Hold", "a D-line+cornerback scheme is selected on third down", "reduce the opponent's next-play volatility by 0.05", "one snap", "each game"),
    _specialist("dline_s_interior_rusher", FootballPosition.D_LINE, FootballPosition.SAFETIES, "Interior Rusher", "Stunt Queue", "a Medium Pass scheme faces any pass play", "+2 D-line power on that snap", "one snap", "each drive"),
    _specialist("dline_s_stunt_tackle", FootballPosition.D_LINE, FootballPosition.SAFETIES, "Stunt Tackle", "Twist Recall", "a D-line+Safety scheme faces a play that gains 0 yards or less", "+0.05 D-line stamina", "rest of game", "once per game"),
    _specialist("lb_dline_front_fit_back", FootballPosition.LINEBACKERS, FootballPosition.D_LINE, "Front-Fit Back", "Front-Fit Shuffle", "a D-line+Linebacker scheme faces an RB Run", "+2 linebacker power on the next defensive snap", "one snap", "each drive"),
    _specialist("lb_dline_run_fit_captain", FootballPosition.LINEBACKERS, FootballPosition.D_LINE, "Run-Fit Captain", "Run-Fit Recall", "the opponent earns a first down on a run", "+0.05 linebacker stamina", "rest of game", "once per half"),
    _specialist("lb_cb_nickel_rover", FootballPosition.LINEBACKERS, FootballPosition.CORNERBACKS, "Nickel Rover", "Hook Exchange", "a Linebacker+Cornerback scheme faces a Short Pass", "+2 linebacker power on that snap", "one snap", "each drive"),
    _specialist("lb_cb_hook_curl_reader", FootballPosition.LINEBACKERS, FootballPosition.CORNERBACKS, "Hook-Curl Reader", "Short-Route Cut", "the opponent completes a pass for fewer than 5 yards", "reduce the opponent's next-play power by 2", "one snap", "each game"),
    _specialist("lb_s_robber_backer", FootballPosition.LINEBACKERS, FootballPosition.SAFETIES, "Robber Backer", "Robber Cache", "a Linebacker+Safety scheme faces a PA Pass", "+2 linebacker power on the next defensive snap", "one snap", "each drive"),
    _specialist("lb_s_green_dog_blitzer", FootballPosition.LINEBACKERS, FootballPosition.SAFETIES, "Green-Dog Blitzer", "Delayed Rotation", "the opponent converts third down while a linebacker is among the selected defenders", "+0.05 linebacker stamina", "rest of game", "once per game"),
    _specialist("cb_dline_edge_corner", FootballPosition.CORNERBACKS, FootballPosition.D_LINE, "Edge Corner", "Edge Rotation", "a D-line+Cornerback scheme faces a Screen Pass", "+2 cornerback power on that snap", "one snap", "each drive"),
    _specialist("cb_dline_force_corner", FootballPosition.CORNERBACKS, FootballPosition.D_LINE, "Force Corner", "Contain Search", "the opponent runs against a D-line+Cornerback scheme", "reduce the opponent's next-play power by 2", "one snap", "each game"),
    _specialist("cb_lb_nickel_matcher", FootballPosition.CORNERBACKS, FootballPosition.LINEBACKERS, "Nickel Matcher", "Nickel Cut", "a Linebacker+Cornerback scheme faces a Short Pass on third down", "+2 cornerback power on that snap", "one snap", "each drive"),
    _specialist("cb_lb_underneath_bracket", FootballPosition.CORNERBACKS, FootballPosition.LINEBACKERS, "Underneath Bracket", "Zone Pivot", "the opponent completes a pass for at least 10 yards against a Linebacker+Cornerback scheme", "+0.05 cornerback stamina", "rest of game", "once per half"),
    _specialist("cb_s_deep_half_corner", FootballPosition.CORNERBACKS, FootballPosition.SAFETIES, "Deep-Half Corner", "Deep Lock", "a Safety+Cornerback scheme faces a Deep Pass", "reduce the opponent's volatility by 0.05 on that snap", "one snap", "each drive"),
    _specialist("cb_s_trail_corner", FootballPosition.CORNERBACKS, FootballPosition.SAFETIES, "Trail Corner", "Trail Filter", "the opponent completes a pass against a Safety+Cornerback scheme", "+2 cornerback power on the defense's next snap", "one snap", "each drive"),
    _specialist("s_dline_post_safety", FootballPosition.SAFETIES, FootballPosition.D_LINE, "Post Safety", "Post Rotation", "a Safety+D-line scheme faces a Medium Pass", "+2 safety power on that snap", "one snap", "each drive"),
    _specialist("s_dline_blitz_safety", FootballPosition.SAFETIES, FootballPosition.D_LINE, "Blitz Safety", "Tackle Box", "an RB Run gains positive yards against a Safety+D-line scheme", "+0.05 safety stamina", "rest of game", "once per half"),
    _specialist("s_lb_box_safety", FootballPosition.SAFETIES, FootballPosition.LINEBACKERS, "Box Safety", "Box Signal", "a Safety+Linebacker scheme faces a PA Pass", "reduce the opponent's next-play power by 2", "one snap", "each drive"),
    _specialist("s_lb_robber_safety", FootballPosition.SAFETIES, FootballPosition.LINEBACKERS, "Robber Safety", "Robber Exchange", "a PA Pass gains at least 10 yards against a Safety+Linebacker scheme", "+2 safety power on the next defensive snap", "one snap", "each drive"),
    _specialist("s_cb_boundary_safety", FootballPosition.SAFETIES, FootballPosition.CORNERBACKS, "Boundary Safety", "Boundary Lock", "a Safety+Cornerback scheme faces a Deep Pass", "+2 safety power on that snap", "one snap", "each drive"),
    _specialist("s_cb_range_safety", FootballPosition.SAFETIES, FootballPosition.CORNERBACKS, "Range Safety", "Range Recall", "a Safety+Cornerback scheme faces a Short Pass", "reduce the opponent's next-play volatility by 0.05", "one snap", "each game"),
)

BASIC_PLAYER_TYPES = tuple(
    FootballPlayerType(f"basic_{position.value.lower()}", position, f"Basic {position.value.replace('_', ' ').title()}", None, None)
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
        if len({perk.display_text for perk in perks}) != len(perks):
            raise RuntimeError("Specialist perk descriptions must be unique within each side.")


_validate_catalog()


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
    if not isinstance(position, FootballPosition):
        raise ValueError("Position must be a FootballPosition.")
    if not isinstance(rng, random.Random):
        raise ValueError("Offer generation requires a random.Random instance.")
    specialists = tuple(
        item
        for item in player_types_for_position(position)
        if item.partner_position is not None
    )
    basic = next(
        item
        for item in player_types_for_position(position)
        if item.partner_position is None
    )
    first, second = rng.sample(specialists, 2)
    return first, second, basic


def player_from_type(
    player_type: FootballPlayerType,
    *,
    name: str | None = None,
    power: float = PLAYER_BASE_POWER,
    volatility: float = PLAYER_BASE_VOLATILITY,
    stamina: float = PLAYER_BASE_STAMINA,
) -> FootballPlayer:
    if player_type_for_id(player_type.type_id) is not player_type:
        raise ValueError("Player type must belong to the validated catalog.")
    return FootballPlayer(
        name=player_type.name if name is None else name,
        position=player_type.position,
        power=power,
        volatility=volatility,
        stamina=stamina,
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
