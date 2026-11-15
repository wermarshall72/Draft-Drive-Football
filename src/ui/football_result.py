from collections.abc import Callable

import pygame

from src.engine.football import FootballTeamSide
from src.engine.football_controller import FootballGameControllerState, FootballRunPhase
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text
from src.ui.text import fit_text


class FootballResultView:
    """Render a completed game's result and expose the appropriate next action."""

    def __init__(
        self,
        display_font: pygame.font.Font,
        title_font: pygame.font.Font,
        label_font: pygame.font.Font,
        small_font: pygame.font.Font,
        open_next_shop: Callable[[], None],
        return_to_menu: Callable[[], None],
    ) -> None:
        self.display_font = display_font
        self.title_font = title_font
        self.label_font = label_font
        self.small_font = small_font
        self.open_next_shop = open_next_shop
        self.return_to_menu = return_to_menu

    def draw(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
        theme: Theme,
    ) -> list[Button]:
        if (
            state.phase is FootballRunPhase.PLAYOFFS
            and state.game_number in state.skipped_games
        ):
            return self._draw_bye_week_marker(surface, content, state, theme)

        match = state.match
        if match is None or match.final_result is None:
            raise RuntimeError("A season result requires the completed match result.")
        result = match.final_result
        won = result.winner is FootballTeamSide.TEAM_A
        result_panel = pygame.Rect(
            content.left + 42,
            content.top + 8,
            content.width - 84,
            content.height - 16,
        )
        draw_panel(surface, result_panel, theme, fill=theme.panel)
        outcome = self.display_font.render(
            "FINAL  /  WIN" if won else "FINAL  /  LOSS",
            True,
            theme.primary_accent if won else theme.danger,
        )
        surface.blit(
            outcome,
            outcome.get_rect(midtop=(result_panel.centerx, result_panel.top + 22)),
        )
        scoreline = (
            f"{match.team_a.team_name}  {result.team_a_score}"
            f"     -     {result.team_b_score}  {match.team_b.team_name}"
        )
        scoreline_surface = self.title_font.render(
            fit_text(scoreline, self.title_font, result_panel.width - 56),
            True,
            theme.text,
        )
        surface.blit(
            scoreline_surface,
            scoreline_surface.get_rect(
                midtop=(result_panel.centerx, result_panel.top + 87)
            ),
        )
        pygame.draw.line(
            surface,
            theme.border_soft,
            (result_panel.left + 28, result_panel.top + 132),
            (result_panel.right - 28, result_panel.top + 132),
            1,
        )
        draw_text(
            surface,
            f"GAME {state.game_number}  |  RECORD {state.wins}-{state.losses}",
            (
                result_panel.centerx
                - self.label_font.size(
                    f"GAME {state.game_number}  |  RECORD {state.wins}-{state.losses}"
                )[0]
                // 2,
                result_panel.top + 154,
            ),
            self.label_font,
            theme.secondary_accent,
        )

        if state.phase is FootballRunPhase.READY_FOR_NEXT_GAME:
            stage = "REGULAR SEASON"
            explanation = "Next up: a fresh coaching shop before the game."
            primary_label = "OPEN NEXT GAME SHOP"
            primary_action = self.open_next_shop
        elif state.phase is FootballRunPhase.FIRED:
            stage = "RUN OVER  /  THREE LOSSES"
            explanation = "Your season is over."
            primary_label = "RETURN TO MAIN MENU"
            primary_action = self.return_to_menu
        else:
            stage = "GAME 10 COMPLETE"
            explanation = "Playoffs reached. No playoff games are available yet."
            primary_label = "RETURN TO MAIN MENU"
            primary_action = self.return_to_menu
        draw_text(
            surface,
            stage,
            (
                result_panel.centerx - self.label_font.size(stage)[0] // 2,
                result_panel.top + 198,
            ),
            self.label_font,
            theme.text,
        )
        explanation_surface = self.small_font.render(
            fit_text(explanation, self.small_font, result_panel.width - 60),
            True,
            theme.muted,
        )
        surface.blit(
            explanation_surface,
            explanation_surface.get_rect(
                midtop=(result_panel.centerx, result_panel.top + 228)
            ),
        )
        primary_rect = pygame.Rect(
            result_panel.centerx - min(370, result_panel.width - 60) // 2,
            result_panel.bottom - 55,
            min(370, result_panel.width - 60),
            42,
        )
        return [Button(primary_label, primary_action, primary_rect, variant="primary")]

    def _draw_bye_week_marker(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
        theme: Theme,
    ) -> list[Button]:
        panel = pygame.Rect(
            content.left + 42,
            content.top + 8,
            content.width - 84,
            content.height - 16,
        )
        draw_panel(surface, panel, theme, fill=theme.panel)
        title = self.display_font.render("BYE WEEK  /  NO GAME RESULT", True, theme.secondary_accent)
        surface.blit(title, title.get_rect(midtop=(panel.centerx, panel.top + 30)))
        draw_text(
            surface,
            f"SCHEDULED GAME 10 SKIPPED  |  RECORD {state.wins}-{state.losses}",
            (
                panel.centerx
                - self.label_font.size(
                    f"SCHEDULED GAME 10 SKIPPED  |  RECORD {state.wins}-{state.losses}"
                )[0]
                // 2,
                panel.top + 102,
            ),
            self.label_font,
            theme.text,
        )
        draw_text(
            surface,
            f"{state.games_played} actual regular-season games played.",
            (
                panel.centerx
                - self.small_font.size(
                    f"{state.games_played} actual regular-season games played."
                )[0]
                // 2,
                panel.top + 139,
            ),
            self.small_font,
            theme.muted,
        )
        draw_wrapped_text(
            surface,
            state.transition_message
            or "Game 10 was skipped without a score or win/loss. You reached the "
            "playoffs marker; playoff games are not available yet.",
            pygame.Rect(panel.left + 45, panel.top + 181, panel.width - 90, 72),
            self.small_font,
            theme.muted,
            line_gap=4,
        )
        primary_rect = pygame.Rect(
            panel.centerx - min(370, panel.width - 60) // 2,
            panel.bottom - 55,
            min(370, panel.width - 60),
            42,
        )
        return [
            Button(
                "RETURN TO MAIN MENU",
                self.return_to_menu,
                primary_rect,
                variant="primary",
            )
        ]
