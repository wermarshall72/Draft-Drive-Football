"""The shared pause menu used by every run screen, plus a generic confirm panel.

One look everywhere: the navy veil, the match popup panel, and stacked 340x48
popup buttons. ``PauseMenu`` holds only transient UI state (open flag, saved
focus, the two-step Quit Run timer, and whether the AUDIO view is showing);
the run screen decides what each entry does. The AUDIO view shows the shared
volume sliders (``volume_slider``) over the application's audio settings.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pygame

from src.ui import football_ui_kit
from src.ui.football_ui_kit import (
    MATCH_DANGER, MATCH_FOCUS, MATCH_INK, MATCH_PANEL, MATCH_PANEL_EDGE,
    MATCH_PANEL_HIGH, MATCH_TEXT, blit_text, draw_popup_button,
    draw_popup_panel, draw_veil, match_font,
)
from src.ui.text import fit_text
from src.ui.volume_slider import (
    BLOCK_HEIGHT, AudioBinding, SliderInput, audio_sliders, local_audio_binding,
    match_slider_palette,
)
from src.ui.widgets import Button

KEEP_PLAYING = "KEEP PLAYING"
RETURN_TO_MENU = "RETURN TO MENU"
QUIT_RUN = "QUIT RUN"
CONFIRM_QUIT = "CONFIRM QUIT"
DEPTH_CHART = "DEPTH CHART"
AUDIO = "AUDIO"
AUDIO_TITLE = "AUDIO"
AUDIO_SUBTITLE = "Esc to go back"
BACK = "BACK"
PLAY_LOG = "PLAY LOG"
PAUSE_TITLE = "PAUSED"
PAUSE_SUBTITLE = "Esc to keep playing"
CONFIRM_SUBTITLE = "Press CONFIRM QUIT again to discard this run"
PAUSE_BUTTON_LABEL = "PAUSE [ESC]"
QUIT_CONFIRM_MS = 3000

PANEL_WIDTH = 420
BUTTON_WIDTH = 340
BUTTON_HEIGHT = 48
BUTTON_STRIDE = 64
BUTTONS_TOP = 98
PANEL_BOTTOM_PAD = 42
CONFIRM_VARIANT = "popup-confirm"
AUDIO_SLIDER_GAP = 18
AUDIO_BACK_GAP = 30


@dataclass(frozen=True)
class MenuEntry:
    label: str
    action: Callable[[], None]
    variant: str = "popup"


class PauseMenu:
    """Open/closed state, the focus to restore, and the armed Quit Run deadline."""

    def __init__(
        self, clock: Callable[[], int] = pygame.time.get_ticks,
        audio: AudioBinding | None = None,
    ) -> None:
        self.clock = clock
        self.is_open = False
        self.saved_focus = 0
        self._confirm_until: int | None = None
        # The application's audio settings (replaced by DesktopApplication).
        self.audio = audio or local_audio_binding()
        self.audio_open = False
        self.slider_input = SliderInput()
        self._audio_index = 1
        self._focus_request: int | None = None

    def show(self, saved_focus: int) -> None:
        self.is_open = True
        self.saved_focus = saved_focus
        self._confirm_until = None
        self.leave_audio()

    def hide(self) -> int:
        self.is_open = False
        self._confirm_until = None
        self.leave_audio()
        return self.saved_focus

    def reset(self) -> None:
        self.is_open = False
        self.saved_focus = 0
        self._confirm_until = None
        self.leave_audio()

    # -- the AUDIO view ----------------------------------------------------------------

    def open_audio(self) -> None:
        self._confirm_until = None
        self.audio_open = True
        self._focus_request = 0

    def close_audio(self) -> None:
        """BACK or Esc: return to the list with focus on AUDIO."""
        self.leave_audio()
        self._focus_request = self._audio_index

    def leave_audio(self) -> None:
        """Drop the AUDIO view without moving focus (the menu itself is closing)."""
        self.slider_input.release()
        self.audio_open = False
        self._focus_request = None

    def take_focus_request(self) -> int | None:
        """The focus index the caller should apply after opening or closing AUDIO."""
        request, self._focus_request = self._focus_request, None
        return request

    # -- two-step Quit Run -----------------------------------------------------------

    @property
    def confirming(self) -> bool:
        if self._confirm_until is not None and self.clock() >= self._confirm_until:
            self._confirm_until = None
        return self._confirm_until is not None

    def remaining_fraction(self) -> float:
        if not self.confirming:
            return 0.0
        assert self._confirm_until is not None
        return max(0.0, min(1.0, (self._confirm_until - self.clock()) / QUIT_CONFIRM_MS))

    def press_quit(self, quit_run: Callable[[], None]) -> None:
        """First press arms CONFIRM QUIT; a second press within the window quits."""
        if self.confirming:
            self._confirm_until = None
            quit_run()
            return
        self._confirm_until = self.clock() + QUIT_CONFIRM_MS

    def cancel_quit(self) -> bool:
        """Disarm CONFIRM QUIT; True when it was armed (so Esc stops there)."""
        armed = self.confirming
        self._confirm_until = None
        return armed

    def entries(
        self,
        *,
        keep_playing: Callable[[], None],
        return_to_menu: Callable[[], None],
        quit_run: Callable[[], None],
        extra: Sequence[MenuEntry] = (),
    ) -> list[MenuEntry]:
        armed = self.confirming
        self._audio_index = 1 + len(extra)
        return [
            MenuEntry(KEEP_PLAYING, keep_playing, "popup-primary"),
            *extra,
            MenuEntry(AUDIO, self.open_audio),
            MenuEntry(RETURN_TO_MENU, return_to_menu),
            MenuEntry(
                CONFIRM_QUIT if armed else QUIT_RUN,
                lambda: self.press_quit(quit_run),
                CONFIRM_VARIANT if armed else "popup-danger",
            ),
        ]


def panel_rect(surface_size: tuple[int, int], entry_count: int, width: int = PANEL_WIDTH) -> pygame.Rect:
    height = BUTTONS_TOP + (entry_count - 1) * BUTTON_STRIDE + BUTTON_HEIGHT + PANEL_BOTTOM_PAD
    rect = pygame.Rect(0, 0, width, height)
    rect.center = (surface_size[0] // 2, surface_size[1] // 2)
    return rect


def draw_menu_panel(
    surface: pygame.Surface,
    title: str,
    subtitle: str,
    entries: Sequence[MenuEntry],
    *,
    focus_index: int,
    hover_index: int | None,
    pressed_index: int | None,
    width: int = PANEL_WIDTH,
    button_width: int = BUTTON_WIDTH,
    confirm_fraction: float = 0.0,
) -> list[Button]:
    """Veil, panel, and stacked buttons; returns the buttons in entry order."""
    draw_veil(surface)
    rect = panel_rect(surface.get_size(), len(entries), width)
    draw_popup_panel(surface, rect, title, subtitle)
    buttons: list[Button] = []
    for index, entry in enumerate(entries):
        button_rect = pygame.Rect(0, rect.top + BUTTONS_TOP + index * BUTTON_STRIDE,
                                  button_width, BUTTON_HEIGHT)
        button_rect.centerx = rect.centerx
        button = Button(entry.label, entry.action, button_rect, variant=entry.variant)
        button.focused = focus_index == index
        buttons.append(button)
        focused, hovered, pressed = (
            focus_index == index, hover_index == index, pressed_index == index,
        )
        if entry.variant == CONFIRM_VARIANT:
            _draw_confirm_button(surface, button, focused=focused, pressed=pressed,
                                 fraction=confirm_fraction)
        else:
            draw_popup_button(surface, button, focused=focused, hovered=hovered, pressed=pressed)
        # Record the label for text-fit audits (the kit button renders it itself).
        font = match_font(17)
        label = fit_text(entry.label, font, button_rect.width - 20)
        audit_rect = pygame.Rect((0, 0), font.size(label))
        audit_rect.center = button_rect.center
        _audit_only(label, audit_rect, button_rect)
    return buttons


def draw_pause_menu(
    surface: pygame.Surface,
    menu: PauseMenu,
    entries: Sequence[MenuEntry],
    *,
    focus_index: int,
    hover_index: int | None,
    pressed_index: int | None,
) -> list[Button]:
    quit_index = len(entries) - 1
    # Moving focus (keyboard or hover) off the armed button reverts it.
    if menu.confirming and focus_index != quit_index:
        menu.cancel_quit()
        entries = [*entries[:-1], MenuEntry(QUIT_RUN, entries[-1].action, "popup-danger")]
    confirming = menu.confirming
    return draw_menu_panel(
        surface, PAUSE_TITLE, CONFIRM_SUBTITLE if confirming else PAUSE_SUBTITLE, entries,
        focus_index=focus_index, hover_index=hover_index, pressed_index=pressed_index,
        confirm_fraction=menu.remaining_fraction(),
    )


def audio_panel_rect(surface_size: tuple[int, int], width: int = PANEL_WIDTH) -> pygame.Rect:
    height = (BUTTONS_TOP + BLOCK_HEIGHT * 2 + AUDIO_SLIDER_GAP + AUDIO_BACK_GAP
              + BUTTON_HEIGHT + PANEL_BOTTOM_PAD)
    rect = pygame.Rect(0, 0, width, height)
    rect.center = (surface_size[0] // 2, surface_size[1] // 2)
    return rect


def draw_pause_audio(
    surface: pygame.Surface,
    menu: PauseMenu,
    *,
    focus_index: int,
    hover_index: int | None,
    pressed_index: int | None,
) -> list[Button]:
    """The pause panel's AUDIO view: Music, Sound effects, and BACK, in that order."""
    draw_veil(surface)
    rect = audio_panel_rect(surface.get_size())
    draw_popup_panel(surface, rect, AUDIO_TITLE, AUDIO_SUBTITLE)
    top = rect.top + BUTTONS_TOP - 8
    left = rect.centerx - BUTTON_WIDTH // 2
    music = pygame.Rect(left, top, BUTTON_WIDTH, BLOCK_HEIGHT)
    effects = music.move(0, BLOCK_HEIGHT + AUDIO_SLIDER_GAP)
    buttons: list[Button] = list(audio_sliders(
        menu.audio, music, effects, match_slider_palette(), dragging=menu.slider_input.dragging,
    ))
    back_rect = pygame.Rect(left, effects.bottom + AUDIO_BACK_GAP, BUTTON_WIDTH, BUTTON_HEIGHT)
    buttons.append(Button(BACK, menu.close_audio, back_rect, variant="popup"))
    for index, button in enumerate(buttons):
        button.focused = focus_index == index
        focused, hovered, pressed = (
            focus_index == index, hover_index == index, pressed_index == index,
        )
        if button.label == BACK:
            draw_popup_button(surface, button, focused=focused, hovered=hovered, pressed=pressed)
        else:
            button.draw(surface, None, None, hovered=hovered, pressed=pressed)
    return buttons


