"""Read-only team totals for the post-game result screen.

Pure: everything is derived from a finished match's recorded events. Only
offensive snaps count, credited to the team that snapped the ball. Plays a
Challenge overturned and two-point tries are excluded. Incomplete passes and
interceptions gain 0 yards; a fumble keeps the yards gained before it.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.engine.football import (
    FootballMatchEvent,
    FootballTeamSide,
    FootballTurnoverType,
    OffensivePlayAction,
)
from src.ui.football_match_events import (
    PlayLineKind,
    offense_side,
    overturned_sequences,
    play_kind,
)


@dataclass(frozen=True)
class TeamGameStats:
    rushing_yards: int = 0
    passing_yards: int = 0
    plays: int = 0
    turnovers: int = 0
    longest_play: int = 0

    @property
    def total_yards(self) -> int:
        return self.rushing_yards + self.passing_yards


@dataclass(frozen=True)
class MatchTeamStats:
    team_a: TeamGameStats
    team_b: TeamGameStats

    def side(self, side: FootballTeamSide) -> TeamGameStats:
        return self.team_a if side is FootballTeamSide.TEAM_A else self.team_b


def snap_yards(event: FootballMatchEvent) -> float:
    """Yards credited to the offense for one snap (0 for incompletions and interceptions)."""
    result = event.play_result
    assert result is not None
    if result.incomplete:
        return 0.0
    if result.turnover:
        interception = (
            result.turnover_type is FootballTurnoverType.INTERCEPTION
            if result.turnover_type is not None
            else play_kind(result.offensive_play) is PlayLineKind.PASS
        )
        if interception:
            return 0.0
    return result.yards_gained


def match_team_stats(events: tuple[FootballMatchEvent, ...]) -> MatchTeamStats:
    overturned = overturned_sequences(events)
    totals = {
        side: {"run": 0.0, "pass": 0.0, "plays": 0, "turnovers": 0, "longest": 0.0}
        for side in FootballTeamSide
    }
    for index, event in enumerate(events):
        result = event.play_result
        if (
            not isinstance(event.action, OffensivePlayAction)
            or result is None
            or result.conversion_attempt
            or event.sequence in overturned
        ):
            continue
        previous = events[index - 1] if index else None
        side_totals = totals[offense_side(event, previous)]
        yards = snap_yards(event)
        kind = "run" if play_kind(result.offensive_play) is PlayLineKind.RUN else "pass"
        side_totals[kind] += yards
        side_totals["plays"] += 1
        side_totals["turnovers"] += int(result.turnover or result.turnover_on_downs)
        side_totals["longest"] = max(side_totals["longest"], yards)

    def build(values: dict) -> TeamGameStats:
        return TeamGameStats(
            rushing_yards=round(values["run"]),
            passing_yards=round(values["pass"]),
            plays=values["plays"],
            turnovers=values["turnovers"],
            longest_play=round(values["longest"]),
        )

    return MatchTeamStats(
        build(totals[FootballTeamSide.TEAM_A]), build(totals[FootballTeamSide.TEAM_B])
    )
