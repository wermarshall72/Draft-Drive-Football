"""Match scoreboard and recent-play presentation."""

import pygame

from src.engine.football import (
    DefensiveSchemeAction, FootballAutomaticAction, FootballConversionAction, FootballMatchEvent,
    FootballTeamSide, OffensivePlayAction,
)
from src.engine.football_controller import FootballGameControllerState
from src.ui.football_display import _PLAY_LABELS, _SCHEME_LABELS
from src.ui.football_match_palette import (
    MATCH_PANEL as _MATCH_PANEL, MATCH_PANEL_EDGE as _MATCH_PANEL_EDGE,
    MATCH_CHALK as _MATCH_CHALK, MATCH_MUTED as _MATCH_MUTED,
    MATCH_BRASS as _MATCH_BRASS,
)
from src.ui.screens import _ui_font
from src.ui.text import fit_text as _fit_text
from src.ui.widgets import draw_text

class FootballMatchStatusView:
    def __init__(self, small_font: pygame.font.Font) -> None:
        self._small_font = small_font

    def draw_scoreboard(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        state: FootballGameControllerState,
        team_accent: pygame.Color,
        opponent_accent: pygame.Color,
    ) -> None:
        match = state.match
        if match is None:
            raise RuntimeError("The controller did not provide an active match state.")

        pygame.draw.rect(surface, _MATCH_PANEL, rect)
        pygame.draw.line(
            surface,
            _MATCH_PANEL_EDGE,
            rect.topleft,
            (rect.right, rect.top),
            1,
        )
        pygame.draw.rect(
            surface,
            team_accent,
            pygame.Rect(rect.left, rect.top, rect.width // 2, 4),
        )
        pygame.draw.rect(
            surface,
            opponent_accent,
            pygame.Rect(rect.centerx, rect.top, rect.width - rect.width // 2, 4),
        )

        score_font = _ui_font(48, bold=True)
        team_font = _ui_font(16, bold=True)
        left_team = match.team_a.team_name.upper()
        right_team = match.team_b.team_name.upper()
        draw_text(
            surface,
            _fit_text(left_team, team_font, rect.width // 3),
            (rect.left + 24, rect.top + 13),
            team_font,
            _MATCH_CHALK,
        )
        draw_text(
            surface,
            str(match.team_a_score),
            (rect.left + 24, rect.top + 35),
            score_font,
            _MATCH_CHALK,
        )
        right_score = score_font.render(str(match.team_b_score), True, _MATCH_CHALK)
        surface.blit(
            right_score,
            right_score.get_rect(
                midright=(rect.right - 24, rect.top + 65),
            ),
        )
        right_name = team_font.render(
            _fit_text(right_team, team_font, rect.width // 3 - 120),
            True,
            _MATCH_CHALK,
        )
        surface.blit(
            right_name,
            right_name.get_rect(topright=(rect.right - 120, rect.top + 13)),
        )

        clock = f"{match.game_clock_seconds // 60:02d}:{match.game_clock_seconds % 60:02d}"
        clock_font = _ui_font(28, bold=True)
        clock_surface = clock_font.render(clock, True, _MATCH_CHALK)
        surface.blit(
            clock_surface,
            clock_surface.get_rect(midtop=(rect.centerx, rect.top + 25)),
        )
        meta = f"Q{match.period}    GAME {state.game_number:02d}    {state.wins}-{state.losses}"
        meta_surface = self._small_font.render(meta, True, _MATCH_MUTED)
        surface.blit(
            meta_surface,
            meta_surface.get_rect(midtop=(rect.centerx, rect.top + 66)),
        )
        pygame.draw.line(
            surface,
            team_accent if match.possession is FootballTeamSide.TEAM_A else _MATCH_PANEL_EDGE,
            (rect.left + 24, rect.bottom - 2),
            (rect.centerx - 16, rect.bottom - 2),
            3,
        )
        pygame.draw.line(
            surface,
            opponent_accent if match.possession is FootballTeamSide.TEAM_B else _MATCH_PANEL_EDGE,
            (rect.centerx + 16, rect.bottom - 2),
            (rect.right - 24, rect.bottom - 2),
            3,
        )

        possession_color = (
            team_accent
            if match.possession is FootballTeamSide.TEAM_A
            else opponent_accent
        )
        possession_center = (
            rect.left + 180
            if match.possession is FootballTeamSide.TEAM_A
            else rect.right - 180
        )
        possession_y = rect.bottom - 14
        pygame.draw.polygon(
            surface,
            possession_color,
            (
                (possession_center - 5, possession_y - 4),
                (possession_center + 5, possession_y - 4),
                (possession_center, possession_y + 3),
            ),
        )

    def draw_history(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        match = state.match
        if match is None:
            raise RuntimeError("The controller did not provide an active match state.")
        pygame.draw.rect(surface, _MATCH_PANEL, rect)
        pygame.draw.rect(
            surface,
            _MATCH_BRASS,
            pygame.Rect(rect.left, rect.top, 3, rect.height),
        )
        label = "SIDELINE NOTES"
        draw_text(
            surface,
            label,
            (rect.left + 14, rect.top + 7),
            self._small_font,
            _MATCH_BRASS,
        )
        if match.match_events:
            latest = match.match_events[-1]
            text = self.format_event(latest, match.team_a.team_name, match.team_b.team_name)
            previous = (
                self.format_event(
                    match.match_events[-2],
                    match.team_a.team_name,
                    match.team_b.team_name,
                )
                if len(match.match_events) > 1
                else ""
            )
        else:
            text = "Opening drive  /  First possession"
            previous = ""
        text_left = rect.left + 142
        available = rect.right - text_left - 18
        draw_text(
            surface,
            _fit_text(text, self._small_font, available),
            (text_left, rect.top + 7),
            self._small_font,
            _MATCH_CHALK,
        )
        if previous:
            previous_surface = self._small_font.render(
                _fit_text(previous, self._small_font, available),
                True,
                _MATCH_MUTED,
            )
            surface.blit(
                previous_surface,
                previous_surface.get_rect(
                    bottomright=(rect.right - 18, rect.bottom - 6),
                ),
            )

    def format_event(
        self, event: FootballMatchEvent, team_a_name: str, team_b_name: str
    ) -> str:
        if isinstance(event.action, DefensiveSchemeAction):
            defense = team_a_name if event.possession is FootballTeamSide.TEAM_B else team_b_name
            description = f"{defense} sets {_SCHEME_LABELS[event.action]}"
        elif isinstance(event.action, OffensivePlayAction):
            result = event.play_result
            offensive_side = event.possession
            if result is not None and result.possession_changed:
                offensive_side = (
                    FootballTeamSide.TEAM_B
                    if event.possession is FootballTeamSide.TEAM_A
                    else FootballTeamSide.TEAM_A
                )
            offense = (
                team_a_name
                if offensive_side is FootballTeamSide.TEAM_A
                else team_b_name
            )
            if result is None:
                description = f"{offense}: {_PLAY_LABELS[event.action]}"
            elif result.turnover and result.points_scored:
                if event.scoring_team is FootballTeamSide.TEAM_A:
                    scorer = team_a_name
                elif event.scoring_team is FootballTeamSide.TEAM_B:
                    scorer = team_b_name
                else:
                    raise ValueError(
                        "A defensive touchdown event must identify its scorer."
                    )
                offense = (
                    team_a_name
                    if event.possession is FootballTeamSide.TEAM_A
                    else team_b_name
                )
                description = (
                    f"{scorer}: defensive touchdown on {offense}'s "
                    f"{_PLAY_LABELS[event.action]} interception"
                )
            elif result.turnover:
                description = f"{offense}: {_PLAY_LABELS[event.action]} - turnover"
            elif result.turnover_on_downs:
                play_outcome = (
                    "incomplete"
                    if result.incomplete
                    else f"{result.yards_gained:+.1f} yd"
                )
                description = (
                    f"{offense}: {_PLAY_LABELS[event.action]} - "
                    f"{play_outcome}, turnover on downs"
                )
            elif result.incomplete:
                description = f"{offense}: {_PLAY_LABELS[event.action]} - incomplete"
            else:
                description = (
                    f"{offense}: {_PLAY_LABELS[event.action]} - "
                    f"{result.yards_gained:+.1f} yd"
                )
        elif isinstance(
            event.action, (FootballConversionAction, FootballAutomaticAction)
        ):
            responsible_side = event.scoring_team or event.possession
            responsible_team = (
                team_a_name
                if responsible_side is FootballTeamSide.TEAM_A
                else team_b_name
            )
            description = (
                f"{responsible_team}: "
                f"{event.description or event.action.value.replace('_', ' ').upper()}"
            )
        elif event.description is not None:
            description = event.description
        else:
            offense = team_a_name if event.possession is FootballTeamSide.TEAM_A else team_b_name
            description = f"{offense}: {event.action.value.replace('_', ' ').upper()}"
        if event.perk_effects:
            description += f" / {'; '.join(event.perk_effects)}"
        return _fit_text(description, self._small_font, 950)
