from collections.abc import Callable

import pygame

from src.engine.football import (
    DefensiveSchemeAction,
    FootballMatchEvent,
    FootballMatchState,
    FootballFourthDownAction,
    FootballPosition,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_controller import (
    FootballGameController,
    FootballGameControllerState,
    FootballHumanDecision,
    FootballRunPhase,
)
from src.engine.football_shop import FootballShopState
from src.engine.football_team_builder import (
    PLAYER_DRAFT_ORDER,
    FootballPlayerCandidate,
)
from src.ui.layout import Layout
from src.ui.screens import Navigate, Quit, Screen, _ui_font
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text

_PLAY_LABELS = {
    OffensivePlayAction.RB_RUN: "RB RUN",
    OffensivePlayAction.SCREEN_PASS: "SCREEN PASS",
    OffensivePlayAction.PA_PASS: "PLAY-ACTION PASS",
    OffensivePlayAction.SHORT_PASS: "SHORT PASS",
    OffensivePlayAction.MEDIUM_PASS: "MEDIUM PASS",
    OffensivePlayAction.DEEP_PASS: "DEEP PASS",
}

_SCHEME_LABELS = {
    DefensiveSchemeAction.RB_RUN: "RB RUN SCHEME",
    DefensiveSchemeAction.SCREEN_PASS: "SCREEN PASS SCHEME",
    DefensiveSchemeAction.PA_PASS: "PLAY-ACTION SCHEME",
    DefensiveSchemeAction.SHORT_PASS: "SHORT PASS SCHEME",
    DefensiveSchemeAction.MEDIUM_PASS: "MEDIUM PASS SCHEME",
    DefensiveSchemeAction.DEEP_PASS: "DEEP PASS SCHEME",
}

_POSITION_LABELS = {
    FootballPosition.QB: "QB",
    FootballPosition.RB: "RB",
    FootballPosition.WR: "WR",
    FootballPosition.O_LINE: "O-LINE",
    FootballPosition.D_LINE: "D-LINE",
    FootballPosition.LINEBACKERS: "LINEBACKERS",
    FootballPosition.CORNERBACKS: "CORNERBACKS",
    FootballPosition.SAFETIES: "SAFETIES",
}

_MATCH_CANVAS = pygame.Color("#101712")
_MATCH_PANEL = pygame.Color("#1a241e")
_MATCH_PANEL_EDGE = pygame.Color("#36443a")
_MATCH_TURF = pygame.Color("#244a35")
_MATCH_TURF_ALT = pygame.Color("#28513a")
_MATCH_TURF_LINE = pygame.Color("#8da891")
_MATCH_CHALK = pygame.Color("#f1eddf")
_MATCH_MUTED = pygame.Color("#a8b2a1")
_MATCH_BRASS = pygame.Color("#dfbd70")
_MATCH_OPPONENT = pygame.Color("#d0785c")
_MATCH_INK = pygame.Color("#15241a")
_MATCH_FOCUS = pygame.Color("#f4d184")


class FootballRunScreen(Screen):
    """Render the current immutable controller state and submit human choices."""

    def __init__(
        self,
        theme: Theme,
        team_name: str,
        navigate: Navigate,
        quit_application: Quit,
    ) -> None:
        super().__init__(theme, navigate, quit_application)
        self.team_name = team_name
        self.controller: FootballGameController | None = None
        self.state: FootballGameControllerState | None = None
        self.last_error: str | None = None
        self.confirm_exit = False
        self._match_visual_state: FootballMatchState | None = None
        self._match_animation_started = 0
        self._match_animation_origin = 0.0
        self._match_animation_target = 0.0
        self._match_animation_gain_origin = 0.0
        self._match_animation_gain_target = 0.0
        self._match_animation_active = False

    def begin(self, controller: FootballGameController) -> None:
        self.controller = controller
        self.state = controller.state
        self.last_error = None
        self.confirm_exit = False
        self._match_visual_state = None
        self._match_animation_active = False

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.confirm_exit = not self.confirm_exit
            return
        if (
            event.type == pygame.KEYDOWN
            and not self.confirm_exit
            and self._current_state().phase is FootballRunPhase.MATCH
            and pygame.K_1 <= event.key <= pygame.K_6
        ):
            choice_index = event.key - pygame.K_1
            if choice_index < len(self.buttons) - 1:
                self.buttons[choice_index].action()
                return
        super().handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        state = self._current_state()
        if state.phase is FootballRunPhase.MATCH:
            self._draw_match_screen(surface, state)
            if self.last_error is not None:
                self._draw_match_error(surface, self.last_error)
            if self.confirm_exit:
                self._draw_exit_confirmation(surface)
            return

        titles = {
            FootballRunPhase.COACH_DRAFT: ("Choose your coach", "RUN SETUP / IDENTITY"),
            FootballRunPhase.PLAYER_DRAFT: (
                "Build your roster",
                "DRAFT / POSITION ORDER",
            ),
            FootballRunPhase.PRE_MATCH_SHOP: (
                "Training room",
                "PRE-MATCH / SIX TRAINING POINTS",
            ),
            FootballRunPhase.READY_FOR_NEXT_GAME: (
                "Final whistle",
                "REGULAR SEASON / NEXT GAME READY",
            ),
            FootballRunPhase.FIRED: ("Run ended", "THREE LOSSES / FIRED"),
            FootballRunPhase.PLAYOFFS: ("Season milestone", "GAME 10 / PLAYOFFS"),
        }
        title, eyebrow = titles[state.phase]
        layout = self._header(surface, title, eyebrow, self.team_name)
        content = pygame.Rect(
            layout.content.left,
            layout.content.top + 34,
            layout.content.width,
            layout.content.height - 34,
        )
        if state.phase is FootballRunPhase.COACH_DRAFT:
            self._draw_coach_selection(surface, content, state)
        elif state.phase is FootballRunPhase.PLAYER_DRAFT:
            self._draw_player_draft(surface, content, state)
        elif state.phase is FootballRunPhase.PRE_MATCH_SHOP:
            self._draw_shop(surface, content, state.shop)
        else:
            self._draw_result(surface, content, state)

        exit_rect = pygame.Rect(
            layout.content.right - 118,
            layout.content.top,
            118,
            30,
        )
        self.buttons.append(
            Button("END RUN", self._request_exit, exit_rect, variant="quiet")
        )
        self._set_buttons(self.buttons)
        self._draw_buttons(surface)

        if self.last_error is not None:
            error_rect = pygame.Rect(
                layout.margin,
                layout.height - 49,
                layout.width - layout.margin * 2,
                18,
            )
            draw_text(
                surface,
                f"CHECK: {self.last_error}",
                error_rect.topleft,
                self._small_font,
                self.theme.danger,
            )
        if self.confirm_exit:
            self._draw_exit_confirmation(surface)

    def _draw_match_screen(
        self,
        surface: pygame.Surface,
        state: FootballGameControllerState,
    ) -> None:
        match = state.match
        if match is None:
            raise RuntimeError("The controller did not provide an active match state.")

        surface.fill(_MATCH_CANVAS)
        width, height = surface.get_size()
        margin = max(24, min(round(width * 0.035), 48))
        content_width = width - margin * 2
        team_accent = self.theme.primary_accent
        opponent_accent = _MATCH_OPPONENT

        scoreboard = pygame.Rect(margin, 24, content_width, 92)
        self._draw_match_scoreboard(surface, scoreboard, state, team_accent, opponent_accent)

        field = pygame.Rect(margin, scoreboard.bottom + 14, content_width, 286)
        self._draw_match_field(surface, field, state, team_accent, opponent_accent)

        history = pygame.Rect(margin, field.bottom + 12, content_width, 50)
        self._draw_match_history(surface, history, state)

        decision_rect = pygame.Rect(
            margin,
            history.bottom + 15,
            content_width,
            max(1, height - history.bottom - 42),
        )
        self._draw_match_decision(surface, decision_rect, state)

        pause_rect = pygame.Rect(scoreboard.right - 102, scoreboard.top + 13, 82, 32)
        self.buttons.append(
            Button("PAUSE", self._request_exit, pause_rect, variant="quiet")
        )
        self._set_buttons(self.buttons)
        for index, button in enumerate(self.buttons[:-1]):
            self._draw_match_call_button(
                surface,
                button,
                index + 1,
                focused=button.focused,
                hovered=self.hover_index == index,
                pressed=self.pressed_index == index,
            )
        self._draw_match_pause_button(
            surface,
            self.buttons[-1],
            focused=self.buttons[-1].focused,
            hovered=self.hover_index == len(self.buttons) - 1,
            pressed=self.pressed_index == len(self.buttons) - 1,
        )

    def _draw_match_scoreboard(
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

    def _draw_match_field(
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
        field = rect.inflate(-10, -10)
        pygame.draw.rect(surface, _MATCH_TURF, field)
        end_zone_width = max(42, round(field.width * 0.075))
        pygame.draw.rect(
            surface,
            team_accent,
            pygame.Rect(field.left, field.top, end_zone_width, field.height),
        )
        pygame.draw.rect(
            surface,
            opponent_accent,
            pygame.Rect(field.right - end_zone_width, field.top, end_zone_width, field.height),
        )

        left_end = pygame.Rect(field.left, field.top, end_zone_width, field.height)
        right_end = pygame.Rect(
            field.right - end_zone_width,
            field.top,
            end_zone_width,
            field.height,
        )
        for end_zone, name, color in (
            (left_end, match.team_a.team_name.upper(), _MATCH_INK),
            (right_end, match.team_b.team_name.upper(), _MATCH_INK),
        ):
            end_text = _fit_text(name, _ui_font(11, bold=True), end_zone.height - 18)
            label = _ui_font(11, bold=True).render(end_text, True, color)
            rotated = pygame.transform.rotate(label, 90)
            surface.blit(rotated, rotated.get_rect(center=end_zone.center))

        playing_left = field.left + end_zone_width
        playing_right = field.right - end_zone_width
        playing_width = playing_right - playing_left
        for stripe_index in range(10):
            stripe = pygame.Rect(
                playing_left + round(playing_width * stripe_index / 10),
                field.top,
                max(1, round(playing_width / 20)),
                field.height,
            )
            if stripe_index % 2:
                pygame.draw.rect(surface, _MATCH_TURF_ALT, stripe)

        line_color = (*_MATCH_TURF_LINE[:3], 155)
        for yard in range(0, 101, 5):
            x = playing_left + round(playing_width * yard / 100)
            is_major = yard % 10 == 0
            pygame.draw.line(
                surface,
                _MATCH_TURF_LINE if is_major else line_color,
                (x, field.top + 5),
                (x, field.bottom - 5),
                2 if is_major else 1,
            )
            if yard % 10 == 0 and yard not in (0, 100):
                number = yard if yard <= 50 else 100 - yard
                label = _ui_font(15, bold=True).render(str(number), True, _MATCH_CHALK)
                surface.blit(
                    label,
                    label.get_rect(center=(x, field.centery - 2)),
                )
            for hash_fraction in (0.32, 0.68):
                hash_y = field.top + round(field.height * hash_fraction)
                pygame.draw.line(
                    surface,
                    line_color,
                    (x, hash_y - 4),
                    (x, hash_y + 4),
                    1,
                )

        field_label = (
            f"OWN {match.offense_field_position:.0f}"
            if match.offense_field_position <= 50
            else f"OPP {100 - match.offense_field_position:.0f}"
        )
        down_suffix = {1: "ST", 2: "ND", 3: "RD", 4: "TH"}[match.down]
        situation = (
            f"{match.down}{down_suffix} & {match.yards_to_go:g}"
        )
        draw_text(
            surface,
            situation,
            (playing_left + 16, rect.top + 15),
            _ui_font(22, bold=True),
            _MATCH_CHALK,
        )
        draw_text(
            surface,
            f"BALL AT {field_label}",
            (playing_left + 16, rect.top + 46),
            self._small_font,
            _MATCH_MUTED,
        )
        scheme = (
            _SCHEME_LABELS[match.current_drive_defensive_scheme]
            if match.current_drive_defensive_scheme is not None
            else "NO DRIVE SCHEME"
        )
        possession_name = (
            match.team_a.team_name
            if match.possession is FootballTeamSide.TEAM_A
            else match.team_b.team_name
        )
        status_text = f"{possession_name.upper()} BALL   /   {scheme}"
        status_width = playing_width - 32
        status = self._small_font.render(
            _fit_text(status_text, self._small_font, status_width),
            True,
            _MATCH_MUTED,
        )
        surface.blit(
            status,
            status.get_rect(topright=(playing_right - 16, rect.top + 17)),
        )

        direction = 1 if match.possession is FootballTeamSide.TEAM_A else -1
        position, line_to_gain = self._animated_field_positions(state)
        ball_x = playing_left + round(playing_width * position / 100)
        target_x = playing_left + round(playing_width * line_to_gain / 100)
        if direction < 0:
            ball_x = playing_right - round(playing_width * position / 100)
            target_x = playing_right - round(playing_width * line_to_gain / 100)
        ball_color = team_accent if match.possession is FootballTeamSide.TEAM_A else opponent_accent
        pygame.draw.line(
            surface,
            _MATCH_BRASS,
            (target_x, field.top + 8),
            (target_x, field.bottom - 8),
            3,
        )
        pygame.draw.line(
            surface,
            ball_color,
            (ball_x, field.top + 8),
            (ball_x, field.bottom - 8),
            2,
        )
        ball_center = (ball_x, field.centery)
        ball_rect = pygame.Rect(0, 0, 28, 17)
        ball_rect.center = ball_center
        pygame.draw.ellipse(surface, _MATCH_CHALK, ball_rect)
        pygame.draw.line(
            surface,
            _MATCH_INK,
            (ball_x - 2, ball_rect.top + 3),
            (ball_x - 2, ball_rect.bottom - 3),
            2,
        )
        for seam_offset in (-5, 1):
            pygame.draw.line(
                surface,
                _MATCH_INK,
                (ball_x + seam_offset, field.centery - 3),
                (ball_x + seam_offset, field.centery + 3),
                1,
            )
        arrow_direction = direction
        arrow_y = field.bottom - 18
        arrow_tip = ball_x + arrow_direction * 24
        pygame.draw.line(
            surface,
            ball_color,
            (ball_x, arrow_y),
            (arrow_tip, arrow_y),
            2,
        )
        pygame.draw.polygon(
            surface,
            ball_color,
            (
                (arrow_tip, arrow_y),
                (arrow_tip - arrow_direction * 7, arrow_y - 5),
                (arrow_tip - arrow_direction * 7, arrow_y + 5),
            ),
        )

    def _animated_field_positions(
        self, state: FootballGameControllerState
    ) -> tuple[float, float]:
        match = state.match
        if match is None:
            raise RuntimeError("The controller did not provide an active match state.")
        previous = self._match_visual_state
        event_count = len(match.match_events)
        if previous is None:
            self._match_visual_state = match
            return (
                match.offense_field_position,
                min(100.0, match.offense_field_position + match.yards_to_go),
            )

        if len(previous.match_events) != event_count:
            self._match_animation_origin = previous.offense_field_position
            self._match_animation_target = match.offense_field_position
            self._match_animation_gain_origin = min(
                100.0,
                previous.offense_field_position + previous.yards_to_go,
            )
            self._match_animation_gain_target = min(
                100.0,
                match.offense_field_position + match.yards_to_go,
            )
            self._match_animation_started = pygame.time.get_ticks()
            self._match_animation_active = True
        self._match_visual_state = match

        if not self._match_animation_active:
            return (
                match.offense_field_position,
                min(100.0, match.offense_field_position + match.yards_to_go),
            )
        elapsed = pygame.time.get_ticks() - self._match_animation_started
        progress = min(1.0, max(0.0, elapsed / 360))
        eased = progress * progress * (3 - 2 * progress)
        if progress >= 1:
            self._match_animation_active = False
        return (
            self._match_animation_origin
            + (self._match_animation_target - self._match_animation_origin) * eased,
            self._match_animation_gain_origin
            + (self._match_animation_gain_target - self._match_animation_gain_origin)
            * eased,
        )

    def _draw_match_history(
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
            text = self._format_event(latest, match.team_a.team_name, match.team_b.team_name)
            previous = (
                self._format_event(
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

    def _draw_match_decision(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        decision = state.human_decision
        if decision is FootballHumanDecision.OFFENSIVE_PLAY:
            labels = tuple(_PLAY_LABELS.items())
            heading = "OFFENSE   /   CALL THE PLAY"
            actions = [
                (
                    label,
                    lambda action=action: self._submit_match_action(
                        lambda: self._require_controller().choose_offensive_play(action)
                    ),
                )
                for action, label in labels
            ]
        elif decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            labels = tuple(_SCHEME_LABELS.items())
            heading = "DEFENSE   /   SET THE DRIVE"
            actions = [
                (
                    label,
                    lambda action=action: self._submit_match_action(
                        lambda: self._require_controller().choose_defensive_scheme(action)
                    ),
                )
                for action, label in labels
            ]
        elif decision is FootballHumanDecision.FOURTH_DOWN:
            heading = "FOURTH DOWN   /   MAKE THE CALL"
            actions = [
                (
                    action.value.replace("_", " ").upper(),
                    lambda action=action: self._submit_match_action(
                        lambda: self._require_controller().choose_fourth_down(action)
                    ),
                )
                for action in FootballFourthDownAction
            ]
        else:
            heading = "LOCAL AI IS RESOLVING ITS DRIVE"
            actions = []

        draw_text(
            surface,
            heading,
            (rect.left + 2, rect.top),
            self._small_font,
            _MATCH_BRASS,
        )
        self._match_call_rect = pygame.Rect(
            rect.left,
            rect.top + 24,
            rect.width,
            max(1, rect.height - 25),
        )
        self.buttons = []
        if not actions:
            draw_text(
                surface,
                "The next snap is being set.",
                (rect.left + 2, rect.top + 34),
                self._small_font,
                _MATCH_MUTED,
            )
            return

        gap_x = 10
        gap_y = 8
        columns = min(3, len(actions))
        rows = (len(actions) + columns - 1) // columns
        button_width = (self._match_call_rect.width - gap_x * (columns - 1)) // columns
        button_height = (self._match_call_rect.height - gap_y * (rows - 1)) // rows
        for index, (label, callback) in enumerate(actions):
            row, column = divmod(index, columns)
            button_rect = pygame.Rect(
                self._match_call_rect.left + column * (button_width + gap_x),
                self._match_call_rect.top + row * (button_height + gap_y),
                button_width,
                button_height,
            )
            self.buttons.append(Button(label, callback, button_rect))

    def _draw_match_call_button(
        self,
        surface: pygame.Surface,
        button: Button,
        shortcut: int,
        *,
        focused: bool,
        hovered: bool,
        pressed: bool,
    ) -> None:
        rect = button.rect.move(0, 2) if pressed else button.rect
        fill = (
            pygame.Color("#2b382e")
            if focused
            else pygame.Color("#202b23")
            if hovered
            else _MATCH_PANEL
        )
        edge = _MATCH_FOCUS if focused else _MATCH_PANEL_EDGE
        points = (
            (rect.left + 7, rect.top),
            (rect.right, rect.top),
            (rect.right, rect.bottom - 7),
            (rect.right - 7, rect.bottom),
            (rect.left, rect.bottom),
            (rect.left, rect.top + 7),
        )
        pygame.draw.polygon(surface, fill, points)
        pygame.draw.lines(surface, edge, True, points, 2 if focused else 1)
        pygame.draw.rect(
            surface,
            _MATCH_BRASS if focused else _MATCH_PANEL_EDGE,
            pygame.Rect(rect.left + 12, rect.top + 11, 28, rect.height - 22),
        )
        shortcut_text = self._small_font.render(f"{shortcut:02d}", True, _MATCH_INK)
        surface.blit(
            shortcut_text,
            shortcut_text.get_rect(
                center=(rect.left + 26, rect.centery),
            ),
        )
        label = _fit_text(button.label, self._label_font, rect.width - 70)
        label_surface = self._label_font.render(label, True, _MATCH_CHALK)
        surface.blit(
            label_surface,
            label_surface.get_rect(
                midleft=(rect.left + 52, rect.centery),
            ),
        )
        if focused:
            pygame.draw.line(
                surface,
                _MATCH_BRASS,
                (rect.left + 52, rect.bottom - 7),
                (min(rect.right - 12, rect.left + 52 + label_surface.get_width()), rect.bottom - 7),
                2,
            )

    def _draw_match_pause_button(
        self,
        surface: pygame.Surface,
        button: Button,
        *,
        focused: bool,
        hovered: bool,
        pressed: bool,
    ) -> None:
        rect = button.rect.move(0, 2) if pressed else button.rect
        fill = _MATCH_PANEL if not hovered else pygame.Color("#2b382e")
        pygame.draw.rect(surface, fill, rect)
        pygame.draw.rect(
            surface,
            _MATCH_FOCUS if focused else _MATCH_PANEL_EDGE,
            rect,
            width=2 if focused else 1,
        )
        label = self._small_font.render("PAUSE  [ESC]", True, _MATCH_CHALK)
        surface.blit(label, label.get_rect(center=rect.center))

    def _submit_match_action(self, action: Callable[[], object]) -> None:
        self._submit(action)

    def _draw_match_error(self, surface: pygame.Surface, message: str) -> None:
        rect = pygame.Rect(24, surface.get_height() - 24, surface.get_width() - 48, 18)
        draw_text(
            surface,
            f"CALL FAILED: {message}",
            rect.topleft,
            self._small_font,
            self.theme.danger,
        )

    def _draw_coach_selection(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        coaches = state.team_builder.coach_offer
        draw_text(
            surface,
            "SELECT YOUR HEAD COACH",
            (content.left + 2, content.top),
            self._small_font,
            self.theme.secondary_accent,
        )
        draw_text(
            surface,
            "Identity only",
            (content.right - 110, content.top),
            self._small_font,
            self.theme.muted,
        )
        gap = 12
        card_top = content.top + 23
        card_height = content.bottom - card_top
        card_width = (content.width - gap * 2) // 3
        buttons: list[Button] = []
        for index, coach in enumerate(coaches):
            rect = pygame.Rect(
                content.left + index * (card_width + gap),
                card_top,
                card_width,
                card_height,
            )
            draw_panel(surface, rect, self.theme, fill=self.theme.panel)
            draw_text(
                surface,
                f"OPTION 0{index + 1}",
                (rect.left + 20, rect.top + 20),
                self._small_font,
                self.theme.secondary_accent,
            )
            draw_text(
                surface,
                coach.name,
                (rect.left + 20, rect.top + 73),
                self._title_font,
                self.theme.text,
            )
            pygame.draw.line(
                surface,
                self.theme.border_soft,
                (rect.left + 20, rect.top + 119),
                (rect.right - 20, rect.top + 119),
                1,
            )
            draw_text(
                surface,
                "HEAD COACH",
                (rect.left + 20, rect.top + 141),
                self._small_font,
                self.theme.muted,
            )
            button_rect = pygame.Rect(
                rect.left + 18,
                rect.bottom - 61,
                rect.width - 36,
                44,
            )
            buttons.append(
                Button(
                    f"CHOOSE {coach.name.upper()}",
                    lambda choice=index: self._submit(
                        lambda: self._require_controller().choose_coach(choice)
                    ),
                    button_rect,
                    variant="primary",
                )
            )
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _draw_player_draft(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        builder = state.team_builder
        required = builder.required_position
        completed = len(builder.selected_players)
        remaining = len(PLAYER_DRAFT_ORDER) - completed
        required_label = _POSITION_LABELS[required] if required is not None else "COMPLETE"
        draw_text(
            surface,
            f"NEXT PICK  /  {required_label}",
            (content.left + 2, content.top),
            self._label_font,
            self.theme.secondary_accent,
        )
        draw_text(
            surface,
            f"{remaining} PICKS LEFT",
            (content.right - 110, content.top + 2),
            self._small_font,
            self.theme.muted,
        )
        progress_top = content.top + 26
        gap = 6
        cell_width = (content.width - gap * 7) // 8
        for index, position in enumerate(PLAYER_DRAFT_ORDER):
            rect = pygame.Rect(
                content.left + index * (cell_width + gap),
                progress_top,
                cell_width,
                28,
            )
            is_done = position in builder.selected_players
            is_current = position is required
            draw_panel(
                surface,
                rect,
                self.theme,
                selected=is_current,
                fill=self.theme.panel_alt if is_done else self.theme.panel,
            )
            draw_text(
                surface,
                _POSITION_LABELS[position],
                (rect.left + 4, rect.top + 7),
                _ui_font(10, bold=True),
                self.theme.primary_accent if is_done else self.theme.text,
            )
            if is_done:
                pygame.draw.circle(
                    surface,
                    self.theme.primary_accent,
                    (rect.right - 9, rect.centery),
                    3,
                )

        offers = tuple(
            candidate
            for candidate in builder.current_offer
            if isinstance(candidate, FootballPlayerCandidate)
        )
        gap = 12
        cards_top = progress_top + 38
        card_width = (content.width - gap * 2) // 3
        card_height = content.bottom - cards_top
        buttons: list[Button] = []
        for index, candidate in enumerate(offers):
            rect = pygame.Rect(
                content.left + index * (card_width + gap),
                cards_top,
                card_width,
                card_height,
            )
            draw_panel(surface, rect, self.theme, fill=self.theme.panel)
            draw_text(
                surface,
                f"PROSPECT  0{index + 1}",
                (rect.left + 18, rect.top + 17),
                self._small_font,
                self.theme.secondary_accent,
            )
            draw_text(
                surface,
                _fit_text(candidate.name, self._title_font, rect.width - 36),
                (rect.left + 18, rect.top + 47),
                self._title_font,
                self.theme.text,
            )
            player = candidate.player
            pygame.draw.line(
                surface,
                self.theme.border_soft,
                (rect.left + 18, rect.top + 91),
                (rect.right - 18, rect.top + 91),
                1,
            )
            metrics = (
                ("POWER", f"{player.power:.1f}", None),
                ("VOLATILITY", f"{player.volatility:.2f}", player.volatility),
                ("STAMINA", f"{player.stamina:.2f}", player.stamina),
            )
            metric_top = rect.top + 108
            for stat_index, (label, value, ratio) in enumerate(metrics):
                y = metric_top + stat_index * 49
                draw_text(
                    surface,
                    label,
                    (rect.left + 18, y),
                    self._small_font,
                    self.theme.muted,
                )
                draw_text(
                    surface,
                    value,
                    (rect.right - 68, y - 3),
                    self._label_font,
                    self.theme.text,
                )
                if ratio is not None:
                    bar = pygame.Rect(rect.left + 18, y + 22, rect.width - 36, 3)
                    pygame.draw.rect(surface, self.theme.border_soft, bar, border_radius=2)
                    pygame.draw.rect(
                        surface,
                        self.theme.secondary_accent,
                        pygame.Rect(bar.left, bar.top, round(bar.width * ratio), bar.height),
                        border_radius=2,
                    )
            draw_wrapped_text(
                surface,
                candidate.description,
                pygame.Rect(
                    rect.left + 18,
                    rect.top + 264,
                    rect.width - 36,
                    max(24, card_height - 328),
                ),
                self._small_font,
                self.theme.muted,
                line_gap=2,
            )
            button_rect = pygame.Rect(
                rect.left + 16,
                rect.bottom - 54,
                rect.width - 32,
                38,
            )
            buttons.append(
                Button(
                    f"DRAFT {candidate.position.value}",
                    lambda choice=index, position=candidate.position: self._submit(
                        lambda: self._require_controller().choose_player(position, choice)
                    ),
                    button_rect,
                    variant="primary" if index == 0 else "quiet",
                )
            )
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _draw_shop(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        shop: FootballShopState | None,
    ) -> None:
        if shop is None:
            raise RuntimeError("The controller did not provide the active shop state.")
        draw_text(
            surface,
            "UPGRADE YOUR LINEUP",
            (content.left + 2, content.top + 2),
            self._label_font,
            self.theme.text,
        )
        points_label = f"{shop.remaining_budget} TRAINING POINTS"
        points_width = self._label_font.size(points_label)[0] + 24
        points_rect = pygame.Rect(
            content.right - points_width,
            content.top - 2,
            points_width,
            28,
        )
        pygame.draw.rect(surface, self.theme.panel_alt, points_rect, border_radius=7)
        draw_text(
            surface,
            points_label,
            (points_rect.left + 12, points_rect.top + 7),
            self._small_font,
            self.theme.secondary_accent,
        )
        gap = 12
        cards_top = content.top + 37
        card_width = (content.width - gap * 2) // 3
        card_height = content.bottom - cards_top - 47
        buttons: list[Button] = []
        for index, upgrade in enumerate(shop.offer):
            rect = pygame.Rect(
                content.left + index * (card_width + gap),
                cards_top,
                card_width,
                card_height,
            )
            purchased = upgrade in shop.purchased_upgrades
            affordable = upgrade.cost <= shop.remaining_budget
            draw_panel(
                surface,
                rect,
                self.theme,
                selected=purchased,
                fill=self.theme.panel_alt if purchased else self.theme.panel,
            )
            draw_text(
                surface,
                f"{upgrade.stat.value.upper()} TRAINING",
                (rect.left + 18, rect.top + 18),
                self._title_font,
                self.theme.text,
            )
            draw_text(
                surface,
                "TARGET",
                (rect.left + 18, rect.top + 64),
                self._small_font,
                self.theme.muted,
            )
            draw_text(
                surface,
                _POSITION_LABELS[upgrade.position],
                (rect.left + 18, rect.top + 83),
                self._label_font,
                self.theme.text,
            )
            draw_text(
                surface,
                upgrade.stat.value.upper(),
                (rect.left + 18, rect.top + 127),
                self._small_font,
                self.theme.muted,
            )
            draw_text(
                surface,
                f"+{upgrade.amount:g}",
                (rect.left + 18, rect.top + 148),
                self._display_font,
                self.theme.secondary_accent,
            )
            reason = (
                "PURCHASED"
                if purchased
                else "AVAILABLE"
                if affordable
                else "NEED MORE POINTS"
            )
            draw_text(
                surface,
                f"COST  {upgrade.cost} TP",
                (rect.left + 18, rect.bottom - 90),
                self._label_font,
                self.theme.text,
            )
            draw_text(
                surface,
                reason,
                (rect.left + 18, rect.bottom - 68),
                self._small_font,
                self.theme.secondary_accent if affordable else self.theme.muted,
            )
            button_rect = pygame.Rect(
                rect.left + 14,
                rect.bottom - 48,
                rect.width - 28,
                34,
            )
            buttons.append(
                Button(
                    "PURCHASED" if purchased else "BUY UPGRADE",
                    lambda choice=index: self._submit(
                        lambda: self._require_controller().buy_upgrade(choice)
                    ),
                    button_rect,
                    enabled=affordable and not purchased,
                    variant="primary",
                )
            )

        finish_rect = pygame.Rect(
            content.right - 244,
            content.bottom - 40,
            244,
            36,
        )
        buttons.append(
            Button(
                "FINISH SHOP / START MATCH",
                lambda: self._submit(self._require_controller().finish_shop),
                finish_rect,
                variant="primary",
            )
        )
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _draw_match(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        match = state.match
        if match is None:
            raise RuntimeError("The controller did not provide an active match state.")

        scoreboard = pygame.Rect(content.left, content.top, content.width, 84)
        draw_panel(surface, scoreboard, self.theme, fill=self.theme.panel)
        score_font = _ui_font(38, bold=True)
        team_width = (scoreboard.width - 180) // 2
        draw_text(
            surface,
            _fit_text(
                match.team_a.team_name.upper(),
                self._label_font,
                team_width - 12,
            ),
            (scoreboard.left + 20, scoreboard.top + 13),
            self._label_font,
            self.theme.text,
        )
        draw_text(
            surface,
            _fit_text(
                match.team_b.team_name.upper(),
                self._label_font,
                team_width - 12,
            ),
            (scoreboard.right - team_width + 4, scoreboard.top + 13),
            self._label_font,
            self.theme.text,
        )
        score_a = score_font.render(str(match.team_a_score), True, self.theme.text)
        score_b = score_font.render(str(match.team_b_score), True, self.theme.text)
        surface.blit(
            score_a,
            score_a.get_rect(midleft=(scoreboard.left + 20, scoreboard.centery + 12)),
        )
        surface.blit(
            score_b,
            score_b.get_rect(midright=(scoreboard.right - 20, scoreboard.centery + 12)),
        )
        center = scoreboard.centerx
        draw_text(
            surface,
            f"GAME {state.game_number:02d}",
            (center - 31, scoreboard.top + 17),
            self._small_font,
            self.theme.muted,
        )
        draw_text(
            surface,
            f"{state.wins}-{state.losses}",
            (center - 15, scoreboard.top + 48),
            self._label_font,
            self.theme.text,
        )
        pygame.draw.line(
            surface,
            self.theme.primary_accent,
            (scoreboard.left + 2, scoreboard.bottom - 3),
            (scoreboard.left + scoreboard.width // 2 - 30, scoreboard.bottom - 3),
            3,
        )
        pygame.draw.line(
            surface,
            self.theme.secondary_accent,
            (scoreboard.centerx + 30, scoreboard.bottom - 3),
            (scoreboard.right - 2, scoreboard.bottom - 3),
            3,
        )

        situation = pygame.Rect(content.left, scoreboard.bottom + 8, content.width, 116)
        draw_panel(surface, situation, self.theme, fill=self.theme.panel_alt)
        clock = f"{match.game_clock_seconds // 60:02d}:{match.game_clock_seconds % 60:02d}"
        possession_name = (
            match.team_a.team_name
            if match.possession is FootballTeamSide.TEAM_A
            else match.team_b.team_name
        )
        draw_text(
            surface,
            f"Q{match.period}",
            (situation.left + 16, situation.top + 12),
            self._label_font,
            self.theme.secondary_accent,
        )
        draw_text(
            surface,
            clock,
            (situation.left + 53, situation.top + 7),
            _ui_font(22, bold=True),
            self.theme.text,
        )
        draw_text(
            surface,
            _fit_text(
                f"BALL  /  {possession_name.upper()}",
                self._small_font,
                205,
            ),
            (situation.right - 221, situation.top + 15),
            self._small_font,
            (
                self.theme.primary_accent
                if match.possession is FootballTeamSide.TEAM_A
                else self.theme.text
            ),
        )

        field_position = match.offense_field_position
        field_label = (
            f"OWN {field_position:.0f}"
            if field_position <= 50
            else f"OPP {100 - field_position:.0f}"
        )
        down_suffix = {1: "ST", 2: "ND", 3: "RD", 4: "TH"}[match.down]
        draw_text(
            surface,
            f"{match.down}{down_suffix} & {match.yards_to_go:.1f}",
            (situation.left + 16, situation.top + 47),
            _ui_font(23, bold=True),
            self.theme.text,
        )
        draw_text(
            surface,
            field_label,
            (situation.left + 165, situation.top + 54),
            self._small_font,
            self.theme.secondary_accent,
        )
        scheme_name = (
            _SCHEME_LABELS[match.current_drive_defensive_scheme]
            if match.current_drive_defensive_scheme is not None
            else "NOT SET"
        )
        draw_text(
            surface,
            f"DRIVE SCHEME  /  {scheme_name}",
            (situation.right - 264, situation.top + 52),
            self._small_font,
            self.theme.muted,
        )

        field = pygame.Rect(
            situation.left + 16,
            situation.top + 88,
            situation.width - 32,
            12,
        )
        pygame.draw.rect(surface, self.theme.canvas, field, border_radius=5)
        for fraction in (0.1, 0.3, 0.5, 0.7, 0.9):
            x = field.left + round(field.width * fraction)
            pygame.draw.line(
                surface,
                self.theme.border,
                (x, field.top + 2),
                (x, field.bottom - 2),
                1,
            )
        line_to_gain = min(100.0, field_position + match.yards_to_go)
        gain_x = field.left + round(field.width * line_to_gain / 100)
        pygame.draw.line(
            surface,
            self.theme.secondary_accent,
            (gain_x, field.top - 2),
            (gain_x, field.bottom + 2),
            2,
        )
        ball_x = field.left + round(field.width * field_position / 100)
        pygame.draw.circle(surface, self.theme.text, (ball_x, field.centery), 5)

        history = pygame.Rect(
            content.left,
            situation.bottom + 8,
            content.width,
            61,
        )
        draw_panel(surface, history, self.theme, fill=self.theme.panel)
        draw_text(
            surface,
            "PLAY BY PLAY",
            (history.left + 14, history.top + 8),
            self._small_font,
            self.theme.secondary_accent,
        )
        recent_events = match.match_events[-2:]
        if recent_events:
            for index, event in enumerate(recent_events):
                draw_text(
                    surface,
                    self._format_event(
                        event,
                        match.team_a.team_name,
                        match.team_b.team_name,
                    ),
                    (history.left + 134, history.top + 8 + index * 22),
                    self._small_font,
                    self.theme.text,
                )
        else:
            draw_text(
                surface,
                "Opening drive",
                (history.left + 134, history.top + 9),
                self._small_font,
                self.theme.muted,
            )

        action_top = history.bottom + 8
        actions_rect = pygame.Rect(
            content.left,
            action_top,
            content.width,
            max(1, content.bottom - action_top),
        )
        self._draw_match_decision(surface, actions_rect, state)

    def _draw_legacy_match_decision(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        decision = state.human_decision
        if decision is FootballHumanDecision.OFFENSIVE_PLAY:
            labels = tuple(_PLAY_LABELS.items())
            heading = "OFFENSE  /  CALL THE PLAY"
            actions = [
                (label, lambda action=action: self._submit(
                    lambda: self._require_controller().choose_offensive_play(action)
                ))
                for action, label in labels
            ]
        elif decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            labels = tuple(_SCHEME_LABELS.items())
            heading = "DEFENSE  /  SET THE DRIVE SCHEME"
            actions = [
                (label, lambda action=action: self._submit(
                    lambda: self._require_controller().choose_defensive_scheme(action)
                ))
                for action, label in labels
            ]
        elif decision is FootballHumanDecision.FOURTH_DOWN:
            heading = "FOURTH DOWN  /  MAKE THE CALL"
            actions = [
                (action.value.replace("_", " ").upper(), lambda action=action: self._submit(
                    lambda: self._require_controller().choose_fourth_down(action)
                ))
                for action in FootballFourthDownAction
            ]
        else:
            heading = "LOCAL AI IS RESOLVING ITS DRIVE"
            actions = []

        draw_text(
            surface,
            heading,
            (rect.left + 2, rect.top + 1),
            self._small_font,
            self.theme.secondary_accent,
        )
        buttons: list[Button] = []
        if actions:
            gap = 10
            button_width = (rect.width - gap * 2) // 3
            button_height = min(44, max(34, (rect.height - 28) // 2))
            for index, (label, callback) in enumerate(actions):
                row, column = divmod(index, 3)
                button_rect = pygame.Rect(
                    rect.left + column * (button_width + gap),
                    rect.top + 22 + row * (button_height + 7),
                    button_width,
                    button_height,
                )
                buttons.append(
                    Button(
                        label,
                        callback,
                        button_rect,
                        variant="primary" if index == 0 else "quiet",
                    )
                )
        else:
            draw_text(
                surface,
                "No human action is currently required.",
                (rect.left + 2, rect.top + 25),
                self._small_font,
                self.theme.muted,
            )
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _draw_result(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
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
        draw_panel(surface, result_panel, self.theme, fill=self.theme.panel)
        outcome = self._display_font.render(
            "FINAL  /  WIN" if won else "FINAL  /  LOSS",
            True,
            self.theme.primary_accent if won else self.theme.danger,
        )
        surface.blit(
            outcome,
            outcome.get_rect(midtop=(result_panel.centerx, result_panel.top + 22)),
        )
        scoreline = (
            f"{match.team_a.team_name}  {result.team_a_score}"
            f"     -     {result.team_b_score}  {match.team_b.team_name}"
        )
        scoreline_surface = self._title_font.render(
            _fit_text(scoreline, self._title_font, result_panel.width - 56),
            True,
            self.theme.text,
        )
        surface.blit(
            scoreline_surface,
            scoreline_surface.get_rect(
                midtop=(result_panel.centerx, result_panel.top + 87)
            ),
        )
        pygame.draw.line(
            surface,
            self.theme.border_soft,
            (result_panel.left + 28, result_panel.top + 132),
            (result_panel.right - 28, result_panel.top + 132),
            1,
        )
        draw_text(
            surface,
            f"GAME {state.game_number}  |  RECORD {state.wins}-{state.losses}",
            (
                result_panel.centerx
                - self._label_font.size(
                    f"GAME {state.game_number}  |  RECORD {state.wins}-{state.losses}"
                )[0]
                // 2,
                result_panel.top + 154,
            ),
            self._label_font,
            self.theme.secondary_accent,
        )

        if state.phase is FootballRunPhase.READY_FOR_NEXT_GAME:
            stage = "REGULAR SEASON"
            explanation = "Next up: regular-season game."
            primary_label = "NEXT REGULAR-SEASON GAME"
            primary_action = self._start_next_game
        elif state.phase is FootballRunPhase.FIRED:
            stage = "RUN OVER  /  THREE LOSSES"
            explanation = "Your season is over."
            primary_label = "RETURN TO MAIN MENU"
            primary_action = self._return_to_menu
        else:
            stage = "GAME 10 COMPLETE"
            explanation = "Playoffs reached. No playoff games are available yet."
            primary_label = "RETURN TO MAIN MENU"
            primary_action = self._return_to_menu
        draw_text(
            surface,
            stage,
            (
                result_panel.centerx - self._label_font.size(stage)[0] // 2,
                result_panel.top + 198,
            ),
            self._label_font,
            self.theme.text,
        )
        explanation_surface = self._small_font.render(
            _fit_text(explanation, self._small_font, result_panel.width - 60),
            True,
            self.theme.muted,
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
        buttons = [
            Button(primary_label, primary_action, primary_rect, variant="primary")
        ]
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _format_event(
        self, event: FootballMatchEvent, team_a_name: str, team_b_name: str
    ) -> str:
        if isinstance(event.action, DefensiveSchemeAction):
            defense = team_a_name if event.possession is FootballTeamSide.TEAM_B else team_b_name
            description = f"{defense} sets {_SCHEME_LABELS[event.action]}"
        elif isinstance(event.action, OffensivePlayAction):
            offense = team_a_name if event.possession is FootballTeamSide.TEAM_A else team_b_name
            result = event.play_result
            if result is None:
                description = f"{offense}: {_PLAY_LABELS[event.action]}"
            elif result.turnover:
                description = f"{offense}: {_PLAY_LABELS[event.action]} - turnover"
            elif result.incomplete:
                description = f"{offense}: {_PLAY_LABELS[event.action]} - incomplete"
            else:
                description = (
                    f"{offense}: {_PLAY_LABELS[event.action]} - "
                    f"{result.yards_gained:+.1f} yd"
                )
        else:
            offense = team_a_name if event.possession is FootballTeamSide.TEAM_A else team_b_name
            description = f"{offense}: {event.action.value.replace('_', ' ').upper()}"
        return _fit_text(description, self._small_font, 950)

    def _draw_exit_confirmation(self, surface: pygame.Surface) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        surface.blit(overlay, (0, 0))
        rect = Layout.from_surface(surface).centered_panel(0.52, 0.30)
        draw_panel(surface, rect, self.theme, fill=self.theme.panel_alt)
        draw_text(
            surface,
            "End this run?",
            (rect.left + 28, rect.top + 24),
            self._title_font,
            self.theme.text,
        )
        draw_wrapped_text(
            surface,
            "Your current draft, upgrades, and season progress will be discarded.",
            pygame.Rect(rect.left + 28, rect.top + 70, rect.width - 56, 48),
            self._body_font,
            self.theme.muted,
        )
        button_width = (rect.width - 76) // 2
        button_y = rect.bottom - 62
        buttons = [
            Button(
                "DISCARD RUN",
                self._return_to_menu,
                pygame.Rect(rect.left + 28, button_y, button_width, 42),
                variant="primary",
            ),
            Button(
                "KEEP PLAYING",
                self._keep_playing,
                pygame.Rect(rect.left + 48 + button_width, button_y, button_width, 42),
            ),
        ]
        self._set_buttons(buttons)
        self._draw_buttons(surface)

    def _submit(self, action: Callable[[], object]) -> None:
        self.last_error = None
        try:
            action()
        except ValueError as error:
            self.last_error = str(error)
        finally:
            self.state = self._require_controller().state

    def _start_next_game(self) -> None:
        self._submit(self._require_controller().start_next_game)

    def _request_exit(self) -> None:
        self.confirm_exit = True

    def _keep_playing(self) -> None:
        self.confirm_exit = False

    def _return_to_menu(self) -> None:
        self.confirm_exit = False
        self.navigate("main_menu")

    def _current_state(self) -> FootballGameControllerState:
        if self.state is None:
            raise RuntimeError("A football run has not been started.")
        return self.state

    def _require_controller(self) -> FootballGameController:
        if self.controller is None:
            raise RuntimeError("A football run has not been started.")
        return self.controller


def _fit_text(text: str, font: pygame.font.Font, width: int) -> str:
    if font.size(text)[0] <= width:
        return text
    shortened = text
    while shortened and font.size(f"{shortened}...")[0] > width:
        shortened = shortened[:-1]
    return f"{shortened}..."
