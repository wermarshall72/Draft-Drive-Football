"""The in-match screen: composes scoreboard, field, outcome strip, hands, piles, popups.

Rules stay in the controller. This module only reads controller state, replays
recorded events, and forwards the human's choices through ``MatchActions``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

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
from src.ui.football_match_hand import HandView
from src.ui.football_match_interaction import HandEvent, HandEventKind, MatchInteraction
from src.ui.football_match_outcome import (
    STRIP_HEIGHT,
    StripAction,
    StripCallbacks,
    decision_actions,
    draw_outcome_strip,
    draw_strip_button,
    status_prompt,
)
from src.ui.football_match_palette import (
    MATCH_CANVAS, MATCH_CANVAS_GLOW, MATCH_DANGER, MATCH_FOCUS, MATCH_INK, MATCH_PANEL,
    MATCH_PANEL_EDGE, MATCH_PANEL_HIGH, MATCH_TEXT, blit_text, match_font,
)
from src.ui.football_match_piles import draw_pile_panel
from src.ui.football_match_playback import EVENT_DURATION_MS, MatchPlayback
from src.ui.football_match_popups import (
    DEPTH, LOG, PAUSE, PILE, PopupState, draw_depth_popup, draw_log_popup,
    draw_pause_menu, draw_pile_popup, draw_popup_button,
)
from src.ui.football_match_scoreboard import SCOREBOARD_HEIGHT, draw_scoreboard
from src.ui.text import fit_text
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


@dataclass(frozen=True)
class MatchActions:
    play_card: Callable[[str], None]
    fallback: Callable[[bool], None]
    fourth_down: Callable[[FootballFourthDownAction], None]
    conversion: Callable[[FootballConversionAction, str | None], None]
    challenge: Callable[[bool], None]
    challenge_touchdown: Callable[[], None]
    end_run: Callable[[], None]


@lru_cache(maxsize=2)
def _backdrop(size: tuple[int, int]) -> pygame.Surface:
    """Navy stadium night: a soft glow under the lights and light-tower flares."""
    surface = pygame.Surface(size)
    surface.fill(MATCH_CANVAS)
    width, height = size
    glow = pygame.Surface(size, pygame.SRCALPHA)
    for radius, alpha in ((560, 22), (420, 26), (300, 30)):
        pygame.draw.ellipse(glow, (*MATCH_CANVAS_GLOW[:3], alpha),
                            pygame.Rect(width // 2 - radius, -radius // 2, radius * 2, radius))
    surface.blit(glow, (0, 0))
    for x in (40, width - 40):
        flare = pygame.Surface((180, 140), pygame.SRCALPHA)
        for radius, alpha in ((80, 18), (52, 26), (28, 40)):
            pygame.draw.circle(flare, (190, 220, 255, alpha), (90, 50), radius)
        surface.blit(flare, (x - 90, -20))
    # A faint crowd band behind the hands.
    for y in range(height - 260, height, 6):
        shade = 12 + (y % 18)
        pygame.draw.line(surface, (shade // 2, 20 + shade // 3, 40 + shade // 2), (0, y), (width, y), 1)
    return surface


class FootballMatchScreen:
    """Owns transient match UI state; recreated (via ``reset``) for each run."""

    def __init__(
        self,
        theme: Theme,
        small_font: pygame.font.Font,
        label_font: pygame.font.Font,
        clock: Callable[[], int] = pygame.time.get_ticks,
    ) -> None:
        self.theme = theme
        self._small_font = small_font
        self._label_font = label_font
        self.clock = clock
        self.reset()

    def reset(self) -> None:
        self.playback = MatchPlayback()
        self.interaction = MatchInteraction()
        self.popup = PopupState()
        self.hand = HandView()
        self._frozen_at: int | None = None
        self._popup_from_pause = False
        self._strip_actions: list[StripAction] = []
        self._selectable_cards: list[Button] = []
        self.buttons: list[Button] = []

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

    def open_pause(self) -> None:
        self._freeze()
        self.interaction.cancel_drag()
        self.popup.show(PAUSE)
        self._popup_from_pause = False

    def open_depth_chart(self) -> None:
        self._freeze()
        self._popup_from_pause = self.popup.kind == PAUSE
        self.popup.show(DEPTH)

    def open_play_log(self) -> None:
        self._freeze()
        self._popup_from_pause = self.popup.kind == PAUSE
        self.popup.show(LOG)

    def open_pile(self, pile_id: str) -> None:
        self._freeze()
        self.interaction.cancel_drag()
        self._popup_from_pause = False
        self.popup.show(PILE, pile_id)

    def close_popups(self) -> None:
        self.popup.close()
        self._popup_from_pause = False
        self._thaw()

    def back_from_popup(self) -> None:
        if self._popup_from_pause and self.popup.kind in (DEPTH, LOG):
            self.popup.show(PAUSE)
            self._popup_from_pause = False
            return
        self.close_popups()

    # -- input -------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> HandEvent:
        escape = event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
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
            if event.type == pygame.MOUSEMOTION:
                self.interaction.pointer = event.pos
            return HandEvent(HandEventKind.IGNORED)
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
        now = self.clock()
        if not self.popup.open:
            self.playback.sync(
                match, now, force_replay=match.status is FootballMatchStatus.COMPLETED
            )
        else:
            now = self._frozen_at if self._frozen_at is not None else now
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
        opponent_hand_rect = draw_scoreboard(
            surface, SCOREBOARD_RECT, display, self.theme,
            game_number=state.game_number, wins=state.wins, losses=state.losses,
            kickoff_next=kicking_next is not None,
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
        )

        callbacks = StripCallbacks(
            actions.fourth_down, actions.conversion, actions.challenge, actions.challenge_touchdown,
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
        current_outcome = (
            outcome(events[-1], events[-2] if len(events) > 1 else None,
                    match.team_a.team_name, match.team_b.team_name)
            if events else None
        )
        rects = draw_outcome_strip(
            surface, STRIP_RECT, current_outcome, prompt=prompt, actions=strip_actions,
            playback_label=playback_label, elapsed_ms=elapsed,
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
                self._draw_pause_button(
                    surface, button, focused=focus_index == index,
                    hovered=hover_index == index, pressed=pressed_index == index,
                )
        if blocked:
            self._draw_post_replay_marks(surface, opponent_hand_rect)
        if error:
            self._draw_error(surface, error)

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
        if kind == PAUSE:
            buttons = draw_pause_menu(
                surface, resume=self.close_popups, depth_chart=self.open_depth_chart,
                play_log=self.open_play_log, end_run=actions.end_run,
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

    @staticmethod
    def _draw_pause_button(
        surface: pygame.Surface, button: Button, *, focused: bool, hovered: bool, pressed: bool
    ) -> None:
        rect = button.rect.move(0, 1) if pressed else button.rect
        fill = MATCH_PANEL_HIGH if hovered or focused else MATCH_PANEL
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        pygame.draw.rect(surface, MATCH_FOCUS if focused else MATCH_PANEL_EDGE, rect,
                         2 if focused else 1, border_radius=6)
        font = match_font(12)
        label = font.render("PAUSE [ESC]", True, MATCH_TEXT)
        surface.blit(label, label.get_rect(center=rect.center))

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
