from dataclasses import dataclass, field
from enum import Enum

import pygame

from src.engine.football import FootballMatchState


class HandEventKind(Enum):
    IGNORED = "ignored"
    HANDLED = "handled"
    SELECTED = "selected"
    INVALID_DROP = "invalid_drop"


@dataclass(frozen=True)
class HandEvent:
    kind: HandEventKind
    copy_id: str | None = None


@dataclass
class MatchInteraction:
    """Own transient hand geometry, drag state, scrolling, and field animation."""

    hand_scroll: int = 0
    hand_max_scroll: int = 0
    hand_area: pygame.Rect | None = None
    card_rects: dict[str, pygame.Rect] = field(default_factory=dict)
    play_area: pygame.Rect | None = None
    dragging_card_id: str | None = None
    visual_state: FootballMatchState | None = None
    animation_started: int = 0
    animation_origin: float = 0.0
    animation_target: float = 0.0
    animation_gain_origin: float = 0.0
    animation_gain_target: float = 0.0
    animation_active: bool = False

    def handle_event(self, event: pygame.event.Event) -> HandEvent:
        if (
            event.type == pygame.MOUSEWHEEL
            and self.hand_area is not None
            and self.hand_max_scroll > 0
        ):
            self.hand_scroll = max(
                0, min(self.hand_max_scroll, self.hand_scroll - event.y)
            )
            return HandEvent(HandEventKind.HANDLED)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            selected = next(
                (copy_id for copy_id, rect in self.card_rects.items()
                 if rect.collidepoint(event.pos)),
                None,
            )
            if selected is not None:
                self.dragging_card_id = selected
                return HandEvent(HandEventKind.HANDLED)
        if (
            event.type == pygame.MOUSEBUTTONUP
            and event.button == 1
            and self.dragging_card_id is not None
        ):
            selected = self.dragging_card_id
            self.dragging_card_id = None
            origin = self.card_rects.get(selected)
            if (
                self.play_area is not None and self.play_area.collidepoint(event.pos)
            ) or (origin is not None and origin.collidepoint(event.pos)):
                return HandEvent(HandEventKind.SELECTED, selected)
            return HandEvent(HandEventKind.INVALID_DROP)
        return HandEvent(HandEventKind.IGNORED)

    def field_positions(
        self, match: FootballMatchState, now: int
    ) -> tuple[float, float]:
        previous = self.visual_state
        if previous is None:
            self.visual_state = match
            return (
                match.offense_field_position,
                min(100.0, match.offense_field_position + match.yards_to_go),
            )

        if len(previous.match_events) != len(match.match_events):
            self.animation_origin = previous.offense_field_position
            self.animation_target = match.offense_field_position
            self.animation_gain_origin = min(
                100.0, previous.offense_field_position + previous.yards_to_go
            )
            self.animation_gain_target = min(
                100.0, match.offense_field_position + match.yards_to_go
            )
            self.animation_started = now
            self.animation_active = True
        self.visual_state = match

        if not self.animation_active:
            return (
                match.offense_field_position,
                min(100.0, match.offense_field_position + match.yards_to_go),
            )
        progress = min(1.0, max(0.0, (now - self.animation_started) / 360))
        eased = progress * progress * (3 - 2 * progress)
        if progress >= 1:
            self.animation_active = False
        return (
            self.animation_origin + (self.animation_target - self.animation_origin) * eased,
            self.animation_gain_origin
            + (self.animation_gain_target - self.animation_gain_origin) * eased,
        )
