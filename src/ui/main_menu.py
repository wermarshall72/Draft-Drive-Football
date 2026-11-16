"""The desktop season menu and its profile-aware controls."""

from collections.abc import Callable

import pygame

from src.application import MainMenuState
from src.engine.football_ai import FootballAIDifficulty
from src.ui.coach_fonts import staff_font
from src.ui.main_menu_art import draw_menu_stadium
from src.ui.screens import Navigate, Quit, Screen
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button, draw_text

_TEXT = pygame.Color("#eef5ff")
_MUTED = pygame.Color("#b5c8dc")
_EDGE = pygame.Color("#507397")


def _marquee(surface: pygame.Surface, text: str, rect: pygame.Rect,
             font: pygame.font.Font, color: pygame.Color) -> None:
    """Keep long, unrestricted profile names and error details legible."""
    rendered = font.render(text, True, color)
    old_clip = surface.get_clip()
    surface.set_clip(old_clip.clip(rect))
    if rendered.get_width() <= rect.width:
        x = rect.left
    else:
        distance = rendered.get_width() - rect.width
        # Pause at both ends so the beginning and end are easy to read.
        travel = distance * 35
        phase = pygame.time.get_ticks() % (travel * 2 + 3000)
        if phase < 1500:
            offset = 0
        elif phase < 1500 + travel:
            offset = (phase - 1500) // 35
        elif phase < 3000 + travel:
            offset = distance
        else:
            offset = distance - (phase - 3000 - travel) // 35
        x = rect.left - offset
    surface.blit(rendered, (x, rect.centery - rendered.get_height() // 2))
    surface.set_clip(old_clip)


class FootballMainMenuScreen(Screen):
    def __init__(
        self,
        theme: Theme,
        menu_state: MainMenuState | None,
        profile_error: str | None,
        navigate: Navigate,
        quit_application: Quit,
        on_start_run: Callable[[FootballAIDifficulty], None],
    ) -> None:
        super().__init__(theme, navigate, quit_application)
        self.menu_state = menu_state
        self.profile_error = profile_error
        self.on_start_run = on_start_run
        self.difficulty = FootballAIDifficulty.STANDARD
        self.title_font = staff_font(48, semibold=True)
        self.menu_font = staff_font(25, semibold=True)
        self.detail_font = staff_font(17)
        self.badge_font = staff_font(21, semibold=True)
        self.small_font = staff_font(15, semibold=True)
        self.overlay: pygame.Surface | None = None
        self.keyboard_focus = True

    def on_enter(self) -> None:
        super().on_enter()
        self.hover_index = None
        self.pressed_index = None
        self.keyboard_focus = True

    def on_exit(self) -> None:
        super().on_exit()
        self.hover_index = None
        self.pressed_index = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.WINDOWLEAVE:
            self.hover_index = None
            self.pressed_index = None
            return
        if event.type == pygame.KEYDOWN:
            self.hover_index = None
            self.pressed_index = None
            self.keyboard_focus = True
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.keyboard_focus = False
        super().handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        draw_menu_stadium(surface, self.theme.primary, self.theme.secondary)
        self.overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        self._draw_overlay(self.overlay)
        surface.blit(self.overlay, (0, 0))

    def _draw_overlay(self, surface: pygame.Surface) -> None:
        draw_text(surface, "COLLEGE FOOTBALL", (36, 20), self.title_font, _TEXT)
        draw_text(surface, "BUILD YOUR PROGRAM  /  CALL THE GAME", (39, 78),
                  self.detail_font, _MUTED)
        pygame.draw.line(surface, _EDGE, (39, 107), (618, 107), 2)

        badge = pygame.Rect(855, 25, 389, 68)
        pygame.draw.rect(surface, "#102e4a", badge, border_radius=6)
        pygame.draw.rect(surface, _EDGE, badge, 2, border_radius=6)
        pygame.draw.rect(surface, self.theme.primary, (badge.left + 13, badge.top + 13, 9, 42))
        pygame.draw.rect(surface, self.theme.secondary, (badge.left + 25, badge.top + 13, 5, 42))
        draw_text(surface, "YOUR PROGRAM", (badge.left + 42, badge.top + 8),
                  self.small_font, _MUTED)
        team_name = self.menu_state.profile.team_name if self.menu_state else "NEW TEAM"
        _marquee(surface, team_name.upper(),
                 pygame.Rect(badge.left + 42, badge.top + 30, badge.width - 54, 29),
                 self.badge_font, _TEXT)

        buttons = [
            Button("START RUN", lambda: self.on_start_run(self.difficulty),
                   pygame.Rect(40, 139, 500, 77), enabled=self.menu_state is not None),
        ]
        for index, difficulty in enumerate(FootballAIDifficulty):
            buttons.append(Button(
                difficulty.value.upper(),
                lambda choice=difficulty: self._select_difficulty(choice),
                pygame.Rect(53 + index * 159, 262, 151, 42),
                variant="primary" if difficulty is self.difficulty else "quiet",
            ))
        buttons.extend((
            Button("SETTINGS" if self.menu_state else "CREATE PROFILE",
                   lambda: self.navigate("settings"), pygame.Rect(40, 323, 500, 77),
                   enabled=self.profile_error is None),
            Button("QUIT", self.quit_application, pygame.Rect(40, 415, 500, 77)),
        ))
        if self.focus_index == 0 and self.menu_state is None:
            self.focus_index = 4 if self.profile_error is None else 5
        self._set_buttons(buttons)
        difficulty_panel = pygame.Rect(40, 228, 500, 86)
        pygame.draw.rect(surface, "#102b47", difficulty_panel, border_radius=6)
        pygame.draw.rect(surface, _EDGE, difficulty_panel, 2, border_radius=6)
        draw_text(surface, "OPPONENT DIFFICULTY", (54, 235), self.small_font, _MUTED)

        details = {
            "START RUN": "Draft your team and begin a new run.",
            "SETTINGS": "Edit your team name and colors.",
            "CREATE PROFILE": "Create a team before starting a run.",
            "QUIT": "Exit the game.",
        }
        for index, button in enumerate(buttons):
            active = (
                (self.keyboard_focus and button.focused)
                or self.hover_index == index
                or self.pressed_index == index
            )
            pressed = self.pressed_index == index
            if 1 <= index <= 3:
                self._draw_difficulty(surface, button, active, pressed)
            else:
                self._draw_menu_button(surface, button, details[button.label], active, pressed)

        if self.profile_error or (self.theme.warning and self.menu_state):
            warning = pygame.Rect(40, 511, 650, 105)
            pygame.draw.rect(surface, "#182c40", warning, border_radius=6)
            pygame.draw.rect(surface, "#e29c82", warning, 2, border_radius=6)
            if self.profile_error:
                draw_text(surface, "PROFILE COULD NOT LOAD", (54, 520),
                          self.small_font, pygame.Color("#ffb4a3"))
                draw_text(surface, "Resolve the saved file outside the game; it will not be overwritten.",
                          (54, 542), self.detail_font, _TEXT)
                _marquee(surface, self.profile_error,
                         pygame.Rect(54, 568, warning.width - 28, 27),
                         self.detail_font, _MUTED)
            else:
                draw_text(surface, "COLOR FALLBACK", (54, 520),
                          self.small_font, pygame.Color("#ffb4a3"))
                _marquee(surface, self.theme.warning or "",
                         pygame.Rect(54, 545, warning.width - 28, 30),
                         self.detail_font, _TEXT)

        footer = pygame.Rect(40, 642, 1200, 49)
        pygame.draw.rect(surface, "#0b223c", footer, border_radius=5)
        pygame.draw.rect(surface, _EDGE, footer, 2, border_radius=5)
        pygame.draw.circle(surface, self.theme.primary, (62, footer.centery), 8)
        active_index = self.focus_index if self.keyboard_focus else self.hover_index
        active_button = (
            buttons[active_index]
            if active_index is not None and 0 <= active_index < len(buttons) else None
        )
        if active_button and active_button.enabled:
            message = details.get(active_button.label, "Select the local opponent's difficulty.")
        else:
            message = "Choose a difficulty, then start a new run."
        _marquee(surface, message, pygame.Rect(80, 650, 1128, 32), self.detail_font, _TEXT)

    def _draw_menu_button(self, surface: pygame.Surface, button: Button,
                          detail: str, active: bool, pressed: bool) -> None:
        rect = button.rect.move(0, 2 if pressed else 0)
        fill = self.theme.primary if active and button.enabled else pygame.Color("#102e4a")
        text = readable_ink(fill) if active and button.enabled else _TEXT
        if not button.enabled:
            fill, text = pygame.Color("#122638"), pygame.Color("#8093a4")
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        pygame.draw.rect(surface, _EDGE, rect, 2, border_radius=6)
        if active and button.enabled:
            pygame.draw.rect(surface, readable_ink(fill), rect.inflate(-4, -4), 3, border_radius=5)
            pygame.draw.rect(surface, self.theme.primary, rect.inflate(-10, -10), 2, border_radius=4)
        if self.keyboard_focus and button.focused and button.enabled:
            focus_label = self.small_font.render("FOCUS", True, text)
            surface.blit(focus_label, (rect.right - focus_label.get_width() - 18, rect.top + 13))
        draw_text(surface, button.label, (rect.left + 25, rect.top + 8), self.menu_font, text)
        draw_text(surface, detail, (rect.left + 26, rect.top + 43), self.detail_font, text)

    def _draw_difficulty(self, surface: pygame.Surface, button: Button,
                         active: bool, pressed: bool) -> None:
        rect = button.rect.move(0, 2 if pressed else 0)
        selected = button.variant == "primary"
        fill = self.theme.primary if selected or active else pygame.Color("#0a2037")
        text = readable_ink(fill) if selected or active else _TEXT
        pygame.draw.rect(surface, fill, rect, border_radius=4)
        pygame.draw.rect(surface, _EDGE, rect, 2, border_radius=4)
        if active:
            pygame.draw.rect(surface, readable_ink(fill), rect.inflate(-4, -4), 2, border_radius=3)
        if self.keyboard_focus and button.focused:
            pygame.draw.rect(surface, readable_ink(fill), rect.inflate(-10, -10), 1, border_radius=2)
        label = self.small_font.render(button.label, True, text)
        surface.blit(label, label.get_rect(center=rect.center))
        if selected:
            pygame.draw.line(surface, text, (rect.left + 12, rect.bottom - 6),
                             (rect.right - 12, rect.bottom - 6), 2)

    def _select_difficulty(self, difficulty: FootballAIDifficulty) -> None:
        self.difficulty = difficulty
