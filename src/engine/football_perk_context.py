"""Pure per-team player-perk history rebuilt from a match's recorded events.

Nothing here is stored on the simulator: drive, half, and game history (snap
index, families used, uses spent, charges) is derived from
``FootballMatchState.match_events`` every time it is needed, so a restored save
continues exactly like an uninterrupted match.

Rules this module encodes (see docs/player-perks-proposal.md §2):

* A drive starts at its defensive-scheme event and lasts until the next one.
  A two-point try belongs to its scoring drive. Halftime ends the drive.
* Halves are period 1, period 2, and overtime (all OT periods together).
* An event's own half is the period *before* it (its recorded snapshot is the
  state after it, which can already be the next period).
* Uses and charge consumption count every event, including plays later
  reversed by a Challenge (perk uses are never refunded). Football history
  (snap index, previous snap, families used, charge creation) ignores reversed
  plays, because the Challenge restored the football state.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from src.engine.football import (
    DEFENSIVE_SCHEME_FAMILIES,
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardFamily,
    FootballMatchEvent,
    FootballMatchState,
    FootballPerkActivation,
    FootballPerkDecision,
    FootballPlayerPerkKind,
    FootballPosition,
    FootballTeamSide,
    OFFENSIVE_PLAY_FAMILIES,
    OffensivePlayAction,
)
from src.engine.football_player_catalog import (
    FootballPlayerPerk,
    player_type_for_id,
)

GOAL_LINE_YARDS = 100.0
FIRST_DOWN_YARDS = 10.0
QB_PASS_FAMILIES = frozenset((
    FootballCardFamily.PA_PASS, FootballCardFamily.MEDIUM_PASS, FootballCardFamily.DEEP_PASS,
))
RB_FAMILIES = frozenset((
    FootballCardFamily.RB_RUN, FootballCardFamily.PA_PASS, FootballCardFamily.SHORT_PASS,
))


def half_of(period: int) -> int:
    """1, 2, or 3 (all overtime periods share one half)."""
    return min(period, 3)


def opponent(side: FootballTeamSide) -> FootballTeamSide:
    return FootballTeamSide.TEAM_B if side is FootballTeamSide.TEAM_A else FootballTeamSide.TEAM_A


def team_perks(
    state: FootballMatchState, side: FootballTeamSide
) -> dict[FootballPlayerPerkKind, tuple[FootballPosition, FootballPlayerPerk]]:
    """The perks a team's roster carries, keyed by kind, with each owner's position."""
    roster = state.team_a if side is FootballTeamSide.TEAM_A else state.team_b
    return dict(_roster_perks(tuple(
        (position, player.player_type_id) for position, player in roster.players.items()
    )))


@lru_cache(maxsize=256)
def _roster_perks(
    slots: tuple[tuple[FootballPosition, str | None], ...],
) -> tuple[tuple[FootballPlayerPerkKind, tuple[FootballPosition, FootballPlayerPerk]], ...]:
    found = []
    for position, type_id in slots:
        if type_id is None:
            continue
        perk = player_type_for_id(type_id).perk
        if perk is not None:
            found.append((perk.kind, (position, perk)))
    return tuple(found)


@dataclass(frozen=True)
class FootballSnapRecord:
    """One regular offensive snap (not a two-point try), with its pre-snap situation."""

    index: int  # 0-based event index
    team: FootballTeamSide
    play: OffensivePlayAction
    family: FootballCardFamily
    scheme: DefensiveSchemeAction | None
    down: int
    yards_to_go: float
    field_position: float
    period: int
    clock: int
    yards: float
    incomplete: bool
    turnover: bool
    touchdown: bool
    first_down: bool
    reversed: bool
    drive: int

    @property
    def completed_pass(self) -> bool:
        return (
            self.family is not FootballCardFamily.RB_RUN
            and not self.incomplete
            and not self.turnover
        )


@dataclass(frozen=True)
class FootballPerkHistory:
    """Everything perks need to know about the match so far, for both teams."""

    snaps: tuple[FootballSnapRecord, ...]
    # (event index, pre-event half, drive index, activation) for every activation.
    activations: tuple[tuple[int, int, int, FootballPerkActivation], ...]
    current_drive: int
    current_half: int
    drive_start_index: int  # index of the current drive's scheme event, or len(events)

    def drive_snaps(self, team: FootballTeamSide) -> tuple[FootballSnapRecord, ...]:
        """The team's non-reversed snaps in the current drive."""
        return tuple(
            snap for snap in self.snaps
            if snap.drive == self.current_drive and snap.team is team and not snap.reversed
        )

    def used(
        self, kind: FootballPlayerPerkKind, team: FootballTeamSide, scope: str
    ) -> bool:
        """Has ``team`` triggered ``kind`` this 'drive', 'half', or 'game'?"""
        for _index, half, drive, activation in self.activations:
            if activation.kind is not kind or activation.team is not team or activation.applied:
                continue
            if scope == "game":
                return True
            if scope == "half" and half == self.current_half:
                return True
            if scope == "drive" and drive == self.current_drive:
                return True
        return False

    def deep_charge(self, offense: FootballTeamSide, *, armed_by_completion: bool,
                    whole_game: bool) -> bool:
        """Charge state over ``offense``'s Deep snaps (Shot Setup / Bait & Jump).

        Each Deep snap consumes the charge (reversed ones included, so a
        challenged play never refunds it); a non-reversed incompletion (Shot
        Setup) or completion (Bait & Jump) then re-arms it.
        """
        armed = False
        for snap in self.snaps:
            if snap.team is not offense or snap.family is not FootballCardFamily.DEEP_PASS:
                continue
            if not whole_game and half_of(snap.period) != self.current_half:
                continue
            armed = False
            if snap.reversed:
                continue
            if armed_by_completion and snap.completed_pass:
                armed = True
            elif not armed_by_completion and snap.incomplete:
                armed = True
        return armed


