from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import pygame

from src.ui.widgets import Button


@dataclass(frozen=True)
class InspectionEvent:
    consumed: bool = False
    update_hover: bool = False
    hover_index: int | None = None


@dataclass
class CoachInspection:
    keyboard: bool = False
    hover_index: int | None = None
    popup_pressed: bool = False
    focus_changed_at: int = 0

    def handle_event(
        self,
        event: pygame.event.Event,
        buttons: Sequence[Button],
        focus_index: int,
        popup_rect: Callable[[int], pygame.Rect],
    ) -> InspectionEvent:
        if event.type == pygame.KEYDOWN:
            self.keyboard = True
            self.hover_index = None
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            if (
                self.keyboard
                and focus_index < len(buttons)
                and buttons[focus_index].variant == "coach-inspect"
                and popup_rect(focus_index).collidepoint(event.pos)
            ):
                self.hover_index = focus_index
            self.keyboard = False
            if (
                self.hover_index is not None
                and popup_rect(self.hover_index).collidepoint(event.pos)
            ):
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.popup_pressed = True
                return InspectionEvent(consumed=True)
            self.hover_index = next(
                (index for index, button in enumerate(buttons)
                 if button.variant == "coach-inspect" and button.rect.collidepoint(event.pos)),
                None,
            )
            if self.hover_index is not None:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.popup_pressed = True
                return InspectionEvent(True, True, self.hover_index)
        elif event.type == pygame.WINDOWLEAVE:
            self.hover_index = None
            self.keyboard = False
            return InspectionEvent(update_hover=True)
        elif event.type == pygame.MOUSEBUTTONUP and self.popup_pressed:
            self.popup_pressed = False
            return InspectionEvent(consumed=True)
        return InspectionEvent()


@dataclass
class PlayerInspection:
    keyboard: bool = False
    hover_index: int | None = None
    popup_pressed: bool = False
    card_rects: list[pygame.Rect] = field(default_factory=list)
    detail_rect: pygame.Rect | None = None

    def handle_event(
        self, event: pygame.event.Event, focus_index: int
    ) -> InspectionEvent:
        if event.type == pygame.KEYDOWN:
            self.keyboard = True
            self.hover_index = None
        elif event.type == pygame.MOUSEBUTTONUP and self.popup_pressed:
            self.popup_pressed = False
            return InspectionEvent(consumed=True)
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            if (
                self.keyboard
                and 0 <= focus_index < len(self.card_rects)
                and self.detail_rect is not None
                and self.detail_rect.collidepoint(event.pos)
            ):
                self.hover_index = focus_index
            self.keyboard = False
            if self.detail_rect is not None and self.detail_rect.collidepoint(event.pos):
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.popup_pressed = True
                return InspectionEvent(consumed=True)
            self.hover_index = next(
                (index for index, rect in enumerate(self.card_rects)
                 if rect.collidepoint(event.pos)),
                None,
            )
        elif event.type == pygame.WINDOWLEAVE:
            self.hover_index = None
            self.keyboard = False
            self.popup_pressed = False
            return InspectionEvent(update_hover=True)
        return InspectionEvent()
