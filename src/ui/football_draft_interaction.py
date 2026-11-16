from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
import secrets

import pygame

from src.ui.widgets import Button
from src.ui.player_art import SKIN_TONES
from src.engine.football_team_builder import FootballPlayerCandidate


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
    window_left: bool = False
    card_rects: list[pygame.Rect] = field(default_factory=list)
    offers: tuple[FootballPlayerCandidate, ...] = ()
    skin_tones: tuple[tuple[int, int, int], ...] = ()

    def set_offers(self, offers: tuple[FootballPlayerCandidate, ...]) -> None:
        if len(offers) != len(self.offers) or any(
            old is not new for old, new in zip(self.offers, offers)
        ):
            self.offers = offers
            self.skin_tones = tuple(secrets.choice(SKIN_TONES) for _ in offers)

    def handle_event(self, event: pygame.event.Event, buttons: Sequence[Button]) -> None:
        if event.type == pygame.KEYDOWN:
            self.keyboard = True
            self.hover_index = None
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            if event.type == pygame.MOUSEBUTTONUP and self.window_left:
                return
            self.window_left = False
            self.keyboard = False
            self.hover_index = next(
                (index for index, button in enumerate(buttons)
                 if button.variant == "draft-select" and button.rect.collidepoint(event.pos)),
                None,
            )
        elif event.type == pygame.WINDOWLEAVE:
            self.hover_index = None
            self.keyboard = False
            self.window_left = True

    def active_index(self, focus_index: int) -> int | None:
        return focus_index if self.keyboard else self.hover_index
