from collections.abc import Callable

import pygame

from src.engine.football import (
    DefensiveSchemeAction,
    FootballConversionAction,
    OffensivePlayAction,
)
from src.engine.football_controller import (
    FootballGameController,
    FootballGameControllerState,
    FootballHumanDecision,
    FootballRunPhase,
)
from src.engine.football_shop import FootballShopSection
from src.ui.coach_fonts import staff_font
from src.ui.football_result import FootballResultView
from src.ui.football_review_view import FootballReviewView
from src.ui.football_shop_view import FootballShopView
from src.ui.football_player_draft_view import FootballPlayerDraftView
from src.ui.football_coach_view import FootballCoachView
from src.ui.football_match_interaction import HandEventKind, MatchInteraction
from src.ui.football_match_screen import FootballMatchScreen, MatchActions
from src.ui.football_draft_interaction import CoachInspection, PlayerInspection
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.football_ui_kit import kit_button, stadium_backdrop
from src.ui.layout import Layout
from src.ui.screens import Navigate, Quit, Screen
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text

RESULT_PHASES = frozenset({
    FootballRunPhase.READY_FOR_NEXT_GAME,
    FootballRunPhase.FIRED,
    FootballRunPhase.PLAYOFFS,
})


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
        self.match_screen = FootballMatchScreen(theme, self._small_font, self._label_font)
        self.coach_inspection = CoachInspection()
        self.player_inspection = PlayerInspection()
        self._staff_body_font = staff_font(16)
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
        self._result_view = FootballResultView(
            self._open_next_shop, self._return_to_menu, self._request_exit,
        )

    def begin(self, controller: FootballGameController) -> None:
        self.controller = controller
        self.state = controller.state
        self.last_error = None
        self.confirm_exit = False
        self.match_screen.reset()
        self.coach_inspection = CoachInspection()
        self.player_inspection = PlayerInspection()
        self.buttons = []
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None
        self.shop_review = ShopReviewInteraction()
        self._shop_view_instance = None

    @property
    def match_interaction(self) -> MatchInteraction:
        return self.match_screen.interaction

    def _match_screen_active(self, state: FootballGameControllerState) -> bool:
        return (
            state.phase is FootballRunPhase.MATCH
            or self.match_screen.holds_final_playback(state)
        )

    def handle_event(self, event: pygame.event.Event) -> None:
        state = self._current_state()
        if self._match_screen_active(state):
            self._handle_match_event(event)
            return
        if (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP
            and self.shop_review.mode is None
        ):
            if not self.confirm_exit and self._shop_view().handle_event(event, **self._inspect_keys()):
                self.hover_index = None if event.type != pygame.MOUSEMOTION else self.hover_index
                return
        if (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP
            and self.shop_review.mode is not None
        ):
            if (
                self.shop_review.mode == "playbook"
                and not self.confirm_exit
                and self.shop_review.inspect.handle_event(event, **self._inspect_keys())
            ):
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self.shop_review.team_popup:
                    self.shop_review.close_team_upgrades()
                    self.buttons = []
                    return
                self._leave_shop_review()
                return
            if self.shop_review.handle_scroll(event):
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
        previous_focus = self.focus_index
        super().handle_event(event)
        if (
            self._current_state().phase is FootballRunPhase.PLAYER_DRAFT
            and not self.confirm_exit
            and event.type == pygame.MOUSEMOTION
            and self.focus_index != previous_focus
        ):
            self._focus(previous_focus)

    def _handle_match_event(self, event: pygame.event.Event) -> None:
        if self.confirm_exit:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._keep_playing()
                return
            super().handle_event(event)
            return
        hand_event = self.match_screen.handle_event(event)
        if hand_event.kind is HandEventKind.SELECTED:
            assert hand_event.copy_id is not None
            self._submit_match_hand_card(hand_event.copy_id)
            return
        if hand_event.kind is HandEventKind.INVALID_DROP:
            self.last_error = "Drop the card on the field to play it."
            self.state = self._require_controller().state
            return
        if hand_event.kind is HandEventKind.HANDLED:
            self.hover_index = None if self.match_screen.popup.open else self.hover_index
            return
        super().handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        state = self._current_state()
        if self._match_screen_active(state):
            self._draw_match_screen(surface, state)
            if self.confirm_exit:
                self._draw_exit_confirmation(surface)
            return
        if state.phase in RESULT_PHASES:
            self._draw_result_screen(surface, state)
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
        }
        title, eyebrow = titles[state.phase]
        if state.phase is FootballRunPhase.PRE_MATCH_SHOP and self.shop_review.mode == "depth":
            title, eyebrow = "Depth chart", "CURRENT RUN / READ ONLY"
        depth_review = (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP
            and self.shop_review.mode == "depth"
        )
        playbook_review = (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP
            and self.shop_review.mode == "playbook"
        )
        if depth_review or playbook_review:
            layout = Layout.from_surface(surface)
            surface.blit(stadium_backdrop(surface.get_size()), (0, 0))
            content = pygame.Rect(20, 15, surface.get_width() - 40, surface.get_height() - 30)
        elif state.phase in (FootballRunPhase.COACH_DRAFT, FootballRunPhase.PLAYER_DRAFT):
            layout = Layout.from_surface(surface)
            if state.phase is FootballRunPhase.COACH_DRAFT:
                self._coach_view().draw_backdrop(surface)
                content = pygame.Rect(38, 122, 1204, 558)
            else:
                self._player_draft_view().draw_backdrop(surface)
                content = pygame.Rect(20, 20, 1240, 674)
        elif state.phase is FootballRunPhase.PRE_MATCH_SHOP and self.shop_review.mode is None:
            layout = Layout.from_surface(surface)
            surface.fill("#061629")
            content = pygame.Rect(20, 16, surface.get_width() - 40, surface.get_height() - 32)
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
                    error=self.last_error,
                )
                if self.shop_review.mode == "depth":
                    buttons = review.draw_depth_chart(surface, content, state)
                else:
                    buttons = review.draw_playbook(
                        surface, content, state.shop,
                        hover_key=getattr(self._button_at(self.hover_index), "inspect_key", None),
                        focus_key=getattr(self._button_at(self.focus_index), "inspect_key", None),
                    )
                self._set_buttons(buttons)
            else:
                shop_view = self._shop_view()
                hovered = self._button_at(self.hover_index)
                focused = self._button_at(self.focus_index)
                shop_buttons = shop_view.draw(
                    surface,
                    content,
                    state.shop,
                    f"CHECK: {self.last_error}" if self.last_error else state.transition_message,
                    state,
                    self.team_name,
                    hover_key=getattr(hovered, "inspect_key", None),
                    focus_key=getattr(focused, "inspect_key", None),
                    error=self.last_error is not None,
                )
                self._set_buttons(shop_buttons)

        exit_rect = (
            pygame.Rect(1097, 37, 145, 32)
            if state.phase is FootballRunPhase.COACH_DRAFT
            else pygame.Rect(38, 647, 254, 32)
            if state.phase is FootballRunPhase.PLAYER_DRAFT
            else pygame.Rect(content.right - 120, content.top, 120, 36)
            if depth_review
            else pygame.Rect(content.right - 120, 656, 120, 42)
            if state.phase is FootballRunPhase.PRE_MATCH_SHOP and self.shop_review.mode is None
            else pygame.Rect(layout.content.right - 118, layout.content.top, 118, 30)
        )
        shop_landing = (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP and self.shop_review.mode is None
        )
        if not playbook_review and not (depth_review and self.shop_review.team_popup):
            if shop_landing:
                end_run = kit_button("END RUN", self._request_exit, exit_rect, variant="kit-danger")
            elif depth_review:
                end_run = kit_button("END RUN", self._request_exit, exit_rect, variant="kit-danger")
            else:
                end_run = Button("END RUN", self._request_exit, exit_rect, variant="quiet")
            self.buttons.append(end_run)
        self._set_buttons(self.buttons)
        self._draw_buttons(surface)
        if shop_landing and not self.confirm_exit:
            self._shop_view().draw_overlay(surface, hovered_button=self._button_at(self.hover_index))
        if playbook_review and not self.confirm_exit:
            self.shop_review.inspect.paint(surface, hovered_button=self._button_at(self.hover_index))
        if self.last_error is not None and state.phase is not FootballRunPhase.PRE_MATCH_SHOP:
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

    def _draw_result_screen(
        self,
        surface: pygame.Surface,
        state: FootballGameControllerState,
    ) -> None:
        """Full-screen result: the view owns the backdrop, header, and every button."""
        buttons = self._result_view.draw(surface, state, self.theme, error=self.last_error)
        if not self.confirm_exit:
            self._set_buttons(buttons)
            self._draw_buttons(surface)
        else:
            for button in buttons:
                button.focused = False
                button.draw(surface, self._main_font, self.theme)
            self._draw_exit_confirmation(surface)

    def _draw_match_screen(
        self,
        surface: pygame.Surface,
        state: FootballGameControllerState,
    ) -> None:
        controller = self._require_controller
        self.match_screen.theme = self.theme
        actions = MatchActions(
            play_card=self._submit_match_hand_card,
            fallback=self._submit_match_fallback,
            fourth_down=lambda action: self._submit_match_action(
                lambda: controller().choose_fourth_down(action)
            ),
            conversion=lambda action, copy_id: self._submit_match_action(
                lambda: controller().choose_conversion(action, copy_id)
            ),
            challenge=lambda accept: self._submit_match_action(
                lambda: controller().respond_to_challenge(accept)
            ),
            challenge_touchdown=lambda: self._submit_match_action(
                controller().challenge_touchdown
            ),
            end_run=self._request_exit,
        )
        buttons = self.match_screen.draw(
            surface, state, actions,
            focus_index=self.focus_index, hover_index=self.hover_index,
            pressed_index=self.pressed_index, error=self.last_error,
        )
        if not self.confirm_exit:
            self._set_buttons(buttons)

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
        elif decision is FootballHumanDecision.CONVERSION:
            self._submit_match_action(
                lambda: self._require_controller().choose_conversion(
                    FootballConversionAction.TWO_POINT, copy_id
                )
            )
        elif decision is FootballHumanDecision.CHALLENGE:
            raise RuntimeError("Challenge prompts use the explicit decision buttons.")
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

    def _submit_match_action(self, action: Callable[[], object]) -> None:
        self._submit(action)

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
            self.theme, self.coach_inspection, self.focus_index,
            self._staff_body_font, self._staff_stat_font,
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
                self._open_playbook,
                lambda: self._submit(self._require_controller().finish_shop),
                lambda section, number: self._submit(
                    lambda: self._require_controller().unlock_shop_slot(
                        section, number
                    )
                ),
                self._purchase_shop_card,
            )
        return self._shop_view_instance

    def _open_playbook(self) -> None:
        self.shop_review.open_playbook()
        self.buttons = []
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None

    def _inspect_keys(self) -> dict:
        return {
            "hover_key": getattr(self._button_at(self.hover_index), "inspect_key", None),
            "focus_key": getattr(self._button_at(self.focus_index), "inspect_key", None),
        }

    def _button_at(self, index: int | None) -> Button | None:
        if index is None or not 0 <= index < len(self.buttons):
            return None
        return self.buttons[index]

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
        old_state = self._current_state()
        try:
            action()
        except ValueError as error:
            self.last_error = str(error)
        finally:
            self.state = self._require_controller().state
            if self.state.phase is not old_state.phase:
                self.buttons = []
                self.focus_index = 0
                self.hover_index = None
                self.pressed_index = None
            elif (
                old_state.phase is FootballRunPhase.PRE_MATCH_SHOP
                and self.state.shop != old_state.shop
            ):
                # Drop stale controls but keep keyboard focus on the same slot.
                self.buttons = []
                self.hover_index = None
                self.pressed_index = None

    def _open_next_shop(self) -> None:
        self._submit(self._require_controller().enter_next_shop)

    def _move_to_next_day(self) -> None:
        self._submit(self._require_controller().move_to_next_day)

    def _request_exit(self) -> None:
        if self._current_state().phase is FootballRunPhase.PRE_MATCH_SHOP:
            self._shop_view().inspect.reset()
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
