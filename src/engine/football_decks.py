"""Football card definitions and the run's initial playbook."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType

from src.engine.football import (
    DEFENSIVE_SCHEME_FAMILIES,
    DefensiveSchemeAction,
    FootballBonusCardAction,
    FootballCardFamily,
    FootballCardCopy,
    FootballPosition,
    OffensivePlayAction,
    OFFENSIVE_PLAY_FAMILIES,
    matchup_for_scheme,
    matchup_for_play,
)

@dataclass(frozen=True)
class FootballBonusCardDefinition:
    action: FootballBonusCardAction
    name: str
    description: str

    @property
    def card_id(self) -> str:
        return self.action.value


@dataclass(frozen=True)
class FootballPlayDefinition:
    action: OffensivePlayAction
    name: str
    description: str
    contributors: tuple[FootballPosition, ...]
    family: FootballCardFamily
    base_yards: float
    clock_seconds: int

    @property
    def card_id(self) -> str:
        return self.action.value

    def __post_init__(self) -> None:
        if not isinstance(self.action, OffensivePlayAction):
            raise ValueError("Play definition action must be an OffensivePlayAction.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Play definition name must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Play definition description must be a non-empty string.")
        if not isinstance(self.family, FootballCardFamily):
            raise ValueError("Play definition family must be a FootballCardFamily.")
        if self.family is not OFFENSIVE_PLAY_FAMILIES[self.action]:
            raise ValueError("Play definition family does not match its action.")
        if not isinstance(self.contributors, tuple) or not self.contributors or any(
            not isinstance(position, FootballPosition)
            for position in self.contributors
        ):
            raise ValueError("Play contributors must be a non-empty position tuple.")
        if self.contributors != matchup_for_play(self.action)[0]:
            raise ValueError("Play contributors must match their family's matchup.")
        if isinstance(self.base_yards, bool) or not isinstance(
            self.base_yards, (int, float)
        ) or not isfinite(self.base_yards):
            raise ValueError("Play base yards must be finite.")
        if isinstance(self.clock_seconds, bool) or not isinstance(
            self.clock_seconds, int
        ) or self.clock_seconds <= 0:
            raise ValueError("Play clock duration must be a positive integer.")


@dataclass(frozen=True)
class FootballSchemeDefinition:
    action: DefensiveSchemeAction
    name: str
    description: str
    contributors: tuple[FootballPosition, ...]
    family: FootballCardFamily
    counters: frozenset[OffensivePlayAction]

    @property
    def card_id(self) -> str:
        return self.action.value

    def __post_init__(self) -> None:
        if not isinstance(self.action, DefensiveSchemeAction):
            raise ValueError("Scheme definition action must be a DefensiveSchemeAction.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Scheme definition name must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Scheme definition description must be a non-empty string.")
        if not isinstance(self.family, FootballCardFamily):
            raise ValueError("Scheme definition family must be a FootballCardFamily.")
        if self.family is not DEFENSIVE_SCHEME_FAMILIES[self.action]:
            raise ValueError("Scheme definition family does not match its action.")
        if not isinstance(self.contributors, tuple) or not self.contributors or any(
            not isinstance(position, FootballPosition)
            for position in self.contributors
        ):
            raise ValueError("Scheme contributors must be a non-empty position tuple.")
        if not isinstance(self.counters, frozenset) or any(
            not isinstance(play, OffensivePlayAction) for play in self.counters
        ):
            raise ValueError("Scheme counters must be an immutable set of offensive plays.")
        contributors, counters = matchup_for_scheme(self.action)
        if self.contributors != contributors or self.counters != counters:
            raise ValueError("Scheme contributors and counters must match its family.")


def _play(
    action: OffensivePlayAction,
    name: str,
    description: str,
    base_yards: float,
    clock_seconds: int,
) -> FootballPlayDefinition:
    contributors, _ = matchup_for_play(action)
    return FootballPlayDefinition(
        action,
        name,
        description,
        contributors,
        OFFENSIVE_PLAY_FAMILIES[action],
        base_yards,
        clock_seconds,
    )


def _scheme(
    action: DefensiveSchemeAction,
    name: str,
    description: str,
) -> FootballSchemeDefinition:
    contributors, counters = matchup_for_scheme(action)
    return FootballSchemeDefinition(
        action,
        name,
        description,
        contributors,
        DEFENSIVE_SCHEME_FAMILIES[action],
        counters,
    )


OFFENSIVE_PLAY_CATALOG = MappingProxyType(
    {
        definition.card_id: definition
        for definition in (
            _play(
                OffensivePlayAction.RB_RUN,
                "Inside Run",
                "O-line and running back press the interior gap.",
                4.0,
                26,
            ),
            _play(
                OffensivePlayAction.SCREEN_PASS,
                "Screen Pass",
                "O-line releases the receiver into space behind the rush.",
                3.5,
                24,
            ),
            _play(
                OffensivePlayAction.PA_PASS,
                "Play-Action Pass",
                "Quarterback and running back sell the run before a pass.",
                5.0,
                28,
            ),
            _play(
                OffensivePlayAction.SHORT_PASS,
                "Short Pass",
                "Running back and receiver work underneath against close coverage.",
                5.5,
                24,
            ),
            _play(
                OffensivePlayAction.MEDIUM_PASS,
                "Medium Pass",
                "Quarterback and O-line hold up for an intermediate route.",
                6.5,
                26,
            ),
            _play(
                OffensivePlayAction.DEEP_PASS,
                "Deep Pass",
                "Quarterback and receiver challenge coverage downfield.",
                8.0,
                28,
            ),
            _play(
                OffensivePlayAction.QB_SNEAK,
                "Quarterback Sneak",
                "A short, direct push through the interior run lane.",
                2.8,
                24,
            ),
            _play(
                OffensivePlayAction.JET_SWEEP,
                "Jet Sweep",
                "A fast handoff sweeps toward the edge behind the run block.",
                4.0,
                22,
            ),
            _play(
                OffensivePlayAction.QUICK_OUT,
                "Quick Out",
                "A quick underneath throw breaks toward the sideline.",
                4.5,
                20,
            ),
            _play(
                OffensivePlayAction.POWER_TOSS,
                "Power Toss",
                "The back follows the line laterally before turning upfield.",
                4.5,
                29,
            ),
            _play(
                OffensivePlayAction.BUBBLE_SCREEN,
                "Bubble Screen",
                "A quick screen puts the receiver in space outside.",
                4.0,
                19,
            ),
            _play(
                OffensivePlayAction.BOOTLEG_KEEPER,
                "Bootleg Keeper",
                "The quarterback sells the run fake, rolls out, and throws on the move.",
                6.0,
                30,
            ),
            _play(
                OffensivePlayAction.SLOT_SLANT,
                "Slot Slant",
                "The receiver cuts inside for a fast underneath target.",
                6.0,
                22,
            ),
            _play(
                OffensivePlayAction.DEEP_DIG,
                "Deep Dig",
                "The receiver bends into an intermediate window across the field.",
                7.0,
                29,
            ),
            _play(
                OffensivePlayAction.GO_ROUTE,
                "Go Route",
                "The receiver pushes vertically for a deep sideline throw.",
                8.5,
                32,
            ),
            _play(
                OffensivePlayAction.INSIDE_ZONE,
                "Inside Zone",
                "The back presses the interior zone and follows the line's block.",
                4.2,
                25,
            ),
            _play(
                OffensivePlayAction.COUNTER_RUN,
                "Counter Run",
                "The offense misdirects the front before pulling into the run lane.",
                4.8,
                28,
            ),
            _play(
                OffensivePlayAction.TUNNEL_SCREEN,
                "Tunnel Screen",
                "The receiver catches behind the line as blockers seal the rush.",
                4.2,
                23,
            ),
            _play(
                OffensivePlayAction.RB_SCREEN,
                "Running Back Screen",
                "The back slips into the flat behind the releasing line.",
                3.8,
                22,
            ),
            _play(
                OffensivePlayAction.WR_SCREEN,
                "Wide Receiver Screen",
                "A quick throw sends the receiver toward open perimeter space.",
                4.1,
                20,
            ),
            _play(
                OffensivePlayAction.DELAY_SCREEN,
                "Delay Screen",
                "The offense invites pressure before releasing a screen outside.",
                4.6,
                27,
            ),
            _play(
                OffensivePlayAction.BOOT_FLOOD,
                "Boot Flood",
                "The quarterback rolls out after a run fake and stretches the levels.",
                6.2,
                30,
            ),
            _play(
                OffensivePlayAction.POST_WHEEL,
                "Post-Wheel",
                "A run fake opens a layered post and wheel route combination.",
                7.0,
                31,
            ),
            _play(
                OffensivePlayAction.PA_CROSSER,
                "Play-Action Crosser",
                "The quarterback sells the handoff and finds a crossing receiver.",
                6.4,
                29,
            ),
            _play(
                OffensivePlayAction.QB_KEEPER_PA,
                "Keeper off Play-Action",
                "The quarterback keeps the ball after the defense honors the run fake.",
                5.2,
                27,
            ),
            _play(
                OffensivePlayAction.STICK_CONCEPT,
                "Stick Concept",
                "The back and receiver create quick underneath choices.",
                5.3,
                23,
            ),
            _play(
                OffensivePlayAction.RB_ANGLE,
                "Running Back Angle",
                "The back angles across the linebackers into a short passing window.",
                5.8,
                25,
            ),
            _play(
                OffensivePlayAction.QUICK_HITCH,
                "Quick Hitch",
                "The receiver settles quickly for a short timing throw.",
                5.0,
                21,
            ),
            _play(
                OffensivePlayAction.DIG_ROUTE,
                "Dig Route",
                "The quarterback targets a receiver cutting into the intermediate middle.",
                6.8,
                27,
            ),
            _play(
                OffensivePlayAction.CURL_COMEBACK,
                "Curl-Back",
                "The receiver turns back to the quarterback in an intermediate window.",
                6.4,
                26,
            ),
            _play(
                OffensivePlayAction.SEAM_PASS,
                "Seam Pass",
                "The quarterback attacks the seam between the second-level defenders.",
                7.0,
                28,
            ),
            _play(
                OffensivePlayAction.CROSSING_ROUTE,
                "Intermediate Cross",
                "A receiver crosses the field behind the underneath coverage.",
                7.2,
                29,
            ),
            _play(
                OffensivePlayAction.POST_ROUTE,
                "Post Route",
                "The receiver breaks toward the deep middle for a vertical throw.",
                9.0,
                32,
            ),
            _play(
                OffensivePlayAction.CORNER_ROUTE,
                "Corner Route",
                "The receiver bends toward the deep sideline away from coverage.",
                9.2,
                33,
            ),
            _play(
                OffensivePlayAction.DOUBLE_MOVE,
                "Double Move",
                "The receiver sells a short break before accelerating downfield.",
                9.5,
                35,
            ),
            _play(
                OffensivePlayAction.GO_BALL,
                "Go Ball",
                "The quarterback attacks deep space with a vertical throw.",
                10.0,
                34,
            ),
        )
    }
)

DEFENSIVE_SCHEME_CATALOG = MappingProxyType(
    {
        definition.card_id: definition
        for definition in (
            _scheme(action, name, description)
            for action, name, description in (
                (
                    DefensiveSchemeAction.RB_RUN,
                    "Run Fit",
                    "D-line and linebackers fit the RB Run family.",
                ),
                (
                    DefensiveSchemeAction.SCREEN_PASS,
                    "Screen Read",
                    "D-line and corners close down screen routes.",
                ),
                (
                    DefensiveSchemeAction.PA_PASS,
                    "Play-Action Read",
                    "Safeties and linebackers read the play fake.",
                ),
                (
                    DefensiveSchemeAction.SHORT_PASS,
                    "Under Coverage",
                    "Linebackers and corners contest short routes.",
                ),
                (
                    DefensiveSchemeAction.MEDIUM_PASS,
                    "Pressure Shell",
                    "Safeties and D-line challenge intermediate routes.",
                ),
                (
                    DefensiveSchemeAction.DEEP_PASS,
                    "Deep Coverage",
                    "Safeties and corners protect the deep passing family.",
                ),
                (
                    DefensiveSchemeAction.GOAL_LINE_FRONT,
                    "Goal-Line Front",
                    "A tight front against the RB Run family.",
                ),
                (
                    DefensiveSchemeAction.COVER_TWO_SHELL,
                    "Cover Two Shell",
                    "Safeties and corners bracket the Deep Pass family.",
                ),
                (
                    DefensiveSchemeAction.FIRE_ZONE_BLITZ,
                    "Fire-Zone Blitz",
                    "Safeties and D-line pressure the Medium Pass family.",
                ),
                (
                    DefensiveSchemeAction.SPILL_FRONT,
                    "Spill Front",
                    "D-line and linebackers set the edge against the run.",
                ),
                (
                    DefensiveSchemeAction.PERIMETER_CHECK,
                    "Perimeter Check",
                    "D-line and corners rally to the screen.",
                ),
                (
                    DefensiveSchemeAction.READ_REACT,
                    "Read and React",
                    "Safeties and linebackers stay disciplined against the fake.",
                ),
                (
                    DefensiveSchemeAction.NICKEL_UNDER,
                    "Nickel Under",
                    "Linebackers and corners close the underneath windows.",
                ),
                (
                    DefensiveSchemeAction.TWO_HIGH_PRESSURE,
                    "Two-High Pressure",
                    "Safeties and D-line contest intermediate routes.",
                ),
                (
                    DefensiveSchemeAction.QUARTERS_COVERAGE,
                    "Quarters Coverage",
                    "Safeties and corners protect the deep routes.",
                ),
                (
                    DefensiveSchemeAction.BEAR_FRONT,
                    "Bear Front",
                    "A heavy interior front compresses the RB Run lanes.",
                ),
                (
                    DefensiveSchemeAction.MAN_PRESS,
                    "Press Man",
                    "Corners disrupt screen releases before rallying to the catch.",
                ),
                (
                    DefensiveSchemeAction.SCREEN_BLITZ,
                    "Screen Blitz",
                    "A delayed rush closes the screen before it develops.",
                ),
                (
                    DefensiveSchemeAction.ROBBER_COVERAGE,
                    "Robber Coverage",
                    "A low safety reads the quarterback and attacks play-action windows.",
                ),
                (
                    DefensiveSchemeAction.SINKING_ZONE,
                    "Sinking Zone",
                    "Linebackers and safeties sink under routes after the fake.",
                ),
                (
                    DefensiveSchemeAction.TWO_MAN_UNDER,
                    "Two-Man Under",
                    "Underneath defenders contest short timing routes.",
                ),
                (
                    DefensiveSchemeAction.HOT_BLITZ,
                    "Hot Blitz",
                    "A fast pressure package challenges short passing concepts.",
                ),
                (
                    DefensiveSchemeAction.THREE_DEEP_BLITZ,
                    "Three-Deep Blitz",
                    "A pressure look challenges intermediate routes behind a deep shell.",
                ),
                (
                    DefensiveSchemeAction.PREVENT_COVERAGE,
                    "Prevent Coverage",
                    "Safeties and corners protect against deep vertical routes.",
                ),
            )
        )
    }
)

BONUS_CARD_CATALOG = MappingProxyType(
    {
        definition.card_id: definition
        for definition in (
            FootballBonusCardDefinition(
                FootballBonusCardAction.OFFENSIVE_DRAW,
                "Offensive Draw",
                "Draw one offensive card to your hand. Costs 10 seconds.",
            ),
            FootballBonusCardDefinition(
                FootballBonusCardAction.DEFENSIVE_DRAW,
                "Defensive Draw",
                "Draw one defensive scheme into your next defensive hand. Costs 10 seconds.",
            ),
            FootballBonusCardDefinition(
                FootballBonusCardAction.OPPONENT_DISCARD,
                "Opponent Discard",
                "Draw one offensive replacement and randomly discard one card from the opposing hand. Costs 10 seconds.",
            ),
            FootballBonusCardDefinition(
                FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD,
                "Offensive Draw & Discard",
                "Draw one offensive replacement and randomly discard one opposing hand card. Costs 10 seconds.",
            ),
            FootballBonusCardDefinition(
                FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD,
                "Defensive Draw & Discard",
                "Draw one defensive scheme and randomly discard one opposing hand card. Costs 10 seconds.",
            ),
            FootballBonusCardDefinition(
                FootballBonusCardAction.CHALLENGE,
                "Challenge",
                "Restore the last human offensive play's football state without refunding clock.",
            ),
        )
    }
)

STARTING_OFFENSIVE_ACTIONS = tuple(
    action
    for action in OffensivePlayAction
    if action
    in (
        OffensivePlayAction.RB_RUN,
        OffensivePlayAction.SCREEN_PASS,
        OffensivePlayAction.PA_PASS,
        OffensivePlayAction.SHORT_PASS,
        OffensivePlayAction.MEDIUM_PASS,
        OffensivePlayAction.DEEP_PASS,
    )
)
STARTING_DEFENSIVE_ACTIONS = tuple(
    action
    for action in DefensiveSchemeAction
    if action
    in (
        DefensiveSchemeAction.RB_RUN,
        DefensiveSchemeAction.SCREEN_PASS,
        DefensiveSchemeAction.PA_PASS,
        DefensiveSchemeAction.SHORT_PASS,
        DefensiveSchemeAction.MEDIUM_PASS,
        DefensiveSchemeAction.DEEP_PASS,
    )
)


def starting_offensive_deck(prefix: str) -> tuple[FootballCardCopy, ...]:
    return tuple(
        FootballCardCopy(f"{prefix}:offense:{action.value}:1", action.value)
        for action in STARTING_OFFENSIVE_ACTIONS
    )


def starting_defensive_deck(prefix: str) -> tuple[FootballCardCopy, ...]:
    return tuple(
        FootballCardCopy(f"{prefix}:defense:{action.value}:1", action.value)
        for action in STARTING_DEFENSIVE_ACTIONS
    )