def perk_history(state: FootballMatchState) -> FootballPerkHistory:
    return _history(state.match_events, state.awaited_action, state.period)


@lru_cache(maxsize=64)
def _history(
    events: tuple[FootballMatchEvent, ...],
    awaited: FootballAwaitedAction | None,
    period: int,
) -> FootballPerkHistory:
    reversed_sequences = {
        sequence for event in events for sequence in event.reverses_event_sequences
    }
    snaps: list[FootballSnapRecord] = []
    activations: list[tuple[int, int, int, FootballPerkActivation]] = []
    drive = -1
    drive_start = len(events)
    scheme: DefensiveSchemeAction | None = None
    for index, event in enumerate(events):
        previous = events[index - 1] if index else None
        pre_period = previous.period if previous is not None else 1
        if isinstance(event.action, DefensiveSchemeAction):
            drive += 1
            drive_start = index
            scheme = event.action
        result = event.play_result
        if result is not None and previous is not None and not result.conversion_attempt:
            family = OFFENSIVE_PLAY_FAMILIES[result.offensive_play]
            team = previous.possession
            line_to_gain = max(0.1, min(
                previous.yards_to_go, GOAL_LINE_YARDS - previous.offense_field_position,
            ))
            touchdown = bool(event.points_scored) and event.scoring_team is team and not result.turnover
            first_down = (
                not result.incomplete
                and not result.turnover
                and not touchdown
                and result.yards_gained >= line_to_gain
            )
            snaps.append(FootballSnapRecord(
                index=index,
                team=team,
                play=result.offensive_play,
                family=family,
                scheme=result.defensive_scheme or scheme,
                down=previous.down,
                yards_to_go=previous.yards_to_go,
                field_position=previous.offense_field_position,
                period=pre_period,
                clock=previous.game_clock_seconds,
                yards=result.yards_gained,
                incomplete=result.incomplete,
                turnover=result.turnover,
                touchdown=touchdown,
                first_down=first_down,
                reversed=event.sequence in reversed_sequences,
                drive=drive,
            ))
        if event.action is FootballPerkDecision.GREEN_DOG_SWAP and event.card_id:
            scheme = DefensiveSchemeAction(event.card_id)
        for activation in event.perk_activations:
            activations.append((index, half_of(pre_period), max(drive, 0), activation))
    current_drive = max(drive, 0)
    if awaited is FootballAwaitedAction.DEFENSIVE_SCHEME:
        # A new drive is about to start: nothing in it has happened yet.
        current_drive = drive + 1
        drive_start = len(events)
    return FootballPerkHistory(
        snaps=tuple(snaps),
        activations=tuple(activations),
        current_drive=current_drive,
        current_half=half_of(period),
        drive_start_index=drive_start,
    )


