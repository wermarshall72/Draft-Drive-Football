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
        self.pressed_index: int | None = None
        if not pygame.font.get_init():
            pygame.font.init()
        self._main_font = _ui_font(18, bold=True)
        self._small_font = _ui_font(13, bold=True)
        self._title_font = _ui_font(28, bold=True)
        self._body_font = pygame.font.SysFont("arial", 18)
        self._display_font = _ui_font(48, bold=True)
        self._label_font = _ui_font(16, bold=True)

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
        mark = pygame.Rect(header.left, header.top + 6, 43, 43)
        pygame.draw.rect(surface, self.theme.primary_accent, mark, border_radius=12)
        ball = pygame.Rect(mark.left + 8, mark.top + 13, 27, 17)
        pygame.draw.ellipse(surface, self.theme.primary_ink, ball)
        pygame.draw.line(
            surface,
            self.theme.primary_accent,
            (ball.centerx - 3, ball.top + 3),
            (ball.centerx + 3, ball.bottom - 3),
            1,
        )
        pygame.draw.line(
            surface,
            self.theme.primary_accent,
            (ball.centerx - 2, ball.centery - 2),
            (ball.centerx + 2, ball.centery - 2),
            1,
        )
        pygame.draw.line(
            surface,
            self.theme.primary_accent,
            (ball.centerx - 1, ball.centery + 2),
            (ball.centerx + 3, ball.centery + 2),
            1,
        )
        draw_text(
            surface,
            "CFB AUTO-BATTLER",
            (mark.right + 14, header.top + 5),
            self._main_font,
            self.theme.text,
        )
        draw_text(
            surface,
            "COLLEGE FOOTBALL / ROGUELIKE",
            (mark.right + 14, header.top + 27),
            self._small_font,
            self.theme.muted,
        )
        team_width = min(
            round(layout.width * 0.28),
            self._main_font.size(team_name.upper())[0] + 52,
        )
        team_badge = pygame.Rect(
            header.right - team_width,
            header.top + 7,
            team_width,
            42,
        )
        pygame.draw.rect(surface, self.theme.panel, team_badge, border_radius=9)
        pygame.draw.rect(
            surface,
            self.theme.border_soft,
            team_badge,
            width=1,
            border_radius=9,
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
        title_y = header.bottom + 15
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
        footer_y = layout.height - 23
        pygame.draw.line(
            surface,
            self.theme.border_soft,
            (layout.margin, footer_y),
            (layout.width - layout.margin, footer_y),
            1,
        )
        draw_text(
            surface,
            "A NEW SEASON. A NEW SHOT.",
            (layout.margin, footer_y + 5),
            self._small_font,
            self.theme.muted,
        )
        return layout

    def _draw_backdrop(self, surface: pygame.Surface, layout: Layout) -> None:
        width, height = surface.get_size()
        wash = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.ellipse(
            wash,
            (*self.theme.primary_dark[:3], 34),
            pygame.Rect(round(width * 0.53), -round(height * 0.45), width, height),
        )
        surface.blit(wash, (0, 0))
        field_y = height - 19
        pygame.draw.line(
            surface,
            self.theme.primary_dark,
            (layout.margin, field_y),
            (width - layout.margin, field_y),
            3,
        )
        for fraction in (0.2, 0.4, 0.6, 0.8):
            x = layout.margin + round((width - layout.margin * 2) * fraction)
            pygame.draw.line(
                surface,
                self.theme.border_soft,
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
        layout = self._header(
            surface, "Saturday starts here", "HOME / MAIN MENU", team_name
        )
        content = layout.content
        hero_height = min(296, round(content.height * 0.64))
        hero = pygame.Rect(content.left, content.top, content.width, hero_height)
        draw_panel(surface, hero, self.theme, fill=self.theme.panel)
        draw_text(
            surface,
            "YOUR PROGRAM  /  YOUR COLORS  /  YOUR CALL",
            (hero.left + 34, hero.top + 27),
            self._small_font,
            self.theme.secondary_accent,
        )
        name = team_name.upper()[:22]
        name_font = _ui_font(56, bold=True)
        while name_font.size(name)[0] > round(hero.width * 0.43):
            name_font = _ui_font(max(34, name_font.get_height() - 3), bold=True)
        draw_text(
            surface,
            name,
            (hero.left + 34, hero.top + 67),
            name_font,
            self.theme.text,
        )
        draw_text(
            surface,
            "THE ROAD TO A NATIONAL TITLE STARTS HERE.",
            (hero.left + 36, hero.top + 125),
            self._label_font,
            self.theme.muted,
        )
        primary_name = (
            self.menu_state.profile.primary_color.display_name.upper()
            if self.menu_state is not None
            else "HOME"
        )
        secondary_name = (
            self.menu_state.profile.secondary_color.display_name.upper()
            if self.menu_state is not None
            else "AWAY"
        )
        swatch_y = hero.top + 173
        for x, label, color in (
            (hero.left + 36, primary_name, self.theme.primary),
            (hero.left + 205, secondary_name, self.theme.secondary),
        ):
            pygame.draw.rect(
                surface,
                color,
                pygame.Rect(x, swatch_y, 29, 22),
                border_radius=5,
            )
            draw_text(
                surface,
                label,
                (x + 39, swatch_y + 3),
                self._small_font,
                self.theme.text,
            )
        self._draw_football_art(surface, hero)
        action_x = hero.right - 314
        action_panel = pygame.Rect(
            action_x,
            hero.top + 17,
            294,
            hero.height - 34,
        )
        draw_panel(surface, action_panel, self.theme, fill=self.theme.panel_alt)
        draw_text(
            surface,
            "SEASON ONE",
            (action_panel.left + 20, action_panel.top + 19),
            self._small_font,
            self.theme.secondary_accent,
        )
        draw_text(
            surface,
            "PRESEASON" if self.menu_state is not None else "GET YOUR TEAM READY",
            (action_panel.left + 20, action_panel.top + 42),
            self._label_font,
            self.theme.muted if self.menu_state is not None else self.theme.text,
        )
        pygame.draw.line(
            surface,
            self.theme.border,
            (action_panel.left + 20, action_panel.top + 72),
            (action_panel.right - 20, action_panel.top + 72),
            1,
        )
        draw_text(
            surface,
            "6 picks  /  10 weeks  /  1 champion",
            (action_panel.left + 20, action_panel.top + 84),
            self._small_font,
            self.theme.text,
        )
        if self.menu_state is None:
            recovery = (
                "Profile could not load; open the terminal client to repair it."
                if self.profile_error is not None
                else "Create a team profile in the terminal to unlock the season."
            )
            draw_wrapped_text(
                surface,
                recovery,
                pygame.Rect(
                    hero.left + 36,
                    swatch_y + 39,
                    round(hero.width * 0.4),
                    55,
                ),
                self._small_font,
                self.theme.danger if self.profile_error is not None else self.theme.muted,
            )
        elif self.theme.warning is not None:
            draw_wrapped_text(
                surface,
                self.theme.warning,
                pygame.Rect(hero.left + 36, swatch_y + 39, 390, 40),
                self._small_font,
                self.theme.danger,
            )

        start_rect = pygame.Rect(
            action_panel.left + 18,
            action_panel.top + 122,
            action_panel.width - 36,
            57,
        )
        utility_y = start_rect.bottom + 10
        utility_width = (action_panel.width - 48) // 2
        settings_rect = pygame.Rect(
            action_panel.left + 18, utility_y, utility_width, 44
        )
        quit_rect = pygame.Rect(
            settings_rect.right + 12, utility_y, utility_width, 44
        )

        guide_top = hero.bottom + 20
        draw_text(
            surface,
            "EXPLORE THE PLAYBOOK",
            (content.left + 2, guide_top),
            self._small_font,
            self.theme.muted,
        )
        cards_y = guide_top + 25
        card_gap = 12
        card_width = (content.width - card_gap * 3) // 4
        card_height = content.bottom - cards_y
        card_specs = (
            ("01   DEPTH CHART", "8 positions, one lineup", "roster"),
            ("02   COACHING", "Shape the way you play", "coaching_shop"),
            ("03   GAME DAY", "Scoreboard & momentum", "match"),
            ("04   SIDELINE", "Choose your run anchor", "coach_selection"),
        )
        start_button = Button(
            "PLAY / START RUN",
            lambda: self.navigate("coach_selection"),
            start_rect,
            enabled=self.menu_state is not None,
            variant="primary",
        )
        buttons = [start_button]
        card_buttons: list[tuple[Button, str]] = []
        for index, (title, caption, destination) in enumerate(card_specs):
            rect = pygame.Rect(
                content.left + index * (card_width + card_gap),
                cards_y,
                card_width,
                card_height,
            )
            card_buttons.append(
                (
                    Button(
                        title,
                        lambda screen=destination: self.navigate(screen),
                        rect,
                    ),
                    caption,
                )
            )
        buttons.extend(button for button, _ in card_buttons)
        buttons.extend(
            (
                Button("SETTINGS", lambda: self.navigate("settings"), settings_rect),
                Button("QUIT", self.quit_application, quit_rect),
            )
        )
        self._set_buttons(buttons)
        self._draw_buttons(surface)
        for button, caption in card_buttons:
            draw_text(
                surface,
                caption,
                (button.rect.left + 18, button.rect.bottom - 29),
                self._small_font,
                self.theme.muted,
            )

    def _draw_football_art(self, surface: pygame.Surface, hero: pygame.Rect) -> None:
        center_x = hero.left + round(hero.width * 0.59)
        center_y = hero.centery + 2
        orbit_color = (*self.theme.border[:3], 130)
        rings = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for inset, width in ((0, 1), (18, 1), (36, 1)):
            ring = pygame.Rect(
                center_x - 118 + inset,
                center_y - 106 + inset,
                236 - inset * 2,
                212 - inset * 2,
            )
            pygame.draw.arc(rings, orbit_color, ring, 0.15, 2.96, width)
            pygame.draw.arc(rings, orbit_color, ring, 3.3, 6.12, width)
        surface.blit(rings, (0, 0))
        for offset in (-66, -22, 22, 66):
            pygame.draw.line(
                surface,
                self.theme.border_soft,
                (center_x + offset, center_y - 68),
                (center_x + offset, center_y - 58),
                2,
            )
            pygame.draw.line(
                surface,
                self.theme.border_soft,
                (center_x + offset, center_y + 58),
                (center_x + offset, center_y + 68),
                2,
            )
        football = pygame.Surface((156, 92), pygame.SRCALPHA)
        pygame.draw.ellipse(
            football,
            (*self.theme.primary_dark[:3], 105),
            (4, 17, 146, 66),
        )
        football_points = (
            (8, 42),
            (23, 19),
            (63, 8),
            (111, 17),
            (149, 42),
            (111, 67),
            (63, 76),
            (23, 65),
        )
        pygame.draw.polygon(
            football,
            self.theme.primary_accent,
            football_points,
        )
        pygame.draw.polygon(
            football,
            self.theme.primary_dark,
            football_points,
            width=2,
        )
        pygame.draw.line(
            football,
            self.theme.primary_ink,
            (68, 18),
            (89, 66),
            2,
        )
        for offset in (-10, 0, 10):
            pygame.draw.line(
                football,
                self.theme.primary_ink,
                (72 + offset, 31 + offset),
                (82 + offset, 26 + offset),
                2,
            )
        rotated = pygame.transform.rotate(football, -17)
        surface.blit(rotated, rotated.get_rect(center=(center_x, center_y)))


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
        route = {
            "Pick your sideline": self._draw_coach_screen,
            "National Signing Day": self._draw_draft_screen,
            "The depth chart": self._draw_roster_screen,
            "The coaching shop": self._draw_shop_screen,
            "Saturday lights": self._draw_match_screen,
            "Team settings": self._draw_settings_screen,
        }.get(self.definition.title)
        if route is None:
            raise RuntimeError(f"No desktop layout for {self.definition.title!r}.")
        route(surface, content)

    def _draw_coach_screen(
        self, surface: pygame.Surface, content: pygame.Rect
    ) -> None:
        draw_text(
            surface,
            "CHOOSE A GAME PLAN",
            (content.left + 2, content.top),
            self._small_font,
            self.theme.muted,
        )
        row_top = content.top + 26
        card_gap = 16
        card_width = (content.width - card_gap * 2) // 3
        card_height = content.height - 88
        schemes = (
            ("01", "AIR RAID", "Stretch the field", "PASS / TEMPO"),
            ("02", "GROUND GAME", "Win between the tackles", "RUN / CONTROL"),
            ("03", "BALANCED", "Adapt to the matchup", "FLEX / RESPONSE"),
        )
        buttons: list[Button] = []
        for index, (number, name, subtitle, style) in enumerate(schemes):
            rect = pygame.Rect(
                content.left + index * (card_width + card_gap),
                row_top,
                card_width,
                card_height,
            )
            draw_panel(
                surface,
                rect,
                self.theme,
                fill=self.theme.panel_alt if index == 0 else self.theme.panel,
            )
            accent = (
                self.theme.primary_accent
                if index == 0
                else self.theme.secondary_accent
                if index == 1
                else self.theme.border
            )
            pygame.draw.rect(
                surface,
                accent,
                pygame.Rect(rect.left, rect.top, rect.width, 5),
                border_radius=3,
            )
            number_font = _ui_font(48, bold=True)
            number_surface = number_font.render(number, True, self.theme.panel_high)
            surface.blit(number_surface, (rect.right - 66, rect.top + 18))
            draw_text(
                surface,
                name,
                (rect.left + 24, rect.top + 36),
                self._title_font,
                self.theme.text,
            )
            draw_text(
                surface,
                subtitle,
                (rect.left + 24, rect.top + 81),
                self._body_font,
                self.theme.muted,
            )
            self._draw_scheme_art(surface, rect, index, accent)
            pygame.draw.line(
                surface,
                self.theme.border_soft,
                (rect.left + 24, rect.bottom - 90),
                (rect.right - 24, rect.bottom - 90),
                1,
            )
            draw_text(
                surface,
                style,
                (rect.left + 24, rect.bottom - 72),
                self._small_font,
                accent,
            )
            buttons.append(
                Button(
                    "VIEW STYLE",
                    lambda: self.navigate("opening_draft"),
                    pygame.Rect(
                        rect.left + 18,
                        rect.bottom - 50,
                        rect.width - 36,
                        36,
                    ),
                    variant="primary" if index == 0 else "quiet",
                )
            )
        self._draw_page_navigation(
            surface,
            content,
            prefix_buttons=buttons,
            back_only=True,
        )

    def _draw_scheme_art(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        style: int,
        accent: pygame.Color,
    ) -> None:
        art = pygame.Rect(
            rect.left + 24,
            rect.top + 132,
            rect.width - 48,
            rect.height - 224,
        )
        pygame.draw.rect(surface, self.theme.canvas_lift, art, border_radius=18)
        center = art.center
        if style == 0:
            points = (
                (art.left + 30, art.bottom - 28),
                (center[0], art.top + 25),
                (art.right - 30, art.bottom - 28),
            )
            pygame.draw.lines(surface, accent, False, points, 3)
            for x, y in points:
                pygame.draw.circle(surface, self.theme.panel, (x, y), 9)
                pygame.draw.circle(surface, accent, (x, y), 5)
        elif style == 1:
            for row in range(3):
                y = art.top + 30 + row * 32
                pygame.draw.line(
                    surface,
                    self.theme.border,
                    (art.left + 24, y),
                    (art.right - 24, y),
                    1,
                )
                pygame.draw.circle(
                    surface,
                    accent,
                    (center[0], y),
                    6 if row == 1 else 4,
                )
            pygame.draw.line(
                surface,
                accent,
                (center[0], art.top + 20),
                (center[0], art.bottom - 17),
                2,
            )
        else:
            pygame.draw.arc(
                surface,
                accent,
                pygame.Rect(center[0] - 50, center[1] - 44, 100, 88),
                0.4,
                5.8,
                3,
            )
            pygame.draw.circle(surface, self.theme.panel, center, 18)
            pygame.draw.circle(surface, accent, center, 8)

    def _draw_draft_screen(
        self, surface: pygame.Surface, content: pygame.Rect
    ) -> None:
        rail_width = 206
        rail = pygame.Rect(content.left, content.top, rail_width, content.height)
        draw_panel(surface, rail, self.theme)
        draw_text(
            surface,
            "SIGNING DAY",
            (rail.left + 18, rail.top + 20),
            self._small_font,
            self.theme.secondary_accent,
        )
        positions = ("QB", "RB", "WR", "OL", "FRONT 7", "SECONDARY")
        for index, label in enumerate(positions):
            y = rail.top + 66 + index * 47
            active = index == 0
            pygame.draw.circle(
                surface,
                self.theme.primary_accent if active else self.theme.border,
                (rail.left + 25, y + 9),
                5,
            )
            draw_text(
                surface,
                label,
                (rail.left + 42, y),
                self._label_font,
                self.theme.text if active else self.theme.muted,
            )
            if index < len(positions) - 1:
                pygame.draw.line(
                    surface,
                    self.theme.border_soft,
                    (rail.left + 25, y + 17),
                    (rail.left + 25, y + 44),
                    1,
                )
        draw_text(
            surface,
            "6 / 6 PICKS",
            (rail.left + 18, rail.bottom - 39),
            self._small_font,
            self.theme.muted,
        )

        offer_left = rail.right + 20
        offer_width = content.right - offer_left
        header_height = 56
        draw_text(
            surface,
            "QUARTERBACK  /  CHOOSE YOUR FOUNDATION",
            (offer_left + 2, content.top + 4),
            self._small_font,
            self.theme.muted,
        )
        offer_top = content.top + header_height
        gap = 13
        card_width = (offer_width - gap * 2) // 3
        card_height = content.height - header_height - 64
        prospects = (
            ("01", "FIELD GENERAL", "ARM / AWARENESS", 0.78),
            ("02", "DUAL THREAT", "SPEED / VISION", 0.91),
            ("03", "POCKET ACE", "ACCURACY / POISE", 0.66),
        )
        buttons: list[Button] = []
        for index, (number, archetype, traits, rating) in enumerate(prospects):
            rect = pygame.Rect(
                offer_left + index * (card_width + gap),
                offer_top,
                card_width,
                card_height,
            )
            draw_panel(
                surface,
                rect,
                self.theme,
                fill=self.theme.panel_alt if index == 1 else self.theme.panel,
            )
            draw_text(
                surface,
                f"PROSPECT  {number}",
                (rect.left + 18, rect.top + 18),
                self._small_font,
                self.theme.muted,
            )
            avatar = pygame.Rect(rect.left + 18, rect.top + 54, rect.width - 36, 112)
            pygame.draw.rect(surface, self.theme.canvas_lift, avatar, border_radius=16)
            self._draw_player_silhouette(surface, avatar, index)
            draw_text(
                surface,
                archetype,
                (rect.left + 18, rect.top + 183),
                self._label_font,
                self.theme.text,
            )
            draw_text(
                surface,
                traits,
                (rect.left + 18, rect.top + 211),
                self._small_font,
                self.theme.muted,
            )
            stat_rect = pygame.Rect(
                rect.left + 18,
                rect.bottom - 65,
                rect.width - 36,
                5,
            )
            pygame.draw.rect(surface, self.theme.border_soft, stat_rect, border_radius=3)
            pygame.draw.rect(
                surface,
                self.theme.primary_accent,
                pygame.Rect(
                    stat_rect.left,
                    stat_rect.top,
                    round(stat_rect.width * rating),
                    stat_rect.height,
                ),
                border_radius=3,
            )
            buttons.append(
                Button(
                    "SCOUT",
                    lambda: self.navigate("roster"),
                    pygame.Rect(
                        rect.left + 14,
                        rect.bottom - 45,
                        rect.width - 28,
                        32,
                    ),
                    variant="primary" if index == 1 else "quiet",
                )
            )
        self._draw_page_navigation(
            surface,
            content,
            prefix_buttons=buttons,
            back_only=True,
        )

    def _draw_player_silhouette(
        self, surface: pygame.Surface, rect: pygame.Rect, variation: int
    ) -> None:
        color = (
            self.theme.primary_accent
            if variation != 1
            else self.theme.secondary_accent
        )
        center_x = rect.centerx
        pygame.draw.circle(surface, color, (center_x, rect.top + 35), 16)
        shoulders = pygame.Rect(center_x - 35, rect.top + 55, 70, 53)
        pygame.draw.ellipse(surface, color, shoulders)
        pygame.draw.line(
            surface,
            self.theme.panel,
            (center_x - 12, rect.top + 60),
            (center_x + 12, rect.top + 60),
            3,
        )
        for stripe_y in (rect.top + 78, rect.top + 88):
            pygame.draw.line(
                surface,
                self.theme.panel,
                (center_x - 23, stripe_y),
                (center_x + 23, stripe_y),
                2,
            )

    def _draw_roster_screen(
        self, surface: pygame.Surface, content: pygame.Rect
    ) -> None:
        field = pygame.Rect(
            content.left,
            content.top,
            content.width,
            content.height - 50,
        )
        draw_panel(surface, field, self.theme, fill=self.theme.canvas_lift)
        field_inner = field.inflate(-18, -18)
        pygame.draw.rect(
            surface,
            self.theme.panel,
            field_inner,
            border_radius=18,
        )
        for x_fraction in (0.25, 0.5, 0.75):
            x = field_inner.left + round(field_inner.width * x_fraction)
            pygame.draw.line(
                surface,
                self.theme.border_soft,
                (x, field_inner.top + 10),
                (x, field_inner.bottom - 10),
                1,
            )
        draw_text(
            surface,
            "OFFENSE",
            (field_inner.left + 24, field_inner.top + 18),
            self._small_font,
            self.theme.muted,
        )
        draw_text(
            surface,
            "DEFENSE",
            (field_inner.left + 24, field_inner.bottom - 138),
            self._small_font,
            self.theme.muted,
        )

        slot_labels = (
            ("QB", "QUARTERBACK", "01"),
            ("RB", "RUNNING BACK", "02"),
            ("WR", "WIDE RECEIVER", "03"),
            ("OL", "OFFENSIVE LINE", "04"),
            ("F7", "FRONT 7", "05"),
            ("DB", "SECONDARY", "06"),
            ("HC", "HEAD COACH", "LOCKED"),
            ("ST", "SPECIAL TEAMS", "08"),
        )
        columns = 4
        gap_x = 12
        gap_y = 10
        top = field_inner.top + 48
        row_height = (field_inner.height - 48 - gap_y - 27) // 2
        cell_width = (field_inner.width - 48 - gap_x * 3) // columns
        buttons = []
        for index, (short, title, number) in enumerate(slot_labels):
            row, column = divmod(index, columns)
            y = top + row * (row_height + gap_y)
            rect = pygame.Rect(
                field_inner.left + 24 + column * (cell_width + gap_x),
                y,
                cell_width,
                row_height,
            )
            draw_panel(
                surface,
                rect,
                self.theme,
                fill=self.theme.panel_alt if short in ("HC", "ST") else self.theme.panel,
            )
            badge = pygame.Rect(rect.left + 14, rect.centery - 18, 38, 36)
            pygame.draw.rect(
                surface,
                self.theme.primary_dark
                if short not in ("HC", "ST")
                else self.theme.secondary_dark,
                badge,
                border_radius=10,
            )
            draw_text(
                surface,
                short,
                (badge.left + 6, badge.top + 9),
                self._small_font,
                self.theme.primary_accent
                if short not in ("HC", "ST")
                else self.theme.secondary_accent,
            )
            draw_text(
                surface,
                title,
                (badge.right + 12, rect.centery - 14),
                self._small_font,
                self.theme.text,
            )
            draw_text(
                surface,
                number,
                (badge.right + 12, rect.centery + 5),
                self._small_font,
                self.theme.muted,
            )
        self._draw_page_navigation(surface, content, back_only=True)

    def _draw_shop_screen(
        self, surface: pygame.Surface, content: pygame.Rect
    ) -> None:
        meter = pygame.Rect(content.left, content.top, content.width, 74)
        draw_panel(surface, meter, self.theme, fill=self.theme.panel_alt)
        draw_text(
            surface,
            "COACHING BUDGET",
            (meter.left + 22, meter.top + 16),
            self._small_font,
            self.theme.muted,
        )
        draw_text(
            surface,
            "12 AP",
            (meter.left + 22, meter.top + 34),
            self._title_font,
            self.theme.text,
        )
        bar = pygame.Rect(meter.left + 180, meter.centery - 5, meter.width - 390, 10)
        pygame.draw.rect(surface, self.theme.border_soft, bar, border_radius=5)
        pygame.draw.rect(
            surface,
            self.theme.primary_accent,
            pygame.Rect(bar.left, bar.top, round(bar.width * 0.72), bar.height),
            border_radius=5,
        )
        for index in range(6):
            x = bar.left + round(bar.width * (index + 1) / 7)
            pygame.draw.circle(surface, self.theme.text, (x, bar.centery), 2)
        draw_text(
            surface,
            "DAY 1 OF 6",
            (bar.right + 20, meter.centery - 9),
            self._small_font,
            self.theme.secondary_accent,
        )

        top = meter.bottom + 22
        card_gap = 16
        card_width = (content.width - card_gap * 2) // 3
        card_height = content.bottom - top - 60
        offers = (
            ("PRACTICE", "PLAYER DEVELOPMENT", "POWER  +", "2 AP", self.theme.primary_accent),
            ("RECOVERY", "TRAINING ROOM", "STAMINA  +", "3 AP", self.theme.secondary_accent),
            ("PLAY CALL", "SIDELINE PACKAGE", "MOMENTUM  +", "4 AP", self.theme.primary_accent),
        )
        buttons = []
        for index, (title, category, effect, cost, accent) in enumerate(offers):
            rect = pygame.Rect(
                content.left + index * (card_width + card_gap),
                top,
                card_width,
                card_height,
            )
            draw_panel(surface, rect, self.theme, fill=self.theme.panel)
            header = pygame.Rect(rect.left, rect.top, rect.width, 118)
            pygame.draw.rect(surface, self.theme.panel_alt, header, border_radius=16)
            pygame.draw.rect(
                surface,
                accent,
                pygame.Rect(rect.left + 20, rect.top + 20, 42, 4),
                border_radius=2,
            )
            draw_text(
                surface,
                category,
                (rect.left + 20, rect.top + 37),
                self._small_font,
                self.theme.muted,
            )
            draw_text(
                surface,
                title,
                (rect.left + 20, rect.top + 62),
                self._title_font,
                self.theme.text,
            )
            draw_text(
                surface,
                effect,
                (rect.left + 22, rect.top + 146),
                self._label_font,
                accent,
            )
            pygame.draw.line(
                surface,
                self.theme.border_soft,
                (rect.left + 20, rect.bottom - 61),
                (rect.right - 20, rect.bottom - 61),
                1,
            )
            draw_text(
                surface,
                cost,
                (rect.left + 22, rect.bottom - 43),
                self._title_font,
                self.theme.text,
            )
            buttons.append(
                Button(
                    "ADD",
                    lambda: self.navigate("match"),
                    pygame.Rect(
                        rect.right - 112,
                        rect.bottom - 49,
                        92,
                        34,
                    ),
                    variant="primary" if index == 0 else "quiet",
                )
            )
        self._draw_page_navigation(
            surface,
            content,
            prefix_buttons=buttons,
            back_only=True,
        )

    def _draw_match_screen(
        self, surface: pygame.Surface, content: pygame.Rect
    ) -> None:
        board = pygame.Rect(content.left, content.top + 16, content.width, 255)
        draw_panel(surface, board, self.theme, fill=self.theme.panel)
        pygame.draw.rect(
            surface,
            self.theme.panel_alt,
            pygame.Rect(board.left + 14, board.top + 14, board.width - 28, 38),
            border_radius=11,
        )
        draw_text(
            surface,
            "WEEK 01",
            (board.left + 30, board.top + 25),
            self._small_font,
            self.theme.muted,
        )
        draw_text(
            surface,
            "KICKOFF",
            (board.centerx - 30, board.top + 25),
            self._small_font,
            self.theme.secondary_accent,
        )
        left_team = pygame.Rect(board.left + 36, board.top + 70, 390, 144)
        right_team = pygame.Rect(board.right - 426, board.top + 70, 390, 144)
        for rect, name, color, score in (
            (left_team, self.team_name.upper(), self.theme.primary_accent, "00"),
            (right_team, "FCS CUPCAKE", self.theme.secondary_accent, "00"),
        ):
            pygame.draw.rect(surface, self.theme.panel_alt, rect, border_radius=18)
            pygame.draw.rect(
                surface,
                color,
                pygame.Rect(rect.left, rect.top, 6, rect.height),
                border_radius=3,
            )
            draw_text(
                surface,
                name[:20],
                (rect.left + 24, rect.top + 20),
                self._small_font,
                self.theme.muted,
            )
            score_font = _ui_font(82, bold=True)
            score_surface = score_font.render(score, True, self.theme.text)
            surface.blit(score_surface, (rect.left + 22, rect.top + 44))
            pygame.draw.line(
                surface,
                self.theme.border,
                (rect.right - 36, rect.top + 20),
                (rect.right - 36, rect.bottom - 20),
                1,
            )
            draw_text(
                surface,
                "HOME" if name == self.team_name.upper() else "AWAY",
                (rect.right - 29 - self._small_font.size("HOME")[0], rect.centery - 6),
                self._small_font,
                self.theme.muted,
            )
        center = pygame.Rect(board.centerx - 42, board.top + 106, 84, 70)
        pygame.draw.circle(surface, self.theme.canvas_lift, center.center, 34)
        draw_text(
            surface,
            "VS",
            (center.centerx - 12, center.centery - 9),
            self._label_font,
            self.theme.text,
        )

        momentum = pygame.Rect(content.left + 24, board.bottom + 24, content.width - 48, 69)
        draw_text(
            surface,
            "MOMENTUM",
            (momentum.left, momentum.top),
            self._small_font,
            self.theme.muted,
        )
        track = pygame.Rect(momentum.left, momentum.top + 25, momentum.width, 14)
        pygame.draw.rect(surface, self.theme.secondary_dark, track, border_radius=7)
        pygame.draw.rect(
            surface,
            self.theme.primary_dark,
            pygame.Rect(track.centerx, track.top, track.width // 2, track.height),
            border_radius=7,
        )
        pygame.draw.circle(surface, self.theme.text, track.center, 12)
        pygame.draw.circle(surface, self.theme.primary_accent, track.center, 5)
        drive_y = momentum.bottom + 28
        for index in range(10):
            x = content.left + 24 + index * ((content.width - 48) // 10)
            pygame.draw.circle(
                surface,
                self.theme.primary_accent if index < 3 else self.theme.border,
                (x, drive_y),
                7 if index < 3 else 5,
            )
        self._draw_page_navigation(surface, content, back_only=True)

    def _draw_settings_screen(
        self, surface: pygame.Surface, content: pygame.Rect
    ) -> None:
        swatch_width = 66
        palette = pygame.Rect(
            content.left,
            content.top,
            round(content.width * 0.62),
            content.height,
        )
        preview = pygame.Rect(
            palette.right + 18,
            content.top,
            content.right - palette.right - 18,
            content.height,
        )
        draw_panel(surface, palette, self.theme)
        draw_text(
            surface,
            "TEAM COLOR SYSTEM",
            (palette.left + 24, palette.top + 24),
            self._small_font,
            self.theme.muted,
        )
        swatches = (
            ("PRIMARY", self.theme.primary, self.theme.primary_accent),
            ("SECONDARY", self.theme.secondary, self.theme.secondary_accent),
            ("SURFACE", self.theme.panel_alt, self.theme.panel_top),
        )
        for index, (label, color, highlight) in enumerate(swatches):
            y = palette.top + 76 + index * 104
            pygame.draw.rect(
                surface,
                self.theme.panel_alt,
                pygame.Rect(palette.left + 20, y, palette.width - 40, 84),
                border_radius=16,
            )
            pygame.draw.rect(
                surface,
                color,
                pygame.Rect(palette.left + 34, y + 14, swatch_width, 56),
                border_radius=12,
            )
            pygame.draw.line(
                surface,
                highlight,
                (palette.left + 46, y + 16),
                (palette.left + 88, y + 16),
                2,
            )
            draw_text(
                surface,
                label,
                (palette.left + 122, y + 22),
                self._label_font,
                self.theme.text,
            )
            draw_text(
                surface,
                "ACTIVE",
                (palette.right - 92, y + 25),
                self._small_font,
                self.theme.muted,
            )
        draw_panel(surface, preview, self.theme, fill=self.theme.panel_alt)
        jersey = pygame.Rect(
            preview.centerx - 75,
            preview.top + 56,
            150,
            182,
        )
        self._draw_jersey(surface, jersey)
        draw_text(
            surface,
            "HOME KIT",
            (preview.centerx - 37, jersey.bottom + 24),
            self._small_font,
            self.theme.muted,
        )
        self._draw_page_navigation(surface, content, back_only=True)

    def _draw_jersey(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        points = (
            (rect.left + 34, rect.top),
            (rect.left + 58, rect.top + 10),
            (rect.right - 58, rect.top + 10),
            (rect.right - 34, rect.top),
            (rect.right, rect.top + 35),
            (rect.right - 20, rect.top + 57),
            (rect.right - 34, rect.top + 46),
            (rect.right - 34, rect.bottom),
            (rect.left + 34, rect.bottom),
            (rect.left + 34, rect.top + 46),
            (rect.left + 20, rect.top + 57),
            (rect.left, rect.top + 35),
        )
        pygame.draw.polygon(surface, self.theme.primary, points)
        pygame.draw.polygon(surface, self.theme.border, points, width=1)
        pygame.draw.polygon(
            surface,
            self.theme.secondary,
            (
                (rect.left + 58, rect.top + 10),
                (rect.left + 76, rect.top + 10),
                (rect.left + 65, rect.top + 42),
                (rect.left + 48, rect.top + 42),
            ),
        )
        pygame.draw.polygon(
            surface,
            self.theme.secondary,
            (
                (rect.right - 58, rect.top + 10),
                (rect.right - 76, rect.top + 10),
                (rect.right - 65, rect.top + 42),
                (rect.right - 48, rect.top + 42),
            ),
        )
        number = _ui_font(58, bold=True).render("08", True, self.theme.primary_ink)
        surface.blit(number, number.get_rect(center=(rect.centerx, rect.centery + 8)))

    def _draw_page_navigation(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        *,
        prefix_buttons: list[Button] | None = None,
        back_only: bool = False,
    ) -> None:
        back_rect = pygame.Rect(content.right - 154, content.bottom - 42, 154, 38)
        buttons = list(prefix_buttons or [])
        if self.definition.next_screen is not None and not back_only:
            next_rect = pygame.Rect(content.right - 330, content.bottom - 42, 164, 38)
            buttons.append(
                Button(
                    "CONTINUE",
                    lambda: self.navigate(self.definition.next_screen or "main_menu"),
                    next_rect,
                    variant="primary",
                )
            )
        buttons.append(
            Button("MAIN MENU", lambda: self.navigate("main_menu"), back_rect)
        )
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _draw_preview_stage(
        self, surface: pygame.Surface, rect: pygame.Rect
    ) -> None:
        draw_text(
            surface,
            "CONCEPT BOARD",
            (rect.left + 20, rect.top + 17),
            self._small_font,
            self.theme.muted,
        )
        visual = pygame.Rect(
            rect.left + 18,
            rect.top + 48,
            rect.width - 36,
            rect.height - 65,
        )
        if self.definition.title == "The depth chart":
            labels = ("QB", "RB", "WR", "OL", "F7", "DB", "HC", "ST")
            columns = 4
            gap_x = 9
            gap_y = 10
            cell_width = (visual.width - gap_x * (columns - 1)) // columns
            cell_height = (visual.height - gap_y) // 2
            for index, label in enumerate(labels):
                row, column = divmod(index, columns)
                cell = pygame.Rect(
                    visual.left + column * (cell_width + gap_x),
                    visual.top + row * (cell_height + gap_y),
                    cell_width,
                    cell_height,
                )
                draw_panel(
                    surface,
                    cell,
                    self.theme,
                    fill=self.theme.panel if index < 6 else self.theme.panel_high,
                )
                pygame.draw.circle(
                    surface,
                    self.theme.primary_accent if index < 6 else self.theme.secondary_accent,
                    (cell.left + 19, cell.centery),
                    5,
                )
                draw_text(
                    surface,
                    label,
                    (cell.left + 32, cell.centery - 8),
                    self._label_font,
                    self.theme.text,
                )
                draw_text(
                    surface,
                    "LOCKED" if label == "HC" else "OPEN SLOT",
                    (cell.right - 82, cell.centery - 6),
                    self._small_font,
                    self.theme.muted,
                )
        elif self.definition.title == "Saturday lights":
            center = visual.centerx
            for x, name, score, color in (
                (visual.left + 8, self.team_name[:13].upper(), "00", self.theme.primary_accent),
                (visual.right - 154, "RIVAL", "00", self.theme.secondary_accent),
            ):
                badge = pygame.Rect(x, visual.top + 20, 146, visual.height - 42)
                draw_panel(surface, badge, self.theme)
                pygame.draw.rect(
                    surface,
                    color,
                    pygame.Rect(badge.left, badge.top, badge.width, 4),
                    border_radius=2,
                )
                draw_text(
                    surface,
                    name,
                    (badge.left + 14, badge.top + 16),
                    self._small_font,
                    self.theme.muted,
                )
                score_font = _ui_font(52, bold=True)
                draw_text(
                    surface,
                    score,
                    (badge.left + 14, badge.top + 40),
                    score_font,
                    self.theme.text,
                )
            pygame.draw.line(
                surface,
                self.theme.border,
                (center, visual.top + 29),
                (center, visual.bottom - 29),
                1,
            )
            draw_text(
                surface,
                "VS",
                (center - 12, visual.centery - 8),
                self._small_font,
                self.theme.secondary_accent,
            )
        elif self.definition.title == "The coaching shop":
            gap = 10
            width = (visual.width - gap * 2) // 3
            for index, title in enumerate(("PRACTICE", "RECOVERY", "PLAY CALL")):
                card = pygame.Rect(
                    visual.left + index * (width + gap),
                    visual.top + 15,
                    width,
                    visual.height - 30,
                )
                draw_panel(surface, card, self.theme)
                pygame.draw.rect(
                    surface,
                    self.theme.primary_accent if index != 1 else self.theme.secondary_accent,
                    pygame.Rect(card.left, card.top, card.width, 4),
                    border_radius=2,
                )
                draw_text(
                    surface,
                    f"0{index + 1}",
                    (card.left + 15, card.top + 16),
                    self._small_font,
                    self.theme.muted,
                )
                draw_text(
                    surface,
                    title,
                    (card.left + 15, card.top + 44),
                    self._label_font,
                    self.theme.text,
                )
                draw_text(
                    surface,
                    "2 AP",
                    (card.left + 15, card.bottom - 31),
                    self._small_font,
                    self.theme.secondary_accent,
                )
        elif self.definition.title == "Pick your sideline":
            gap = 10
            width = (visual.width - gap * 2) // 3
            for index, title in enumerate(("AIR RAID", "GROUND GAME", "BALANCED")):
                card = pygame.Rect(
                    visual.left + index * (width + gap),
                    visual.top + 15,
                    width,
                    visual.height - 30,
                )
                draw_panel(surface, card, self.theme, selected=index == 0)
                draw_text(
                    surface,
                    f"COACH 0{index + 1}",
                    (card.left + 15, card.top + 16),
                    self._small_font,
                    self.theme.muted,
                )
                draw_text(
                    surface,
                    title,
                    (card.left + 15, card.top + 47),
                    self._label_font,
                    self.theme.text,
                )
                pygame.draw.line(
                    surface,
                    self.theme.border,
                    (card.left + 15, card.bottom - 39),
                    (card.right - 15, card.bottom - 39),
                    2,
                )
        elif self.definition.title == "National Signing Day":
            gap = 10
            width = (visual.width - gap * 2) // 3
            prospects = (
                ("01 / QUARTERBACK", "FIELD GENERAL", "ARM / AWARENESS"),
                ("02 / QUARTERBACK", "DUAL THREAT", "SPEED / VISION"),
                ("03 / QUARTERBACK", "POCKET ACE", "ACCURACY / POISE"),
            )
            for index, (position, archetype, traits) in enumerate(prospects):
                card = pygame.Rect(
                    visual.left + index * (width + gap),
                    visual.top + 10,
                    width,
                    visual.height - 20,
                )
                draw_panel(surface, card, self.theme)
                pygame.draw.rect(
                    surface,
                    self.theme.primary_accent
                    if index != 1
                    else self.theme.secondary_accent,
                    pygame.Rect(card.left, card.top, card.width, 4),
                    border_radius=2,
                )
                draw_text(
                    surface,
                    position,
                    (card.left + 15, card.top + 16),
                    self._small_font,
                    self.theme.muted,
                )
                draw_text(
                    surface,
                    archetype,
                    (card.left + 15, card.top + 48),
                    self._label_font,
                    self.theme.text,
                )
                pygame.draw.line(
                    surface,
                    self.theme.border_soft,
                    (card.left + 15, card.top + 77),
                    (card.right - 15, card.top + 77),
                    1,
                )
                draw_text(
                    surface,
                    traits,
                    (card.left + 15, card.top + 91),
                    self._small_font,
                    self.theme.muted,
                )
                pygame.draw.rect(
                    surface,
                    self.theme.panel_high,
                    pygame.Rect(card.left + 15, card.bottom - 22, card.width - 30, 5),
                    border_radius=2,
                )
                pygame.draw.rect(
                    surface,
                    self.theme.primary_accent,
                    pygame.Rect(
                        card.left + 15,
                        card.bottom - 22,
                        round((card.width - 30) * (0.76 - index * 0.12)),
                        5,
                    ),
                    border_radius=2,
                )
        else:
            swatches = (
                ("PRIMARY", self.theme.primary),
                ("SECONDARY", self.theme.secondary),
                ("UI ACCENT", self.theme.primary_accent),
                ("SURFACE", self.theme.panel_high),
            )
            for index, (label, color) in enumerate(swatches):
                x = visual.left + index * 112
                pygame.draw.rect(
                    surface,
                    color,
                    pygame.Rect(x, visual.centery - 22, 88, 52),
                    border_radius=9,
                )
                draw_text(
                    surface,
                    label,
                    (x, visual.centery + 42),
                    self._small_font,
                    self.theme.muted,
                )
