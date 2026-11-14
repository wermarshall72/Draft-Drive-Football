from collections.abc import Callable
from decimal import Decimal

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
from src.engine.football_coaches import (
    FootballCoachProfile,
    FootballCoachSide,
)
from src.engine.football_player_catalog import (
    MAX_COMBINED_PLAYER_MODIFIER,
    PARTNERSHIP_BONUS,
    player_type_for_id,
)
from src.engine.football_controller import (
    FootballGameController,
    FootballGameControllerState,
    FootballHumanDecision,
    FootballRunPhase,
)
from src.engine.football_shop import (
    FootballShopRarity,
    FootballShopSection,
    FootballShopSlotState,
    FootballShopState,
)
from src.engine.football_team_builder import (
    PLAYER_DRAFT_ORDER,
    FootballPlayerCandidate,
)
from src.ui.coach_art import draw_playbook_mark, draw_recruiting_table
from src.ui.coach_fonts import coach_font, staff_font
from src.ui.layout import Layout
from src.ui.player_art import draw_draft_player
from src.ui.screens import Navigate, Quit, Screen, _ui_font
from src.ui.theme import Theme, readable_ink
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
_COACH_PAPER = pygame.Color("#e8d9b8")
_COACH_INK = pygame.Color("#252b25")
_COACH_MUTED = pygame.Color("#5f6254")
_COACH_GREEN = pygame.Color("#34574a")
_COACH_RUST = pygame.Color("#884b39")
_STAFF_PAPER = pygame.Color("#a1a8a3")
_STAFF_INK = pygame.Color("#182620")
_STAFF_MUTED = pygame.Color("#303c35")
_COACH_GOLD = pygame.Color("#f1ce7b")
_COACH_CHALK = pygame.Color("#f5ead1")
_DRAFT_PURPLE = pygame.Color("#a600e8")
_DRAFT_PURPLE_PRESSED = pygame.Color("#7800b5")
_STAFF_CARD = pygame.Color("#242d30")
_STAFF_PERK = pygame.Color("#354044")
_STAFF_POSITIVE = pygame.Color("#9fe4ad")
_STAFF_NEGATIVE = pygame.Color("#ff9d98")
_RARITY_COLORS = {
    FootballShopRarity.COMMON: pygame.Color("#a8b2a1"),
    FootballShopRarity.UNCOMMON: pygame.Color("#68c58a"),
    FootballShopRarity.RARE: pygame.Color("#df786d"),
    FootballShopRarity.VERY_RARE: pygame.Color("#c18be8"),
}


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
        self._coach_keyboard_inspection = False
        self._coach_hover_index: int | None = None
        self._coach_popup_pressed = False
        self._draft_keyboard_inspection = False
        self._draft_hover_index: int | None = None
        self._draft_card_rects: list[pygame.Rect] = []
        self._draft_inspection_region: pygame.Rect | None = None
        self._draft_detail_rect: pygame.Rect | None = None
        self._coach_title_font = coach_font(40, handwritten=True)
        self._coach_name_font = coach_font(23, bold=True)
        self._coach_detail_font = coach_font(15)
        self._coach_stat_font = coach_font(15, bold=True)
        self._coach_small_font = coach_font(14, bold=True)
        self._coach_main_font = coach_font(17, bold=True)
        self._coach_body_font = coach_font(16)
        self._coach_button_font = coach_font(16, bold=True)
        self._coach_section_font = coach_font(23, bold=True)
        self._staff_name_font = staff_font(25, semibold=True)
        self._staff_label_font = staff_font(15)
        self._staff_body_font = staff_font(16)
        self._staff_detail_font = staff_font(16)
        self._staff_stat_font = staff_font(16, semibold=True)
        self._staff_small_font = staff_font(14, semibold=True)
        self._staff_main_font = staff_font(18, semibold=True)
        self._staff_button_font = staff_font(17, semibold=True)
        self._staff_dialog_title_font = staff_font(27, semibold=True)
        self._draft_title_font = staff_font(36, semibold=True)
        self._draft_name_font = staff_font(25, semibold=True)
        self._draft_stat_font = staff_font(21, semibold=True)
        self._draft_label_font = staff_font(14, semibold=True)
        self._draft_detail_font = staff_font(15)
        self._draft_small_font = staff_font(13)
        self._draft_button_font = staff_font(17, semibold=True)
        self._coach_focus_changed_at = 0

    def begin(self, controller: FootballGameController) -> None:
        self.controller = controller
        self.state = controller.state
        self.last_error = None
        self.confirm_exit = False
        self._match_visual_state = None
        self._match_animation_active = False
        self._coach_keyboard_inspection = False
        self._coach_hover_index = None
        self._coach_popup_pressed = False
        self._draft_keyboard_inspection = False
        self._draft_hover_index = None
        self._draft_card_rects = []
        self._draft_inspection_region = None
        self._draft_detail_rect = None
        self._coach_focus_changed_at = pygame.time.get_ticks()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._current_state().phase is FootballRunPhase.COACH_DRAFT and not self.confirm_exit:
            if event.type == pygame.KEYDOWN:
                self._coach_keyboard_inspection = True
                self._coach_hover_index = None
            elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                if (
                    self._coach_keyboard_inspection
                    and self.focus_index < len(self.buttons)
                    and self.buttons[self.focus_index].variant == "coach-inspect"
                    and self._coach_popup_rect(self.focus_index).collidepoint(event.pos)
                ):
                    self._coach_hover_index = self.focus_index
                self._coach_keyboard_inspection = False
                if (
                    self._coach_hover_index is not None
                    and self._coach_popup_rect(self._coach_hover_index).collidepoint(event.pos)
                ):
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self._coach_popup_pressed = True
                    return
                self._coach_hover_index = next(
                    (index for index, button in enumerate(self.buttons)
                     if button.variant == "coach-inspect" and button.rect.collidepoint(event.pos)),
                    None,
                )
                if self._coach_hover_index is not None:
                    self.hover_index = self._coach_hover_index
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self._coach_popup_pressed = True
                    return
            elif event.type == pygame.WINDOWLEAVE:
                self.hover_index = None
                self._coach_hover_index = None
                self._coach_keyboard_inspection = False
            elif event.type == pygame.MOUSEBUTTONUP and self._coach_popup_pressed:
                self._coach_popup_pressed = False
                return
        if self._current_state().phase is FootballRunPhase.PLAYER_DRAFT and not self.confirm_exit:
            if event.type == pygame.KEYDOWN:
                self._draft_keyboard_inspection = True
                self._draft_hover_index = None
            elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                self._draft_keyboard_inspection = False
                hovered_index = next(
                    (index for index, rect in enumerate(self._draft_card_rects)
                     if rect.collidepoint(event.pos)),
                    None,
                )
                if hovered_index is not None:
                    self._draft_hover_index = hovered_index
                elif (
                    self._draft_inspection_region is None
                    or not self._draft_inspection_region.collidepoint(event.pos)
                ):
                    self._draft_hover_index = None
            elif event.type == pygame.WINDOWLEAVE:
                self.hover_index = None
                self._draft_hover_index = None
                self._draft_keyboard_inspection = False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.confirm_exit = not self.confirm_exit
            self._coach_hover_index = None
            self._coach_popup_pressed = False
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
        previous_focus = self.focus_index
        super().handle_event(event)
        if (
            self._current_state().phase is FootballRunPhase.PLAYER_DRAFT
            and not self.confirm_exit
            and event.type == pygame.MOUSEMOTION
            and self.focus_index != previous_focus
        ):
            self._focus(previous_focus)
        if (
            self._current_state().phase is FootballRunPhase.COACH_DRAFT
            and self.focus_index != previous_focus
        ):
            self._coach_focus_changed_at = pygame.time.get_ticks()

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
            FootballRunPhase.COACH_DRAFT: ("Choose your staff", "RUN SETUP / COACHES"),
            FootballRunPhase.PLAYER_DRAFT: (
                "Build your roster",
                "DRAFT / POSITION ORDER",
            ),
            FootballRunPhase.PRE_MATCH_SHOP: (
                "Coaching shop",
                (
                    f"GAME {state.game_number:02d} / "
                    f"SHOP DAY {state.shop.day:02d}"
                    if state.shop is not None
                    else f"GAME {state.game_number:02d} / PRE-GAME SHOP"
                ),
            ),
            FootballRunPhase.READY_FOR_NEXT_GAME: (
                "Final whistle",
                "REGULAR SEASON / NEXT GAME READY",
            ),
            FootballRunPhase.FIRED: ("Run ended", "THREE LOSSES / FIRED"),
            FootballRunPhase.PLAYOFFS: ("Season milestone", "GAME 10 / PLAYOFFS"),
        }
        title, eyebrow = titles[state.phase]
        if state.phase in (FootballRunPhase.COACH_DRAFT, FootballRunPhase.PLAYER_DRAFT):
            layout = Layout.from_surface(surface)
            if state.phase is FootballRunPhase.COACH_DRAFT:
                self._draw_coach_backdrop(surface)
                content = pygame.Rect(38, 122, 1204, 558)
            else:
                self._draw_draft_backdrop(surface)
                content = pygame.Rect(38, 91, 1204, 599)
        else:
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

        exit_rect = (
            pygame.Rect(1097, 37, 145, 32)
            if state.phase is FootballRunPhase.COACH_DRAFT
            else pygame.Rect(1097, 10, 145, 32)
            if state.phase is FootballRunPhase.PLAYER_DRAFT
            else pygame.Rect(layout.content.right - 118, layout.content.top, 118, 30)
        )
        self.buttons.append(
            Button("END RUN", self._request_exit, exit_rect, variant="quiet")
        )
        self._set_buttons(self.buttons)
        self._draw_buttons(surface)
        if state.phase is FootballRunPhase.COACH_DRAFT and not self.confirm_exit:
            inspected_index = (
                self.focus_index if self._coach_keyboard_inspection
                else self._coach_hover_index
            )
            if (
                inspected_index is not None
                and inspected_index < len(self.buttons)
                and self.buttons[inspected_index].variant == "coach-inspect"
            ):
                pair = state.team_builder.coach_offer[inspected_index // 3]
                coach = pair.offense if inspected_index % 3 == 1 else pair.defense
                self._draw_coach_details(
                    surface, self._coach_popup_rect(inspected_index), coach,
                    staff_index=inspected_index // 3,
                )

        if self.last_error is not None:
            error_rect = pygame.Rect(
                layout.margin,
                layout.height - 23
                if state.phase is FootballRunPhase.PLAYER_DRAFT
                else layout.height - 49,
                layout.width - layout.margin * 2,
                18,
            )
            draw_text(
                surface,
                f"CHECK: {self.last_error}",
                error_rect.topleft,
                self._staff_small_font
                if state.phase is FootballRunPhase.COACH_DRAFT
                else self._draft_label_font
                if state.phase is FootballRunPhase.PLAYER_DRAFT
                else self._small_font,
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

    def _draw_coach_backdrop(self, surface: pygame.Surface) -> None:
        draw_recruiting_table(surface)
        draw_text(surface, "Recruiting  /  Staff", (40, 12), self._staff_label_font, _COACH_CHALK)
        draw_text(surface, "Build your staff", (38, 29), self._coach_title_font, _COACH_CHALK)
        draw_text(
            surface, "Hover or tab to scout a coach.", (42, 101),
            self._staff_body_font, _COACH_CHALK,
        )
        team = _fit_text(self.team_name.upper(), self._staff_small_font, 250)
        draw_text(surface, team, (820, 46), self._staff_small_font, _COACH_CHALK)

    def _draw_coach_selection(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        coach_pairs = state.team_builder.coach_offer
        gap = 16
        card_top = content.top + 12
        card_height = 546
        card_width = (content.width - gap * 2) // 3
        buttons: list[Button] = []
        for index, pair in enumerate(coach_pairs):
            rect = pygame.Rect(
                content.left + index * (card_width + gap),
                card_top + (4 if index != 1 else 0),
                card_width,
                card_height - (4 if index != 1 else 0),
            )
            focused = self.focus_index // 3 == index and self.focus_index < 9
            pygame.draw.rect(surface, "#171b17", rect.move(5, 7), border_radius=14)
            pygame.draw.rect(surface, "#7d8580", rect.move(2, 3), border_radius=14)
            pygame.draw.rect(surface, _STAFF_PAPER, rect, border_radius=14)
            pygame.draw.rect(surface, "#151a18" if focused else "#68736c", rect,
                             4 if focused else 1, border_radius=14)
            if focused:
                pygame.draw.rect(surface, self.theme.primary, rect.inflate(-4, -4), 2,
                                 border_radius=12)
                progress = min(1.0, max(0.0, (
                    pygame.time.get_ticks() - self._coach_focus_changed_at
                ) / 140))
                pygame.draw.line(
                    surface, self.theme.primary, (rect.left + 18, rect.top + 3),
                    (rect.left + 18 + round((rect.width - 36) * progress), rect.top + 3), 2,
                )
            pygame.draw.rect(surface, "#6b746c", (rect.left + 18, rect.top - 5, 54, 10),
                             border_radius=4)
            pygame.draw.circle(surface, "#5d5948", (rect.left + 45, rect.top), 3)
            draw_text(
                surface, f"Staff 0{index + 1}", (rect.left + 18, rect.top + 12),
                self._staff_main_font, _STAFF_INK,
            )
            draw_text(surface, "Position modifiers", (rect.right - 132, rect.top + 15),
                      self._staff_label_font, _STAFF_MUTED)
            draw_text(surface, "Locked for the run", (rect.left + 18, rect.bottom - 82),
                      self._staff_label_font, _STAFF_MUTED)
            button_rect = pygame.Rect(
                rect.left + 17, rect.bottom - 55, rect.width - 34, 40,
            )
            buttons.append(
                Button(
                    f"CHOOSE STAFF 0{index + 1}",
                    lambda choice=index: self._submit(
                        lambda: self._require_controller().choose_coach(choice)
                    ),
                    button_rect,
                    variant="coach-select",
                )
            )
            for side_index, coach in enumerate((pair.offense, pair.defense)):
                row = pygame.Rect(
                    rect.left + 12, rect.top + 47 + side_index * 211,
                    rect.width - 24, 198,
                )
                button_index = index * 3 + side_index + 1
                if self._coach_hover_index == button_index and not self._coach_keyboard_inspection:
                    pygame.draw.rect(surface, readable_ink(self.theme.secondary), row, 5,
                                     border_radius=10)
                    pygame.draw.rect(surface, self.theme.secondary, row, 2, border_radius=10)
                mark = pygame.Rect(row.left - 4, row.top + 44, 64, 64)
                draw_playbook_mark(surface, mark, offense=side_index == 0,
                                   color=self._coach_mark_color(index, buttons[index * 3]))
                text_x = row.left + 100
                draw_text(
                    surface, coach.side.value.title(), (text_x, row.top + 24),
                    self._staff_label_font, _STAFF_INK,
                )
                draw_text(
                    surface, coach.name, (text_x, row.top + 45),
                    self._staff_name_font, _STAFF_INK,
                )
                if self._coach_keyboard_inspection and self.focus_index == button_index:
                    pygame.draw.line(
                        surface, _STAFF_INK, (text_x, row.top + 77),
                        (text_x + self._staff_name_font.size(coach.name)[0], row.top + 77), 2,
                    )
                    draw_text(surface, "SCOUTING", (text_x, row.top + 158),
                              self._staff_small_font, _STAFF_INK)
                for position_index, (position, modifier) in enumerate(
                    coach.position_modifiers.items()
                ):
                    x = text_x + (position_index % 2) * 120
                    y = row.top + 96 + (position_index // 2) * 25
                    draw_text(
                        surface,
                        f"{_coach_position_label(position)} {round(modifier * 100):+d}%",
                        (x, y), self._staff_stat_font,
                        _STAFF_MUTED if modifier == 0 else _STAFF_INK,
                    )
                buttons.append(
                    Button(
                        f"INSPECT {coach.side.value.upper()} {index + 1}",
                        lambda: None, row, variant="coach-inspect",
                    )
                )
        self._set_buttons(buttons)

    def _coach_popup_rect(self, index: int) -> pygame.Rect:
        row = self.buttons[index].rect
        return pygame.Rect(row.left + 54, self.buttons[index // 3 * 3 + 1].rect.top,
                           row.width - 54, 423)

    def _coach_button_active(self, index: int, button: Button) -> bool:
        return button.enabled and (
            self.focus_index == index or self.hover_index == index
            or (self.focus_index < 9 and self.focus_index // 3 == index // 3)
        )

    def _coach_mark_color(self, staff_index: int, button: Button) -> pygame.Color:
        return (
            self.theme.primary if self._coach_button_active(staff_index * 3, button)
            else self.theme.secondary
        )

    def _draw_coach_details(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        coach: FootballCoachProfile,
        *,
        staff_index: int,
    ) -> None:
        pygame.draw.rect(surface, "#111b17", rect.move(5, 7), border_radius=14)
        pygame.draw.rect(surface, _STAFF_CARD, rect, border_radius=14)
        keyboard_focus = (
            self._coach_keyboard_inspection
            and self.focus_index < len(self.buttons)
            and self.buttons[self.focus_index].variant == "coach-inspect"
        )
        pygame.draw.rect(surface, readable_ink(self.theme.secondary), rect, 5, border_radius=14)
        pygame.draw.rect(surface, self.theme.secondary, rect, 2, border_radius=14)
        if keyboard_focus:
            pygame.draw.rect(surface, "#ffffff", rect.inflate(-12, -12), 1, border_radius=9)
        mark = pygame.Rect(rect.left + 13, rect.top + 15, 58, 58)
        pygame.draw.rect(surface, "#a1a8a3", mark, border_radius=10)
        draw_playbook_mark(surface, mark.inflate(-5, -5),
                           offense=coach.side is FootballCoachSide.OFFENSE,
                           color=self._coach_mark_color(staff_index, self.buttons[staff_index * 3]))
        draw_text(
            surface, coach.side.value.title(), (rect.left + 84, rect.top + 17),
            self._staff_label_font, _COACH_CHALK,
        )
        draw_text(surface, coach.name, (rect.left + 84, rect.top + 37),
                  self._staff_main_font, _COACH_CHALK)
        if keyboard_focus:
            draw_text(surface, "Keyboard scouting", (rect.left + 84, rect.top + 61),
                      self._staff_label_font, _COACH_CHALK)
        left = rect.left + 16
        y = rect.top + 88
        draw_text(surface, "Position modifiers", (left, y), self._staff_main_font, _COACH_CHALK)
        for offset, (position, modifier) in enumerate(coach.position_modifiers.items()):
            draw_text(
                surface, f"{_coach_position_label(position)} {round(modifier * 100):+d}%",
                (left + (offset % 2) * 140, y + 21 + (offset // 2) * 23),
                self._staff_stat_font,
                _STAFF_POSITIVE if modifier > 0 else _STAFF_NEGATIVE if modifier < 0
                else _COACH_CHALK,
            )
        perk_rect = pygame.Rect(left, rect.top + 157, rect.width - 32, 135)
        pygame.draw.rect(surface, _STAFF_PERK, perk_rect, border_radius=8)
        draw_text(surface, "Perk", (left + 10, perk_rect.top + 6),
                  self._staff_main_font, _COACH_CHALK)
        draw_wrapped_text(
            surface, _coach_perk_summary(coach),
            pygame.Rect(left + 10, perk_rect.top + 25, perk_rect.width - 20, 105),
            self._staff_detail_font, _COACH_CHALK, line_gap=1,
        )
        action_y = rect.top + 298
        draw_text(
            surface,
            "Play modifier sum" if coach.side is FootballCoachSide.OFFENSE
            else "Scheme modifier sum",
            (left, action_y), self._staff_main_font, _COACH_CHALK,
        )
        font = self._staff_detail_font
        for offset, (action, percentage) in enumerate(coach.action_percentages.items()):
            x = left + (offset % 2) * 140
            draw_text(
                surface, f"{_coach_action_label(action.value)}  {percentage}%",
                (x, action_y + 22 + (offset // 2) * 22), font, _COACH_CHALK,
            )
        draw_text(
            surface, "100% + position modifiers; not team power",
            (left, rect.bottom - 24),
            self._staff_small_font, "#c1c6c4",
        )

    def _draw_buttons(self, surface: pygame.Surface) -> None:
        for index, button in enumerate(self.buttons):
            if button.variant == "coach-inspect":
                continue
            if button.variant not in ("coach-select", "draft-select"):
                button.draw(
                    surface,
                    self._staff_button_font
                    if self._current_state().phase is FootballRunPhase.COACH_DRAFT
                    else self._main_font,
                    self.theme,
                    hovered=self.hover_index == index, pressed=self.pressed_index == index,
                )
                continue
            if button.variant == "coach-select":
                active = self._coach_button_active(index, button)
                pressed = self.pressed_index == index and button.enabled
                rect = button.rect.move(0, 2) if pressed else button.rect
                fill = self.theme.primary if active else (
                    pygame.Color("#c9ceca") if button.enabled else pygame.Color("#8b928d")
                )
                pygame.draw.rect(surface, fill, rect, border_radius=8)
                pygame.draw.rect(surface, readable_ink(fill), rect, 1, border_radius=8)
                if button.focused:
                    pygame.draw.rect(surface, "#111416", rect.inflate(6, 6), 3, border_radius=11)
                    pygame.draw.rect(surface, "#ffffff", rect.inflate(4, 4), 1, border_radius=10)
                if pressed:
                    pygame.draw.line(surface, readable_ink(fill), (rect.left + 12, rect.top + 4),
                                     (rect.right - 12, rect.top + 4), 2)
                label = self._staff_button_font.render(
                    button.label.title(), True, readable_ink(fill),
                )
                surface.blit(label, label.get_rect(center=rect.center))
                continue
            if button.variant == "draft-select":
                pressed = self.pressed_index == index and button.enabled
                hovered = self.hover_index == index and button.enabled
                rect = button.rect.move(0, 2) if pressed else button.rect
                fill = (
                    _DRAFT_PURPLE_PRESSED
                    if pressed else _DRAFT_PURPLE
                ) if button.enabled else pygame.Color("#b9beb9")
                pygame.draw.rect(surface, fill, rect, border_radius=8)
                pygame.draw.rect(
                    surface,
                    readable_ink(fill),
                    rect,
                    1,
                    border_radius=8,
                )
                if hovered:
                    pygame.draw.rect(
                        surface,
                        pygame.Color("#f5ead1"),
                        rect.inflate(-3, -3),
                        2,
                        border_radius=6,
                    )
                if button.focused:
                    pygame.draw.rect(surface, "#111416", rect.inflate(7, 7), 3,
                                     border_radius=11)
                    pygame.draw.rect(surface, "#ffffff", rect.inflate(3, 3), 1,
                                     border_radius=9)
                if pressed:
                    pygame.draw.line(
                        surface, readable_ink(fill),
                        (rect.left + 12, rect.top + 4),
                        (rect.right - 12, rect.top + 4), 2,
                    )
                position = button.label.removeprefix("DRAFT ").strip()
                label = self._draft_button_font.render(
                    f"Draft {position}", True, readable_ink(fill)
                )
                surface.blit(label, label.get_rect(center=rect.center))
                continue
            active = button.enabled and (
                button.focused or self.hover_index == index
            )
            rect = button.rect.move(0, 2) if self.pressed_index == index else button.rect
            green = _COACH_GREEN
            ink = _COACH_INK
            muted = _COACH_MUTED
            fill = green if active else (
                "#f3e5c7" if button.enabled else "#c5b794"
            )
            border = ink if active else (green if button.enabled else "#777f78")
            radius = 0
            pygame.draw.rect(surface, fill, rect, border_radius=radius)
            pygame.draw.rect(surface, border, rect, 1, border_radius=radius)
            if button.focused:
                pygame.draw.rect(surface, _COACH_GOLD, rect.inflate(4, 4), 2,
                                 border_radius=radius + 2 if radius else 0)
            label = self._coach_button_font.render(
                button.label, True,
                _COACH_CHALK if active else (green if button.enabled else muted),
            )
            surface.blit(label, label.get_rect(center=rect.center))

    def _draw_player_draft(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> None:
        builder = state.team_builder
        completed = len(builder.selected_players)
        required = builder.required_position
        current_label = (
            _draft_position_label(required) if required is not None else "Complete"
        )
        draw_text(
            surface,
            f"Pick {completed + 1} of {len(PLAYER_DRAFT_ORDER)}  ·  {current_label}",
            (content.left + 2, content.top),
            self._draft_label_font,
            _COACH_CHALK,
        )
        remaining_label = f"{len(PLAYER_DRAFT_ORDER) - completed} picks remaining"
        draw_text(
            surface,
            remaining_label,
            (content.right - self._draft_small_font.size(remaining_label)[0],
             content.top + 2),
            self._draft_small_font,
            _COACH_CHALK,
        )

        gap = 5
        cell_width = (
            content.width - gap * (len(PLAYER_DRAFT_ORDER) - 1)
        ) // len(PLAYER_DRAFT_ORDER)
        progress_top = content.top + 22
        progress_height = 58
        for index, position in enumerate(PLAYER_DRAFT_ORDER):
            rect = pygame.Rect(
                content.left + index * (cell_width + gap),
                progress_top,
                cell_width,
                progress_height,
            )
            selected = builder.selected_players.get(position)
            current = position is builder.required_position
            fill = _STAFF_PAPER if selected else (
                pygame.Color("#253932") if current else pygame.Color("#202a27")
            )
            pygame.draw.rect(surface, fill, rect, border_radius=6)
            pygame.draw.rect(
                surface,
                _DRAFT_PURPLE if current else pygame.Color("#64706a"),
                rect,
                2 if current else 1,
                border_radius=6,
            )
            text_color = _STAFF_INK if selected else _COACH_CHALK
            status = "Drafted" if selected else ("Current pick" if current else "Up next")
            draw_text(
                surface,
                _draft_position_label(position),
                (rect.left + 7, rect.top + 4),
                self._draft_label_font,
                text_color,
            )
            draw_text(
                surface,
                status,
                (rect.left + 7, rect.top + 21),
                self._draft_small_font,
                _STAFF_INK if selected else (
                    _DRAFT_PURPLE if current else pygame.Color("#c0c6c2")
                ),
            )
            if selected:
                draw_wrapped_text(
                    surface,
                    selected.name,
                    pygame.Rect(rect.left + 7, rect.top + 37, rect.width - 14, 18),
                    self._draft_small_font,
                    _STAFF_INK,
                    line_gap=0,
                )

        offers = tuple(candidate for candidate in builder.current_offer
                       if isinstance(candidate, FootballPlayerCandidate))
        gap = 16
        card_top = progress_top + progress_height + 10
        card_width = (content.width - gap * 2) // 3
        details_height = 174
        detail_top = content.bottom - details_height
        choice_bottom = detail_top - 9
        self._draft_card_rects = [
            pygame.Rect(
                content.left + index * (card_width + gap),
                card_top,
                card_width,
                choice_bottom - card_top,
            )
            for index in range(len(offers))
        ]
        details = pygame.Rect(
            content.left,
            detail_top,
            content.width,
            details_height,
        )
        self._draft_detail_rect = details
        self._draft_inspection_region = pygame.Rect(
            content.left,
            card_top,
            content.width,
            content.bottom - card_top,
        )
        inspected_index = self.focus_index if self._draft_keyboard_inspection else self._draft_hover_index
        inspected = (
            offers[inspected_index]
            if inspected_index is not None and 0 <= inspected_index < len(offers)
            else None
        )
        buttons: list[Button] = []
        for index, (candidate, rect) in enumerate(zip(offers, self._draft_card_rects)):
            title_width = rect.width - 80
            draw_text(
                surface,
                _fit_text(candidate.name, self._draft_name_font, title_width),
                (rect.left + 4, rect.top + 1),
                self._draft_name_font,
                _COACH_CHALK,
            )
            name_width = 62
            name_rect = pygame.Rect(
                rect.right - name_width - 4,
                rect.top + 2,
                name_width,
                27,
            )
            pygame.draw.rect(surface, "#202a27", name_rect, border_radius=7)
            pygame.draw.rect(
                surface, "#64706a", name_rect, 1, border_radius=7
            )
            draw_text(
                surface,
                _draft_position_label(candidate.position).upper(),
                (name_rect.left + 7, name_rect.top + 6),
                self._draft_small_font,
                _COACH_CHALK,
            )

            if inspected_index == index:
                pygame.draw.line(
                    surface,
                    _DRAFT_PURPLE,
                    (rect.left + 4, rect.top + 31),
                    (rect.left + min(title_width, 174), rect.top + 31),
                    3,
                )
            portrait = pygame.Rect(rect.centerx - 90, rect.top + 34, 180, 185)
            draw_draft_player(
                surface, portrait, self.theme.primary, self.theme.secondary, pose=index
            )

            strip = pygame.Rect(rect.left + 4, rect.bottom - 105, rect.width - 8, 62)
            pygame.draw.rect(surface, "#111b20", strip, border_radius=10)
            pygame.draw.rect(surface, "#718087", strip, 2, border_radius=10)
            player = candidate.player
            metrics = (
                ("Power", str(player.power)),
                ("Volatility", _draft_percentage(player.volatility)),
                ("Stamina", _draft_percentage(player.stamina)),
            )
            for stat_index, (label, value) in enumerate(metrics):
                stat_width = strip.width // 3
                x = strip.left + 12 + stat_index * stat_width
                draw_text(
                    surface,
                    label,
                    (x, strip.top + 7),
                    self._draft_small_font,
                    pygame.Color("#c0c9c8"),
                )
                draw_text(
                    surface,
                    value,
                    (x, strip.top + 27),
                    self._draft_stat_font,
                    _COACH_CHALK,
                )
                if stat_index < len(metrics) - 1:
                    pygame.draw.line(
                        surface,
                        pygame.Color("#4b5a5f"),
                        (strip.left + (stat_index + 1) * stat_width, strip.top + 10),
                        (strip.left + (stat_index + 1) * stat_width, strip.bottom - 10),
                        1,
                    )
            buttons.append(Button(
                f"DRAFT {candidate.position.value}",
                lambda choice=index, position=candidate.position: self._submit(
                    lambda: self._require_controller().choose_player(position, choice)),
                pygame.Rect(rect.left + 10, rect.bottom - 40, rect.width - 20, 34),
                variant="draft-select",
            ))
        self.buttons = buttons
        self._draw_draft_details(
            surface,
            details,
            inspected,
            keyboard_inspected=self._draft_keyboard_inspection,
        )

    def _draw_draft_backdrop(self, surface: pygame.Surface) -> None:
        draw_recruiting_table(surface)
        draw_text(
            surface,
            "Build your roster",
            (38, 8),
            self._draft_title_font,
            _COACH_CHALK,
        )

    def _draw_draft_details(
        self, surface: pygame.Surface, rect: pygame.Rect,
        candidate: FootballPlayerCandidate | None,
        *,
        keyboard_inspected: bool = False,
    ) -> None:
        pygame.draw.rect(surface, "#111b20", rect, border_radius=9)
        pygame.draw.rect(surface, "#718087", rect, 1, border_radius=9)
        draw_text(
            surface,
            "Generic player illustration · not a portrait",
            (rect.left + 18, rect.bottom - 17),
            self._draft_small_font,
            pygame.Color("#aeb8b7"),
        )
        if candidate is None:
            draw_text(
                surface,
                "Scout a prospect",
                (rect.left + 18, rect.top + 13),
                self._draft_label_font,
                _COACH_CHALK,
            )
            draw_text(
                surface,
                "Hover or use Tab / arrow keys to inspect. Enter or Space activates the focused pick.",
                (rect.left + 18, rect.top + 37),
                self._draft_small_font,
                _COACH_CHALK,
            )
            return
        if candidate.player.player_type_id is None:
            raise RuntimeError("Drafted players must have a catalog player type.")
        player_type = player_type_for_id(candidate.player.player_type_id)
        inspected_label = "Focused prospect" if keyboard_inspected else "Scouting"
        heading = f"{inspected_label} / {candidate.name}  ·  {_POSITION_LABELS[candidate.position]}"
        draw_text(
            surface,
            _fit_text(heading, self._draft_label_font, rect.width - 36),
            (rect.left + 18, rect.top + 9),
            self._draft_label_font,
            _COACH_CHALK,
        )
        stats = (
            f"Power {candidate.player.power}   ·   "
            f"Volatility {_draft_percentage(candidate.player.volatility)}   ·   "
            f"Stamina {_draft_percentage(candidate.player.stamina)}"
        )
        draw_text(
            surface,
            stats,
            (rect.left + 18, rect.top + 29),
            self._draft_small_font,
            pygame.Color("#c1c6c4"),
        )
        left = rect.left + 18
        right = rect.left + 365
        draw_text(
            surface,
            "Partnership",
            (left, rect.top + 52),
            self._draft_label_font,
            _COACH_GOLD,
        )
        perk_heading = (
            f"Perk · {player_type.perk.name} · planned and inactive"
            if player_type.perk else "Perk"
        )
        draw_text(
            surface,
            perk_heading,
            (right, rect.top + 52),
            self._draft_label_font,
            _COACH_GOLD,
        )
        if player_type.partner_position is None:
            partnership = "None. No partnership bonus."
        else:
            partnership = (
                f"{_POSITION_LABELS[player_type.partner_position]} partner: "
                f"+{PARTNERSHIP_BONUS:.0%} contribution when both players contribute "
                "to the same play. Combined coach and partnership contribution "
                f"tops out at {MAX_COMBINED_PLAYER_MODIFIER:.0%} of base."
            )
        draw_wrapped_text(
            surface,
            partnership,
            pygame.Rect(left, rect.top + 73, 330, rect.bottom - rect.top - 95),
            self._draft_detail_font,
            _COACH_CHALK,
            line_gap=0,
        )
        if player_type.perk is None:
            draw_text(
                surface,
                "None. This player type has no perk.",
                (right, rect.top + 73),
                self._draft_detail_font,
                _COACH_CHALK,
            )
        else:
            perk = player_type.perk
            perk_lines = (
                f"Trigger: {perk.trigger}",
                f"Effect: {perk.effect}",
                f"Duration: {perk.duration}  ·  Reset: {perk.reset}",
                f"Dependency: {perk.dependency}",
            )
            for index, line in enumerate(perk_lines):
                draw_text(
                    surface,
                    line,
                    (right, rect.top + 73 + index * 20),
                    self._draft_detail_font,
                    _COACH_CHALK,
                )

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
            "THREE SHOPS  /  ONE SHARED AP BUDGET",
            (content.left + 2, content.top + 2),
            self._label_font,
            self.theme.text,
        )
        points_label = f"{shop.remaining_ap} ACTION POINTS"
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
        draw_text(
            surface,
            "Unspent AP expires when you finish the shop.",
            (content.left + 2, content.top + 27),
            self._small_font,
            self.theme.muted,
        )
        gap = 10
        panel_top = content.top + 50
        panel_bottom = content.bottom - 56
        panel_width = (content.width - gap * 2) // 3
        panel_height = max(1, panel_bottom - panel_top)
        buttons: list[Button] = []
        for section_index, section_id in enumerate(FootballShopSection):
            section = shop.section(section_id)
            panel = pygame.Rect(
                content.left + section_index * (panel_width + gap),
                panel_top,
                panel_width,
                panel_height,
            )
            draw_panel(surface, panel, self.theme, fill=self.theme.panel)
            draw_text(
                surface,
                section.title,
                (panel.left + 12, panel.top + 11),
                self._label_font,
                self.theme.text,
            )
            if not section.catalog_available:
                status = (
                    "No play/scheme cards yet."
                    if section_id is FootballShopSection.PLAYS_SCHEMES
                    else "No coach upgrades yet."
                    if section_id is FootballShopSection.COACH_UPGRADES
                    else "No eligible player upgrades."
                )
                draw_text(
                    surface,
                    status,
                    (panel.left + 12, panel.top + 31),
                    self._small_font,
                    self.theme.muted,
                )
            row_top = panel.top + 54
            row_bottom = panel.bottom - 10
            row_height = max(1, (row_bottom - row_top) // len(section.slots))
            for slot_index, slot in enumerate(section.slots):
                row = pygame.Rect(
                    panel.left + 8,
                    row_top + slot_index * row_height,
                    panel.width - 16,
                    max(1, row_height - 5),
                )
                self._draw_shop_slot(
                    surface, row, slot, buttons, shop.remaining_ap
                )

        footer_top = content.bottom - 44
        reroll_rect = pygame.Rect(
            content.left,
            footer_top,
            220,
            36,
        )
        buttons.append(
            Button(
                "MOVE TO NEXT DAY  /  1 AP",
                self._move_to_next_day,
                reroll_rect,
                enabled=shop.remaining_ap >= 1,
                variant="quiet",
            )
        )
        finish_rect = pygame.Rect(
            content.right - 260,
            footer_top,
            260,
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

    def _draw_shop_slot(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        slot: FootballShopSlotState,
        buttons: list[Button],
        remaining_ap: int,
    ) -> None:
        card = slot.card
        purchased = slot.purchased
        fill = self.theme.panel_alt if purchased else self.theme.panel
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        pygame.draw.rect(surface, self.theme.border_soft, rect, width=1, border_radius=6)
        text_left = rect.left + 8
        button_width = min(94, max(68, rect.width // 4))
        button_rect = pygame.Rect(
            rect.right - button_width - 5,
            rect.centery - 14,
            button_width,
            28,
        )
        text_width = max(1, button_rect.left - text_left - 8)

        if not slot.unlocked:
            cost = slot.unlock_cost
            draw_text(
                surface,
                f"SLOT {slot.slot_number}  /  LOCKED",
                (text_left, rect.top + 5),
                self._small_font,
                self.theme.text,
            )
            if slot.disabled_reason:
                draw_text(
                    surface,
                    _fit_text(slot.disabled_reason, self._small_font, text_width),
                    (text_left, rect.top + 25),
                    self._small_font,
                    self.theme.muted,
                )
            buttons.append(
                Button(
                    f"UNLOCK {cost} AP" if cost is not None else "LOCKED",
                    lambda section=slot.section, number=slot.slot_number: self._submit(
                        lambda: self._require_controller().unlock_shop_slot(
                            section, number
                        )
                    ),
                    button_rect,
                    enabled=slot.can_unlock,
                    variant="quiet",
                )
            )
            return

        if card is None:
            draw_text(
                surface,
                f"SLOT {slot.slot_number}  /  EMPTY",
                (text_left, rect.top + 5),
                self._small_font,
                self.theme.text,
            )
            reason = slot.disabled_reason or "No eligible cards."
            draw_text(
                surface,
                _fit_text(reason, self._small_font, text_width),
                (text_left, rect.top + 25),
                self._small_font,
                self.theme.muted,
            )
            return

        rarity_label = card.rarity.value.replace("_", " ").upper()
        draw_text(
            surface,
            _fit_text(card.name, self._small_font, text_width),
            (text_left, rect.top + 4),
            self._small_font,
            self.theme.text,
        )
        draw_text(
            surface,
            _fit_text(
                f"{rarity_label}  /  {card.cost} AP",
                self._small_font,
                text_width,
            ),
            (text_left, rect.top + 23),
            self._small_font,
            _RARITY_COLORS[card.rarity],
        )
        if purchased:
            reason = "PURCHASED"
        elif card.cost > remaining_ap:
            reason = f"NEED {card.cost - remaining_ap} MORE AP"
        elif card.upgrade is not None:
            reason = f"{card.upgrade.stat.value.upper()}  /  {_POSITION_LABELS[card.upgrade.position]}"
        else:
            reason = _fit_text(card.description, self._small_font, text_width)
        if rect.height >= 58:
            draw_text(
                surface,
                _fit_text(reason, self._small_font, text_width),
                (text_left, rect.top + 41),
                self._small_font,
                self.theme.secondary_accent if not purchased else self.theme.muted,
            )
        button_label = (
            "PURCHASED"
            if purchased
            else f"NEED {card.cost - remaining_ap} AP"
            if card.cost > remaining_ap
            else "BUY"
        )
        buttons.append(
            Button(
                button_label,
                lambda section=slot.section, card_id=card.card_id: self._submit(
                    lambda: self._require_controller().buy_shop_card(
                        section, card_id
                    )
                ),
                button_rect,
                enabled=not purchased and card.cost <= remaining_ap,
                variant="primary" if not purchased else "quiet",
            )
        )

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
            explanation = "Next up: a fresh coaching shop before the game."
            primary_label = "OPEN NEXT GAME SHOP"
            primary_action = self._open_next_shop
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
        if event.perk_effects:
            description += f" / {'; '.join(event.perk_effects)}"
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
            self._staff_dialog_title_font
            if self._current_state().phase is FootballRunPhase.COACH_DRAFT else self._title_font,
            self.theme.text,
        )
        draw_wrapped_text(
            surface,
            "Your current draft, upgrades, and season progress will be discarded.",
            pygame.Rect(rect.left + 28, rect.top + 70, rect.width - 56, 48),
            self._staff_body_font
            if self._current_state().phase is FootballRunPhase.COACH_DRAFT else self._body_font,
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

    def _open_next_shop(self) -> None:
        self._submit(self._require_controller().enter_next_shop)

    def _move_to_next_day(self) -> None:
        self._submit(self._require_controller().move_to_next_day)

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


def _draft_percentage(value: float) -> str:
    percentage = format(Decimal(str(value)) * 100, "f")
    if "." in percentage:
        percentage = percentage.rstrip("0").rstrip(".")
    return f"{percentage}%"


def _draft_position_label(position: FootballPosition) -> str:
    labels = {
        FootballPosition.QB: "QB",
        FootballPosition.RB: "RB",
        FootballPosition.WR: "WR",
        FootballPosition.O_LINE: "O-line",
        FootballPosition.D_LINE: "D-line",
        FootballPosition.LINEBACKERS: "Linebackers",
        FootballPosition.CORNERBACKS: "Cornerbacks",
        FootballPosition.SAFETIES: "Safeties",
    }
    return labels[position]


def _coach_position_label(position: FootballPosition) -> str:
    labels = {
        FootballPosition.QB: "QB",
        FootballPosition.RB: "RB",
        FootballPosition.WR: "WR",
        FootballPosition.O_LINE: "O-LINE",
        FootballPosition.D_LINE: "D-LINE",
        FootballPosition.LINEBACKERS: "LB",
        FootballPosition.CORNERBACKS: "CB",
        FootballPosition.SAFETIES: "S",
    }
    return labels[position]


def _coach_perk_summary(coach: FootballCoachProfile) -> str:
    perk = coach.perk
    if perk is None:
        return "No perk."
    return (
        f"{perk.effect} {perk.trigger} {perk.duration} {perk.reset}"
    )


def _coach_action_label(action: str) -> str:
    labels = {
        "rb_run": "RB Run",
        "screen_pass": "Screen",
        "pa_pass": "PA Pass",
        "short_pass": "Short",
        "medium_pass": "Medium",
        "deep_pass": "Deep",
    }
    return labels[action]