# Perks whose firing depends on the defense's active call (its family or which
# defensive players contribute). The defense's call is secret from the offense, so
# these never feed the offense's blind estimate, preview notes, or what the
# offense is shown. Offensive kinds depend on the rival's call; defensive kinds
# on their owner's own call. Screen Wall and Captain's Adjustment depend on the
# call only for their standing (``applied``) effect, not for their trigger.
OFFENSE_SCHEME_KEYED_PERKS = frozenset((
    FootballPlayerPerkKind.SILENT_COUNT,
    FootballPlayerPerkKind.HOT_ROUTE,
    FootballPlayerPerkKind.SCREEN_WALL,
))
DEFENSE_SCHEME_KEYED_PERKS = frozenset((
    FootballPlayerPerkKind.HOLD_THE_FRONT,
    FootballPlayerPerkKind.EDGE_SET,
    FootballPlayerPerkKind.CONTAIN,
    FootballPlayerPerkKind.STUNT_SACK,
    FootballPlayerPerkKind.FIT_AND_SHED,
    FootballPlayerPerkKind.CAPTAINS_ADJUSTMENT,
    FootballPlayerPerkKind.FORCE_AND_FOLD,
    FootballPlayerPerkKind.NICKEL_LOCK,
    FootballPlayerPerkKind.BRACKET,
    FootballPlayerPerkKind.DEEP_LOCK,
    FootballPlayerPerkKind.SAFETY_BLITZ,
    FootballPlayerPerkKind.DOWNHILL_FILL,
    FootballPlayerPerkKind.TIP_DRILL,
))
_APPLIED_ONLY_SCHEME_KEYED = frozenset((
    FootballPlayerPerkKind.SCREEN_WALL,
    FootballPlayerPerkKind.CAPTAINS_ADJUSTMENT,
))


def scheme_keyed_defense(activation: FootballPerkActivation) -> FootballTeamSide | None:
    """The team whose secret defense call this activation depends on, or None."""
    if activation.kind in _APPLIED_ONLY_SCHEME_KEYED and not activation.applied:
        return None
    if activation.kind in OFFENSE_SCHEME_KEYED_PERKS:
        return opponent(activation.team)
    if activation.kind in DEFENSE_SCHEME_KEYED_PERKS:
        return activation.team
    return None


def scheme_family(scheme: DefensiveSchemeAction) -> FootballCardFamily:
    return DEFENSIVE_SCHEME_FAMILIES[scheme]


@dataclass(frozen=True)
class FootballPerkEstimateInputs:
    """Player-perk changes to one play's estimate, all computed before the roll.

    ``power`` maps (side, position) to flat power added before fatigue, where
    side is "offense" or "defense". ``counter`` overrides whether the scheme
    counters the play (None keeps the family rule). ``activations`` lists the
    perks that shaped the estimate, in order, for previews and event records.
    """

    power: tuple[tuple[str, FootballPosition, float], ...] = ()
    counter: bool | None = None
    yards: float = 0.0
    incomplete: float = 0.0
    interception: float = 0.0
    keep_read: bool = False
    activations: tuple[FootballPerkActivation, ...] = ()

    def power_delta(self, side: str, position: FootballPosition) -> float:
        return sum(amount for owner, slot, amount in self.power if owner == side and slot is position)


NO_PERK_INPUTS = FootballPerkEstimateInputs()


