from collections.abc import Callable

import pygame

from src.engine.football import (
    DefensiveSchemeAction,
    OffensivePlayAction,
)
from src.engine.football_controller import (
    FootballGameController,
    FootballGameControllerState,
    FootballHumanDecision,
    FootballRunPhase,
)
from src.engine.football_shop import FootballShopSection
from src.ui.coach_fonts import coach_font, staff_font
from src.ui.football_result import FootballResultView
from src.ui.football_display import (
    _SCHEME_LABELS,
)
from src.ui.football_review_view import FootballReviewView
from src.ui.football_depth_chart import DepthChartButton
from src.ui.football_shop_view import FootballShopView
from src.ui.football_player_draft_view import FootballPlayerDraftView
from src.ui.football_coach_view import FootballCoachView
from src.ui.football_match_field import draw_match_field
from src.ui.football_match_decision_view import FootballMatchDecisionView
from src.ui.football_match_palette import (
    MATCH_CANVAS as _MATCH_CANVAS, MATCH_PANEL as _MATCH_PANEL,
    MATCH_PANEL_EDGE as _MATCH_PANEL_EDGE, MATCH_CHALK as _MATCH_CHALK,
    MATCH_OPPONENT as _MATCH_OPPONENT, MATCH_FOCUS as _MATCH_FOCUS,
)
from src.ui.football_match_status import FootballMatchStatusView
from src.ui.football_match_interaction import HandEventKind, MatchInteraction
from src.ui.football_draft_interaction import CoachInspection, PlayerInspection
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.layout import Layout
from src.ui.screens import Navigate, Quit, Screen
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text

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
        self.match_interaction = MatchInteraction()
        self.coach_inspection = CoachInspection()
        self.player_inspection = PlayerInspection()
        self._coach_title_font = coach_font(40, handwritten=True)
        self._coach_name_font = coach_font(23, bold=True)
        self._coach_detail_font = coach_font(15)
        self._coach_stat_font = coach_font(15, bold=True)
        self._coach_small_font = coach_font(14, bold=True)
        self._coach_main_font = coach_font(17, bold=True)
        self._coach_body_font = coach_font(16)
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
        self._draft_detail_font = staff_font(14)
        self._draft_small_font = staff_font(13)
        self._draft_button_font = staff_font(17, semibold=True)
        self.shop_review = ShopReviewInteraction()
        self._shop_view_instance: FootballShopView | None = None
        self._focus_shop_navigation_after_details = False
        self._result_view = FootballResultView(
            self._display_font, self._title_font, self._label_font, self._small_font,
            self._open_next_shop, self._return_to_menu,
        )

    def begin(self, controller: FootballGameController) -> None:
        self.controller = controller
        self.state = controller.state
        self.last_error = None
        self.confirm_exit = False
        self.match_interaction = MatchInteraction()
        self.coach_inspection = CoachInspection()
        self.player_inspection = PlayerInspection()
        self.buttons = []
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None
        self.shop_review = ShopReviewInteraction()
        self._shop_view_instance = None
        self._focus_shop_navigation_after_details = False

    def handle_event(self, event: pygame.event.Event) -> None:
        state = self._current_state()
        if (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP
            and self.shop_review.mode is None
        ):
            if self._focus_shop_navigation_after_details:
                return
            shop_view = self._shop_view()
            if shop_view.coach_details_open:
                details_rect = shop_view.coach_details_rect
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self._close_coach_details()
                    return
                if details_rect is None:
                    return
                if (
                    event.type == pygame.MOUSEMOTION
                    and not details_rect.collidepoint(event.pos)
                ):
                    self._close_coach_details()
                    return
                if (
                    event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)
                    and not details_rect.collidepoint(event.pos)
                ):
                    self._close_coach_details()
                    return
        if (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP
            and self.shop_review.mode is not None
        ):
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._leave_shop_review()
                return
            if self.shop_review.handle_scroll(event):
                return
        if state.phase is FootballRunPhase.MATCH and not self.confirm_exit:
            hand_event = self.match_interaction.handle_event(event)
            if hand_event.kind is HandEventKind.SELECTED:
                assert hand_event.copy_id is not None
                self._submit_match_hand_card(hand_event.copy_id)
                return
            if hand_event.kind is HandEventKind.INVALID_DROP:
                self.last_error = "Invalid drop. Place the card in the play area."
                self.state = self._require_controller().state
                return
            if hand_event.kind is HandEventKind.HANDLED:
                return
        if self._current_state().phase is FootballRunPhase.COACH_DRAFT and not self.confirm_exit:
            self.coach_inspection.handle_event(event)
            if (
                event.type == pygame.MOUSEMOTION
                and self.coach_inspection.hover_index is not None
                and self.coach_inspection.hover_index < len(self.buttons)
            ):
                self._focus(self.coach_inspection.hover_index)
            if event.type == pygame.WINDOWLEAVE:
                self.hover_index = None
                self.pressed_index = None
        if self._current_state().phase is FootballRunPhase.PLAYER_DRAFT and not self.confirm_exit:
            self.player_inspection.handle_event(event)
            if event.type == pygame.WINDOWLEAVE:
                self.hover_index = None
                self.pressed_index = None
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.shop_review.mode is not None:
                self._leave_shop_review()
                return
            self.confirm_exit = not self.confirm_exit
            self.coach_inspection.hover_index = None
            self.buttons = []
            self.focus_index = 0
            self.hover_index = None
            self.pressed_index = None
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
        if state.phase is FootballRunPhase.PRE_MATCH_SHOP and self.shop_review.mode == "depth":
            title, eyebrow = "Depth chart", "CURRENT RUN / READ ONLY"
        depth_review = (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP
            and self.shop_review.mode == "depth"
        )
        if depth_review:
            layout = Layout.from_surface(surface)
            surface.fill("#061629")
            content = pygame.Rect(20, 15, surface.get_width() - 40, surface.get_height() - 30)
        elif state.phase in (FootballRunPhase.COACH_DRAFT, FootballRunPhase.PLAYER_DRAFT):
            layout = Layout.from_surface(surface)
            if state.phase is FootballRunPhase.COACH_DRAFT:
                self._coach_view().draw_backdrop(surface)
                content = pygame.Rect(38, 122, 1204, 558)
            else:
                self._player_draft_view().draw_backdrop(surface)
                content = pygame.Rect(20, 20, 1240, 674)
        else:
            layout = self._header(surface, title, eyebrow, self.team_name)
            content = pygame.Rect(
                layout.content.left,
                layout.content.top + 34,
                layout.content.width,
                layout.content.height - 34,
            )
        if state.phase is FootballRunPhase.COACH_DRAFT:
            self._set_buttons(self._coach_view().draw(surface, content, state))
        elif state.phase is FootballRunPhase.PLAYER_DRAFT:
            self.buttons = self._player_draft_view().draw(surface, content, state)
        elif state.phase is FootballRunPhase.PRE_MATCH_SHOP:
            if self.shop_review.mode is not None:
                review = FootballReviewView(
                    self.theme, self._small_font, self._label_font, self.shop_review,
                    self._leave_shop_review,
                    lambda copy_id: self._submit(
                        lambda: self._require_controller().remove_owned_card(copy_id)
                    ),
                )
                buttons = (
                    review.draw_depth_chart(surface, content, state)
                    if self.shop_review.mode == "depth"
                    else review.draw_playbook(surface, content, state.shop)
                )
                self._set_buttons(buttons)
                self._draw_buttons(surface)
            else:
                shop_view = self._shop_view()
                restore_navigation_focus = (
                    self._focus_shop_navigation_after_details
                )
                if (
                    shop_view.coach_details_open
                    and shop_view.coach_details_rect is None
                ):
                    self.focus_index = 0
                    self.hover_index = None
                    self.pressed_index = None
                shop_buttons = shop_view.draw(
                    surface,
                    content,
                    state.shop,
                    state.transition_message,
                )
                if restore_navigation_focus:
                    self.focus_index = next(
                        (
                            index
                            for index, button in enumerate(shop_buttons)
                            if button.label == "DEPTH CHART"
                        ),
                        0,
                    )
                    self.hover_index = None
                    self._focus_shop_navigation_after_details = False
                self._set_buttons(shop_buttons)
                self._draw_buttons(surface)
        else:
            self._set_buttons(self._result_view.draw(surface, content, state, self.theme))
            self._draw_buttons(surface)

        exit_rect = (
            pygame.Rect(1097, 37, 145, 32)
            if state.phase is FootballRunPhase.COACH_DRAFT
            else pygame.Rect(38, 647, 254, 32)
            if state.phase is FootballRunPhase.PLAYER_DRAFT
            else pygame.Rect(content.right - 112, content.top, 112, 30)
            if depth_review
            else pygame.Rect(layout.content.right - 118, layout.content.top, 118, 30)
        )
        self.buttons.append(
            (DepthChartButton if depth_review else Button)(
                "END RUN", self._request_exit, exit_rect, variant="quiet"
            )
        )
        self._set_buttons(self.buttons)
        self._draw_buttons(surface)
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
        status = FootballMatchStatusView(self._small_font)
        status.draw_scoreboard(surface, scoreboard, state, team_accent, opponent_accent)

        field = pygame.Rect(margin, scoreboard.bottom + 14, content_width, 286)
        draw_match_field(
            surface, field, match, team_accent, opponent_accent,
            self._small_font, self.match_interaction, _SCHEME_LABELS,
        )

        history = pygame.Rect(margin, field.bottom + 12, content_width, 50)
        status.draw_history(surface, history, state)

        decision_rect = pygame.Rect(
            margin,
            history.bottom + 15,
            content_width,
            max(1, height - history.bottom - 42),
        )
        decision_view = FootballMatchDecisionView(
            self._small_font, self._label_font, self.match_interaction,
            self.focus_index, self.hover_index, self.pressed_index,
            self._submit_match_hand_card,
            lambda action: self._submit_match_action(
                lambda: self._require_controller().choose_fourth_down(action)
            ),
            lambda action, copy_id: self._submit_match_action(
                lambda: self._require_controller().choose_conversion(action, copy_id)
            ),
            self._submit_match_fallback,
        )
        self.buttons = decision_view.draw(surface, decision_rect, state)

        pause_rect = pygame.Rect(scoreboard.right - 102, scoreboard.top + 13, 82, 32)
        self.buttons.append(
            Button("PAUSE", self._request_exit, pause_rect, variant="quiet")
        )
        self._set_buttons(self.buttons)
        for index, button in enumerate(self.buttons[:-1]):
            if button.variant != "hand-card":
                decision_view.draw_call_button(
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

    def _submit_match_hand_card(self, copy_id: str) -> None:
        state = self._current_state()
        decision = state.human_decision
        if decision is FootballHumanDecision.OFFENSIVE_PLAY:
            self._submit_match_action(
                lambda: self._require_controller().choose_offensive_play(copy_id)
            )
        elif decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            self._submit_match_action(
                lambda: self._require_controller().choose_defensive_scheme(copy_id)
            )
        else:
            raise RuntimeError("A hand card can only be played during a play or scheme call.")

    def _submit_match_fallback(self, offensive: bool) -> None:
        self._submit_match_action(
            lambda: (
                self._require_controller().choose_offensive_play(OffensivePlayAction.RB_RUN)
                if offensive
                else self._require_controller().choose_defensive_scheme(DefensiveSchemeAction.RB_RUN)
            )
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

    def _draw_buttons(self, surface: pygame.Surface) -> None:
        for index, button in enumerate(self.buttons):
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
                self._coach_view().draw_button(
                    surface, button, index, pressed=self.pressed_index == index,
                )
                continue
            if button.variant == "draft-select":
                pressed = self.pressed_index == index and button.enabled
                active = self.player_inspection.active_index(self.focus_index) == index
                rect = button.rect.move(0, 2) if pressed else button.rect
                fill = self.theme.primary if active else pygame.Color("#234b70")
                if pressed:
                    fill = self.theme.primary_dark
                pygame.draw.rect(surface, fill, rect, border_radius=8)
                pygame.draw.rect(
                    surface,
                    readable_ink(fill),
                    rect,
                    1,
                    border_radius=8,
                )
                if active:
                    pygame.draw.rect(
                        surface,
                        pygame.Color("#f5ead1"),
                        rect.inflate(-3, -3),
                        2,
                        border_radius=6,
                    )
                if button.focused and self.player_inspection.keyboard:
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

    def _coach_view(self) -> FootballCoachView:
        return FootballCoachView(
            self.theme, self.team_name, self.coach_inspection,
            self.focus_index, self.hover_index,
            self._coach_title_font, self._staff_name_font, self._staff_label_font,
            self._staff_body_font, self._staff_detail_font, self._staff_stat_font,
            self._staff_small_font, self._staff_main_font, self._staff_button_font,
            lambda choice: self._submit(
                lambda: self._require_controller().choose_coach(choice)
            ),
        )

    def _player_draft_view(self) -> FootballPlayerDraftView:
        return FootballPlayerDraftView(
            self.theme, self.player_inspection, self.focus_index,
            self._draft_title_font, self._draft_name_font, self._draft_label_font,
            self._draft_small_font, self._draft_stat_font, self._draft_detail_font,
            lambda position, choice, appearance: self._submit(
                lambda: self._require_controller().choose_player(
                    position, choice, appearance=appearance
                )
            ),
        )

    def _leave_shop_review(self) -> None:
        if (
            self._current_state().shop is not None
            and self._current_state().shop.pending_removal is not None
        ):
            self._submit(self._require_controller().cancel_card_removal)
        self.shop_review.close()
        self.buttons = []
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None

    def _open_depth_chart(self) -> None:
        self.shop_review.open_depth_chart()
        self.buttons = []
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None

    def _shop_view(self) -> FootballShopView:
        if self._shop_view_instance is None:
            self._shop_view_instance = FootballShopView(
                self.theme, self._small_font, self._label_font,
                self._move_to_next_day, self._open_depth_chart,
                self.shop_review.open_playbook,
                lambda: self._submit(self._require_controller().finish_shop),
                lambda section, number: self._submit(
                    lambda: self._require_controller().unlock_shop_slot(
                        section, number
                    )
                ),
                self._purchase_shop_card,
                self._close_coach_details,
            )
        return self._shop_view_instance

    def _close_coach_details(self) -> None:
        self._shop_view().close_coach_details()
        self.hover_index = None
        self.pressed_index = None
        self._focus_shop_navigation_after_details = True

    def _purchase_shop_card(
        self, section: FootballShopSection, card_id: str, is_removal: bool,
    ) -> None:
        self._submit(lambda: self._require_controller().buy_shop_card(section, card_id))
        shop = self._current_state().shop
        if is_removal and shop is not None and shop.pending_removal is not None:
            self.shop_review.open_playbook()

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
        old_phase = self._current_state().phase
        try:
            action()
        except ValueError as error:
            self.last_error = str(error)
        finally:
            self.state = self._require_controller().state
            if self.state.phase is not old_phase:
                self.buttons = []
                self.focus_index = 0
                self.hover_index = None
                self.pressed_index = None

    def _open_next_shop(self) -> None:
        self._submit(self._require_controller().enter_next_shop)

    def _move_to_next_day(self) -> None:
        self._submit(self._require_controller().move_to_next_day)

    def _request_exit(self) -> None:
        if (
            self._current_state().phase is FootballRunPhase.PRE_MATCH_SHOP
            and self._shop_view().coach_details_open
        ):
            self._close_coach_details()
        self.confirm_exit = True
        self.buttons = []
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None

    def _keep_playing(self) -> None:
        self.confirm_exit = False
        self.buttons = []
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None

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
