from collections.abc import Callable

import pygame

from src.application import MainMenuState
from src.engine.football_ai import FootballAIDifficulty
from src.ui.screens import Navigate, Quit, Screen, _ui_font
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text


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

    def draw(self, surface: pygame.Surface) -> None:
        team_name = (
            self.menu_state.profile.team_name
            if self.menu_state is not None
            else "NEW TEAM"
        )
        layout = self._header(surface, "Build your season", "HOME / SEASON", team_name)
        content = layout.content
        hero = pygame.Rect(content.left, content.top, content.width, 286)
        draw_panel(surface, hero, self.theme, fill=self.theme.panel)

        copy_width = hero.width - 390
        draw_text(
            surface,
            "COLLEGE FOOTBALL  /  ROGUELIKE SEASON",
            (hero.left + 32, hero.top + 28),
            self._small_font,
            self.theme.secondary_accent,
        )
        name = team_name.upper()
        if len(name) > 24:
            name = f"{name[:21]}..."
        name_font = _ui_font(54, bold=True)
        while name_font.size(name)[0] > copy_width - 64 and name_font.get_height() > 32:
            name_font = _ui_font(name_font.get_height() - 2, bold=True)
        draw_text(
            surface,
            name,
            (hero.left + 30, hero.top + 66),
            name_font,
            self.theme.text,
        )
        draw_text(
            surface,
            "BUILD A ROSTER. CALL THE GAME.",
            (hero.left + 34, hero.top + 131),
            self._label_font,
            self.theme.text,
        )
        draw_wrapped_text(
            surface,
            "Eight picks. One training stop. Every snap is yours.",
            pygame.Rect(hero.left + 34, hero.top + 165, copy_width - 54, 46),
            self._body_font,
            self.theme.muted,
        )

        if self.menu_state is not None:
            profile = self.menu_state.profile
            for index, (label, color) in enumerate(
                (
                    (profile.primary_color.display_name.upper(), self.theme.primary),
                    (profile.secondary_color.display_name.upper(), self.theme.secondary),
                )
            ):
                x = hero.left + 34 + index * 154
                pygame.draw.rect(
                    surface,
                    color,
                    pygame.Rect(x, hero.bottom - 42, 24, 18),
                    border_radius=4,
                )
                draw_text(
                    surface,
                    label,
                    (x + 32, hero.bottom - 42),
                    self._small_font,
                    self.theme.muted,
                )
        elif self.profile_error is not None:
            draw_wrapped_text(
                surface,
                "Team profile could not load. Repair it from the terminal client.",
                pygame.Rect(hero.left + 34, hero.bottom - 58, copy_width - 54, 42),
                self._small_font,
                self.theme.danger,
            )
        else:
            draw_text(
                surface,
                "Create a team profile to start a season.",
                (hero.left + 34, hero.bottom - 48),
                self._small_font,
                self.theme.muted,
            )

        action = pygame.Rect(hero.right - 344, hero.top + 14, 328, hero.height - 28)
        draw_panel(surface, action, self.theme, fill=self.theme.panel_alt)
        draw_text(
            surface,
            "OPPONENT DIFFICULTY",
            (action.left + 18, action.top + 16),
            self._small_font,
            self.theme.muted,
        )
        gap = 6
        option_width = (action.width - 36 - gap * 2) // 3
        buttons: list[Button] = []
        for index, difficulty in enumerate(FootballAIDifficulty):
            rect = pygame.Rect(
                action.left + 18 + index * (option_width + gap),
                action.top + 38,
                option_width,
                36,
            )
            buttons.append(
                Button(
                    difficulty.value.upper(),
                    lambda choice=difficulty: self._select_difficulty(choice),
                    rect,
                    variant="primary" if difficulty is self.difficulty else "quiet",
                )
            )

        start_rect = pygame.Rect(action.left + 18, action.top + 87, action.width - 36, 50)
        buttons.insert(
            0,
            Button(
                "START RUN",
                lambda: self.on_start_run(self.difficulty),
                start_rect,
                enabled=self.menu_state is not None,
                variant="primary",
            ),
        )
        utility_y = action.bottom - 47
        utility_gap = 10
        utility_width = (action.width - 36 - utility_gap) // 2
        buttons.extend(
            (
                Button(
                    "SETTINGS",
                    lambda: self.navigate("settings"),
                    pygame.Rect(action.left + 18, utility_y, utility_width, 34),
                ),
                Button(
                    "QUIT",
                    self.quit_application,
                    pygame.Rect(
                        action.left + 18 + utility_width + utility_gap,
                        utility_y,
                        utility_width,
                        34,
                    ),
                ),
            )
        )

        if self.theme.warning is not None and self.menu_state is not None:
            draw_text(
                surface,
                "COLOR FALLBACK",
                (hero.left + 34, hero.bottom - 48),
                self._small_font,
                self.theme.danger,
            )

        overview_top = hero.bottom + 18
        overview_height = max(92, content.bottom - overview_top)
        overview = pygame.Rect(content.left, overview_top, content.width, overview_height)
        draw_panel(surface, overview, self.theme, fill=self.theme.panel_alt)
        stages = (
            ("01", "DRAFT", "8 positions"),
            ("02", "TRAIN", "Spend 6 points"),
            ("03", "KICK OFF", "Call every play"),
        )
        column_width = overview.width // len(stages)
        for index, (number, title, detail) in enumerate(stages):
            left = overview.left + index * column_width
            if index:
                pygame.draw.line(
                    surface,
                    self.theme.border_soft,
                    (left, overview.top + 17),
                    (left, overview.bottom - 17),
                    1,
                )
            draw_text(
                surface,
                number,
                (left + 20, overview.top + 20),
                self._small_font,
                self.theme.secondary_accent,
            )
            draw_text(
                surface,
                title,
                (left + 56, overview.top + 17),
                self._label_font,
                self.theme.text,
            )
            draw_text(
                surface,
                detail,
                (left + 56, overview.top + 45),
                self._small_font,
                self.theme.muted,
            )

        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _select_difficulty(self, difficulty: FootballAIDifficulty) -> None:
        self.difficulty = difficulty
