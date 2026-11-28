"""Sequential replay of match events that arrive in one controller update."""

from __future__ import annotations

from dataclasses import dataclass

from src.engine.football import FootballMatchState
from src.ui.football_match_events import (
    RivalDriveEnd,
    is_real_play,
    rival_drive_end,
    rival_replay,
)

EVENT_DURATION_MS = 1000
LINE_DRAW_MS = 400


@dataclass
class MatchPlayback:
    """Track which recorded events the screen has shown and when each began.

    One new event animates in place without blocking input. Two or more new
    events (an AI drive, a scoring sequence) replay one at a time for
    ``EVENT_DURATION_MS`` each, and input stays blocked until the final event
    has finished or the player skips.

    When the new events end a rival drive, the replay stops before the possession
    change (``drive.hold``) and the drive result box opens; ``release`` (its
    button) then plays the held events as one play animation. The box is
    presentation only: nothing here changes the match.
    """

    match_key: tuple[int, str, str] | None = None
    shown: int = 0
    target: int = 0
    step_started: int = 0
    replaying: bool = False
    origin: int = 0  # events already settled when the current replay began
    drive: RivalDriveEnd | None = None  # the rival drive these events end, if any
    released: bool = False  # the drive result box was closed
    rival: bool = False  # the current replay is (part of) a rival drive
    step_first: int | None = None  # first event animated by the current step, if several

    def reset(self) -> None:
        self.match_key = None
        self.shown = 0
        self.target = 0
        self.step_started = 0
        self.replaying = False
        self.origin = 0
        self._clear_drive()

    def _clear_drive(self) -> None:
        self.drive = None
        self.released = False
        self.rival = False
        self.step_first = None

    @staticmethod
    def _key(match: FootballMatchState) -> tuple[int, str, str]:
        return (match.random_seed, match.team_a.team_name, match.team_b.team_name)

    def sync(self, match: FootballMatchState, now: int, *, force_replay: bool = False) -> None:
        """Pick up new events and advance the replay clock to ``now``.

        ``force_replay`` replays even a single new event; the screen uses it for
        a match's final events so they show before the results screen.
        """
        total = len(match.match_events)
        key = self._key(match)
        if key != self.match_key or total < self.target:
            # A new match (or a history that shrank) starts fully shown.
            self.match_key = key
            self.shown = self.target = total
            self.step_started = now - EVENT_DURATION_MS
            self.replaying = False
            self._clear_drive()
            return
        if total > self.target:
            pending_from = self.shown if self.replaying else self.target
            self.target = total
            if not self.replaying:
                self._clear_drive()
                events = match.match_events
                self.drive = rival_drive_end(events, pending_from, match.team_b.team_name)
                self.rival = rival_replay(events, pending_from, total)
            if (
                total - pending_from >= 2 or self.replaying or force_replay
                or self.drive is not None
            ):
                if not self.replaying:
                    self.origin = pending_from
                    self.shown = min(pending_from + 1, self._stop())
                    self.step_started = now
                    # A possession change that is the first new event opens the box at once.
                    self.replaying = self._stop() > pending_from
            else:
                self.shown = total
                self.step_started = now
        self._advance(now)

    def _stop(self) -> int:
        """Where the current replay ends: the held possession change, else the target."""
        if self.drive is not None and not self.released:
            return min(self.drive.hold, self.target)
        return self.target

    def _advance(self, now: int) -> None:
        if not self.replaying:
            return
        while now - self.step_started >= EVENT_DURATION_MS:
            if self.shown >= self._stop():
                self.replaying = False
                self.step_first = None
                return
            self.shown += 1
            self.step_started += EVENT_DURATION_MS

    def blocking(self) -> bool:
        return self.replaying or self.box_open

    @property
    def box_open(self) -> bool:
        """The drive result box is up: the replay reached the held possession change."""
        return self.drive is not None and not self.released and not self.replaying

    @property
    def rival_drive_replay(self) -> bool:
        """A rival drive is replaying (SKIP jumps to the end of the drive)."""
        return self.replaying and self.rival and not self.released

    @property
    def chart_visible(self) -> bool:
        return self.drive is not None and (self.released or not self.replaying)

    def chart_range(self) -> tuple[int, int]:
        """Events drawn as the drive chart: the drive, then any released events shown."""
        assert self.drive is not None
        end = self.shown if self.released else self.drive.hold
        return self.drive.start, max(end, self.drive.hold)

    def skip(self) -> None:
        """Jump to the end of the replay; its line appears fully drawn.

        A rival drive stops at its result box, never past it.
        """
        self.shown = max(self.shown, self._stop())
        self.step_started -= EVENT_DURATION_MS * 2
        self.replaying = False
        self.step_first = None

    def release(self, now: int, events: tuple) -> None:
        """Close the result box and play the held possession change.

        A single held snap or kick (with any scheme call after it) animates as one
        play; more than one replays as usual.
        """
        if not self.box_open:
            return
        assert self.drive is not None
        self.released = True
        hold = self.drive.hold
        plays = sum(1 for index in range(hold, self.target) if is_real_play(events[index]))
        self.origin = hold
        self.step_started = now
        if plays <= 1:
            self.shown = self.target
            self.step_first = hold
            self.replaying = plays == 1
        else:
            self.shown = hold + 1
            self.step_first = None
            self.replaying = True

    def finish(self) -> None:
        """Show everything at once, with no result box (leaving the match, resuming)."""
        self.skip()
        self.shown = self.target
        self._clear_drive()

    def current_step_start(self) -> int:
        """The first event the current animation step covers."""
        return self.step_first if self.step_first is not None else self.shown - 1

    def line_progress(self, now: int) -> float:
        return max(0.0, min(1.0, (now - self.step_started) / LINE_DRAW_MS))

    def step_progress(self, now: int) -> float:
        return max(0.0, min(1.0, (now - self.step_started) / EVENT_DURATION_MS))

    @property
    def replay_position(self) -> tuple[int, int]:
        """(current play number, plays in this replay), both 1-based."""
        return self.shown - self.origin, self.target - self.origin

    def debug_show(self, index: int, started: int) -> None:
        """Freeze on event ``index`` (0-based) as if mid-replay; used by tools."""
        self.shown = index + 1
        self.origin = index
        self.step_started = started
        self.replaying = True
