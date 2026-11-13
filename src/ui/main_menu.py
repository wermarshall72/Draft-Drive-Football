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
        layout = self._header(surface, "Saturday starts here", "OFFLINE SEASON", team_name)
        content = layout.content
        hero_height = min(286, round(content.height * 0.62))
        hero = pygame.Rect(content.left, content.top, content.width, hero_height)
        draw_panel(surface, hero, self.theme)

        draw_text(
            surface,
            "YOUR TEAM. YOUR CALLS.",
            (hero.left + 34, hero.top + 27),
            self._small_font,
            self.theme.secondary_accent,
        )
        title = team_name.upper()[:22]
        title_font = _ui_font(56, bold=True)
        while title_font.size(title)[0] > round(hero.width * 0.45):
            title_font = _ui_font(max(34, title_font.get_height() - 3), bold=True)
        draw_text(surface, title, (hero.left + 34, hero.top + 68), title_font, self.theme.text)
        draw_wrapped_text(
            surface,
            "Draft eight positions, tune your roster with Training Points, then call every play against local AI.",
            pygame.Rect(hero.left + 36, hero.top + 137, 430, 58),
            self._body_font,
            self.theme.muted,
        )

        action = pygame.Rect(hero.right - 324, hero.top + 15, 304, hero.height - 30)
        draw_panel(surface, action, self.theme, fill=self.theme.panel_alt)
        draw_text(
            surface,
            "LOCAL AI DIFFICULTY",
            (action.left + 18, action.top + 16),
            self._small_font,
            self.theme.secondary_accent,
        )
        difficulty_y = action.top + 42
        difficulty_gap = 7
        difficulty_width = (action.width - 36 - difficulty_gap * 2) // 3
        buttons: list[Button] = []
        for index, difficulty in enumerate(FootballAIDifficulty):
            rect = pygame.Rect(
                action.left + 18 + index * (difficulty_width + difficulty_gap),
                difficulty_y,
                difficulty_width,
                36,
            )
            button = Button(
                difficulty.value.upper(),
                lambda choice=difficulty: self._select_difficulty(choice),
                rect,
                variant="primary" if difficulty is self.difficulty else "quiet",
            )
            buttons.append(button)

        draw_text(
            surface,
            "8 positions  /  6 Training Points  /  up to 10 games",
            (action.left + 18, action.top + 87),
            self._small_font,
            self.theme.text,
        )
        start_rect = pygame.Rect(action.left + 16, action.top + 118, action.width - 32, 54)
        buttons.insert(
            0,
            Button(
                "PLAY / START RUN",
                lambda: self.on_start_run(self.difficulty),
                start_rect,
                enabled=self.menu_state is not None,
                variant="primary",
            ),
        )
        settings_rect = pygame.Rect(action.left + 16, action.bottom - 49, 126, 36)
        quit_rect = pygame.Rect(action.right - 142, action.bottom - 49, 126, 36)
        buttons.extend(
            (
                Button("SETTINGS", lambda: self.navigate("settings"), settings_rect),
                Button("QUIT", self.quit_application, quit_rect),
            )
        )

        if self.menu_state is None:
            message = (
                "Profile could not load; use the terminal client to repair it."
                if self.profile_error is not None
                else "Create a saved team profile before starting a run."
            )
            draw_wrapped_text(
                surface,
                message,
                pygame.Rect(hero.left + 36, hero.bottom - 60, 440, 42),
                self._small_font,
                self.theme.danger if self.profile_error is not None else self.theme.muted,
            )
        elif self.theme.warning is not None:
            draw_wrapped_text(
                surface,
                self.theme.warning,
                pygame.Rect(hero.left + 36, hero.bottom - 54, 440, 36),
                self._small_font,
                self.theme.danger,
            )

        guide_y = hero.bottom + 18
        draw_text(
            surface,
            "YOUR SEASON",
            (content.left + 2, guide_y),
            self._small_font,
            self.theme.muted,
        )
        cards_y = guide_y + 24
        card_gap = 12
        card_width = (content.width - card_gap * 2) // 3
        card_height = content.bottom - cards_y
        for index, (heading, detail) in enumerate(
            (
                ("01  BUILD", "Choose a coach and draft all eight positions."),
                ("02  TRAIN", "Spend from one six-point upgrade shop."),
                ("03  PLAY", "Call offense and defense against local AI."),
            )
        ):
            rect = pygame.Rect(
                content.left + index * (card_width + card_gap),
                cards_y,
                card_width,
                card_height,
            )
            draw_panel(surface, rect, self.theme, fill=self.theme.panel)
            draw_text(
                surface,
                heading,
                (rect.left + 18, rect.top + 17),
                self._label_font,
                self.theme.text,
            )
            draw_wrapped_text(
                surface,
                detail,
                pygame.Rect(rect.left + 18, rect.top + 48, rect.width - 36, rect.height - 58),
                self._small_font,
                self.theme.muted,
            )

        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _select_difficulty(self, difficulty: FootballAIDifficulty) -> None:
        self.difficulty = difficulty
