"""Sequential replay of match events that arrive in one controller update."""

from __future__ import annotations

from dataclasses import dataclass

from src.engine.football import FootballMatchState

EVENT_DURATION_MS = 1000
LINE_DRAW_MS = 400


@dataclass
class MatchPlayback:
    """Track which recorded events the screen has shown and when each began.

    One new event animates in place without blocking input. Two or more new
    events (an AI drive, a scoring sequence) replay one at a time for
    ``EVENT_DURATION_MS`` each, and input stays blocked until the final event
    has finished or the player skips.
    """

    match_key: tuple[int, str, str] | None = None
    shown: int = 0
    target: int = 0
    step_started: int = 0
    replaying: bool = False
    origin: int = 0  # events already settled when the current replay began

    def reset(self) -> None:
        self.match_key = None
        self.shown = 0
        self.target = 0
        self.step_started = 0
        self.replaying = False
        self.origin = 0

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
            return
        if total > self.target:
            pending_from = self.shown if self.replaying else self.target
            self.target = total
            if total - pending_from >= 2 or self.replaying or force_replay:
                if not self.replaying:
                    self.origin = pending_from
                    self.shown = pending_from + 1
                    self.step_started = now
                self.replaying = True
            else:
                self.shown = total
                self.step_started = now
        self._advance(now)

    def _advance(self, now: int) -> None:
        if not self.replaying:
            return
        while now - self.step_started >= EVENT_DURATION_MS:
            if self.shown >= self.target:
                self.replaying = False
                return
            self.shown += 1
            self.step_started += EVENT_DURATION_MS

    def blocking(self) -> bool:
        return self.replaying

    def skip(self) -> None:
        """Jump straight to the latest event; its line appears fully drawn."""
        self.shown = self.target
        self.step_started -= EVENT_DURATION_MS * 2
        self.replaying = False

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
