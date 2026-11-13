from typing import Callable

import pygame

from src.ui.layout import Layout
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_panel, draw_text

Navigate = Callable[[str], None]
Quit = Callable[[], None]


def _ui_font(size: int, *, bold: bool = False) -> pygame.font.Font:
    for family in ("Avenir Next", "Arial", "Liberation Sans"):
        path = pygame.font.match_font(family)
        if path is not None:
            font = pygame.font.Font(path, size)
            font.set_bold(bold)
            return font
    font = pygame.font.Font(None, size)
    font.set_bold(bold)
    return font


class Screen:
    def __init__(
        self,
        theme: Theme,
        navigate: Navigate,
        quit_application: Quit,
    ) -> None:
        self.theme = theme
        self.navigate = navigate
        self.quit_application = quit_application
        self.buttons: list[Button] = []
        self.focus_index = 0
        self.hover_index: int | None = None
        self.pressed_index: int | None = None
        if not pygame.font.get_init():
            pygame.font.init()
        self._main_font = _ui_font(16, bold=True)
        self._small_font = _ui_font(12, bold=True)
        self._title_font = _ui_font(27, bold=True)
        self._body_font = _ui_font(15)
        self._display_font = _ui_font(48, bold=True)
        self._label_font = _ui_font(15, bold=True)

    def on_enter(self) -> None:
        self.focus_index = next(
            (index for index, button in enumerate(self.buttons) if button.enabled),
            0,
        )

    def on_exit(self) -> None:
        self.buttons.clear()

    def _set_buttons(self, buttons: list[Button]) -> None:
        self.buttons = buttons
        if self.buttons and (
            self.focus_index >= len(self.buttons)
            or not self.buttons[self.focus_index].enabled
        ):
            self.focus_index = next(
                (index for index, button in enumerate(self.buttons) if button.enabled),
                0,
            )
        for index, button in enumerate(self.buttons):
            button.focused = index == self.focus_index and button.enabled

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self.hover_index = next(
                (
                    index
                    for index, button in enumerate(self.buttons)
                    if button.rect.collidepoint(event.pos) and button.enabled
                ),
                None,
            )
            if self.hover_index is not None:
                self._focus(self.hover_index)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed_index = next(
                (
                    index
                    for index, button in enumerate(self.buttons)
                    if button.enabled and button.rect.collidepoint(event.pos)
                ),
                None,
            )
            if self.pressed_index is not None:
                self._focus(self.pressed_index)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pressed_index = self.pressed_index
            self.pressed_index = None
            if (
                pressed_index is not None
                and self.buttons[pressed_index].enabled
                and self.buttons[pressed_index].rect.collidepoint(event.pos)
            ):
                self.buttons[pressed_index].action()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.navigate("main_menu")
            elif event.key in (pygame.K_TAB, pygame.K_DOWN, pygame.K_RIGHT):
                self._move_focus(1)
            elif event.key in (pygame.K_UP, pygame.K_LEFT):
                self._move_focus(-1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.buttons and self.buttons[self.focus_index].enabled:
                    self.buttons[self.focus_index].action()

    def _focus(self, index: int) -> None:
        self.focus_index = index
        for button_index, button in enumerate(self.buttons):
            button.focused = button_index == index

    def _move_focus(self, direction: int) -> None:
        enabled = [
            index for index, button in enumerate(self.buttons) if button.enabled
        ]
        if not enabled:
            return
        try:
            current = enabled.index(self.focus_index)
        except ValueError:
            current = -1 if direction > 0 else 0
        self._focus(enabled[(current + direction) % len(enabled)])

    def _header(
        self,
        surface: pygame.Surface,
        title: str,
        eyebrow: str,
        team_name: str,
    ) -> Layout:
        layout = Layout.from_surface(surface)
        surface.fill(self.theme.canvas)
        self._draw_backdrop(surface, layout)
        header = layout.header
        mark = pygame.Rect(header.left, header.top + 7, 38, 38)
        pygame.draw.rect(surface, self.theme.primary_accent, mark, border_radius=8)
        for offset in (11, 19, 27):
            pygame.draw.line(
                surface,
                self.theme.primary_ink,
                (mark.left + offset, mark.top + 11),
                (mark.left + offset, mark.bottom - 11),
                3,
            )
        draw_text(
            surface,
            "COLLEGE FOOTBALL",
            (mark.right + 14, header.top + 5),
            self._main_font,
            self.theme.text,
        )
        draw_text(
            surface,
            "SEASON MODE",
            (mark.right + 14, header.top + 27),
            self._small_font,
            self.theme.muted,
        )
        team_width = min(
            round(layout.width * 0.28),
            max(145, self._main_font.size(team_name.upper())[0] + 48),
        )
        team_badge = pygame.Rect(
            header.right - team_width,
            header.top + 7,
            team_width,
            42,
        )
        pygame.draw.rect(surface, self.theme.panel, team_badge, border_radius=8)
        pygame.draw.rect(
            surface,
            self.theme.border_soft,
            team_badge,
            width=1,
            border_radius=8,
        )
        pygame.draw.circle(
            surface,
            self.theme.primary_accent,
            (team_badge.left + 16, team_badge.centery),
            4,
        )
        safe_team_name = team_name.upper()
        while (
            self._small_font.size(safe_team_name)[0] > team_width - 44
            and len(safe_team_name) > 3
        ):
            safe_team_name = safe_team_name[:-4] + "..."
        team_label = self._small_font.render(safe_team_name, True, self.theme.text)
        surface.blit(
            team_label,
            team_label.get_rect(midleft=(team_badge.left + 29, team_badge.centery)),
        )
        title_y = header.bottom + 12
        draw_text(
            surface,
            eyebrow.upper(),
            (layout.margin + 2, title_y),
            self._small_font,
            self.theme.secondary_accent,
        )
        draw_text(
            surface,
            title,
            (layout.margin, title_y + 17),
            self._title_font,
            self.theme.text,
        )
        return layout

    def _draw_backdrop(self, surface: pygame.Surface, layout: Layout) -> None:
        width, height = surface.get_size()
        field_y = height - 12
        pygame.draw.line(
            surface,
            self.theme.border_soft,
            (layout.margin, field_y),
            (width - layout.margin, field_y),
            1,
        )
        for fraction in (0.2, 0.4, 0.6, 0.8):
            x = layout.margin + round((width - layout.margin * 2) * fraction)
            pygame.draw.line(
                surface,
                self.theme.border,
                (x, field_y - 4),
                (x, field_y + 4),
                1,
            )

    def _draw_buttons(self, surface: pygame.Surface) -> None:
        for index, button in enumerate(self.buttons):
            button.draw(
                surface,
                self._main_font,
                self.theme,
                hovered=self.hover_index == index,
                pressed=self.pressed_index == index,
            )


class SettingsScreen(Screen):
    def __init__(
        self,
        theme: Theme,
        team_name: str,
        navigate: Navigate,
        quit_application: Quit,
    ) -> None:
        super().__init__(theme, navigate, quit_application)
        self.team_name = team_name

    def draw(self, surface: pygame.Surface) -> None:
        layout = self._header(surface, "Team settings", "TEAM PROFILE", self.team_name)
        content = layout.content
        panel = pygame.Rect(content.left, content.top, content.width, content.height)
        draw_panel(surface, panel, self.theme, fill=self.theme.panel)
        draw_text(
            surface,
            "SAVED TEAM COLORS",
            (panel.left + 26, panel.top + 23),
            self._small_font,
            self.theme.secondary_accent,
        )
        draw_text(
            surface,
            "Your saved profile sets the team palette.",
            (panel.left + 26, panel.top + 50),
            self._body_font,
            self.theme.muted,
        )

        swatches = (
            ("PRIMARY", self.theme.primary, self.theme.primary_accent),
            ("SECONDARY", self.theme.secondary, self.theme.secondary_accent),
        )
        row_width = (panel.width - 64) // 2
        for index, (label, color, accent) in enumerate(swatches):
            row = pygame.Rect(
                panel.left + 26 + index * (row_width + 12),
                panel.top + 91,
                row_width,
                120,
            )
            draw_panel(surface, row, self.theme, fill=self.theme.panel_alt)
            pygame.draw.rect(
                surface,
                color,
                pygame.Rect(row.left + 16, row.top + 16, 54, row.height - 32),
                border_radius=7,
            )
            draw_text(
                surface,
                label,
                (row.left + 86, row.top + 25),
                self._small_font,
                self.theme.muted,
            )
            pygame.draw.rect(
                surface,
                accent,
                pygame.Rect(row.left + 86, row.top + 53, row.width - 104, 8),
                border_radius=4,
            )
            draw_text(
                surface,
                "INTERFACE ACCENT",
                (row.left + 86, row.top + 71),
                self._small_font,
                self.theme.text,
            )

        draw_text(
            surface,
            "PROFILE EDITING",
            (panel.left + 26, panel.top + 239),
            self._small_font,
            self.theme.secondary_accent,
        )
        draw_text(
            surface,
            "Edit your team name and colors from the terminal client.",
            (panel.left + 26, panel.top + 262),
            self._body_font,
            self.theme.muted,
        )
        back_rect = pygame.Rect(panel.right - 174, panel.bottom - 54, 148, 38)
        self._set_buttons(
            [Button("MAIN MENU", lambda: self.navigate("main_menu"), back_rect)]
        )
        self._draw_buttons(surface)
