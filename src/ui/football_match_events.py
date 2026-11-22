"""Read-only interpretation of match events for the match screen.

Everything here is pure: it turns recorded ``FootballMatchEvent`` snapshots into
field play lines, outcome-strip text, and display snapshots. Field positions in
this module are *absolute*: 0 is Team A's goal line (left end zone) and 100 is
Team B's goal line (right end zone).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from src.engine.football import (
    OFFENSIVE_PLAY_FAMILIES,
    DefensiveSchemeAction,
    FootballAutomaticAction,
    FootballBonusCardAction,
    FootballCardFamily,
    FootballConversionAction,
    FootballFourthDownAction,
    FootballAwaitedAction,
    FootballMatchEvent,
    FootballMatchState,
    FootballMatchStatus,
    FootballTeamSide,
    FootballTurnoverType,
    OffensivePlayAction,
)
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)

KICKOFF_SPOT = 35.0
CONVERSION_SPOT = 98.0
SAFETY_POINTS = 2


class PlayLineKind(Enum):
    RUN = "run"
    PASS = "pass"
    OTHER = "other"


class OutcomeEmphasis(Enum):
    NORMAL = "normal"
    SCORE = "score"
    TURNOVER = "turnover"


@dataclass(frozen=True)
class PlaySegment:
    kind: PlayLineKind
    start: float
    end: float


@dataclass(frozen=True)
class PlayLine:
    """The drawable result of one snap or kick, in absolute field yards."""

    segments: tuple[PlaySegment, ...] = ()
    incomplete_at: float | None = None
    turnover_at: float | None = None
    blocked_at: float | None = None
    flash_end_zone: float | None = None  # 0.0 = left end zone, 100.0 = right


CLEAR_LINE = PlayLine()


@dataclass(frozen=True)
class Outcome:
    headline: str
    detail: str
    kind: PlayLineKind
    emphasis: OutcomeEmphasis = OutcomeEmphasis.NORMAL


def opponent(side: FootballTeamSide) -> FootballTeamSide:
    return FootballTeamSide.TEAM_B if side is FootballTeamSide.TEAM_A else FootballTeamSide.TEAM_A


def absolute_spot(side: FootballTeamSide, offense_position: float) -> float:
    return offense_position if side is FootballTeamSide.TEAM_A else 100.0 - offense_position


def direction(side: FootballTeamSide) -> int:
    return 1 if side is FootballTeamSide.TEAM_A else -1


def attacking_goal(side: FootballTeamSide) -> float:
    return 100.0 if side is FootballTeamSide.TEAM_A else 0.0


def own_goal(side: FootballTeamSide) -> float:
    return 0.0 if side is FootballTeamSide.TEAM_A else 100.0


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def play_family_kind(family: FootballCardFamily) -> PlayLineKind:
    return PlayLineKind.RUN if family is FootballCardFamily.RB_RUN else PlayLineKind.PASS


def play_kind(action: OffensivePlayAction) -> PlayLineKind:
    return play_family_kind(OFFENSIVE_PLAY_FAMILIES[action])


def _event_spot(event: FootballMatchEvent) -> float:
    return absolute_spot(event.possession, event.offense_field_position)


def _same_period(previous: FootballMatchEvent, event: FootballMatchEvent) -> bool:
    # Overtime periods reposition the ball; a snapshot taken after that reset no
    # longer describes where the play itself ended.
    return event.period == previous.period or event.period < 3


def _segment(kind: PlayLineKind, start: float, end: float) -> tuple[PlaySegment, ...]:
    start, end = _clamp(start), _clamp(end)
    if abs(end - start) < 0.05:
        return ()
    return (PlaySegment(kind, start, end),)


def play_line(
    event: FootballMatchEvent, previous: FootballMatchEvent | None
) -> PlayLine | None:
    """Return the line for a snap or kick, ``CLEAR_LINE`` to clear, or ``None`` to keep.

    ``previous`` is the event before ``event``; its snapshot is the pre-snap spot.
    """
    action = event.action
    if isinstance(action, FootballBonusCardAction):
        return CLEAR_LINE if event.reverses_event_sequences else None
    if isinstance(action, DefensiveSchemeAction) or action is FootballFourthDownAction.GO_FOR_IT:
        return None
    if action is FootballAutomaticAction.KICKOFF:
        return _kickoff_line(event)
    if previous is None:
        return None
    side = previous.possession
    start = _event_spot(previous)
    forward = direction(side)
    if isinstance(action, OffensivePlayAction):
        return _offensive_line(event, previous, side, start, forward)
    if action is FootballFourthDownAction.PUNT:
        return _punt_line(event, previous, side, start, forward)
    if action is FootballFourthDownAction.FIELD_GOAL:
        if event.blocked:
            return _blocked_line(event, previous, side, start)
        segments = _segment(PlayLineKind.OTHER, start, attacking_goal(side))
        return PlayLine(
            segments=segments,
            flash_end_zone=attacking_goal(side) if event.points_scored else None,
        )
    if isinstance(action, FootballConversionAction):
        return _conversion_line(event, side)
    return None


def _offensive_line(
    event: FootballMatchEvent,
    previous: FootballMatchEvent,
    side: FootballTeamSide,
    start: float,
    forward: int,
) -> PlayLine:
    result = event.play_result
    assert result is not None
    kind = play_kind(result.offensive_play)
    if result.incomplete:
        return PlayLine(incomplete_at=start)
    if result.turnover:
        spot = _clamp(start + forward * result.yards_gained)
        segments = _segment(kind, start, spot)
        defense = opponent(side)
        flash = None
        if event.points_scored == SAFETY_POINTS:
            # A fumble behind the offense's own goal line is a safety, not a return.
            segments = _segment(kind, start, own_goal(side))
            return PlayLine(
                segments=segments, turnover_at=own_goal(side), flash_end_zone=own_goal(side)
            )
        if event.points_scored and event.scoring_team is defense:
            end = attacking_goal(defense)
            flash = end
        elif _same_period(previous, event) and event.possession is defense:
            end = _event_spot(event)
        else:
            end = spot
        segments += _segment(PlayLineKind.OTHER, spot, end)
        return PlayLine(segments=segments, turnover_at=spot, flash_end_zone=flash)
    end = _clamp(start + forward * result.yards_gained)
    flash = None
    if event.points_scored and event.scoring_team is side:
        end = attacking_goal(side)
        flash = end
    elif event.points_scored:
        end = own_goal(side)
        flash = end
    return PlayLine(segments=_segment(kind, start, end), flash_end_zone=flash)


def _punt_line(
    event: FootballMatchEvent,
    previous: FootballMatchEvent,
    side: FootballTeamSide,
    start: float,
    forward: int,
) -> PlayLine:
    if event.blocked:
        return _blocked_line(event, previous, side, start)
    gross = event.gross_yards or 0.0
    landing = _clamp(start + forward * gross)
    segments = _segment(PlayLineKind.OTHER, start, landing)
    returned = event.return_yards or 0.0
    if returned:
        segments += _segment(PlayLineKind.OTHER, landing, landing - forward * returned)
    return PlayLine(segments=segments)


def _blocked_line(
    event: FootballMatchEvent,
    previous: FootballMatchEvent,
    side: FootballTeamSide,
    start: float,
) -> PlayLine:
    if event.points_scored:
        end = own_goal(side)
        return PlayLine(
            segments=_segment(PlayLineKind.OTHER, start, end),
            blocked_at=start,
            flash_end_zone=end,
        )
    end = _event_spot(event) if _same_period(previous, event) else start
    return PlayLine(segments=_segment(PlayLineKind.OTHER, start, end), blocked_at=start)


def _kickoff_line(event: FootballMatchEvent) -> PlayLine:
    receiving = event.possession
    kicking = opponent(receiving)
    kick_spot = absolute_spot(kicking, KICKOFF_SPOT)
    landing = absolute_spot(kicking, min(100.0, KICKOFF_SPOT + (event.gross_yards or 0.0)))
    segments = _segment(PlayLineKind.OTHER, kick_spot, landing)
    returned = event.return_yards or 0.0
    flash = None
    if event.points_scored:
        end = attacking_goal(receiving)
        flash = end
    else:
        end = absolute_spot(receiving, returned) if returned else landing
    segments += _segment(PlayLineKind.OTHER, landing, end)
    return PlayLine(segments=segments, flash_end_zone=flash)


def _conversion_line(event: FootballMatchEvent, side: FootballTeamSide) -> PlayLine:
    start = absolute_spot(side, CONVERSION_SPOT)
    goal = attacking_goal(side)
    if event.action is FootballConversionAction.EXTRA_POINT:
        if event.blocked:
            return PlayLine(blocked_at=start)
        return PlayLine(segments=_segment(PlayLineKind.OTHER, start, goal))
    kind = (
        play_kind(OffensivePlayAction(event.card_id))
        if event.card_id in OFFENSIVE_PLAY_CATALOG
        else PlayLineKind.RUN
    )
    description = (event.description or "").lower()
    if "incomplete" in description:
        return PlayLine(incomplete_at=start)
    if event.points_scored and event.scoring_team is side:
        return PlayLine(segments=_segment(kind, start, goal))
    if "intercepted" in description or "fumbled" in description or event.points_scored:
        return PlayLine(turnover_at=start)
    gross = event.gross_yards or 0.0
    return PlayLine(segments=_segment(kind, start, start + direction(side) * gross))


def latest_play_line(events: tuple[FootballMatchEvent, ...]) -> tuple[int, PlayLine] | None:
    """The newest drawable line and the index of the event that produced it."""
    for index in range(len(events) - 1, -1, -1):
        line = play_line(events[index], events[index - 1] if index else None)
        if line is not None:
            if line == CLEAR_LINE:
                return None
            return index, line
    return None


def team_name(side: FootballTeamSide | None, team_a: str, team_b: str) -> str:
    return team_a if side is FootballTeamSide.TEAM_A else team_b


def format_yards(yards: float) -> str:
    if abs(yards) < 0.05:
        return "NO GAIN"
    if abs(yards) < 0.5:
        value = f"{yards:+.1f}"
    else:
        value = f"{round(yards):+d}"
    unit = "YARD" if value in ("+1", "-1") else "YARDS"
    return f"{value} {unit}"


def offense_side(
    event: FootballMatchEvent, previous: FootballMatchEvent | None
) -> FootballTeamSide:
    """The team that snapped the ball for an offensive-play event."""
    if previous is not None:
        return previous.possession
    result = event.play_result
    if result is not None and result.points_scored and not result.turnover and event.scoring_team:
        # A touchdown keeps the scorer on offense for the conversion; a safety does not.
        if result.points_scored == SAFETY_POINTS:
            return opponent(event.scoring_team)
        return event.scoring_team
    if result is not None and result.possession_changed:
        return opponent(event.possession)
    return event.possession


def _play_name(action: OffensivePlayAction) -> str:
    return OFFENSIVE_PLAY_CATALOG[action.value].name.upper()


def outcome(
    event: FootballMatchEvent,
    previous: FootballMatchEvent | None,
    team_a: str,
    team_b: str,
) -> Outcome:
    """Outcome-strip headline and detail for one recorded event."""
    action = event.action
    if isinstance(action, OffensivePlayAction):
        return _offensive_outcome(event, previous, team_a, team_b)
    if isinstance(action, DefensiveSchemeAction):
        scheme = DEFENSIVE_SCHEME_CATALOG[action.value]
        defense = team_name(opponent(event.possession), team_a, team_b)
        return Outcome(
            f"DEFENSE SET · {scheme.name.upper()}",
            f"{defense.upper()} · COUNTERS {scheme.family.label.upper()}",
            PlayLineKind.OTHER,
        )
    if isinstance(action, FootballBonusCardAction):
        bonus = BONUS_CARD_CATALOG[action.value]
        if action is FootballBonusCardAction.CHALLENGE:
            return Outcome(
                "CHALLENGE · PLAY OVERTURNED",
                f"{team_a.upper()} · BALL RESTORED TO THE PREVIOUS SPOT",
                PlayLineKind.OTHER,
                OutcomeEmphasis.TURNOVER,
            )
        return Outcome(
            bonus.name.upper(),
            f"{team_a.upper()} · {bonus_effect(action)} · 10s",
            PlayLineKind.OTHER,
        )
    kicking = previous.possession if previous is not None else event.possession
    kicking_name = team_name(kicking, team_a, team_b).upper()
    if action is FootballFourthDownAction.GO_FOR_IT:
        return Outcome("GOING FOR IT", f"{kicking_name} · 4TH DOWN", PlayLineKind.OTHER)
    if action is FootballFourthDownAction.PUNT:
        if event.blocked:
            return _blocked_outcome(event, "PUNT", kicking_name, team_a, team_b)
        gross = round(event.gross_yards or 0.0)
        returned = round(event.return_yards or 0.0)
        description = (event.description or "").lower()
        if "touchback" in description:
            detail = "TOUCHBACK"
        elif returned:
            detail = f"RETURNED {returned}"
        else:
            detail = "NO RETURN"
        return Outcome(f"PUNT · {gross} YARDS", f"{detail} · {kicking_name}", PlayLineKind.OTHER)
    if action is FootballFourthDownAction.FIELD_GOAL:
        if event.blocked:
            return _blocked_outcome(event, "FIELD GOAL", kicking_name, team_a, team_b)
        distance = round(event.field_goal_distance or 0.0)
        if event.points_scored:
            return Outcome(
                f"FIELD GOAL GOOD · {distance} YDS",
                f"+3 · {kicking_name}",
                PlayLineKind.OTHER,
                OutcomeEmphasis.SCORE,
            )
        return Outcome(
            f"FIELD GOAL MISSED · {distance} YDS",
            f"NO GOOD · {kicking_name}",
            PlayLineKind.OTHER,
        )
    if action is FootballAutomaticAction.KICKOFF:
        receiving = team_name(event.possession, team_a, team_b).upper()
        kicker = team_name(opponent(event.possession), team_a, team_b).upper()
        if event.points_scored:
            return Outcome(
                "KICKOFF RETURN TOUCHDOWN!", f"+6 · {receiving}",
                PlayLineKind.OTHER, OutcomeEmphasis.SCORE,
            )
        returned = round(event.return_yards or 0.0)
        if not returned:
            return Outcome("KICKOFF · TOUCHBACK", f"{kicker} KICKS · {receiving} BALL", PlayLineKind.OTHER)
        return Outcome(
            f"KICKOFF · RETURNED {returned}",
            f"{kicker} KICKS · {receiving} BALL",
            PlayLineKind.OTHER,
        )
    if isinstance(action, FootballConversionAction):
        return _conversion_outcome(event, kicking, team_a, team_b)
    return Outcome(action.value.replace("_", " ").upper(), "", PlayLineKind.OTHER)


def _blocked_outcome(
    event: FootballMatchEvent, kick: str, kicking_name: str, team_a: str, team_b: str
) -> Outcome:
    if event.points_scored:
        scorer = team_name(event.scoring_team, team_a, team_b).upper()
        return Outcome(
            "BLOCKED KICK · RETURNED FOR TD!", f"+6 · {scorer}",
            PlayLineKind.OTHER, OutcomeEmphasis.SCORE,
        )
    return Outcome(
        "BLOCKED KICK", f"{kick} · {kicking_name} · TURNOVER", PlayLineKind.OTHER,
        OutcomeEmphasis.TURNOVER,
    )


def _offensive_outcome(
    event: FootballMatchEvent,
    previous: FootballMatchEvent | None,
    team_a: str,
    team_b: str,
) -> Outcome:
    result = event.play_result
    assert result is not None
    side = offense_side(event, previous)
    kind = play_kind(result.offensive_play)
    offense = team_name(side, team_a, team_b).upper()
    detail = f"{_play_name(result.offensive_play)} · {offense}"
    defense = opponent(side)
    if result.turnover:
        if result.turnover_type is not None:
            interception = result.turnover_type is FootballTurnoverType.INTERCEPTION
        else:
            interception = kind is PlayLineKind.PASS
        name = "INTERCEPTION" if interception else "FUMBLE"
        if event.points_scored == SAFETY_POINTS:
            return Outcome(f"{name} · SAFETY", detail, kind, OutcomeEmphasis.TURNOVER)
        if event.points_scored and event.scoring_team is defense:
            return Outcome(f"{name} · RETURNED FOR TD!", detail, kind, OutcomeEmphasis.TURNOVER)
        line = play_line(event, previous) if previous is not None else None
        returned = 0
        if line is not None and len(line.segments) and line.turnover_at is not None:
            last = line.segments[-1]
            if last.kind is PlayLineKind.OTHER and last.start == line.turnover_at:
                returned = round(abs(last.end - last.start))
        headline = f"{name} · RETURNED {returned}" if returned else name
        return Outcome(headline, detail, kind, OutcomeEmphasis.TURNOVER)
    if event.points_scored and event.scoring_team is side:
        return Outcome("TOUCHDOWN!", f"{detail} · {format_yards(result.yards_gained)}", kind, OutcomeEmphasis.SCORE)
    if event.points_scored:
        return Outcome("SAFETY", f"{detail} · {format_yards(result.yards_gained)}", kind, OutcomeEmphasis.TURNOVER)
    if result.incomplete:
        if result.turnover_on_downs:
            return Outcome("INCOMPLETE · TURNOVER ON DOWNS", detail, kind, OutcomeEmphasis.TURNOVER)
        return Outcome("INCOMPLETE", detail, kind)
    yards = format_yards(result.yards_gained)
    if result.turnover_on_downs:
        return Outcome(f"{yards} · TURNOVER ON DOWNS", detail, kind, OutcomeEmphasis.TURNOVER)
    first_down = (
        previous is not None
        and event.possession is side
        and event.down == 1
        and event.period == previous.period
    )
    return Outcome(f"{yards} · FIRST DOWN" if first_down else yards, detail, kind)


def _conversion_outcome(
    event: FootballMatchEvent, side: FootballTeamSide, team_a: str, team_b: str
) -> Outcome:
    name = team_name(side, team_a, team_b).upper()
    description = (event.description or "").lower()
    if event.action is FootballConversionAction.EXTRA_POINT:
        if event.points_scored and event.scoring_team is side:
            return Outcome("EXTRA POINT GOOD", f"+1 · {name}", PlayLineKind.OTHER, OutcomeEmphasis.SCORE)
        if event.points_scored:
            scorer = team_name(event.scoring_team, team_a, team_b).upper()
            return Outcome("BLOCKED XP · RETURNED FOR 2", f"+2 · {scorer}", PlayLineKind.OTHER, OutcomeEmphasis.TURNOVER)
        if event.blocked:
            return Outcome("EXTRA POINT BLOCKED", name, PlayLineKind.OTHER, OutcomeEmphasis.TURNOVER)
        return Outcome("EXTRA POINT MISSED", name, PlayLineKind.OTHER)
    play = (
        OffensivePlayAction(event.card_id)
        if event.card_id in OFFENSIVE_PLAY_CATALOG
        else OffensivePlayAction.RB_RUN
    )
    kind = play_kind(play)
    detail = f"{_play_name(play)} · {name}"
    if event.points_scored and event.scoring_team is side:
        return Outcome("2-PT GOOD", f"+2 · {detail}", kind, OutcomeEmphasis.SCORE)
    if event.points_scored:
        scorer = team_name(event.scoring_team, team_a, team_b).upper()
        return Outcome("2-PT RETURNED FOR 2", f"+2 · {scorer}", kind, OutcomeEmphasis.TURNOVER)
    if "incomplete" in description:
        return Outcome("2-PT FAILED · INCOMPLETE", detail, kind)
    if "intercepted" in description or "fumbled" in description:
        return Outcome("2-PT FAILED · TURNOVER", detail, kind, OutcomeEmphasis.TURNOVER)
    return Outcome("2-PT FAILED", f"{detail} · {format_yards(event.gross_yards or 0.0)}", kind)


def bonus_effect(action: FootballBonusCardAction) -> str:
    return {
        FootballBonusCardAction.OFFENSIVE_DRAW: "DRAW 1 PLAY",
        FootballBonusCardAction.DEFENSIVE_DRAW: "DRAW 1 SCHEME",
        FootballBonusCardAction.OPPONENT_DISCARD: "DRAW 1 · OPP DISCARDS",
        FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD: "DRAW PLAY · OPP DISCARDS",
        FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD: "DRAW SCHEME · OPP DISCARDS",
        FootballBonusCardAction.CHALLENGE: "UNDO YOUR LAST PLAY",
    }[action]


def is_real_play(event: FootballMatchEvent) -> bool:
    """Snaps and kicks; not scheme calls, Go For It, or bonus cards."""
    return isinstance(
        event.action, (OffensivePlayAction, FootballConversionAction, FootballAutomaticAction)
    ) or event.action in (FootballFourthDownAction.PUNT, FootballFourthDownAction.FIELD_GOAL)


def replay_label(
    events: tuple[FootballMatchEvent, ...], origin: int, shown: int, target: int
) -> str:
    """Strip label for a replay of ``events[origin:target]`` showing ``shown`` events."""
    plays = [index for index in range(origin, target) if is_real_play(events[index])]
    current = shown - 1
    if current in plays:
        return f"REPLAYING · PLAY {plays.index(current) + 1} OF {len(plays)} · [S] SKIP"
    if plays:
        noun = "PLAY" if len(plays) == 1 else "PLAYS"
        return f"REPLAYING · {len(plays)} {noun} · [S] SKIP"
    return "REPLAYING · [S] SKIP"


def period_label(period: int) -> str:
    if period == 1:
        return "1ST HALF"
    if period == 2:
        return "2ND HALF"
    overtime = period - 2
    return "OT" if overtime == 1 else f"{overtime}OT"


def period_banner(
    event: FootballMatchEvent, previous: FootballMatchEvent | None
) -> str | None:
    """A field banner for the moment a half, overtime, or the match ends."""
    if event.status.value == "completed":
        return "FINAL"
    if previous is None or event.period == previous.period:
        return None
    if event.period == 2:
        return "HALFTIME"
    return "OVERTIME" if event.period == 3 else f"OVERTIME {event.period - 2}"


def active_scheme(
    events: tuple[FootballMatchEvent, ...],
) -> DefensiveSchemeAction | None:
    """The scheme set for the drive in progress after ``events``."""
    scheme: DefensiveSchemeAction | None = None
    for index, event in enumerate(events):
        if isinstance(event.action, DefensiveSchemeAction):
            scheme = event.action
            continue
        previous = events[index - 1] if index else None
        if (
            previous is not None
            and event.possession is not previous.possession
        ) or isinstance(
            event.action,
            (FootballConversionAction, FootballAutomaticAction),
        ) or event.action in (
            FootballFourthDownAction.PUNT,
            FootballFourthDownAction.FIELD_GOAL,
        ) or (previous is not None and event.period != previous.period and event.period >= 3):
            scheme = None
    return scheme


def kickoff_pending(match: FootballMatchState, shown_events: int) -> FootballTeamSide | None:
    """The kicking team when the event shown next is an automatic kickoff.

    After a PAT, 2-point try, field goal, or safety the simulator records a
    placeholder receiving-team state before the kickoff event; that placeholder
    is not a real drive and should not be displayed as one.
    """
    events = match.match_events
    if not 0 < shown_events < len(events):
        return None
    following = events[shown_events]
    if following.action is not FootballAutomaticAction.KICKOFF:
        return None
    return opponent(following.possession)


def snapshot_state(
    match: FootballMatchState, shown_events: int
) -> FootballMatchState:
    """``match`` as it looked right after its first ``shown_events`` events."""
    if shown_events >= len(match.match_events):
        return match
    if shown_events <= 0:
        raise ValueError("A display snapshot needs at least one recorded event.")
    events = match.match_events[:shown_events]
    event = events[-1]
    completed = event.status is FootballMatchStatus.COMPLETED
    awaiting_conversion = (
        not completed
        and event.down == 1
        and event.yards_to_go == 2.0
        and event.offense_field_position == CONVERSION_SPOT
    )
    scheme = None if completed else active_scheme(events)
    if awaiting_conversion and scheme is None:
        scheme = DefensiveSchemeAction.GOAL_LINE_FRONT
    kicking = None if awaiting_conversion else kickoff_pending(match, shown_events)
    possession, position = event.possession, event.offense_field_position
    down, yards_to_go = event.down, event.yards_to_go
    if kicking is not None:
        # Show the ball on the kicking team's tee instead of a drive that has not started.
        possession, position, down, yards_to_go, scheme = kicking, KICKOFF_SPOT, 1, 10.0, None
    return replace(
        match,
        team_a_score=event.team_a_score,
        team_b_score=event.team_b_score,
        possession=possession,
        offense_field_position=position,
        down=down,
        yards_to_go=yards_to_go,
        game_clock_seconds=event.game_clock_seconds,
        period=event.period,
        status=event.status,
        awaited_action=FootballAwaitedAction.CONVERSION if awaiting_conversion else None,
        conversion_team=event.possession if awaiting_conversion else None,
        current_drive_defensive_scheme=scheme,
        final_result=match.final_result if completed else None,
        match_events=events,
    )


def overturned_sequences(events: tuple[FootballMatchEvent, ...]) -> frozenset[int]:
    return frozenset(
        sequence for event in events for sequence in event.reverses_event_sequences
    )
