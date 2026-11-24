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
from src.ui.football_inspect import InspectState
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.football_pause_menu import PauseMenu, draw_pause_button, draw_pause_menu
from src.ui.football_ui_kit import draw_message_banner, stadium_backdrop
from src.ui.layout import Layout
from src.ui.screens import Navigate, Quit, Screen
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_text

RESULT_PHASES = frozenset({
    FootballRunPhase.READY_FOR_NEXT_GAME,
    FootballRunPhase.FIRED,
    FootballRunPhase.PLAYOFFS,
})
# A run in one of these phases is over: it cannot be paused or resumed.
ENDED_PHASES = frozenset({FootballRunPhase.FIRED, FootballRunPhase.PLAYOFFS})
PAUSE_LABEL = "PAUSE"
RUN_PAUSE_VARIANT = "run-pause"
# Coach selection and the player draft show choice errors in the header, between the
# title and PAUSE.
COACH_ERROR_RECT = pygame.Rect(640, 18, 484, 52)


class FootballRunScreen(Screen):
    """Render the current immutable controller state and submit human choices."""

    def __init__(
        self,
        theme: Theme,
        team_name: str,
        navigate: Navigate,
        quit_application: Quit,
        *,
        clock: Callable[[], int] = pygame.time.get_ticks,
        on_run_discarded: Callable[[], None] = lambda: None,
    ) -> None:
        super().__init__(theme, navigate, quit_application)
        self.team_name = team_name
        self.controller: FootballGameController | None = None
        self.state: FootballGameControllerState | None = None
        self.last_error: str | None = None
        self.on_run_discarded = on_run_discarded
        self.pause = PauseMenu(clock)
        self._clock = clock
        self._resume_focus: int | None = None
        self.match_screen = FootballMatchScreen(
            theme, self._small_font, self._label_font, pause_menu=self.pause,
        )
        self.coach_inspection = self._new_coach_inspection()
        self.player_inspection = PlayerInspection()
        self._staff_button_font = staff_font(17, semibold=True)
        self.shop_review = ShopReviewInteraction()
        self._shop_view_instance: FootballShopView | None = None
        self._result_view = FootballResultView(
            self._open_next_shop, self._quit_run, self._open_pause,
        )

    def begin(self, controller: FootballGameController) -> None:
        self.controller = controller
        self.state = controller.state
        self.last_error = None
        self._resume_focus = None
        self.match_screen.reset()
        self.coach_inspection = self._new_coach_inspection()
        self.player_inspection = PlayerInspection()
        self.buttons = []
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None
        self.shop_review = ShopReviewInteraction()
        self._shop_view_instance = None

    def resume(self) -> None:
        """Return to a remembered run exactly where it was left; never resets it."""
        controller = self._require_controller()
        self.state = controller.state
        # Rebuild cached views so a profile edit's theme colors apply.
        self._shop_view_instance = None
        self._resume_focus = self.pause.hide()
        self.buttons = []
        self.hover_index = None
        self.pressed_index = None

    def on_enter(self) -> None:
        super().on_enter()
        if self._resume_focus is not None:
            self.focus_index = self._resume_focus
            self._resume_focus = None

    @property
    def resumable(self) -> bool:
        return self.controller is not None and self.controller.state.phase not in ENDED_PHASES

    @property
    def pause_open(self) -> bool:
        """True while any pause menu covers the run (outside or inside a match)."""
        return self.pause.is_open or self.match_screen.popup.kind == "pause"

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
        escape = event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
        if self.pause.is_open:
            if escape:
                if not self.pause.cancel_quit():
                    self._keep_playing()
                return
            super().handle_event(event)
            return
        if self._match_screen_active(state):
            self._handle_match_event(event)
            return
        if (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP
            and self.shop_review.mode is None
        ):
            if self._shop_view().handle_event(event):
                self.hover_index = None if event.type != pygame.MOUSEMOTION else self.hover_index
                return
        if (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP
            and self.shop_review.mode is not None
        ):
            if (
                self.shop_review.mode == "playbook"
                and self.shop_review.inspect.handle_event(event)
            ):
                return
            if escape:
                if self.shop_review.team_popup:
                    self.shop_review.close_team_upgrades()
                    self.buttons = []
                    return
                if state.shop is not None and state.shop.pending_removal is not None:
                    # Esc cancels a pending removal (and its Playbook) before pausing.
                    self._leave_shop_review()
                    return
            if self.shop_review.handle_scroll(event):
                return
        if self._current_state().phase is FootballRunPhase.COACH_DRAFT:
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
            # Esc hides a visible coach panel before it can pause.
            if self.coach_inspection.inspect.handle_event(event):
                return
        if self._current_state().phase is FootballRunPhase.PLAYER_DRAFT:
            self.player_inspection.handle_event(event)
            if event.type == pygame.WINDOWLEAVE:
                self.hover_index = None
                self.pressed_index = None
        if escape:
            if self._current_state().phase not in ENDED_PHASES:
                self._open_pause()
            return
        previous_focus = self.focus_index
        super().handle_event(event)
        if self.state is None:  # the action discarded the run
            return
        if (
            self._current_state().phase is FootballRunPhase.PLAYER_DRAFT
            and not self.pause.is_open
            and event.type == pygame.MOUSEMOTION
            and self.focus_index != previous_focus
        ):
            self._focus(previous_focus)

    def _handle_match_event(self, event: pygame.event.Event) -> None:
        popup_before = self.match_screen.popup.kind
        self._dispatch_match_event(event)
        self._sync_match_pause_focus(popup_before)

    def _sync_match_pause_focus(self, before: str | None) -> None:
        """Open the match pause on KEEP PLAYING and restore the old focus on close."""
        after = self.match_screen.popup.kind
        if before == after or self.controller is None:
            return
        if after == "pause" and before is None:
            self.pause.saved_focus = self.focus_index
            self.focus_index = 0
        elif after == "pause":
            self.focus_index = {"depth": 1, "log": 2}.get(before, 0)
        elif after is None and before == "pause":
            self.focus_index = self.pause.saved_focus
        else:
            return
        self.buttons = []
        self.hover_index = None
        self.pressed_index = None

    def _dispatch_match_event(self, event: pygame.event.Event) -> None:
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
        if not self.pause.is_open:
            self._draw_screen(surface)
            return
        # Draw the screen underneath as it was left, then the menu on top.
        menu_focus, menu_hover, menu_pressed = self.focus_index, self.hover_index, self.pressed_index
        self.focus_index, self.hover_index, self.pressed_index = self.pause.saved_focus, None, None
        self._draw_screen(surface)
        self.focus_index, self.hover_index, self.pressed_index = menu_focus, menu_hover, menu_pressed
        entries = self.pause.entries(
            keep_playing=self._keep_playing,
            return_to_menu=self._return_to_menu,
            quit_run=self._quit_run,
        )
        buttons = draw_pause_menu(
            surface, self.pause, entries, focus_index=self.focus_index,
            hover_index=self.hover_index, pressed_index=self.pressed_index,
        )
        self._set_buttons(buttons)

    def _draw_screen(self, surface: pygame.Surface) -> None:
        state = self._current_state()
        if self._match_screen_active(state):
            self._draw_match_screen(surface, state)
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
                self._player_draft_view().draw_backdrop(surface, state)
                content = pygame.Rect(38, 122, 1204, 558)
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
            self.buttons = self._coach_view().draw(surface, content, state)
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
                self.buttons = buttons
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
                self.buttons = shop_buttons

        pause_rect = (
            pygame.Rect(1140, 20, 120, 36)
            if state.phase in (FootballRunPhase.COACH_DRAFT, FootballRunPhase.PLAYER_DRAFT)
            else pygame.Rect(content.right - 120, content.top, 120, 36)
            if depth_review or playbook_review
            else pygame.Rect(content.right - 120, 656, 120, 42)
            if state.phase is FootballRunPhase.PRE_MATCH_SHOP and self.shop_review.mode is None
            else pygame.Rect(layout.content.right - 118, layout.content.top, 118, 30)
        )
        shop_landing = (
            state.phase is FootballRunPhase.PRE_MATCH_SHOP and self.shop_review.mode is None
        )
        if not (depth_review and self.shop_review.team_popup):
            self.buttons.append(
                Button(PAUSE_LABEL, self._open_pause, pause_rect, variant=RUN_PAUSE_VARIANT)
            )
        self._set_buttons(self.buttons)
        self._draw_buttons(surface)
        if shop_landing and not self.pause.is_open:
            self._shop_view().draw_overlay(surface)
        if playbook_review and not self.pause.is_open:
            self.shop_review.inspect.paint(surface)
        if state.phase is FootballRunPhase.COACH_DRAFT and not self.pause.is_open:
            self._coach_view().draw_overlay(surface)
        if self.last_error is not None and state.phase in (
            FootballRunPhase.COACH_DRAFT, FootballRunPhase.PLAYER_DRAFT,
        ):
            draw_message_banner(surface, COACH_ERROR_RECT, f"CHECK: {self.last_error}", danger=True)
        elif self.last_error is not None and state.phase is not FootballRunPhase.PRE_MATCH_SHOP:
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

    def _draw_result_screen(
        self,
        surface: pygame.Surface,
        state: FootballGameControllerState,
    ) -> None:
        """Full-screen result: the view owns the backdrop, header, and every button."""
        buttons = self._result_view.draw(surface, state, self.theme, error=self.last_error)
        self._set_buttons(buttons)
        self._draw_buttons(surface)

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
            return_to_menu=self._return_to_menu,
            quit_run=self._quit_run,
        )
        buttons = self.match_screen.draw(
            surface, state, actions,
            focus_index=self.focus_index, hover_index=self.hover_index,
            pressed_index=self.pressed_index, error=self.last_error,
        )
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
            if button.variant == RUN_PAUSE_VARIANT:
                draw_pause_button(
                    surface, button, focused=button.focused,
                    hovered=self.hover_index == index, pressed=self.pressed_index == index,
                )
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
                self._coach_view().draw_button(
                    surface, button, index, pressed=self.pressed_index == index,
                )
                continue
            if button.variant == "draft-select":
                self._player_draft_view().draw_button(
                    surface, button, index, pressed=self.pressed_index == index,
                )
                continue

    def _new_coach_inspection(self) -> CoachInspection:
        return CoachInspection(inspect=InspectState(lambda: self._clock()))

    def _coach_view(self) -> FootballCoachView:
        return FootballCoachView(
            self.theme, self.coach_inspection, self.focus_index,
            lambda choice: self._submit(
                lambda: self._require_controller().choose_coach(choice)
            ),
            self.team_name,
        )

    def _player_draft_view(self) -> FootballPlayerDraftView:
        return FootballPlayerDraftView(
            self.theme, self.player_inspection, self.focus_index,
            lambda position, choice, appearance: self._submit(
                lambda: self._require_controller().choose_player(
                    position, choice, appearance=appearance
                )
            ),
            self.team_name,
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

    # -- pause menu and leaving the run ----------------------------------------------

    def _open_pause(self) -> None:
        state = self._current_state()
        if state.phase in ENDED_PHASES and not self._match_screen_active(state):
            return
        if self._match_screen_active(state):
            popup_before = self.match_screen.popup.kind
            self.match_screen.open_pause()
            self._sync_match_pause_focus(popup_before)
            return
        if state.phase is FootballRunPhase.PRE_MATCH_SHOP:
            self._shop_view().inspect.reset()
            self.shop_review.inspect.reset()
        self.coach_inspection.hover_index = None
        self.coach_inspection.reset_inspect()
        self.pause.show(self.focus_index)
        self.buttons = []
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None

    def _keep_playing(self) -> None:
        self.focus_index = self.pause.hide()
        self.buttons = []
        self.hover_index = None
        self.pressed_index = None

    def _return_to_menu(self) -> None:
        """Leave for the main menu, remembering the run unless it has ended."""
        if self._require_controller().state.phase in ENDED_PHASES:
            self._quit_run()
            return
        focus = self.pause.saved_focus
        self.pause.hide()
        self.match_screen.settle()
        self.state = self._require_controller().state
        self.pause.saved_focus = focus
        self.navigate("main_menu")

    def _quit_run(self) -> None:
        """QUIT RUN, or leaving a run that has ended: forget it and show the menu."""
        self._discard_run()
        self.navigate("main_menu")

    def _discard_run(self) -> None:
        self.pause.reset()
        self.match_screen.reset()
        self.controller = None
        self.state = None
        self._resume_focus = None
        self.buttons = []
        self.on_run_discarded()

    def _current_state(self) -> FootballGameControllerState:
        if self.state is None:
            raise RuntimeError("A football run has not been started.")
        return self.state

    def _require_controller(self) -> FootballGameController:
        if self.controller is None:
            raise RuntimeError("A football run has not been started.")
        return self.controller
