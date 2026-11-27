"""The in-match screen: composes scoreboard, field, outcome strip, hands, piles, popups.

Rules stay in the controller. This module only reads controller state, replays
recorded events, and forwards the human's choices through ``MatchActions``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from src.engine.football import (
    FootballConversionAction,
    FootballFourthDownAction,
    FootballMatchState,
    FootballMatchStatus,
)
from src.engine.football_controller import FootballGameControllerState, FootballRunPhase
from src.ui.football_match_events import (
    latest_play_line,
    outcome,
    kickoff_pending,
    period_banner,
    replay_label,
    snapshot_state,
)
from src.ui.football_match_field import FIELD_HEIGHT, FieldOverlay, draw_match_field
from src.ui.football_inspect import InspectState
from src.ui.football_match_hand import HandView
from src.ui.football_match_interaction import HandEvent, HandEventKind, MatchInteraction
from src.ui.football_match_outcome import (
    STRIP_HEIGHT,
    StripAction,
    StripCallbacks,
    decision_actions,
    draw_outcome_strip,
    draw_strip_button,
    prompt_lines,
    status_prompt,
)
from src.ui.football_match_palette import (
    MATCH_CANVAS, MATCH_DANGER, MATCH_INK, MATCH_MUTED, MATCH_PANEL, MATCH_PANEL_DEEP,
    MATCH_PANEL_EDGE, MATCH_TEXT, blit_text, match_font, plain_font,
)
from src.ui.football_match_perks import (
    TrayPerk, draw_green_dog_panel, draw_perk_popup, draw_perk_tray, draw_read_keys_panel,
    draw_tray_tooltip, has_read_keys, tray_perks,
)
from src.ui.football_match_piles import draw_pile_panel
from src.engine.football_controller import FootballHumanDecision
from src.ui.football_match_playback import EVENT_DURATION_MS, MatchPlayback
from src.ui.football_match_popups import (
    DEPTH, LOG, PAUSE, PILE, PopupState, draw_depth_popup, draw_log_popup,
    draw_pile_popup, draw_popup_button,
)
from src.ui.football_pause_menu import (
    DEPTH_CHART, PLAY_LOG, MenuEntry, PauseMenu, draw_pause_audio, draw_pause_button,
    draw_pause_menu,
)
from src.ui.football_match_scoreboard import SCOREBOARD_HEIGHT, draw_scoreboard
from src.ui.football_ui_kit import stadium_backdrop
from src.ui.text import fit_text
from src.ui.football_ai_team_colors import opponent_colors
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button

MARGIN = 16
GAP = 8
SCOREBOARD_RECT = pygame.Rect(MARGIN, 8, 1280 - MARGIN * 2, SCOREBOARD_HEIGHT)
FIELD_RECT = pygame.Rect(MARGIN, SCOREBOARD_RECT.bottom + GAP, 1280 - MARGIN * 2, FIELD_HEIGHT)
STRIP_RECT = pygame.Rect(MARGIN, FIELD_RECT.bottom + 6, 1280 - MARGIN * 2, STRIP_HEIGHT)
BOTTOM_TOP = STRIP_RECT.bottom + GAP
BOTTOM_HEIGHT = 720 - 8 - BOTTOM_TOP
LEFT_PILES_RECT = pygame.Rect(MARGIN, BOTTOM_TOP, 256 - MARGIN - 8, BOTTOM_HEIGHT)
HAND_RECT = pygame.Rect(256, BOTTOM_TOP, 768, BOTTOM_HEIGHT)
RIGHT_PILES_RECT = pygame.Rect(1024 + 8, BOTTOM_TOP, 256 - MARGIN - 8, BOTTOM_HEIGHT)
POST_REPLAY_NOTE = "HANDS & PILES UPDATE AFTER REPLAY"
GROUP_NOTE_OFFSET = 120
PAUSE_RECT = pygame.Rect(SCOREBOARD_RECT.centerx + 94, SCOREBOARD_RECT.top + 10, 84, 26)
# Every perk the human's roster carries, in the team block between the score and the
# clock panel: offense chips on the top row, defense chips below.
PERK_TRAY_RECT = pygame.Rect(SCOREBOARD_RECT.left + 190, SCOREBOARD_RECT.top + 36, 250, 48)
# The tray's hover tooltip and click popup sit just under the scoreboard, over the field.
PERK_OVERLAY_TOP = SCOREBOARD_RECT.bottom + 4
PERK_CHIP_VARIANT = "perk-chip"


@dataclass(frozen=True)
class MatchActions:
    play_card: Callable[[str], None]
    fallback: Callable[[bool], None]
    fourth_down: Callable[[FootballFourthDownAction], None]
    conversion: Callable[[FootballConversionAction, str | None], None]
    challenge: Callable[[bool], None]
    challenge_touchdown: Callable[[], None]
    return_to_menu: Callable[[], None]
    quit_run: Callable[[], None]
    green_dog: Callable[[str | None], None] = lambda _copy_id: None


_backdrop = stadium_backdrop


class FootballMatchScreen:
    """Owns transient match UI state; recreated (via ``reset``) for each run."""

    def __init__(
        self,
        theme: Theme,
        small_font: pygame.font.Font,
        label_font: pygame.font.Font,
        clock: Callable[[], int] = pygame.time.get_ticks,
        pause_menu: PauseMenu | None = None,
    ) -> None:
        self.theme = theme
        self._small_font = small_font
        self._label_font = label_font
        self.clock = clock
        self.pause_menu = pause_menu or PauseMenu(clock)
        self.reset()

    def reset(self) -> None:
        self.playback = MatchPlayback()
        self.interaction = MatchInteraction()
        self.popup = PopupState()
        self.hand = HandView()
        # Hover/focus tooltip for offense cards, after the shop's inspect delay.
        self.card_tip = InspectState(lambda: self.clock())
        self.card_tip_rect: pygame.Rect | None = None
        # The perk tray: hover tooltip (same delay) and the click/Enter rules popup.
        self.perk_tip = InspectState(lambda: self.clock())
        self.perk_tip_rect: pygame.Rect | None = None
        self.perk_popup_key: tuple[str, str] | None = None
        self.perk_popup_rect: pygame.Rect | None = None
        self._tray: list[tuple[TrayPerk, pygame.Rect]] = []
        self._frozen_at: int | None = None
        self.read_keys_hidden = False
        self._popup_from_pause = False
        self._strip_actions: list[StripAction] = []
        self._selectable_cards: list[Button] = []
        self.buttons: list[Button] = []
        self.pause_menu.reset()

    def settle(self) -> None:
        """Leave the match for the menu: close popups and finish any replay."""
        self.close_perk_popup()
        self.close_popups()
        self.interaction.cancel_drag()
        self.pause_menu.reset()
        if self.playback.blocking():
            self.playback.skip()

    # -- state -------------------------------------------------------------------

    def holds_final_playback(self, state: FootballGameControllerState) -> bool:
        """Keep showing a finished match until its last events have replayed."""
        match = state.match
        if match is None or state.phase is FootballRunPhase.MATCH:
            return False
        if match.status is not FootballMatchStatus.COMPLETED:
            return False
        if self.playback.match_key != MatchPlayback._key(match):
            return False
        if not self.popup.open:
            self.playback.sync(match, self.clock(), force_replay=True)
        return self.playback.blocking() or self.playback.target < len(match.match_events)

    def sync_playback(self, match: FootballMatchState) -> int:
        """Start or advance this frame's replay; returns the (frozen) time used.

        Idempotent within a frame, so callers can sync before drawing (one-time
        tips must know whether a replay is about to block input).
        """
        now = self.clock()
        if not self.popup.open:
            self.playback.sync(
                match, now, force_replay=match.status is FootballMatchStatus.COMPLETED
            )
            return now
        return self._frozen_at if self._frozen_at is not None else now

    def input_blocked(self) -> bool:
        return self.playback.blocking()

    def display_match(self, match: FootballMatchState) -> FootballMatchState:
        if self.playback.shown <= 0 or self.playback.match_key != MatchPlayback._key(match):
            return match
        return snapshot_state(match, self.playback.shown)

    # -- popups ------------------------------------------------------------------

    def _freeze(self) -> None:
        if self._frozen_at is None:
            self._frozen_at = self.clock()

    def _thaw(self) -> None:
        if self._frozen_at is not None:
            self.playback.step_started += self.clock() - self._frozen_at
            self._frozen_at = None

    # -- the perk tray's rules popup ----------------------------------------------

    def toggle_perk_popup(self, key: tuple[str, str]) -> None:
        """Open a chip's rules popup, or close it when that chip's popup is open."""
        self.perk_popup_key = None if self.perk_popup_key == key else key
        self.perk_tip.reset()

    def close_perk_popup(self) -> None:
        self.perk_popup_key = None
        self.perk_popup_rect = None

    def _handle_perk_popup_event(self, event: pygame.event.Event) -> HandEvent | None:
        """While the rules popup is open it takes every key but Tab and every click.

        Esc, Enter, and Space close it; a click on a chip switches to (or closes)
        that chip's popup; any other click closes it. Nothing reaches the hand or
        strip, so the popup never makes a match decision or advances a replay.
        """
        if self.perk_popup_key is None or self.popup.open:
            return None
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                return None
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.close_perk_popup()
            return HandEvent(HandEventKind.HANDLED)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button != 1:
                return HandEvent(HandEventKind.HANDLED)
            chip = next((item for item, rect in self._tray if rect.collidepoint(event.pos)), None)
            if chip is not None:
                self.toggle_perk_popup(chip.key)
            elif self.perk_popup_rect is None or not self.perk_popup_rect.collidepoint(event.pos):
                self.close_perk_popup()
            return HandEvent(HandEventKind.HANDLED)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return HandEvent(HandEventKind.HANDLED)
        return None

    def open_pause(self) -> None:
        self.close_perk_popup()
        self._freeze()
        self.interaction.cancel_drag()
        self.pause_menu.leave_audio()
        self.popup.show(PAUSE)
        self._popup_from_pause = False

    def open_depth_chart(self) -> None:
        self.close_perk_popup()
        self._freeze()
        self.pause_menu.cancel_quit()
        self._popup_from_pause = self.popup.kind == PAUSE
        self.popup.show(DEPTH)

    def open_play_log(self) -> None:
        self.close_perk_popup()
        self._freeze()
        self.pause_menu.cancel_quit()
        self._popup_from_pause = self.popup.kind == PAUSE
        self.popup.show(LOG)

    def open_pile(self, pile_id: str) -> None:
        self.close_perk_popup()
        self._freeze()
        self.interaction.cancel_drag()
        self._popup_from_pause = False
        self.popup.show(PILE, pile_id)

    def close_popups(self) -> None:
        self.pause_menu.cancel_quit()
        self.pause_menu.leave_audio()
        self.popup.close()
        self._popup_from_pause = False
        self._thaw()

    def back_from_popup(self) -> None:
        if self.popup.kind == PAUSE and self.pause_menu.audio_open:
            self.pause_menu.close_audio()
            return
        if self.popup.kind == PAUSE and self.pause_menu.cancel_quit():
            return
        if self.popup.kind == DEPTH and self.popup.review.team_popup:
            self.popup.review.close_team_upgrades()
            return
        if self._popup_from_pause and self.popup.kind in (DEPTH, LOG):
            self.popup.show(PAUSE)
            self._popup_from_pause = False
            return
        self.close_popups()

    # -- input -------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> HandEvent:
        escape = event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
        perk_popup = self._handle_perk_popup_event(event)
        if perk_popup is not None:
            return perk_popup
        if not self.popup.open and self.perk_tip.handle_event(event):
            return HandEvent(HandEventKind.HANDLED)  # Esc hid a visible perk tooltip
        if not self.popup.open and self.card_tip.handle_event(event):
            return HandEvent(HandEventKind.HANDLED)  # Esc hid a visible card tooltip
        if self.popup.open:
            if escape:
                self.back_from_popup()
                return HandEvent(HandEventKind.HANDLED)
            if self.popup.handle_scroll(event):
                return HandEvent(HandEventKind.HANDLED)
            return HandEvent(HandEventKind.IGNORED)
        if escape:
            self.open_pause()
            return HandEvent(HandEventKind.HANDLED)
        if self.playback.blocking():
            if event.type == pygame.KEYDOWN and event.key == pygame.K_s:
                self.playback.skip()
                return HandEvent(HandEventKind.HANDLED)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                return HandEvent(HandEventKind.HANDLED)
            if event.type == pygame.MOUSEMOTION:
                self.interaction.pointer = event.pos
            return HandEvent(HandEventKind.IGNORED)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            self.read_keys_hidden = not self.read_keys_hidden  # show or hide Read Keys
            return HandEvent(HandEventKind.HANDLED)
        if event.type == pygame.KEYDOWN and pygame.K_1 <= event.key <= pygame.K_9:
            index = event.key - pygame.K_1
            targets = self.shortcut_targets()
            if index < len(targets):
                targets[index].action()
                return HandEvent(HandEventKind.HANDLED)
        return self.interaction.handle_event(event)

    def shortcut_targets(self) -> list[Button]:
        """Number keys 1-9: outcome-strip buttons first, then playable cards and fallbacks."""
        strip = [button for button in self.buttons if button.variant.startswith("strip")]
        cards = [button for button in self._selectable_cards if button.enabled]
        return strip + cards

    # -- drawing -----------------------------------------------------------------

    def draw(
        self,
        surface: pygame.Surface,
        state: FootballGameControllerState,
        actions: MatchActions,
        *,
        focus_index: int,
        hover_index: int | None,
        pressed_index: int | None,
        error: str | None,
    ) -> list[Button]:
        match = state.match
        if match is None:
            raise RuntimeError("The controller did not provide an active match state.")
        now = self.sync_playback(match)
        display = self.display_match(match)
        kicking_next = (
            kickoff_pending(match, self.playback.shown)
            if self.playback.match_key == MatchPlayback._key(match)
            and display.conversion_team is None
            else None
        )
        blocked = self.playback.blocking()
        if blocked or self.popup.open:
            self.interaction.cancel_drag()

        surface.blit(_backdrop(surface.get_size()), (0, 0))
        opponent = opponent_colors(state.opponent_team)
        opponent_hand_rect = draw_scoreboard(
            surface, SCOREBOARD_RECT, display, self.theme,
            game_number=state.game_number, wins=state.wins, losses=state.losses,
            kickoff_next=kicking_next is not None, opponent=opponent,
        )

        events = display.match_events
        current_index = len(events) - 1
        latest = latest_play_line(events)
        line = latest[1] if latest is not None else None
        line_is_current = latest is not None and latest[0] == current_index
        elapsed = max(0, now - self.playback.step_started)
        banner = None
        if events and elapsed < EVENT_DURATION_MS + 300:
            banner = period_banner(events[-1], events[-2] if len(events) > 1 else None)
            if banner == "FINAL" and match.status is not FootballMatchStatus.COMPLETED:
                banner = None
        overlay = FieldOverlay(
            line=line,
            line_progress=self.playback.line_progress(now) if line_is_current else 1.0,
            flash_elapsed_ms=elapsed if line_is_current else None,
            banner=banner,
            drop_hint=self.interaction.dragging and not blocked,
        )
        draw_match_field(
            surface, FIELD_RECT, display, self.theme.primary, overlay,
            human_scheme_highlight=True, kickoff_pending=kicking_next is not None,
            opponent=opponent,
            opponent_short=(
                state.opponent_team.abbreviation if state.opponent_team is not None else None
            ),
        )
        decision = state.human_decision
        if not blocked and not self.popup.open:
            if decision is FootballHumanDecision.GREEN_DOG:
                draw_green_dog_panel(surface, FIELD_RECT, match)
            elif (
                decision is FootballHumanDecision.DEFENSIVE_SCHEME
                and has_read_keys(match)
                and not self.read_keys_hidden
            ):
                draw_read_keys_panel(surface, FIELD_RECT, match)

        callbacks = StripCallbacks(
            actions.fourth_down, actions.conversion, actions.challenge, actions.challenge_touchdown,
            actions.green_dog,
        )
        if blocked:
            prompt = ""
            strip_actions = [StripAction("SKIP >>", self.playback.skip, "strip-skip")]
            playback_label = replay_label(
                match.match_events, self.playback.origin, self.playback.shown, self.playback.target
            )
        else:
            prompt, strip_actions = decision_actions(state, callbacks)
            prompt = prompt or status_prompt(state)
            playback_label = None
        sub_lines = () if blocked else prompt_lines(state)
        current_outcome = (
            outcome(events[-1], events[-2] if len(events) > 1 else None,
                    match.team_a.team_name, match.team_b.team_name)
            if events else None
        )
        self.strip_prompt_width = max(
            [match_font(14).size(prompt)[0] if prompt else 0]
            + [plain_font(12).size(line)[0] for line in sub_lines]
        )
        rects = draw_outcome_strip(
            surface, STRIP_RECT, current_outcome, prompt=prompt, actions=strip_actions,
            playback_label=playback_label, elapsed_ms=elapsed, sub_lines=sub_lines,
        )
        buttons: list[Button] = [
            Button(action.label, action.callback, rect, enabled=action.enabled, variant=action.variant)
            for action, rect in zip(strip_actions, rects)
        ]
        self._strip_actions = strip_actions

        self.interaction.play_areas = (FIELD_RECT, STRIP_RECT)
        hand_buttons = self.hand.draw(
            surface, HAND_RECT, state, display, self.interaction,
            input_blocked=blocked,
            focus_index=focus_index, hover_index=hover_index, pressed_index=pressed_index,
            button_offset=len(buttons),
            choose_card=actions.play_card,
            choose_fallback=actions.fallback,
        )
        self._selectable_cards = [
            button for button in hand_buttons if button.variant in ("hand-card", "hand-fallback")
        ]
        buttons.extend(hand_buttons)
        buttons.extend(self._draw_tray(surface, display, len(buttons), focus_index, hover_index))

        offense_deck, defense_deck = match.team_a_offense_deck, match.team_a_defense_deck
        assert offense_deck is not None and defense_deck is not None
        initial = (match.team_a.team_name.strip()[:1] or "?").upper()
        for rect, deck, offensive in (
            (LEFT_PILES_RECT, offense_deck, True),
            (RIGHT_PILES_RECT, defense_deck, False),
        ):
            buttons.extend(
                draw_pile_panel(
                    surface, rect, deck, offensive=offensive,
                    back_color=self.theme.primary, back_ink=readable_ink(self.theme.primary),
                    initial=initial, focus_index=focus_index, hover_index=hover_index,
                    button_offset=len(buttons), open_pile=self.open_pile, enabled=True,
                )
            )
        buttons.append(Button("PAUSE", self.open_pause, PAUSE_RECT, variant="match-pause"))

        for index, button in enumerate(buttons):
            if button.variant.startswith("strip"):
                shortcut = index + 1 if not blocked else None
                draw_strip_button(
                    surface, button, shortcut=shortcut, focused=focus_index == index,
                    hovered=hover_index == index, pressed=pressed_index == index,
                )
            elif button.variant == "match-pause":
                draw_pause_button(
                    surface, button, focused=focus_index == index,
                    hovered=hover_index == index, pressed=pressed_index == index,
                )
        if blocked:
            self._draw_post_replay_marks(surface, opponent_hand_rect)
        if error:
            self._draw_error(surface, error)
        self.card_tip_rect = None
        if not blocked and not self.popup.open and not self.suppress_card_tip:
            self._draw_card_tooltip(surface, display, buttons, focus_index, hover_index)
        else:
            self.card_tip.reset()
        self._draw_perk_overlays(surface, display, buttons, focus_index, hover_index)

        if self.popup.open:
            buttons = self._draw_popup(surface, state, display, focus_index, hover_index, pressed_index, actions)
        self.buttons = buttons
        return buttons

    def _draw_popup(
        self,
        surface: pygame.Surface,
        state: FootballGameControllerState,
        display: FootballMatchState,
        focus_index: int,
        hover_index: int | None,
        pressed_index: int | None,
        actions: MatchActions,
    ) -> list[Button]:
        kind = self.popup.kind
        match = state.match
        assert match is not None
        if kind == PAUSE and self.pause_menu.audio_open:
            return draw_pause_audio(
                surface, self.pause_menu, focus_index=focus_index,
                hover_index=hover_index, pressed_index=pressed_index,
            )
        if kind == PAUSE:
            entries = self.pause_menu.entries(
                keep_playing=self.close_popups,
                return_to_menu=actions.return_to_menu,
                quit_run=actions.quit_run,
                extra=(MenuEntry(DEPTH_CHART, self.open_depth_chart),
                       MenuEntry(PLAY_LOG, self.open_play_log)),
            )
            return draw_pause_menu(
                surface, self.pause_menu, entries, focus_index=focus_index,
                hover_index=hover_index, pressed_index=pressed_index,
            )
        elif kind == DEPTH:
            buttons = draw_depth_popup(
                surface, state, self.theme, self._small_font, self._label_font,
                self.popup, self.back_from_popup,
            )
            for index, button in enumerate(buttons):
                button.focused = focus_index == index
                button.draw(surface, self._label_font, self.theme,
                            hovered=hover_index == index, pressed=pressed_index == index)
            return buttons
        elif kind == LOG:
            buttons = draw_log_popup(surface, display, self.popup, self.back_from_popup)
        else:
            buttons = draw_pile_popup(surface, match, self.popup, self.back_from_popup)
        for index, button in enumerate(buttons):
            draw_popup_button(surface, button, focused=focus_index == index,
                              hovered=hover_index == index, pressed=pressed_index == index)
        return buttons

    def _draw_tray(
        self, surface: pygame.Surface, display: FootballMatchState, offset: int,
        focus_index: int, hover_index: int | None,
    ) -> list[Button]:
        """The perk chips, focusable right after the hand; each opens its rules popup."""
        def local(index: int | None) -> int | None:
            return index - offset if index is not None and index >= offset else None

        keys = [item.key for item in tray_perks(display)]
        if self.perk_popup_key is not None and self.perk_popup_key not in keys:
            self.close_perk_popup()
        open_index = keys.index(self.perk_popup_key) if self.perk_popup_key in keys else None
        self._tray = draw_perk_tray(
            surface, PERK_TRAY_RECT, display,
            focused=local(focus_index), hovered=local(hover_index), open_index=open_index,
        )
        return [
            Button(f"PERK {item.perk.name.upper()}", lambda key=item.key: self.toggle_perk_popup(key),
                   rect, variant=PERK_CHIP_VARIANT)
            for item, rect in self._tray
        ]

    def _draw_perk_overlays(
        self, surface: pygame.Surface, display: FootballMatchState, buttons: list[Button],
        focus_index: int, hover_index: int | None,
    ) -> None:
        """The tray's open rules popup, or its hover tooltip, just under the scoreboard."""
        self.perk_tip_rect = None
        self.perk_popup_rect = None
        if self.popup.open or not self._tray:
            self.perk_tip.reset()
            return
        by_key = {item.key: (item, rect) for item, rect in self._tray}
        if self.perk_popup_key is not None:
            self.perk_tip.reset()
            item, rect = by_key[self.perk_popup_key]
            self.perk_popup_rect = draw_perk_popup(
                surface, item, display, (rect.left - 12, PERK_OVERLAY_TOP),
            )
            return
        chip_keys = {
            index: item.key
            for index, (item, _rect) in enumerate(self._tray, start=self._tray_offset(buttons))
        }
        shown = self.perk_tip.update(
            chip_keys.get(hover_index) if hover_index is not None else None,
            chip_keys.get(focus_index),
        )
        self.perk_tip.shown_key = shown
        if shown is None:
            return
        item, rect = by_key[shown]
        self.perk_tip_rect = draw_tray_tooltip(surface, item, rect, PERK_OVERLAY_TOP)

    @staticmethod
    def _tray_offset(buttons: list[Button]) -> int:
        return next(
            (index for index, button in enumerate(buttons) if button.variant == PERK_CHIP_VARIANT),
            len(buttons),
        )

    suppress_card_tip = False  # set while a one-time tip occupies the strip
    strip_prompt_width = 0  # this frame's strip prompt width (one-time tips stay clear)

    def _draw_card_tooltip(
        self,
        surface: pygame.Surface,
        display: FootballMatchState,
        buttons: list[Button],
        focus_index: int,
        hover_index: int | None,
    ) -> None:
        targets = self.hand.tooltip_targets or {}

        def key(index: int | None):
            target = targets.get(index) if index is not None else None
            return target[0] if target is not None else None

        shown = self.card_tip.update(key(hover_index), key(focus_index))
        self.card_tip.shown_key = shown
        if shown is None:
            return
        _copy_id, card_id, anchor = next(
            target for target in targets.values() if target[0] == shown
        )
        lines = self.hand.card_tooltip(display, card_id)
        if not lines:
            return
        strip_buttons = [b.rect for b in buttons if b.variant.startswith("strip")]
        limit = min((rect.left for rect in strip_buttons), default=STRIP_RECT.right) - 8
        self.card_tip_rect = draw_card_tooltip(surface, lines, anchor, right_limit=limit)

    @staticmethod
    def _draw_post_replay_marks(surface: pygame.Surface, opponent_hand: pygame.Rect) -> None:
        """Events carry no deck snapshots, so mid-replay hands, piles, and opponent
        counts already show the post-replay state; dim them and say so once."""
        for area, alpha in (
            (HAND_RECT, 120), (LEFT_PILES_RECT, 110), (RIGHT_PILES_RECT, 110),
            (opponent_hand.inflate(6, 6), 130),
        ):
            veil = pygame.Surface(area.size, pygame.SRCALPHA)
            veil.fill((*MATCH_CANVAS[:3], alpha))
            surface.blit(veil, area.topleft)
        font = match_font(13)
        text = POST_REPLAY_NOTE
        plate = pygame.Rect((0, 0), font.size(text)).inflate(22, 10)
        plate.center = (HAND_RECT.centerx, HAND_RECT.top + GROUP_NOTE_OFFSET)
        pygame.draw.rect(surface, MATCH_INK, plate.inflate(2, 2), border_radius=9)
        pygame.draw.rect(surface, MATCH_PANEL, plate, border_radius=8)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE, plate, 1, border_radius=8)
        blit_text(surface, font, text, MATCH_TEXT, HAND_RECT, center=plate.center)

    @staticmethod
    def _draw_error(surface: pygame.Surface, message: str) -> None:
        font = match_font(14)
        text = fit_text(f"CHECK: {message}", font, HAND_RECT.width - 40)
        rendered = font.render(text, True, MATCH_INK)
        plate = rendered.get_rect().inflate(24, 10)
        plate.midtop = (HAND_RECT.centerx, STRIP_RECT.bottom - 4)
        pygame.draw.rect(surface, MATCH_DANGER, plate, border_radius=8)
        surface.blit(rendered, rendered.get_rect(center=plate.center))


