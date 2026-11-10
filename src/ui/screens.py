from dataclasses import dataclass
from typing import Callable

import pygame

from src.application import MainMenuState
from src.profile import ProfileError
from src.ui.layout import Layout
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text

Navigate = Callable[[str], None]
Quit = Callable[[], None]


@dataclass(frozen=True)
class ScreenCopy:
    title: str
    eyebrow: str
    description: str
    detail: str
    next_screen: str | None = None
    next_label: str | None = None


SCREEN_COPY = {
    "coach_selection": ScreenCopy(
        "Pick your sideline",
        "RUN SETUP / PREVIEW",
        "Every run starts with a coach pairing that gives your team its identity.",
        "Coach cards, scheme effects, and confirmation will be built here.",
        "opening_draft",
        "Opening draft preview",
    ),
    "opening_draft": ScreenCopy(
        "National Signing Day",
        "OPENING DRAFT / PREVIEW",
        "Build a foundation across the six player groups before the season begins.",
        "Player offers, position order, and action points will be presented here.",
        "roster",
        "Roster preview",
    ),
    "roster": ScreenCopy(
        "The depth chart",
        "ROSTER / PREVIEW",
        "A compact eight-slot board will keep your lineup readable at a glance.",
        "Player cards, the locked coach, and special teams will live here.",
        "coaching_shop",
        "Coaching shop preview",
    ),
    "coaching_shop": ScreenCopy(
        "The coaching shop",
        "BETWEEN GAMES / PREVIEW",
        "Spend action points on practice, recovery, and sideline adjustments.",
        "Offers, costs, and day-by-day decisions will be presented here.",
        "match",
        "Match presentation preview",
    ),
    "match": ScreenCopy(
        "Saturday lights",
        "MATCH CENTER / PREVIEW",
        "A fast, hands-off matchup will turn the roster into a stadium story.",
        "Scoreboard, drive events, and the momentum tug-of-war will appear here.",
        None,
        None,
    ),
    "settings": ScreenCopy(
        "Team settings",
        "PROFILE / PREVIEW",
        "Your team identity and color palette are read from the saved profile.",
        "Profile editing remains available from the terminal client in this step.",
        None,
        None,
    ),
}


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
        if not pygame.font.get_init():
            pygame.font.init()
        self._main_font = pygame.font.SysFont("dejavusansmono", 20, bold=True)
        self._small_font = pygame.font.SysFont("dejavusansmono", 14, bold=True)
        self._title_font = pygame.font.SysFont("dejavusansmono", 27, bold=True)
        self._body_font = pygame.font.SysFont("dejavusans", 19)

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
                (
                    index
                    for index, button in enumerate(self.buttons)
                    if button.enabled
                ),
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
            for index, button in enumerate(self.buttons):
                if button.enabled and button.rect.collidepoint(event.pos):
                    self._focus(index)
                    button.action()
                    return
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
        header = layout.header
        pygame.draw.rect(surface, self.theme.panel, header, border_radius=9)
        pygame.draw.rect(surface, self.theme.border, header, width=1, border_radius=9)
        pygame.draw.rect(
            surface,
            self.theme.primary,
            pygame.Rect(header.left, header.top, 8, header.height),
            border_radius=4,
        )
        draw_text(
            surface,
            f"CFB / AUTO-BATTLER   /   {eyebrow.upper()}",
            (header.left + 24, header.top + 13),
            self._small_font,
            self.theme.secondary,
        )
        draw_text(
            surface,
            title.upper(),
            (header.left + 24, header.top + 34),
            self._title_font,
            self.theme.text,
        )
        team_label = self._small_font.render(team_name.upper(), True, self.theme.muted)
        surface.blit(
            team_label,
            team_label.get_rect(midright=(header.right - 22, header.centery)),
        )
        field = pygame.Rect(
            layout.margin,
            layout.height - max(70, layout.margin),
            layout.width - layout.margin * 2,
            max(30, round(layout.height * 0.045)),
        )
        pygame.draw.rect(surface, self.theme.primary_dark, field, border_radius=5)
        for fraction in (0.25, 0.5, 0.75):
            x = field.left + round(field.width * fraction)
            pygame.draw.line(
                surface,
                self.theme.border,
                (x, field.top + 5),
                (x, field.bottom - 5),
                1,
            )
        pygame.draw.line(
            surface,
            self.theme.secondary_dark,
            (field.left + 10, field.centery),
            (field.right - 10, field.centery),
            2,
        )
        return layout

    def _draw_buttons(self, surface: pygame.Surface) -> None:
        for index, button in enumerate(self.buttons):
            button.draw(
                surface,
                self._main_font,
                self.theme,
                hovered=self.hover_index == index,
            )