def estimate_perk_inputs(
    state: FootballMatchState,
    offense_side: FootballTeamSide,
    play: OffensivePlayAction,
    scheme: DefensiveSchemeAction,
    *,
    is_conversion: bool = False,
    history: FootballPerkHistory | None = None,
) -> FootballPerkEstimateInputs:
    """The estimate-phase perks (power, counter, yards, odds) for a snap in ``state``."""
    from src.engine.football_decks import DEFENSIVE_SCHEME_CATALOG, OFFENSIVE_PLAY_CATALOG

    offense_perks = team_perks(state, offense_side)
    defense_side = opponent(offense_side)
    defense_perks = team_perks(state, defense_side)
    if not offense_perks and not defense_perks:
        return NO_PERK_INPUTS
    K = FootballPlayerPerkKind
    history = history or perk_history(state)
    family = OFFENSIVE_PLAY_FAMILIES[play]
    defense_family = DEFENSIVE_SCHEME_FAMILIES[scheme]
    offense_slots = OFFENSIVE_PLAY_CATALOG[play.value].contributors
    defense_slots = DEFENSIVE_SCHEME_CATALOG[scheme.value].contributors
    power: list[tuple[str, FootballPosition, float]] = []
    activations: list[FootballPerkActivation] = []
    yards = incomplete = interception = 0.0
    counter: bool | None = None
    keep_read = False

    def has(perks, kind) -> FootballPlayerPerk | None:
        entry = perks.get(kind)
        return entry[1] if entry is not None else None

    def fire(kind, team, value=0.0, applied=False) -> None:
        activations.append(FootballPerkActivation(kind, team, float(value), applied))

    if is_conversion:
        # Perks ignore two-point tries except Keep Read.
        perk = has(offense_perks, K.KEEP_READ)
        if (
            perk is not None
            and family is FootballCardFamily.PA_PASS
            and not history.used(K.KEEP_READ, offense_side, "half")
        ):
            keep_read = True
            fire(K.KEEP_READ, offense_side)
        return FootballPerkEstimateInputs(keep_read=keep_read, activations=tuple(activations))

    drive_snaps = history.drive_snaps(offense_side)
    previous = drive_snaps[-1] if drive_snaps else None
    down = state.down
    natural_counter = defense_family is family
    pass_play = family is not FootballCardFamily.RB_RUN

    # -- offense: power ------------------------------------------------------------
    perk = has(offense_perks, K.POCKET_PRESENCE)
    if perk is not None and FootballPosition.QB in offense_slots and len(drive_snaps) + 1 >= perk.value("from_snap"):
        power.append(("offense", FootballPosition.QB, perk.value("power")))
        fire(K.POCKET_PRESENCE, offense_side, perk.value("power"))
    perk = has(offense_perks, K.MOTION_JUMP)
    if (
        perk is not None
        and FootballPosition.WR in offense_slots
        and not history.used(K.MOTION_JUMP, offense_side, "drive")
    ):
        power.append(("offense", FootballPosition.WR, perk.value("power")))
        fire(K.MOTION_JUMP, offense_side, perk.value("power"))
    perk = has(offense_perks, K.PULL_LEAD)
    if (
        perk is not None
        and down >= 3
        and state.yards_to_go <= perk.value("distance")
        and FootballPosition.O_LINE in offense_slots
    ):
        power.append(("offense", FootballPosition.O_LINE, perk.value("power")))
        fire(K.PULL_LEAD, offense_side, perk.value("power"))
    perk = has(offense_perks, K.SCREEN_WALL)
    if (
        perk is not None
        and FootballPosition.D_LINE in defense_slots
        and history.used(K.SCREEN_WALL, offense_side, "drive")
    ):
        power.append(("defense", FootballPosition.D_LINE, -perk.value("power")))
        fire(K.SCREEN_WALL, offense_side, perk.value("power"), applied=True)

    # -- defense: power -----------------------------------------------------------
    perk = has(defense_perks, K.EDGE_SET)
    if (
        perk is not None
        and not drive_snaps
        and FootballPosition.D_LINE in defense_slots
        and not history.used(K.EDGE_SET, defense_side, "drive")
    ):
        power.append(("defense", FootballPosition.D_LINE, perk.value("power")))
        fire(K.EDGE_SET, defense_side, perk.value("power"))
    perk = has(defense_perks, K.CAPTAINS_ADJUSTMENT)
    if (
        perk is not None
        and FootballPosition.LINEBACKERS in defense_slots
        and history.used(K.CAPTAINS_ADJUSTMENT, defense_side, "drive")
    ):
        power.append(("defense", FootballPosition.LINEBACKERS, perk.value("power")))
        fire(K.CAPTAINS_ADJUSTMENT, defense_side, perk.value("power"), applied=True)
    perk = has(defense_perks, K.NICKEL_LOCK)
    if perk is not None and down == 3 and FootballPosition.CORNERBACKS in defense_slots:
        power.append(("defense", FootballPosition.CORNERBACKS, perk.value("power")))
        fire(K.NICKEL_LOCK, defense_side, perk.value("power"))
    perk = has(defense_perks, K.DOWNHILL_FILL)
    if (
        perk is not None
        and family is FootballCardFamily.RB_RUN
        and FootballPosition.SAFETIES in defense_slots
    ):
        power.append(("defense", FootballPosition.SAFETIES, perk.value("power")))
        fire(K.DOWNHILL_FILL, defense_side, perk.value("power"))

    # -- counter status: Force & Fold creates one, then Silent Count may cancel ----------
    countered = natural_counter
    perk = has(defense_perks, K.FORCE_AND_FOLD)
    force_fold = (
        perk is not None
        and family is FootballCardFamily.RB_RUN
        and defense_family is FootballCardFamily.SCREEN_PASS
    )
    if force_fold:
        countered = True
    perk = has(offense_perks, K.SILENT_COUNT)
    if (
        perk is not None
        and down >= 3
        and countered
        and not history.used(K.SILENT_COUNT, offense_side, "half")
    ):
        countered = False
        fire(K.SILENT_COUNT, offense_side)
    elif force_fold:
        fire(K.FORCE_AND_FOLD, defense_side)
    if countered != natural_counter:
        counter = countered

    # -- additive yards ---------------------------------------------------------------
    perk = has(offense_perks, K.CHECKDOWN)
    if (
        perk is not None
        and family in RB_FAMILIES
        and previous is not None
        and previous.family in QB_PASS_FAMILIES
        and previous.incomplete
    ):
        yards += perk.value("yards")
        fire(K.CHECKDOWN, offense_side, perk.value("yards"))
    perk = has(offense_perks, K.DOWNHILL)
    if (
        perk is not None
        and family is FootballCardFamily.RB_RUN
        and previous is not None
        and previous.family in RB_FAMILIES
    ):
        bonus = perk.value("run_yards") if previous.family is FootballCardFamily.RB_RUN else perk.value("yards")
        yards += bonus
        fire(K.DOWNHILL, offense_side, bonus)

    # -- odds -------------------------------------------------------------------------
    perk = has(offense_perks, K.KEEP_READ)
    if (
        perk is not None
        and family is FootballCardFamily.PA_PASS
        and down >= 3
        and not history.used(K.KEEP_READ, offense_side, "half")
    ):
        keep_read = True
        fire(K.KEEP_READ, offense_side)
    perk = has(offense_perks, K.SHOT_SETUP)
    if (
        perk is not None
        and family is FootballCardFamily.DEEP_PASS
        and history.deep_charge(offense_side, armed_by_completion=False, whole_game=False)
    ):
        incomplete += perk.value("incompletion")
        fire(K.SHOT_SETUP, offense_side, perk.value("incompletion"))
    perk = has(defense_perks, K.SAFETY_BLITZ)
    if (
        perk is not None
        and pass_play
        and down in (2, 3)
        and defense_family is FootballCardFamily.MEDIUM_PASS
        and FootballPosition.D_LINE in defense_slots
    ):
        incomplete += perk.value("incompletion")
        yards += perk.value("yards")
        fire(K.SAFETY_BLITZ, defense_side, perk.value("yards"))
    perk = has(defense_perks, K.BAIT_AND_JUMP)
    if (
        perk is not None
        and family is FootballCardFamily.DEEP_PASS
        and history.deep_charge(offense_side, armed_by_completion=True, whole_game=True)
        and not history.used(K.BAIT_AND_JUMP, defense_side, "half")
    ):
        interception += perk.value("interception")
        fire(K.BAIT_AND_JUMP, defense_side, perk.value("interception"))

    return FootballPerkEstimateInputs(
        power=tuple(power),
        counter=counter,
        yards=yards,
        incomplete=incomplete,
        interception=interception,
        keep_read=keep_read,
        activations=tuple(activations),
    )