TOOLTIP_FONT_SIZE = 13


def draw_card_tooltip(
    surface: pygame.Surface,
    lines: tuple[str, ...],
    anchor: pygame.Rect,
    *,
    right_limit: int = STRIP_RECT.right,
) -> pygame.Rect:
    """A compact two-by-two tooltip over the outcome strip, above the hovered card.

    It sits inside the strip so it never covers the hand or the field, and it never
    takes clicks. The last line (the rival's call is secret) is muted.
    """
    font = plain_font(TOOLTIP_FONT_SIZE, False)
    pad, gap = 14, 22
    left_column = (lines[0], lines[1])
    right_column = tuple(lines[2:4])
    max_width = max(200, right_limit - STRIP_RECT.left - 8)
    left_width = max(font.size(line)[0] for line in left_column)
    right_width = min(
        max(font.size(line)[0] for line in right_column),
        max_width - left_width - gap - pad * 2,
    )
    rect = pygame.Rect(0, 0, pad * 2 + left_width + gap + right_width, STRIP_RECT.height - 8)
    rect.centerx = anchor.centerx
    rect.centery = STRIP_RECT.centery
    rect.right = min(rect.right, right_limit)
    rect.left = max(rect.left, STRIP_RECT.left + 4)
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=10)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=10)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=10)
    row_height = font.get_height() + 4
    top = rect.centery - row_height
    for column, (x, width) in enumerate(
        ((rect.left + pad, left_width), (rect.left + pad + left_width + gap, right_width))
    ):
        for row, line in enumerate(left_column if column == 0 else right_column):
            color = MATCH_TEXT
            if column == 1 and row == 1:
                color = MATCH_MUTED
            box = pygame.Rect(x, top + row * row_height, width, row_height)
            blit_text(surface, font, fit_text(line, font, width), color, box,
                      midleft=(x, box.centery))
    return rect
