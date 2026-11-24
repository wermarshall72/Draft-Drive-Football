from __future__ import annotations

from dataclasses import dataclass, field
import secrets
from typing import TYPE_CHECKING

import pygame

from src.ui.player_art import SKIN_TONES
from src.engine.football_team_builder import FootballPlayerCandidate
from src.engine.football import FootballPosition
from src.engine.football_appearance import FootballPlayerAppearance

if TYPE_CHECKING:
    from src.ui.football_inspect import InspectState


def _new_inspect_state() -> InspectState:
    # Imported lazily: football_inspect imports the player draft view, which imports this module.
    from src.ui.football_inspect import InspectState
    return InspectState()


CoachKey = tuple[str, int, str]  # ("coach", pair index, "offense" | "defense" | "pair")
# Keys that move keyboard focus; they hand the coach panel from the pointer to focus.
_FOCUS_KEYS = frozenset({pygame.K_TAB, pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT})


@dataclass
class CoachInspection:
    """Pair highlight plus the coach inspect panel on the coach selection screen.

    ``card_rects`` and ``coach_rects`` come from the last drawn frame. A coach's
    portrait/modifier column and perk row open that coach's inspect panel; a
    keyboard-focused pair opens one panel describing both of its coaches.
    """

    keyboard: bool = True
    hover_index: int | None = None
    window_left: bool = False
    card_rects: list[pygame.Rect] = field(default_factory=list)
    coach_rects: list[tuple[CoachKey, pygame.Rect]] = field(default_factory=list)
    hover_coach: CoachKey | None = None
    inspect: InspectState = field(default_factory=_new_inspect_state)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            # Only keys that move or use focus hand the highlight to the keyboard.
            if event.key in _FOCUS_KEYS or event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.keyboard = True
                self.hover_index = None
            if event.key in _FOCUS_KEYS:
                self.hover_coach = None
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            if event.type == pygame.MOUSEBUTTONUP and self.window_left:
                return
            self.window_left = False
            self.keyboard = False
            self.hover_index = next(
                (index for index, rect in enumerate(self.card_rects)
                 if rect.collidepoint(event.pos)),
                None,
            )
            self.hover_coach = next(
                (key for key, rect in self.coach_rects if rect.collidepoint(event.pos)), None,
            )
        elif event.type == pygame.WINDOWLEAVE:
            self.hover_index = None
            self.hover_coach = None
            self.keyboard = False
            self.window_left = True

    def active_index(self, focus_index: int) -> int | None:
        return focus_index if self.keyboard else self.hover_index

    def focus_key(self, focus_index: int) -> CoachKey | None:
        """The keyboard-focused pair, whose panel shows both coaches (None off the pairs)."""
        if 0 <= focus_index < len(self.card_rects):
            return ("coach", focus_index, "pair")
        return None

    def reset_inspect(self) -> None:
        self.hover_coach = None
        self.inspect.reset()


@dataclass
class PlayerInspection:
    keyboard: bool = False
    hover_index: int | None = None
    window_left: bool = False
    card_rects: list[pygame.Rect] = field(default_factory=list)
    offers: tuple[FootballPlayerCandidate, ...] = ()
    skin_tones: tuple[tuple[int, int, int], ...] = ()
    portraits: list[tuple[pygame.Rect, FootballPlayerAppearance, bool]] = field(default_factory=list)
    # The tracker row lit as the active card's partner position in the last drawn frame.
    partner_row: FootballPosition | None = None

    def set_offers(self, offers: tuple[FootballPlayerCandidate, ...]) -> None:
        if len(offers) != len(self.offers) or any(
            old is not new for old, new in zip(self.offers, offers)
        ):
            self.offers = offers
            self.skin_tones = tuple(secrets.choice(SKIN_TONES) for _ in offers)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            self.keyboard = True
            self.hover_index = None
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            if event.type == pygame.MOUSEBUTTONUP and self.window_left:
                return
            self.window_left = False
            self.keyboard = False
            self.hover_index = next(
                (index for index, rect in enumerate(self.card_rects)
                 if rect.collidepoint(event.pos)),
                None,
            )
        elif event.type == pygame.WINDOWLEAVE:
            self.hover_index = None
            self.keyboard = False
            self.window_left = True

    def active_index(self, focus_index: int) -> int | None:
        return focus_index if self.keyboard else self.hover_index