class MainMenuScreen(Screen):
    def __init__(
        self,
        theme: Theme,
        menu_state: MainMenuState | None,
        profile_error: str | None,
        navigate: Navigate,
        quit_application: Quit,
    ) -> None:
        super().__init__(theme, navigate, quit_application)
        self.menu_state = menu_state
        self.profile_error = profile_error

    def draw(self, surface: pygame.Surface) -> None:
        team_name = (
            self.menu_state.profile.team_name
            if self.menu_state is not None
            else "NEW TEAM"
        )
        layout = self._header(surface, "Saturday starts here", "HOME / MAIN MENU", team_name)
        content = layout.content
        hero_width = round(content.width * 0.55)
        hero = pygame.Rect(content.left, content.top, hero_width, content.height)
        draw_panel(surface, hero, self.theme, selected=True)
        draw_text(
            surface,
            "YOUR PROGRAM",
            (hero.left + 30, hero.top + 28),
            self._small_font,
            self.theme.secondary,
        )
        name = team_name.upper()
        name_font = pygame.font.SysFont("dejavusansmono", 34, bold=True)
        draw_text(
            surface,
            name[:24],
            (hero.left + 30, hero.top + 62),
            name_font,
            self.theme.text,
        )
        accent_y = hero.top + 124
        pygame.draw.rect(
            surface,
            self.theme.primary,
            pygame.Rect(hero.left + 30, accent_y, 90, 7),
            border_radius=3,
        )
        pygame.draw.rect(
            surface,
            self.theme.secondary,
            pygame.Rect(hero.left + 128, accent_y, 42, 7),
            border_radius=3,
        )
        detail = (
            "A new season. Eight slots. One shot at the title."
            if self.menu_state is not None
            else "Your sideline is waiting for its first team profile."
        )
        draw_wrapped_text(
            surface,
            detail,
            pygame.Rect(hero.left + 30, accent_y + 28, hero.width - 60, 54),
            self._body_font,
            self.theme.muted,
        )
        status_rect = pygame.Rect(
            hero.left + 30,
            accent_y + 104,
            hero.width - 60,
            104,
        )
        draw_panel(surface, status_rect, self.theme)
        draw_text(
            surface,
            "SEASON STATUS",
            (status_rect.left + 18, status_rect.top + 15),
            self._small_font,
            self.theme.secondary,
        )
        draw_text(
            surface,
            "PRESEASON" if self.menu_state is not None else "PROFILE NEEDED",
            (status_rect.left + 18, status_rect.top + 42),
            self._title_font,
            self.theme.text,
        )
        pygame.draw.line(
            surface,
            self.theme.border,
            (status_rect.right - 152, status_rect.top + 18),
            (status_rect.right - 152, status_rect.bottom - 18),
            1,
        )
        draw_text(
            surface,
            "8 SLOTS",
            (status_rect.right - 130, status_rect.top + 26),
            self._small_font,
            self.theme.muted,
        )
        draw_text(
            surface,
            "1 TITLE",
            (status_rect.right - 130, status_rect.top + 57),
            self._small_font,
            self.theme.muted,
        )
        if self.menu_state is None:
            if self.profile_error is None:
                message = "Create a team with `python -m src.main` to unlock Play."
            else:
                message = "Profile could not be loaded. Check the saved profile in the CLI."
            draw_text(
                surface,
                message,
                (hero.left + 30, status_rect.bottom + 16),
                self._small_font,
                self.theme.danger if self.profile_error else self.theme.secondary,
            )
            if self.profile_error is not None:
                draw_text(
                    surface,
                    self.profile_error[:76],
                    (hero.left + 30, status_rect.bottom + 40),
                    self._small_font,
                    self.theme.muted,
                )
        else:
            if self.theme.warning is not None:
                draw_text(
                    surface,
                    self.theme.warning,
                    (hero.left + 30, status_rect.bottom + 14),
                    self._small_font,
                    self.theme.danger,
                )
            primary_name = self.menu_state.profile.primary_color.display_name.upper()
            secondary_name = self.menu_state.profile.secondary_color.display_name.upper()
            draw_text(
                surface,
                f"PRIMARY / {primary_name}",
                (hero.left + 30, hero.bottom - 82),
                self._small_font,
                self.theme.muted,
            )
            draw_text(
                surface,
                f"SECONDARY / {secondary_name}",
                (hero.left + 200, hero.bottom - 82),
                self._small_font,
                self.theme.muted,
            )
            pygame.draw.rect(
                surface,
                self.theme.primary,
                pygame.Rect(hero.left + 30, hero.bottom - 54, 138, 23),
                border_radius=5,
            )
            pygame.draw.rect(
                surface,
                self.theme.secondary,
                pygame.Rect(hero.left + 200, hero.bottom - 54, 138, 23),
                border_radius=5,
            )

        menu_x = hero.right + 22
        menu_width = content.right - menu_x
        labels = (
            ("PLAY / START RUN", "coach_selection", self.menu_state is not None),
            ("ROSTER PREVIEW", "roster", True),
            ("COACHING SHOP", "coaching_shop", True),
            ("MATCH PRESENTATION", "match", True),
            ("SETTINGS", "settings", True),
            ("QUIT", "quit", True),
        )
        gap = 10
        button_height = max(48, (content.height - gap * (len(labels) - 1)) // len(labels))
        buttons: list[Button] = []
        for index, (label, destination, enabled) in enumerate(labels):
            rect = pygame.Rect(
                menu_x,
                content.top + index * (button_height + gap),
                menu_width,
                button_height,
            )
            action = (
                self.quit_application
                if destination == "quit"
                else lambda screen=destination: self.navigate(screen)
            )
            buttons.append(Button(label, action, rect, enabled=enabled))
        self._set_buttons(buttons)
        self._draw_buttons(surface)


class PlaceholderScreen(Screen):
    def __init__(
        self,
        theme: Theme,
        definition: ScreenCopy,
        team_name: str,
        navigate: Navigate,
        quit_application: Quit,
    ) -> None:
        super().__init__(theme, navigate, quit_application)
        self.definition = definition
        self.team_name = team_name

    def draw(self, surface: pygame.Surface) -> None:
        layout = self._header(
            surface,
            self.definition.title,
            self.definition.eyebrow,
            self.team_name,
        )
        content = layout.content
        main_panel = pygame.Rect(
            content.left,
            content.top,
            round(content.width * 0.66),
            content.height,
        )
        side_panel = pygame.Rect(
            main_panel.right + 20,
            content.top,
            content.right - main_panel.right - 20,
            content.height,
        )
        draw_panel(surface, main_panel, self.theme, selected=True)
        draw_text(
            surface,
            self.definition.title.upper(),
            (main_panel.left + 30, main_panel.top + 30),
            self._title_font,
            self.theme.text,
        )
        draw_text(
            surface,
            self.definition.eyebrow,
            (main_panel.left + 30, main_panel.top + 74),
            self._small_font,
            self.theme.secondary,
        )
        draw_wrapped_text(
            surface,
            self.definition.description,
            pygame.Rect(
                main_panel.left + 30,
                main_panel.top + 126,
                main_panel.width - 60,
                56,
            ),
            self._body_font,
            self.theme.muted,
        )
        card_rect = pygame.Rect(
            main_panel.left + 30,
            main_panel.top + 190,
            main_panel.width - 60,
            min(116, max(84, main_panel.height // 4)),
        )
        draw_panel(surface, card_rect, self.theme, selected=True)
        draw_text(
            surface,
            "SHELL PREVIEW",
            (card_rect.left + 22, card_rect.top + 18),
            self._small_font,
            self.theme.primary,
        )
        draw_wrapped_text(
            surface,
            self.definition.detail,
            pygame.Rect(
                card_rect.left + 22,
                card_rect.top + 48,
                card_rect.width - 44,
                card_rect.height - 54,
            ),
            self._body_font,
            self.theme.text,
        )
        draw_panel(surface, side_panel, self.theme)
        draw_text(
            surface,
            "ON THE PLAYBOOK",
            (side_panel.left + 22, side_panel.top + 24),
            self._small_font,
            self.theme.secondary,
        )
        draw_text(
            surface,
            "PREVIEW ONLY",
            (side_panel.left + 22, side_panel.top + 62),
            self._title_font,
            self.theme.text,
        )
        draw_text(
            surface,
            "No gameplay state or",
            (side_panel.left + 22, side_panel.top + 110),
            self._body_font,
            self.theme.muted,
        )
        draw_text(
            surface,
            "database is changed.",
            (side_panel.left + 22, side_panel.top + 136),
            self._body_font,
            self.theme.muted,
        )
        draw_text(
            surface,
            "ESC  /  MAIN MENU",
            (side_panel.left + 22, side_panel.bottom - 46),
            self._small_font,
            self.theme.muted,
        )
        button_rect = pygame.Rect(
            side_panel.left + 18,
            side_panel.bottom - 112,
            side_panel.width - 36,
            52,
        )
        buttons = [
            Button(
                "MAIN MENU",
                lambda: self.navigate("main_menu"),
                pygame.Rect(
                    side_panel.left + 18,
                    side_panel.bottom - 58,
                    side_panel.width - 36,
                    44,
                ),
            )
        ]
        if self.definition.next_screen is not None:
            buttons.insert(
                0,
                Button(
                    self.definition.next_label or "CONTINUE",
                    lambda: self.navigate(self.definition.next_screen or "main_menu"),
                    button_rect,
                ),
            )
        self._set_buttons(buttons)
        self._draw_buttons(surface)
