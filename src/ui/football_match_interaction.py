from dataclasses import dataclass, field
from enum import Enum

import pygame


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
    """Own transient hand geometry, per-group scrolling, and drag state."""

    group_scroll: dict[str, int] = field(default_factory=lambda: {"offense": 0, "defense": 0})
    group_max_scroll: dict[str, int] = field(default_factory=lambda: {"offense": 0, "defense": 0})
    group_areas: dict[str, pygame.Rect] = field(default_factory=dict)
    card_rects: dict[str, pygame.Rect] = field(default_factory=dict)
    play_areas: tuple[pygame.Rect, ...] = ()
    dragging_card_id: str | None = None
    drag_origin: tuple[int, int] | None = None
    pointer: tuple[int, int] | None = None
    auto_scroll_key: tuple | None = None

    @property
    def dragging(self) -> bool:
        """True once a pressed card has moved far enough to be a drag."""
        if self.dragging_card_id is None or self.drag_origin is None or self.pointer is None:
            return False
        dx = self.pointer[0] - self.drag_origin[0]
        dy = self.pointer[1] - self.drag_origin[1]
        return dx * dx + dy * dy >= 64

    def scroll_group(self, group: str, delta: int) -> None:
        maximum = self.group_max_scroll.get(group, 0)
        self.group_scroll[group] = max(0, min(maximum, self.group_scroll.get(group, 0) + delta))

    def handle_event(self, event: pygame.event.Event) -> HandEvent:
        if event.type == pygame.MOUSEMOTION:
            self.pointer = event.pos
            return HandEvent(HandEventKind.IGNORED)
        if event.type == pygame.MOUSEWHEEL and self.pointer is not None:
            for group, area in self.group_areas.items():
                if area.collidepoint(self.pointer) and self.group_max_scroll.get(group, 0):
                    self.scroll_group(group, -event.y)
                    return HandEvent(HandEventKind.HANDLED)
            return HandEvent(HandEventKind.IGNORED)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pointer = event.pos
            selected = next(
                (copy_id for copy_id, rect in self.card_rects.items()
                 if rect.collidepoint(event.pos)),
                None,
            )
            if selected is not None:
                self.dragging_card_id = selected
                self.drag_origin = event.pos
                return HandEvent(HandEventKind.HANDLED)
        if (
            event.type == pygame.MOUSEBUTTONUP
            and event.button == 1
            and self.dragging_card_id is not None
        ):
            selected = self.dragging_card_id
            self.dragging_card_id = None
            self.drag_origin = None
            self.pointer = event.pos
            origin = self.card_rects.get(selected)
            if any(area.collidepoint(event.pos) for area in self.play_areas) or (
                origin is not None and origin.collidepoint(event.pos)
            ):
                return HandEvent(HandEventKind.SELECTED, selected)
            return HandEvent(HandEventKind.INVALID_DROP)
        return HandEvent(HandEventKind.IGNORED)

    def cancel_drag(self) -> None:
        self.dragging_card_id = None
        self.drag_origin = None