def _draw_confirm_button(
    surface: pygame.Surface, button: Button, *, focused: bool, pressed: bool, fraction: float,
) -> None:
    rect = button.rect.move(0, 2) if pressed else button.rect
    if focused:
        pygame.draw.rect(surface, MATCH_DANGER, rect.inflate(6, 6), 2, border_radius=11)
    pygame.draw.rect(surface, MATCH_DANGER, rect, border_radius=9)
    pygame.draw.rect(surface, MATCH_INK, rect, 2, border_radius=9)
    bar_width = round((rect.width - 20) * fraction)
    if bar_width > 0:
        pygame.draw.rect(surface, MATCH_INK, (rect.left + 10, rect.bottom - 7, bar_width, 3),
                         border_radius=2)
    font = match_font(17)
    label = font.render(fit_text(button.label, font, rect.width - 20), True, MATCH_INK)
    surface.blit(label, label.get_rect(center=rect.center))


def _audit_only(text: str, rect: pygame.Rect, container: pygame.Rect) -> None:
    """Add a record to an active ``text_audit`` without drawing anything."""
    records = football_ui_kit._TEXT_AUDIT
    if records is not None:
        records.append((text, pygame.Rect(rect), pygame.Rect(container)))


def draw_pause_button(
    surface: pygame.Surface, button: Button, *, focused: bool, hovered: bool, pressed: bool,
) -> None:
    """The gameplay scoreboard's PAUSE [ESC] look, sized to the caller's slot."""
    rect = button.rect.move(0, 1) if pressed else button.rect
    fill = MATCH_PANEL_HIGH if hovered or focused else MATCH_PANEL
    pygame.draw.rect(surface, fill, rect, border_radius=6)
    pygame.draw.rect(surface, MATCH_FOCUS if focused else MATCH_PANEL_EDGE, rect,
                     2 if focused else 1, border_radius=6)
    font = match_font(12 if rect.height <= 28 else 15)
    blit_text(surface, font, PAUSE_BUTTON_LABEL, MATCH_TEXT, rect, center=rect.center)
