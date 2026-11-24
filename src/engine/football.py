"""Validated domain models for interactive football matches.

This module is intentionally separate from the legacy auto-battler models.
Future match resolution must create a ``random.Random`` instance from the
match's ``random_seed`` and use that instance for all match randomness.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Real
from types import MappingProxyType
from typing import Any, Mapping

from src.engine.save_data import (
    UnsupportedSave,
    build,
    enum_value,
    required,
    items,
    lookup,
    optional,
    optional_enum,
)


class FootballPosition(str, Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    O_LINE = "O_LINE"
    D_LINE = "D_LINE"
    LINEBACKERS = "LINEBACKERS"
    CORNERBACKS = "CORNERBACKS"
    SAFETIES = "SAFETIES"


class FootballTeamSide(str, Enum):
    TEAM_A = "team_a"
    TEAM_B = "team_b"


class FootballMatchStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class FootballAwaitedAction(str, Enum):
    OFFENSIVE_PLAY = "offensive_play"
    DEFENSIVE_SCHEME = "defensive_scheme"
    FOURTH_DOWN_DECISION = "fourth_down_decision"
    CONVERSION = "conversion"


class FootballConversionAction(str, Enum):
    EXTRA_POINT = "extra_point"
    TWO_POINT = "two_point"


class FootballAutomaticAction(str, Enum):
    KICKOFF = "kickoff"


class FootballTurnoverType(str, Enum):
    INTERCEPTION = "interception"
    FUMBLE = "fumble"


class FootballCardFamily(str, Enum):
    RB_RUN = "rb_run"
    SCREEN_PASS = "screen_pass"
    PA_PASS = "pa_pass"
    SHORT_PASS = "short_pass"
    MEDIUM_PASS = "medium_pass"
    DEEP_PASS = "deep_pass"

    @property
    def label(self) -> str:
        return {
            FootballCardFamily.RB_RUN: "RB Run",
            FootballCardFamily.SCREEN_PASS: "Screen Pass",
            FootballCardFamily.PA_PASS: "Play-Action Pass",
            FootballCardFamily.SHORT_PASS: "Short Pass",
            FootballCardFamily.MEDIUM_PASS: "Medium Pass",
            FootballCardFamily.DEEP_PASS: "Deep Pass",
        }[self]


class FootballCoachUpgradeKind(str, Enum):
    OFFENSE_POWER_BOOST = "offense_power_boost"
    DEFENSE_POWER_BOOST = "defense_power_boost"
    OFFENSE_VOLATILITY_REDUCTION = "offense_volatility_reduction"
    DEFENSE_VOLATILITY_REDUCTION = "defense_volatility_reduction"
    OFFENSE_STAMINA_BOOST = "offense_stamina_boost"
    DEFENSE_STAMINA_BOOST = "defense_stamina_boost"
    FUTURE_SHOP_AP = "future_shop_ap"
    OFFENSIVE_PLAY_CLOCK_DELTA = "offensive_play_clock_delta"
    OFFENSIVE_FAMILY_YARDAGE_DELTA = "offensive_family_yardage_delta"
    DEFENSIVE_FAMILY_YARDAGE_REDUCTION = "defensive_family_yardage_reduction"
    INTERCEPTION_RISK_REDUCTION = "interception_risk_reduction"
    FIELD_GOAL_ACCURACY_BONUS = "field_goal_accuracy_bonus"
    BLOCKED_KICK_RISK_REDUCTION = "blocked_kick_risk_reduction"
    PUNT_RETURN_YARDS_BONUS = "punt_return_yards_bonus"
    KICKOFF_RETURN_YARDS_BONUS = "kickoff_return_yards_bonus"
    BYE_WEEK = "bye_week"


@dataclass(frozen=True)
class FootballCoachUpgradeEffect:
    """A typed, run-owned coach effect consumed by the shop and match engine."""

    upgrade_id: str
    kind: FootballCoachUpgradeKind
    magnitude: float
    family: FootballCardFamily | None = None

    def __post_init__(self) -> None:
        _validate_name(self.upgrade_id, "Coach upgrade identifier")
        if not isinstance(self.kind, FootballCoachUpgradeKind):
            raise ValueError("Coach upgrade kind must be a FootballCoachUpgradeKind.")
        if isinstance(self.magnitude, bool):
            raise ValueError("Coach upgrade magnitude must be numeric.")
        _validate_finite_number(self.magnitude, "Coach upgrade magnitude")
        if self.kind is FootballCoachUpgradeKind.BYE_WEEK:
            if self.magnitude != 0:
                raise ValueError("Bye Week must not have a numeric match effect.")
        elif self.kind in (
            FootballCoachUpgradeKind.OFFENSIVE_PLAY_CLOCK_DELTA,
            FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
        ):
            if self.magnitude == 0:
                raise ValueError("Coach upgrade magnitude must not be zero.")
        elif self.magnitude <= 0:
            raise ValueError("Coach upgrade magnitude must be positive.")
        if self.kind is FootballCoachUpgradeKind.FUTURE_SHOP_AP and (
            self.magnitude <= 0 or int(self.magnitude) != self.magnitude
        ):
            raise ValueError("Future-shop AP bonuses must be positive whole numbers.")
        family_required = self.kind in (
            FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
            FootballCoachUpgradeKind.DEFENSIVE_FAMILY_YARDAGE_REDUCTION,
        )
        if family_required != (self.family is not None):
            raise ValueError(
                "Only family-specific coach upgrades may specify a card family."
            )
        if self.family is not None and not isinstance(self.family, FootballCardFamily):
            raise ValueError("Coach upgrade family must be a FootballCardFamily.")

    def to_save_data(self) -> str:
        """Saved by its stable upgrade ID; magnitudes come from the current catalog."""
        return self.upgrade_id

    @classmethod
    def from_save_data(cls, data: Any) -> "FootballCoachUpgradeEffect":
        from src.engine.football_shop import COACH_UPGRADE_CATALOG

        effects = {
            card.coach_upgrade_effect.upgrade_id: card.coach_upgrade_effect
            for card in COACH_UPGRADE_CATALOG
            if card.coach_upgrade_effect is not None
        }
        return lookup(effects, data, "coach upgrade")


class OffensivePlayAction(str, Enum):
    RB_RUN = "rb_run"
    SCREEN_PASS = "screen_pass"
    PA_PASS = "pa_pass"
    SHORT_PASS = "short_pass"
    MEDIUM_PASS = "medium_pass"
    DEEP_PASS = "deep_pass"
    QB_SNEAK = "qb_sneak"
    JET_SWEEP = "jet_sweep"
    QUICK_OUT = "quick_out"
    POWER_TOSS = "power_toss"
    BUBBLE_SCREEN = "bubble_screen"
    BOOTLEG_KEEPER = "bootleg_keeper"
    SLOT_SLANT = "slot_slant"
    DEEP_DIG = "deep_dig"
    GO_ROUTE = "go_route"
    INSIDE_ZONE = "inside_zone"
    COUNTER_RUN = "counter_run"
    TUNNEL_SCREEN = "tunnel_screen"
    RB_SCREEN = "rb_screen"
    WR_SCREEN = "wr_screen"
    DELAY_SCREEN = "delay_screen"
    BOOT_FLOOD = "boot_flood"
    POST_WHEEL = "post_wheel"
    PA_CROSSER = "pa_crosser"
    QB_KEEPER_PA = "qb_keeper_pa"
    STICK_CONCEPT = "stick_concept"
    RB_ANGLE = "rb_angle"
    QUICK_HITCH = "quick_hitch"
    DIG_ROUTE = "dig_route"
    CURL_COMEBACK = "curl_comeback"
    SEAM_PASS = "seam_pass"
    CROSSING_ROUTE = "crossing_route"
    POST_ROUTE = "post_route"
    CORNER_ROUTE = "corner_route"
    DOUBLE_MOVE = "double_move"
    GO_BALL = "go_ball"


class DefensiveSchemeAction(str, Enum):
    RB_RUN = "rb_run"
    SCREEN_PASS = "screen_pass"
    PA_PASS = "pa_pass"
    SHORT_PASS = "short_pass"
    MEDIUM_PASS = "medium_pass"
    DEEP_PASS = "deep_pass"
    GOAL_LINE_FRONT = "goal_line_front"
    COVER_TWO_SHELL = "cover_two_shell"
    FIRE_ZONE_BLITZ = "fire_zone_blitz"
    SPILL_FRONT = "spill_front"
    PERIMETER_CHECK = "perimeter_check"
    READ_REACT = "read_react"
    NICKEL_UNDER = "nickel_under"
    TWO_HIGH_PRESSURE = "two_high_pressure"
    QUARTERS_COVERAGE = "quarters_coverage"
    BEAR_FRONT = "bear_front"
    MAN_PRESS = "man_press"
    SCREEN_BLITZ = "screen_blitz"
    ROBBER_COVERAGE = "robber_coverage"
    SINKING_ZONE = "sinking_zone"
    TWO_MAN_UNDER = "two_man_under"
    HOT_BLITZ = "hot_blitz"
    THREE_DEEP_BLITZ = "three_deep_blitz"
    PREVENT_COVERAGE = "prevent_coverage"


class FootballBonusCardAction(str, Enum):
    OFFENSIVE_DRAW = "offensive_draw"
    DEFENSIVE_DRAW = "defensive_draw"
    OPPONENT_DISCARD = "opponent_discard"
    OFFENSIVE_DRAW_DISCARD = "offensive_draw_discard"
    DEFENSIVE_DRAW_DISCARD = "defensive_draw_discard"
    CHALLENGE = "challenge"


class FootballFourthDownAction(str, Enum):
    GO_FOR_IT = "go_for_it"
    PUNT = "punt"
    FIELD_GOAL = "field_goal"


OFFENSIVE_PLAY_FAMILIES = MappingProxyType(
    {
        OffensivePlayAction.RB_RUN: FootballCardFamily.RB_RUN,
        OffensivePlayAction.QB_SNEAK: FootballCardFamily.RB_RUN,
        OffensivePlayAction.JET_SWEEP: FootballCardFamily.RB_RUN,
        OffensivePlayAction.POWER_TOSS: FootballCardFamily.RB_RUN,
        OffensivePlayAction.INSIDE_ZONE: FootballCardFamily.RB_RUN,
        OffensivePlayAction.COUNTER_RUN: FootballCardFamily.RB_RUN,
        OffensivePlayAction.SCREEN_PASS: FootballCardFamily.SCREEN_PASS,
        OffensivePlayAction.BUBBLE_SCREEN: FootballCardFamily.SCREEN_PASS,
        OffensivePlayAction.TUNNEL_SCREEN: FootballCardFamily.SCREEN_PASS,
        OffensivePlayAction.RB_SCREEN: FootballCardFamily.SCREEN_PASS,
        OffensivePlayAction.WR_SCREEN: FootballCardFamily.SCREEN_PASS,
        OffensivePlayAction.DELAY_SCREEN: FootballCardFamily.SCREEN_PASS,
        OffensivePlayAction.PA_PASS: FootballCardFamily.PA_PASS,
        OffensivePlayAction.BOOTLEG_KEEPER: FootballCardFamily.PA_PASS,
        OffensivePlayAction.BOOT_FLOOD: FootballCardFamily.PA_PASS,
        OffensivePlayAction.POST_WHEEL: FootballCardFamily.PA_PASS,
        OffensivePlayAction.PA_CROSSER: FootballCardFamily.PA_PASS,
        OffensivePlayAction.QB_KEEPER_PA: FootballCardFamily.PA_PASS,
        OffensivePlayAction.SHORT_PASS: FootballCardFamily.SHORT_PASS,
        OffensivePlayAction.QUICK_OUT: FootballCardFamily.SHORT_PASS,
        OffensivePlayAction.SLOT_SLANT: FootballCardFamily.SHORT_PASS,
        OffensivePlayAction.STICK_CONCEPT: FootballCardFamily.SHORT_PASS,
        OffensivePlayAction.RB_ANGLE: FootballCardFamily.SHORT_PASS,
        OffensivePlayAction.QUICK_HITCH: FootballCardFamily.SHORT_PASS,
        OffensivePlayAction.MEDIUM_PASS: FootballCardFamily.MEDIUM_PASS,
        OffensivePlayAction.DEEP_DIG: FootballCardFamily.MEDIUM_PASS,
        OffensivePlayAction.DIG_ROUTE: FootballCardFamily.MEDIUM_PASS,
        OffensivePlayAction.CURL_COMEBACK: FootballCardFamily.MEDIUM_PASS,
        OffensivePlayAction.SEAM_PASS: FootballCardFamily.MEDIUM_PASS,
        OffensivePlayAction.CROSSING_ROUTE: FootballCardFamily.MEDIUM_PASS,
        OffensivePlayAction.DEEP_PASS: FootballCardFamily.DEEP_PASS,
        OffensivePlayAction.GO_ROUTE: FootballCardFamily.DEEP_PASS,
        OffensivePlayAction.POST_ROUTE: FootballCardFamily.DEEP_PASS,
        OffensivePlayAction.CORNER_ROUTE: FootballCardFamily.DEEP_PASS,
        OffensivePlayAction.DOUBLE_MOVE: FootballCardFamily.DEEP_PASS,
        OffensivePlayAction.GO_BALL: FootballCardFamily.DEEP_PASS,
    }
)

DEFENSIVE_SCHEME_FAMILIES = MappingProxyType(
    {
        DefensiveSchemeAction.RB_RUN: FootballCardFamily.RB_RUN,
        DefensiveSchemeAction.GOAL_LINE_FRONT: FootballCardFamily.RB_RUN,
        DefensiveSchemeAction.SPILL_FRONT: FootballCardFamily.RB_RUN,
        DefensiveSchemeAction.BEAR_FRONT: FootballCardFamily.RB_RUN,
        DefensiveSchemeAction.SCREEN_PASS: FootballCardFamily.SCREEN_PASS,
        DefensiveSchemeAction.PERIMETER_CHECK: FootballCardFamily.SCREEN_PASS,
        DefensiveSchemeAction.MAN_PRESS: FootballCardFamily.SCREEN_PASS,
        DefensiveSchemeAction.SCREEN_BLITZ: FootballCardFamily.SCREEN_PASS,
        DefensiveSchemeAction.PA_PASS: FootballCardFamily.PA_PASS,
        DefensiveSchemeAction.READ_REACT: FootballCardFamily.PA_PASS,
        DefensiveSchemeAction.ROBBER_COVERAGE: FootballCardFamily.PA_PASS,
        DefensiveSchemeAction.SINKING_ZONE: FootballCardFamily.PA_PASS,
        DefensiveSchemeAction.SHORT_PASS: FootballCardFamily.SHORT_PASS,
        DefensiveSchemeAction.NICKEL_UNDER: FootballCardFamily.SHORT_PASS,
        DefensiveSchemeAction.TWO_MAN_UNDER: FootballCardFamily.SHORT_PASS,
        DefensiveSchemeAction.HOT_BLITZ: FootballCardFamily.SHORT_PASS,
        DefensiveSchemeAction.MEDIUM_PASS: FootballCardFamily.MEDIUM_PASS,
        DefensiveSchemeAction.FIRE_ZONE_BLITZ: FootballCardFamily.MEDIUM_PASS,
        DefensiveSchemeAction.TWO_HIGH_PRESSURE: FootballCardFamily.MEDIUM_PASS,
        DefensiveSchemeAction.THREE_DEEP_BLITZ: FootballCardFamily.MEDIUM_PASS,
        DefensiveSchemeAction.DEEP_PASS: FootballCardFamily.DEEP_PASS,
        DefensiveSchemeAction.COVER_TWO_SHELL: FootballCardFamily.DEEP_PASS,
        DefensiveSchemeAction.QUARTERS_COVERAGE: FootballCardFamily.DEEP_PASS,
        DefensiveSchemeAction.PREVENT_COVERAGE: FootballCardFamily.DEEP_PASS,
    }
)

FOOTBALL_PLAY_MATCHUPS = MappingProxyType({
    FootballCardFamily.RB_RUN: (
        (FootballPosition.O_LINE, FootballPosition.RB),
        (FootballPosition.D_LINE, FootballPosition.LINEBACKERS),
    ),
    FootballCardFamily.SCREEN_PASS: (
        (FootballPosition.O_LINE, FootballPosition.WR),
        (FootballPosition.D_LINE, FootballPosition.CORNERBACKS),
    ),
    FootballCardFamily.PA_PASS: (
        (FootballPosition.QB, FootballPosition.RB),
        (FootballPosition.SAFETIES, FootballPosition.LINEBACKERS),
    ),
    FootballCardFamily.SHORT_PASS: (
        (FootballPosition.RB, FootballPosition.WR),
        (FootballPosition.LINEBACKERS, FootballPosition.CORNERBACKS),
    ),
    FootballCardFamily.MEDIUM_PASS: (
        (FootballPosition.QB, FootballPosition.O_LINE),
        (FootballPosition.SAFETIES, FootballPosition.D_LINE),
    ),
    FootballCardFamily.DEEP_PASS: (
        (FootballPosition.QB, FootballPosition.WR),
        (FootballPosition.SAFETIES, FootballPosition.CORNERBACKS),
    ),
})

FOOTBALL_SCHEME_MATCHUPS = MappingProxyType({
    FootballCardFamily.RB_RUN: (
        (FootballPosition.D_LINE, FootballPosition.LINEBACKERS),
    ),
    FootballCardFamily.SCREEN_PASS: (
        (FootballPosition.D_LINE, FootballPosition.CORNERBACKS),
    ),
    FootballCardFamily.PA_PASS: (
        (FootballPosition.SAFETIES, FootballPosition.LINEBACKERS),
    ),
    FootballCardFamily.SHORT_PASS: (
        (FootballPosition.LINEBACKERS, FootballPosition.CORNERBACKS),
    ),
    FootballCardFamily.MEDIUM_PASS: (
        (FootballPosition.SAFETIES, FootballPosition.D_LINE),
    ),
    FootballCardFamily.DEEP_PASS: (
        (FootballPosition.SAFETIES, FootballPosition.CORNERBACKS),
    ),
})

def matchup_for_play(
    play: OffensivePlayAction,
) -> tuple[tuple[FootballPosition, ...], tuple[FootballPosition, ...]]:
    if not isinstance(play, OffensivePlayAction) or play not in OFFENSIVE_PLAY_FAMILIES:
        raise ValueError(f"Unsupported play: {play!r}")
    return FOOTBALL_PLAY_MATCHUPS[OFFENSIVE_PLAY_FAMILIES[play]]


def matchup_for_scheme(
    scheme: DefensiveSchemeAction,
) -> tuple[tuple[FootballPosition, ...], frozenset[OffensivePlayAction]]:
    if not isinstance(scheme, DefensiveSchemeAction) or scheme not in DEFENSIVE_SCHEME_FAMILIES:
        raise ValueError(f"Unsupported scheme: {scheme!r}")
    family = DEFENSIVE_SCHEME_FAMILIES[scheme]
    contributors = FOOTBALL_SCHEME_MATCHUPS[family][0]
    counters = frozenset(
        play
        for play, play_family in OFFENSIVE_PLAY_FAMILIES.items()
        if play_family is family
    )
    return contributors, counters


@dataclass(frozen=True)
class FootballCardCopy:
    """One owned copy of a play or scheme, identified independently of its type."""

    copy_id: str
    card_id: str

    def __post_init__(self) -> None:
        _validate_name(self.copy_id, "Card copy identifier")
        _validate_name(self.card_id, "Card identifier")

    def to_save_data(self) -> list[str]:
        return [self.copy_id, self.card_id]

    @classmethod
    def from_save_data(cls, data: Any) -> "FootballCardCopy":
        from src.engine.football_decks import (
            BONUS_CARD_CATALOG,
            DEFENSIVE_SCHEME_CATALOG,
            OFFENSIVE_PLAY_CATALOG,
        )

        if (
            not isinstance(data, list)
            or len(data) != 2
            or not all(isinstance(value, str) for value in data)
        ):
            raise UnsupportedSave("A card copy must be [copy_id, card_id].")
        copy_id, card_id = data
        if not any(
            card_id in catalog
            for catalog in (
                OFFENSIVE_PLAY_CATALOG,
                DEFENSIVE_SCHEME_CATALOG,
                BONUS_CARD_CATALOG,
            )
        ):
            raise UnsupportedSave(f"Unknown card: {card_id!r}.")
        return build("card copy", lambda: cls(copy_id, card_id))


def card_copies_to_save_data(cards: tuple[FootballCardCopy, ...]) -> list[list[str]]:
    return [card.to_save_data() for card in cards]


def card_copies_from_save_data(data: Any, what: str) -> tuple[FootballCardCopy, ...]:
    return tuple(FootballCardCopy.from_save_data(item) for item in items(data, what))


@dataclass(frozen=True)
class FootballDeckState:
    """Owned cards and their match-local draw, hand, and discard zones."""

    owned: tuple[FootballCardCopy, ...]
    draw_pile: tuple[FootballCardCopy, ...] = ()
    hand: tuple[FootballCardCopy, ...] = ()
    discard_pile: tuple[FootballCardCopy, ...] = ()

    def __post_init__(self) -> None:
        zones = (self.owned, self.draw_pile, self.hand, self.discard_pile)
        if any(
            not isinstance(zone, tuple)
            or any(not isinstance(card, FootballCardCopy) for card in zone)
            for zone in zones
        ):
            raise ValueError("Deck cards and zones must be immutable tuples of card copies.")
        owned_ids = [card.copy_id for card in self.owned]
        if len(owned_ids) != len(set(owned_ids)):
            raise ValueError("Owned card copy identifiers must be unique.")
        zone_cards = self.draw_pile + self.hand + self.discard_pile
        zone_ids = [card.copy_id for card in zone_cards]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("A card copy cannot be in more than one deck zone.")
        if zone_ids and set(zone_ids) != set(owned_ids):
            raise ValueError("Every owned card copy must be in exactly one deck zone.")

    def to_save_data(self) -> dict[str, Any]:
        """Owned copies in order; each zone lists copy IDs in its exact order."""
        return {
            "owned": card_copies_to_save_data(self.owned),
            "draw_pile": [card.copy_id for card in self.draw_pile],
            "hand": [card.copy_id for card in self.hand],
            "discard_pile": [card.copy_id for card in self.discard_pile],
        }

    @classmethod
    def from_save_data(cls, data: Any) -> "FootballDeckState":
        owned = card_copies_from_save_data(required(data, "owned", list, "Deck"), "Deck cards")
        by_copy_id = {card.copy_id: card for card in owned}

        def zone(name: str) -> tuple[FootballCardCopy, ...]:
            return tuple(
                lookup(by_copy_id, copy_id, f"card copy in the {name}")
                for copy_id in items(required(data, name, list, "Deck"), f"Deck {name}")
            )

        return build(
            "deck",
            lambda: cls(owned, zone("draw_pile"), zone("hand"), zone("discard_pile")),
        )


def _validate_name(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")


def _validate_finite_number(value: Real, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be a finite number.")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{field_name} must be a finite number.")


def _validate_nonnegative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")


@dataclass(frozen=True)
class FootballPlayer:
    name: str
    position: FootballPosition
    power: float
    volatility: float
    stamina: float
    player_type_id: str | None = None

    def __post_init__(self) -> None:
        _validate_name(self.name, "Player name")
        if not isinstance(self.position, FootballPosition):
            raise ValueError("Player position must be a FootballPosition.")
        _validate_finite_number(self.power, "Power")
        if self.power < 0:
            raise ValueError("Power must be non-negative.")
        _validate_finite_number(self.volatility, "Volatility")
        if not 0 <= self.volatility <= 1:
            raise ValueError("Volatility must be between 0 and 1.")
        _validate_finite_number(self.stamina, "Stamina")
        if not 0 <= self.stamina <= 1:
            raise ValueError("Stamina must be between 0 and 1.")
        if self.player_type_id is not None:
            _validate_name(self.player_type_id, "Player type identifier")
            from src.engine.football_player_catalog import player_type_for_id

            player_type = player_type_for_id(self.player_type_id)
            if player_type.position is not self.position:
                raise ValueError("Player type position must match the player's position.")

    def to_save_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "position": self.position.value,
            "power": self.power,
            "volatility": self.volatility,
            "stamina": self.stamina,
        }
        if self.player_type_id is not None:
            data["player_type_id"] = self.player_type_id
        return data

    @classmethod
    def from_save_data(cls, data: Any) -> "FootballPlayer":
        from src.engine.football_player_catalog import PLAYER_TYPES_BY_ID

        what = "Player"
        type_id = optional(data, "player_type_id", str, what)
        if type_id is not None:
            lookup(PLAYER_TYPES_BY_ID, type_id, "player type")
        return build(
            "player",
            lambda: cls(
                name=required(data, "name", str, what),
                position=enum_value(
                    FootballPosition, required(data, "position", str, what), "position"
                ),
                power=required(data, "power", float, what),
                volatility=required(data, "volatility", float, what),
                stamina=required(data, "stamina", float, what),
                player_type_id=type_id,
            ),
        )


@dataclass(frozen=True)
class FootballCoach:
    name: str

    def __post_init__(self) -> None:
        _validate_name(self.name, "Coach name")


@dataclass(frozen=True)
class FootballCoachAssignment:
    offensive_coach_id: str
    defensive_coach_id: str

    def __post_init__(self) -> None:
        _validate_name(self.offensive_coach_id, "Offensive coach identifier")
        _validate_name(self.defensive_coach_id, "Defensive coach identifier")


@dataclass(frozen=True)
class FootballSpecialTeams:
    name: str = "Special Teams"

    def __post_init__(self) -> None:
        _validate_name(self.name, "Special-teams name")


@dataclass(frozen=True)
class FootballRoster:
    team_name: str
    players: Mapping[FootballPosition, FootballPlayer]
    coach: FootballCoach
    special_teams: FootballSpecialTeams
    coach_assignment: FootballCoachAssignment | None = None

    def __post_init__(self) -> None:
        _validate_name(self.team_name, "Team name")
        if not isinstance(self.players, Mapping):
            raise ValueError("Players must map each FootballPosition to a player.")
        if any(not isinstance(position, FootballPosition) for position in self.players):
            raise ValueError("Player slots must use FootballPosition identifiers.")

        expected_positions = set(FootballPosition)
        actual_positions = set(self.players)
        if actual_positions != expected_positions:
            missing = expected_positions - actual_positions
            extra = actual_positions - expected_positions
            raise ValueError(
                f"Roster must contain exactly one player for each position "
                f"(missing={sorted(position.value for position in missing)}, "
                f"extra={sorted(str(position) for position in extra)})."
            )
        for position, player in self.players.items():
            if not isinstance(player, FootballPlayer):
                raise ValueError(f"The {position.value} slot must contain a FootballPlayer.")
            if player.position is not position:
                raise ValueError(
                    f"The {position.value} slot cannot contain a "
                    f"{player.position.value} player."
                )
        if not isinstance(self.coach, FootballCoach):
            raise ValueError("Coach must be a FootballCoach.")
        if not isinstance(self.special_teams, FootballSpecialTeams):
            raise ValueError("Special teams must be a FootballSpecialTeams object.")
        if self.coach_assignment is not None and not isinstance(
            self.coach_assignment, FootballCoachAssignment
        ):
            raise ValueError("Coach assignment must be a FootballCoachAssignment or None.")
        object.__setattr__(self, "players", MappingProxyType(dict(self.players)))

    def to_save_data(self) -> dict[str, Any]:
        """Players in roster order; the coach assignment by its two coach IDs."""
        data: dict[str, Any] = {
            "team_name": self.team_name,
            "players": [player.to_save_data() for player in self.players.values()],
            "coach": self.coach.name,
            "special_teams": self.special_teams.name,
        }
        if self.coach_assignment is not None:
            data["coach_assignment"] = [
                self.coach_assignment.offensive_coach_id,
                self.coach_assignment.defensive_coach_id,
            ]
        return data

    @classmethod
    def from_save_data(cls, data: Any) -> "FootballRoster":
        from src.engine.football_coaches import COACHES_BY_ID

        what = "Roster"
        players = [
            FootballPlayer.from_save_data(item)
            for item in items(required(data, "players", list, what), "Roster players")
        ]
        assignment_data = optional(data, "coach_assignment", list, what)
        assignment = None
        if assignment_data is not None:
            if len(assignment_data) != 2:
                raise UnsupportedSave("A coach assignment must list two coach IDs.")
            for coach_id in assignment_data:
                lookup(COACHES_BY_ID, coach_id, "coach")
            assignment = FootballCoachAssignment(*assignment_data)
        return build(
            "roster",
            lambda: cls(
                team_name=required(data, "team_name", str, what),
                players={player.position: player for player in players},
                coach=FootballCoach(required(data, "coach", str, what)),
                special_teams=FootballSpecialTeams(required(data, "special_teams", str, what)),
                coach_assignment=assignment,
            ),
        )


@dataclass(frozen=True)
class FootballPlayResult:
    offensive_play: OffensivePlayAction
    yards_gained: float
    clock_seconds_used: int
    points_scored: int = 0
    turnover: bool = False
    possession_changed: bool = False
    defensive_scheme: DefensiveSchemeAction | None = None
    incomplete: bool = False
    offense_power: float = 0.0
    defense_power: float = 0.0
    perk_effects: tuple[str, ...] = ()
    turnover_on_downs: bool = False
    turnover_type: FootballTurnoverType | None = None
    conversion_attempt: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.offensive_play, OffensivePlayAction):
            raise ValueError("Offensive play must be an OffensivePlayAction.")
        _validate_finite_number(self.yards_gained, "Yards gained")
        _validate_nonnegative_int(self.clock_seconds_used, "Clock seconds used")
        _validate_nonnegative_int(self.points_scored, "Points scored")
        if not isinstance(self.turnover, bool):
            raise ValueError("Turnover must be a boolean.")
        if not isinstance(self.possession_changed, bool):
            raise ValueError("Possession changed must be a boolean.")
        if not isinstance(self.turnover_on_downs, bool):
            raise ValueError("Turnover on downs must be a boolean.")
        if not isinstance(self.conversion_attempt, bool):
            raise ValueError("Conversion attempt must be a boolean.")
        if self.turnover_type is not None and not self.turnover:
            raise ValueError("A turnover type can only be set for a turnover.")
        if self.turnover_type is not None and not isinstance(
            self.turnover_type, FootballTurnoverType
        ):
            raise ValueError("Turnover type must be a FootballTurnoverType or None.")
        if self.turnover_on_downs and (
            self.turnover or not self.possession_changed
        ):
            raise ValueError(
                "A turnover on downs must change possession without a play turnover."
            )
        if not isinstance(self.incomplete, bool):
            raise ValueError("Incomplete must be a boolean.")
        if (
            self.defensive_scheme is not None
            and not isinstance(self.defensive_scheme, DefensiveSchemeAction)
        ):
            raise ValueError("Defensive scheme must be a DefensiveSchemeAction or None.")
        _validate_finite_number(self.offense_power, "Offense power")
        _validate_finite_number(self.defense_power, "Defense power")
        if self.offense_power < 0 or self.defense_power < 0:
            raise ValueError("Play powers must be non-negative.")
        if not isinstance(self.perk_effects, tuple) or any(
            not isinstance(effect, str) or not effect.strip()
            for effect in self.perk_effects
        ):
            raise ValueError("Perk effects must be a tuple of non-empty strings.")


@dataclass(frozen=True)
class FootballMatchEvent:
    """Immutable record of one caller action and the resulting match snapshot."""

    sequence: int
    action: (
        OffensivePlayAction
        | FootballBonusCardAction
        | DefensiveSchemeAction
        | FootballFourthDownAction
        | FootballConversionAction
        | FootballAutomaticAction
    )
    team_a_score: int
    team_b_score: int
    possession: FootballTeamSide
    offense_field_position: float
    down: int
    yards_to_go: float
    game_clock_seconds: int
    period: int
    status: FootballMatchStatus
    clock_seconds_used: int = 0
    play_result: FootballPlayResult | None = None
    points_scored: int = 0
    scoring_team: FootballTeamSide | None = None
    field_goal_distance: float | None = None
    perk_effects: tuple[str, ...] = ()
    description: str | None = None
    gross_yards: float | None = None
    return_yards: float | None = None
    blocked: bool = False
    card_id: str | None = None
    card_copy_id: str | None = None
    reverses_event_sequences: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _validate_nonnegative_int(self.sequence, "Event sequence")
        if self.sequence == 0:
            raise ValueError("Event sequence must be positive.")
        if not isinstance(
            self.action,
            (
                OffensivePlayAction,
                FootballBonusCardAction,
                DefensiveSchemeAction,
                FootballFourthDownAction,
                FootballConversionAction,
                FootballAutomaticAction,
            ),
        ):
            raise ValueError("Event action must be a supported football action.")
        if self.play_result is not None and not isinstance(
            self.play_result, FootballPlayResult
        ):
            raise ValueError("Play result must be a FootballPlayResult or None.")
        if isinstance(self.action, OffensivePlayAction):
            if self.play_result is None or self.play_result.offensive_play is not self.action:
                raise ValueError("Offensive-play events must include their matching result.")
        elif self.play_result is not None:
            raise ValueError("Only offensive-play events can include a play result.")
        if self.card_id is not None:
            _validate_name(self.card_id, "Event card identifier")
        if self.card_copy_id is not None:
            _validate_name(self.card_copy_id, "Event card-copy identifier")
            if self.card_id is None:
                raise ValueError("An event card copy must identify its catalog card.")
        if not isinstance(self.reverses_event_sequences, tuple) or any(
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 1
            or sequence >= self.sequence
            for sequence in self.reverses_event_sequences
        ) or len(self.reverses_event_sequences) != len(
            set(self.reverses_event_sequences)
        ):
            raise ValueError("Reversed event sequences must be unique earlier events.")
        if isinstance(
            self.action,
            (
                OffensivePlayAction,
                FootballBonusCardAction,
                DefensiveSchemeAction,
            ),
        ):
            if self.card_id is not None and self.card_id != self.action.value:
                raise ValueError("Event card identifier must match its selected action.")
        if self.action is FootballConversionAction.EXTRA_POINT and self.card_id is not None:
            raise ValueError("An extra-point event cannot identify an offensive card.")
        _validate_nonnegative_int(self.points_scored, "Event points scored")
        if self.points_scored and not isinstance(self.scoring_team, FootballTeamSide):
            raise ValueError("Scoring events must identify the scoring team.")
        if not self.points_scored and self.scoring_team is not None:
            raise ValueError("Non-scoring events cannot identify a scoring team.")
        if self.description is not None:
            _validate_name(self.description, "Event description")
        if not isinstance(self.blocked, bool):
            raise ValueError("Blocked must be a boolean.")
        for value, label in (
            (self.gross_yards, "Gross yards"),
            (self.return_yards, "Return yards"),
        ):
            if value is not None:
                _validate_finite_number(value, label)
                if value < 0:
                    raise ValueError(f"{label} must be non-negative.")
        if not isinstance(self.possession, FootballTeamSide):
            raise ValueError("Event possession must be a FootballTeamSide.")
        _validate_finite_number(self.offense_field_position, "Event field position")
        if not 0 <= self.offense_field_position <= 100:
            raise ValueError("Event field position must be between 0 and 100.")
        if isinstance(self.down, bool) or not isinstance(self.down, int) or not 1 <= self.down <= 4:
            raise ValueError("Event down must be an integer from 1 through 4.")
        _validate_finite_number(self.yards_to_go, "Event yards to go")
        if self.yards_to_go <= 0:
            raise ValueError("Event yards to go must be positive.")
        _validate_nonnegative_int(self.game_clock_seconds, "Event game clock seconds")
        _validate_nonnegative_int(self.clock_seconds_used, "Event clock seconds used")
        _validate_nonnegative_int(self.period, "Event period")
        if self.period == 0:
            raise ValueError("Event period must be positive.")
        if not isinstance(self.status, FootballMatchStatus):
            raise ValueError("Event status must be a FootballMatchStatus.")
        _validate_nonnegative_int(self.team_a_score, "Event team A score")
        _validate_nonnegative_int(self.team_b_score, "Event team B score")
        if self.field_goal_distance is not None:
            _validate_finite_number(self.field_goal_distance, "Field-goal distance")
            if self.field_goal_distance < 0:
                raise ValueError("Field-goal distance must be non-negative.")
        if isinstance(self.action, FootballFourthDownAction):
            if (
                self.action is FootballFourthDownAction.FIELD_GOAL
            ) != (self.field_goal_distance is not None):
                raise ValueError("Only field-goal events must record field-goal distance.")
            if self.action is FootballFourthDownAction.FIELD_GOAL and self.points_scored not in (0, 3, 6):
                raise ValueError("Field-goal events can score zero, three, or six points.")
        elif self.field_goal_distance is not None:
            raise ValueError("Only field-goal events can record field-goal distance.")
        if (
            self.play_result is not None
            and self.clock_seconds_used != self.play_result.clock_seconds_used
        ):
            raise ValueError("Event clock use must match its play result.")
        if self.play_result is not None and self.points_scored != self.play_result.points_scored:
            raise ValueError("Event scoring must match its play result.")
        if not isinstance(self.perk_effects, tuple) or any(
            not isinstance(effect, str) or not effect.strip()
            for effect in self.perk_effects
        ):
            raise ValueError("Perk effects must be a tuple of non-empty strings.")
        if self.play_result is not None and self.perk_effects != self.play_result.perk_effects:
            raise ValueError("Event perk effects must match its play result.")


@dataclass(frozen=True)
class FootballMatchResult:
    team_a_score: int
    team_b_score: int
    winner: FootballTeamSide | None
    completed: bool

    def __post_init__(self) -> None:
        _validate_nonnegative_int(self.team_a_score, "Team A score")
        _validate_nonnegative_int(self.team_b_score, "Team B score")
        if self.winner is not None and not isinstance(self.winner, FootballTeamSide):
            raise ValueError("Winner must be a FootballTeamSide or None.")
        if not isinstance(self.completed, bool):
            raise ValueError("Completed must be a boolean.")


@dataclass(frozen=True)
class FootballMatchState:
    """Match snapshot; field position is yards from the offense's own goal line.

    Position 0 is the offense's own goal line and 100 is the opponent's goal
    line. Resolution must use a per-match ``random.Random`` initialized from
    ``random_seed`` rather than module-global randomness.
    """

    team_a: FootballRoster
    team_b: FootballRoster
    random_seed: int
    team_a_score: int
    team_b_score: int
    possession: FootballTeamSide
    down: int
    yards_to_go: float
    offense_field_position: float
    game_clock_seconds: int
    period: int
    status: FootballMatchStatus = FootballMatchStatus.IN_PROGRESS
    awaited_action: FootballAwaitedAction | None = None
    current_drive_defensive_scheme: DefensiveSchemeAction | None = None
    final_result: FootballMatchResult | None = None
    match_events: tuple[FootballMatchEvent, ...] = ()
    team_a_offense_deck: FootballDeckState | None = None
    team_a_defense_deck: FootballDeckState | None = None
    team_b_offense_deck: FootballDeckState | None = None
    team_b_defense_deck: FootballDeckState | None = None
    conversion_team: FootballTeamSide | None = None
    team_a_coach_upgrades: tuple[FootballCoachUpgradeEffect, ...] = ()
    team_b_coach_upgrades: tuple[FootballCoachUpgradeEffect, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.team_a, FootballRoster) or not isinstance(
            self.team_b, FootballRoster
        ):
            raise ValueError("Both teams must be FootballRoster objects.")
        if (
            isinstance(self.random_seed, bool)
            or not isinstance(self.random_seed, int)
        ):
            raise ValueError("Random seed must be an integer.")
        _validate_nonnegative_int(self.team_a_score, "Team A score")
        _validate_nonnegative_int(self.team_b_score, "Team B score")
        if not isinstance(self.possession, FootballTeamSide):
            raise ValueError("Possession must be a FootballTeamSide.")
        if (
            isinstance(self.down, bool)
            or not isinstance(self.down, int)
            or not 1 <= self.down <= 4
        ):
            raise ValueError("Down must be an integer from 1 through 4.")
        _validate_finite_number(self.yards_to_go, "Yards to go")
        if self.yards_to_go <= 0:
            raise ValueError("Yards to go must be positive.")
        _validate_finite_number(self.offense_field_position, "Offense field position")
        if not 0 <= self.offense_field_position <= 100:
            raise ValueError("Offense field position must be between 0 and 100.")
        _validate_nonnegative_int(self.game_clock_seconds, "Game clock seconds")
        if (
            isinstance(self.period, bool)
            or not isinstance(self.period, int)
            or self.period < 1
        ):
            raise ValueError("Period must be a positive integer.")
        maximum_clock = 900 if self.period <= 2 else 300
        if self.game_clock_seconds > maximum_clock:
            raise ValueError(
                f"Game clock seconds cannot exceed {maximum_clock} in period {self.period}."
            )
        if not isinstance(self.status, FootballMatchStatus):
            raise ValueError("Status must be a FootballMatchStatus.")
        if self.awaited_action is not None and not isinstance(
            self.awaited_action, FootballAwaitedAction
        ):
            raise ValueError("Awaited action must be a FootballAwaitedAction or None.")
        if self.current_drive_defensive_scheme is not None and not isinstance(
            self.current_drive_defensive_scheme, DefensiveSchemeAction
        ):
            raise ValueError(
                "Current defensive scheme must be a DefensiveSchemeAction or None."
            )
        if self.conversion_team is not None and not isinstance(
            self.conversion_team, FootballTeamSide
        ):
            raise ValueError("Conversion team must be a FootballTeamSide or None.")
        if self.final_result is not None and not isinstance(
            self.final_result, FootballMatchResult
        ):
            raise ValueError("Final result must be a FootballMatchResult or None.")
        if not isinstance(self.match_events, tuple) or any(
            not isinstance(event, FootballMatchEvent) for event in self.match_events
        ):
            raise ValueError("Match events must be an immutable tuple of football events.")
        if any(
            deck is not None and not isinstance(deck, FootballDeckState)
            for deck in (
                self.team_a_offense_deck,
                self.team_a_defense_deck,
                self.team_b_offense_deck,
                self.team_b_defense_deck,
            )
        ):
            raise ValueError("Match decks must be FootballDeckState instances or None.")
        if any(
            not isinstance(upgrades, tuple)
            or any(
                not isinstance(upgrade, FootballCoachUpgradeEffect)
                for upgrade in upgrades
            )
            or len({upgrade.upgrade_id for upgrade in upgrades}) != len(upgrades)
            for upgrades in (
                self.team_a_coach_upgrades,
                self.team_b_coach_upgrades,
            )
        ):
            raise ValueError(
                "Match coach upgrades must be unique immutable effect tuples."
            )
        if any(event.sequence != index for index, event in enumerate(self.match_events, 1)):
            raise ValueError("Match event sequence numbers must be contiguous.")
        if self.status is FootballMatchStatus.COMPLETED:
            if self.final_result is None or not self.final_result.completed:
                raise ValueError("A completed match must have a completed final result.")
            if self.team_a_score == self.team_b_score:
                raise ValueError("A completed match cannot end in a tie.")
            if (
                self.final_result.team_a_score != self.team_a_score
                or self.final_result.team_b_score != self.team_b_score
            ):
                raise ValueError("Final result scores must match the match state.")
            if self.final_result.winner is not (
                FootballTeamSide.TEAM_A
                if self.team_a_score > self.team_b_score
                else FootballTeamSide.TEAM_B
            ):
                raise ValueError("Final result winner must match the match scores.")
            if self.awaited_action is not None or self.current_drive_defensive_scheme is not None:
                raise ValueError("A completed match cannot await an action or retain a scheme.")
            if self.conversion_team is not None:
                raise ValueError("A completed match cannot await a conversion.")
        elif self.final_result is not None:
            raise ValueError("An in-progress match cannot have a final result.")
        if self.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME:
            if self.down != 1:
                raise ValueError("A new defensive drive must start on first down.")
            if self.current_drive_defensive_scheme is not None:
                raise ValueError("A new defensive drive cannot already have a scheme.")
        elif self.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY:
            if self.current_drive_defensive_scheme is None:
                raise ValueError("An active drive must have a defensive scheme.")
        elif self.awaited_action is FootballAwaitedAction.FOURTH_DOWN_DECISION:
            if self.current_drive_defensive_scheme is None:
                raise ValueError("An active drive must have a defensive scheme.")
        elif self.awaited_action is FootballAwaitedAction.CONVERSION:
            if (
                self.conversion_team is None
                or self.conversion_team is not self.possession
                or self.current_drive_defensive_scheme is None
                or self.down != 1
                or self.yards_to_go != 2.0
                or self.offense_field_position != 98.0
            ):
                raise ValueError(
                    "A conversion must identify its team and use the two-yard line."
                )
        elif self.conversion_team is not None:
            raise ValueError("A conversion team is only valid while awaiting a conversion.")
        if (
            self.awaited_action is FootballAwaitedAction.FOURTH_DOWN_DECISION
            and self.down != 4
        ):
            raise ValueError("A fourth-down decision must be awaited on fourth down.")


# -- save data for match history and match state ---------------------------------
#
# Match events and play results are the bulk of a mid-match save, so fields
# that hold their default value are omitted and an event's sequence number is
# implied by its position in the history.

_EVENT_ACTION_TYPES: Mapping[str, type[Enum]] = MappingProxyType({
    "play": OffensivePlayAction,
    "bonus": FootballBonusCardAction,
    "scheme": DefensiveSchemeAction,
    "fourth_down": FootballFourthDownAction,
    "conversion": FootballConversionAction,
    "automatic": FootballAutomaticAction,
})


def _action_to_save_data(action: Enum) -> list[str]:
    # Several action enums share values (e.g. "rb_run"), so each is tagged.
    for tag, enum_type in _EVENT_ACTION_TYPES.items():
        if type(action) is enum_type:
            return [tag, action.value]
    raise ValueError(f"Unsupported event action: {action!r}.")


def _action_from_save_data(data: Any) -> Enum:
    if not isinstance(data, list) or len(data) != 2:
        raise UnsupportedSave("An event action must be [kind, value].")
    tag, value = data
    enum_type = lookup(_EVENT_ACTION_TYPES, tag, "event action kind")
    return enum_value(enum_type, value, "event action")


def _without_defaults(data: dict[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if key not in defaults or value != defaults[key]
    }


_PLAY_RESULT_DEFAULTS = MappingProxyType({
    "points_scored": 0, "turnover": False, "possession_changed": False,
    "defensive_scheme": None, "incomplete": False, "offense_power": 0.0,
    "defense_power": 0.0, "perk_effects": [], "turnover_on_downs": False,
    "turnover_type": None, "conversion_attempt": False,
})


def play_result_to_save_data(result: FootballPlayResult) -> dict[str, Any]:
    return _without_defaults({
        "offensive_play": result.offensive_play.value,
        "yards_gained": result.yards_gained,
        "clock_seconds_used": result.clock_seconds_used,
        "points_scored": result.points_scored,
        "turnover": result.turnover,
        "possession_changed": result.possession_changed,
        "defensive_scheme": (
            result.defensive_scheme.value if result.defensive_scheme is not None else None
        ),
        "incomplete": result.incomplete,
        "offense_power": result.offense_power,
        "defense_power": result.defense_power,
        "perk_effects": list(result.perk_effects),
        "turnover_on_downs": result.turnover_on_downs,
        "turnover_type": (
            result.turnover_type.value if result.turnover_type is not None else None
        ),
        "conversion_attempt": result.conversion_attempt,
    }, _PLAY_RESULT_DEFAULTS)


def play_result_from_save_data(data: Any) -> FootballPlayResult:
    what = "Play result"
    return build("play result", lambda: FootballPlayResult(
        offensive_play=enum_value(
            OffensivePlayAction, required(data, "offensive_play", str, what), "play"
        ),
        yards_gained=required(data, "yards_gained", float, what),
        clock_seconds_used=required(data, "clock_seconds_used", int, what),
        points_scored=optional(data, "points_scored", int, what, 0),
        turnover=optional(data, "turnover", bool, what, False),
        possession_changed=optional(data, "possession_changed", bool, what, False),
        defensive_scheme=optional_enum(
            DefensiveSchemeAction, optional(data, "defensive_scheme", str, what), "scheme"
        ),
        incomplete=optional(data, "incomplete", bool, what, False),
        offense_power=optional(data, "offense_power", float, what, 0.0),
        defense_power=optional(data, "defense_power", float, what, 0.0),
        perk_effects=tuple(optional(data, "perk_effects", list, what, [])),
        turnover_on_downs=optional(data, "turnover_on_downs", bool, what, False),
        turnover_type=optional_enum(
            FootballTurnoverType, optional(data, "turnover_type", str, what), "turnover type"
        ),
        conversion_attempt=optional(data, "conversion_attempt", bool, what, False),
    ))


_EVENT_DEFAULTS = MappingProxyType({
    "clock_seconds_used": 0, "play_result": None, "points_scored": 0,
    "scoring_team": None, "field_goal_distance": None, "perk_effects": [],
    "description": None, "gross_yards": None, "return_yards": None,
    "blocked": False, "card_id": None, "card_copy_id": None,
    "reverses_event_sequences": [],
})


def match_event_to_save_data(event: FootballMatchEvent) -> dict[str, Any]:
    """One event; its ``sequence`` is its 1-based position in the saved history."""
    return _without_defaults({
        "action": _action_to_save_data(event.action),
        "team_a_score": event.team_a_score,
        "team_b_score": event.team_b_score,
        "possession": event.possession.value,
        "offense_field_position": event.offense_field_position,
        "down": event.down,
        "yards_to_go": event.yards_to_go,
        "game_clock_seconds": event.game_clock_seconds,
        "period": event.period,
        "status": event.status.value,
        "clock_seconds_used": event.clock_seconds_used,
        "play_result": (
            play_result_to_save_data(event.play_result)
            if event.play_result is not None else None
        ),
        "points_scored": event.points_scored,
        "scoring_team": event.scoring_team.value if event.scoring_team is not None else None,
        "field_goal_distance": event.field_goal_distance,
        "perk_effects": list(event.perk_effects),
        "description": event.description,
        "gross_yards": event.gross_yards,
        "return_yards": event.return_yards,
        "blocked": event.blocked,
        "card_id": event.card_id,
        "card_copy_id": event.card_copy_id,
        "reverses_event_sequences": list(event.reverses_event_sequences),
    }, _EVENT_DEFAULTS)


def match_event_from_save_data(data: Any, sequence: int) -> FootballMatchEvent:
    what = f"Match event {sequence}"
    play_data = optional(data, "play_result", dict, what)
    return build(what.lower(), lambda: FootballMatchEvent(
        sequence=sequence,
        action=_action_from_save_data(required(data, "action", list, what)),
        team_a_score=required(data, "team_a_score", int, what),
        team_b_score=required(data, "team_b_score", int, what),
        possession=enum_value(FootballTeamSide, required(data, "possession", str, what), "team"),
        offense_field_position=required(data, "offense_field_position", float, what),
        down=required(data, "down", int, what),
        yards_to_go=required(data, "yards_to_go", float, what),
        game_clock_seconds=required(data, "game_clock_seconds", int, what),
        period=required(data, "period", int, what),
        status=enum_value(FootballMatchStatus, required(data, "status", str, what), "status"),
        clock_seconds_used=optional(data, "clock_seconds_used", int, what, 0),
        play_result=(
            play_result_from_save_data(play_data) if play_data is not None else None
        ),
        points_scored=optional(data, "points_scored", int, what, 0),
        scoring_team=optional_enum(
            FootballTeamSide, optional(data, "scoring_team", str, what), "team"
        ),
        field_goal_distance=optional(data, "field_goal_distance", float, what),
        perk_effects=tuple(optional(data, "perk_effects", list, what, [])),
        description=optional(data, "description", str, what),
        gross_yards=optional(data, "gross_yards", float, what),
        return_yards=optional(data, "return_yards", float, what),
        blocked=optional(data, "blocked", bool, what, False),
        card_id=optional(data, "card_id", str, what),
        card_copy_id=optional(data, "card_copy_id", str, what),
        reverses_event_sequences=tuple(
            optional(data, "reverses_event_sequences", list, what, [])
        ),
    ))


def match_result_to_save_data(result: FootballMatchResult) -> dict[str, Any]:
    return {
        "team_a_score": result.team_a_score,
        "team_b_score": result.team_b_score,
        "winner": result.winner.value if result.winner is not None else None,
        "completed": result.completed,
    }


def match_result_from_save_data(data: Any) -> FootballMatchResult:
    what = "Match result"
    return build("match result", lambda: FootballMatchResult(
        team_a_score=required(data, "team_a_score", int, what),
        team_b_score=required(data, "team_b_score", int, what),
        winner=optional_enum(FootballTeamSide, optional(data, "winner", str, what), "team"),
        completed=required(data, "completed", bool, what),
    ))


_MATCH_DECK_FIELDS = (
    "team_a_offense_deck", "team_a_defense_deck",
    "team_b_offense_deck", "team_b_defense_deck",
)


def match_state_to_save_data(
    state: FootballMatchState, *, events_prefix_of: FootballMatchState | None = None,
) -> dict[str, Any]:
    """The full match snapshot.

    With ``events_prefix_of``, a history that is a prefix of that state's
    history is stored as its length (``match_events_prefix``) instead of a copy;
    the simulator uses this for its Challenge rollback snapshot.
    """
    data: dict[str, Any] = {
        "team_a": state.team_a.to_save_data(),
        "team_b": state.team_b.to_save_data(),
        "random_seed": state.random_seed,
        "team_a_score": state.team_a_score,
        "team_b_score": state.team_b_score,
        "possession": state.possession.value,
        "down": state.down,
        "yards_to_go": state.yards_to_go,
        "offense_field_position": state.offense_field_position,
        "game_clock_seconds": state.game_clock_seconds,
        "period": state.period,
        "status": state.status.value,
        "awaited_action": (
            state.awaited_action.value if state.awaited_action is not None else None
        ),
        "current_drive_defensive_scheme": (
            state.current_drive_defensive_scheme.value
            if state.current_drive_defensive_scheme is not None else None
        ),
        "final_result": (
            match_result_to_save_data(state.final_result)
            if state.final_result is not None else None
        ),
        "conversion_team": (
            state.conversion_team.value if state.conversion_team is not None else None
        ),
        "team_a_coach_upgrades": [
            effect.to_save_data() for effect in state.team_a_coach_upgrades
        ],
        "team_b_coach_upgrades": [
            effect.to_save_data() for effect in state.team_b_coach_upgrades
        ],
    }
    for name in _MATCH_DECK_FIELDS:
        deck = getattr(state, name)
        data[name] = deck.to_save_data() if deck is not None else None
    events = state.match_events
    if (
        events_prefix_of is not None
        and len(events) <= len(events_prefix_of.match_events)
        and events_prefix_of.match_events[: len(events)] == events
    ):
        data["match_events_prefix"] = len(events)
    else:
        data["match_events"] = [match_event_to_save_data(event) for event in events]
    return data


def match_state_from_save_data(
    data: Any, *, events_prefix_of: FootballMatchState | None = None,
) -> FootballMatchState:
    what = "Match state"
    if isinstance(data, Mapping) and "match_events_prefix" in data:
        length = required(data, "match_events_prefix", int, what)
        if events_prefix_of is None or not 0 <= length <= len(events_prefix_of.match_events):
            raise UnsupportedSave("A match-history prefix has no matching history.")
        events = events_prefix_of.match_events[:length]
    else:
        events = tuple(
            match_event_from_save_data(item, index)
            for index, item in enumerate(
                items(required(data, "match_events", list, what), "Match events"), 1
            )
        )
    decks = {
        name: (
            FootballDeckState.from_save_data(data[name])
            if optional(data, name, dict, what) is not None else None
        )
        for name in _MATCH_DECK_FIELDS
    }
    final_result = optional(data, "final_result", dict, what)
    return build("match state", lambda: FootballMatchState(
        team_a=FootballRoster.from_save_data(required(data, "team_a", dict, what)),
        team_b=FootballRoster.from_save_data(required(data, "team_b", dict, what)),
        random_seed=required(data, "random_seed", int, what),
        team_a_score=required(data, "team_a_score", int, what),
        team_b_score=required(data, "team_b_score", int, what),
        possession=enum_value(FootballTeamSide, required(data, "possession", str, what), "team"),
        down=required(data, "down", int, what),
        yards_to_go=required(data, "yards_to_go", float, what),
        offense_field_position=required(data, "offense_field_position", float, what),
        game_clock_seconds=required(data, "game_clock_seconds", int, what),
        period=required(data, "period", int, what),
        status=enum_value(FootballMatchStatus, required(data, "status", str, what), "status"),
        awaited_action=optional_enum(
            FootballAwaitedAction, optional(data, "awaited_action", str, what),
            "awaited action",
        ),
        current_drive_defensive_scheme=optional_enum(
            DefensiveSchemeAction,
            optional(data, "current_drive_defensive_scheme", str, what), "scheme",
        ),
        final_result=(
            match_result_from_save_data(final_result) if final_result is not None else None
        ),
        match_events=events,
        conversion_team=optional_enum(
            FootballTeamSide, optional(data, "conversion_team", str, what), "team"
        ),
        team_a_coach_upgrades=tuple(
            FootballCoachUpgradeEffect.from_save_data(item)
            for item in items(required(data, "team_a_coach_upgrades", list, what), "Upgrades")
        ),
        team_b_coach_upgrades=tuple(
            FootballCoachUpgradeEffect.from_save_data(item)
            for item in items(required(data, "team_b_coach_upgrades", list, what), "Upgrades")
        ),
        **decks,
    ))
