"""Match hand and decision presentation with explicit action callbacks."""

from collections.abc import Callable

import pygame

from src.engine.football import (
    FootballBonusCardAction,
    FootballConversionAction,
    FootballFourthDownAction,
    FootballTeamSide,
)
from src.engine.football_controller import FootballGameControllerState, FootballHumanDecision
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)
from src.engine.football_simulator import (
    adjusted_offensive_play_clock_seconds,
    calculate_match_play_estimate,
)
from src.ui.football_display import _POSITION_LABELS
from src.ui.football_match_interaction import MatchInteraction
from src.ui.football_match_palette import (
    MATCH_PANEL as _MATCH_PANEL, MATCH_PANEL_EDGE as _MATCH_PANEL_EDGE,
    MATCH_CHALK as _MATCH_CHALK, MATCH_MUTED as _MATCH_MUTED,
    MATCH_BRASS as _MATCH_BRASS, MATCH_INK as _MATCH_INK,
    MATCH_FOCUS as _MATCH_FOCUS,
)
from src.ui.text import fit_text as _fit_text
from src.ui.widgets import Button, draw_text

class FootballMatchDecisionView:
    def __init__(
        self, small_font: pygame.font.Font, label_font: pygame.font.Font,
        interaction: MatchInteraction, focus_index: int, hover_index: int | None,
        pressed_index: int | None, choose_card: Callable[[str], None],
        choose_fourth_down: Callable[[FootballFourthDownAction], None],
        choose_conversion: Callable[[FootballConversionAction, str | None], None],
        choose_fallback: Callable[[bool], None],
        choose_challenge: Callable[[bool], None] | None = None,
        challenge_touchdown: Callable[[], None] | None = None,
    ) -> None:
        self._small_font = small_font
        self._label_font = label_font
        self.match_interaction = interaction
        self.focus_index = focus_index
        self.hover_index = hover_index
        self.pressed_index = pressed_index
        self.choose_card = choose_card
        self.choose_fourth_down = choose_fourth_down
        self.choose_conversion = choose_conversion
        self.choose_fallback = choose_fallback
        self.choose_challenge = choose_challenge
        self.challenge_touchdown = challenge_touchdown

    def draw(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        state: FootballGameControllerState,
    ) -> list[Button]:
        decision = state.human_decision
        if decision is FootballHumanDecision.OFFENSIVE_PLAY:
            return self._draw_hand(surface, rect, state, offensive=True)
        elif decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            return self._draw_hand(surface, rect, state, offensive=False)
        elif decision is FootballHumanDecision.FOURTH_DOWN:
            heading = "FOURTH DOWN   /   MAKE THE CALL"
            actions = [
                (
                    action.value.replace("_", " ").upper(),
                    lambda action=action: self.choose_fourth_down(action),
                )
                for action in FootballFourthDownAction
            ]
        elif decision is FootballHumanDecision.CONVERSION:
            heading = "TOUCHDOWN   /   CHOOSE YOUR CONVERSION"
            actions = [
                (
                    "EXTRA POINT",
                    lambda: self.choose_conversion(FootballConversionAction.EXTRA_POINT, None),
                ),
            ]
            match = state.match
            if match is None:
                raise RuntimeError("The controller did not provide an active match state.")
            deck = match.team_a_offense_deck
            if deck is None:
                raise RuntimeError("The human offensive deck is not initialized.")
            playable_cards = tuple(
                card
                for card in deck.hand
                if card.card_id in OFFENSIVE_PLAY_CATALOG
            )
            if playable_cards:
                actions.extend(
                    (
                        f"2PT: {OFFENSIVE_PLAY_CATALOG[card.card_id].name}",
                        lambda card_id=card.copy_id: self.choose_conversion(
                            FootballConversionAction.TWO_POINT, card_id
                        ),
                    )
                    for card in playable_cards
                )
            else:
                actions.append(
                    (
                        "2PT: BASIC RUN",
                        lambda: self.choose_conversion(FootballConversionAction.TWO_POINT, None),
                    )
                )
            if state.challenge_available:
                challenge_touchdown = self.challenge_touchdown
                if challenge_touchdown is None:
                    raise RuntimeError(
                        "The conversion view requires a touchdown Challenge callback."
                    )
                actions.append(
                    (
                        "CHALLENGE / RESTORE TOUCHDOWN",
                        challenge_touchdown,
                    )
                )
        elif decision is FootballHumanDecision.CHALLENGE:
            choose_challenge = self.choose_challenge
            if choose_challenge is None:
                raise RuntimeError("The view requires a challenge-response callback.")
            heading = "TURNOVER / FAILED FOURTH DOWN  /  CHALLENGE?"
            actions = [
                (
                    "CHALLENGE / RESTORE THE LAST PLAY",
                    lambda: choose_challenge(True),
                ),
                (
                    "DECLINE / CONTINUE THE MATCH",
                    lambda: choose_challenge(False),
                ),
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
        self.match_interaction.hand_area = None
        self.match_interaction.card_rects = {}
        self.match_interaction.play_area = None
        call_rect = pygame.Rect(
            rect.left,
            rect.top + 24,
            rect.width,
            max(1, rect.height - 25),
        )
        buttons: list[Button] = []
        if not actions:
            draw_text(
                surface,
                "The next snap is being set.",
                (rect.left + 2, rect.top + 34),
                self._small_font,
                _MATCH_MUTED,
            )
            return buttons

        gap_x = 10
        gap_y = 8
        columns = min(3, len(actions))
        rows = (len(actions) + columns - 1) // columns
        button_width = (call_rect.width - gap_x * (columns - 1)) // columns
        button_height = (call_rect.height - gap_y * (rows - 1)) // rows
        for index, (label, callback) in enumerate(actions):
            row, column = divmod(index, columns)
            button_rect = pygame.Rect(
                call_rect.left + column * (button_width + gap_x),
                call_rect.top + row * (button_height + gap_y),
                button_width,
                button_height,
            )
            buttons.append(Button(label, callback, button_rect))
        return buttons

    def _draw_hand(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        state: FootballGameControllerState,
        *,
        offensive: bool,
    ) -> list[Button]:
        match = state.match
        if match is None:
            raise RuntimeError("The controller did not provide an active match state.")
        deck = (
            match.team_a_offense_deck
            if offensive
            else match.team_a_defense_deck
        )
        if deck is None:
            raise RuntimeError("The controller did not provide the human's match deck.")
        catalog = OFFENSIVE_PLAY_CATALOG if offensive else DEFENSIVE_SCHEME_CATALOG

        draw_text(
            surface,
            (
                "OFFENSE  /  CALL THE PLAY  /  SELECT OR DRAG A CARD"
                if offensive
                else "DEFENSE  /  SET THE DRIVE  /  SELECT OR DRAG A CARD"
            ),
            (rect.left + 2, rect.top),
            self._small_font,
            _MATCH_BRASS,
        )
        self.match_interaction.play_area = pygame.Rect(
            rect.left,
            rect.top + 20,
            rect.width,
            32,
        )
        pygame.draw.rect(
            surface,
            _MATCH_PANEL,
            self.match_interaction.play_area,
            border_radius=5,
        )
        pygame.draw.rect(
            surface,
            _MATCH_BRASS,
            self.match_interaction.play_area,
            width=1,
            border_radius=5,
        )
        draw_text(
            surface,
            (
                "DROP PLAY HERE  /  NORMAL CLOCK USES LIVE VALUE; "
                "INCOMPLETE PASSES USE SEPARATE 5s RULE; "
                "CONVERSIONS & SPECIAL TEAMS UNCHANGED"
                if offensive
                else "DROP SCHEME HERE"
            ),
            (self.match_interaction.play_area.left + 10, self.match_interaction.play_area.top + 8),
            self._small_font,
            _MATCH_CHALK,
        )
        pile_label = (
            f"HAND {len(deck.hand)}   /   DRAW {len(deck.draw_pile)}   /   "
            f"DISCARD {len(deck.discard_pile)}"
        )
        hand_top = self.match_interaction.play_area.bottom + 5
        draw_text(
            surface,
            pile_label,
            (rect.left + 2, hand_top),
            self._small_font,
            _MATCH_MUTED,
        )
        hand_top += self._small_font.get_height() + 2
        self.match_interaction.hand_area = pygame.Rect(
            rect.left,
            hand_top,
            rect.width,
            max(1, rect.bottom - hand_top),
        )
        self.match_interaction.card_rects = {}
        buttons: list[Button] = []
        if deck.hand:
            columns = min(3, len(deck.hand))
            gap_x = 8
            gap_y = 5
            card_width = (rect.width - gap_x * (columns - 1)) // columns
            card_height = 54
            visible_rows = max(
                1,
                (self.match_interaction.hand_area.height + gap_y) // (card_height + gap_y),
            )
            total_rows = (len(deck.hand) + columns - 1) // columns
            self.match_interaction.hand_max_scroll = max(0, total_rows - visible_rows)
            self.match_interaction.hand_scroll = min(
                self.match_interaction.hand_scroll, self.match_interaction.hand_max_scroll
            )
            start = self.match_interaction.hand_scroll * columns
            visible_cards = deck.hand[start : start + visible_rows * columns]
            for visible_index, card in enumerate(visible_cards):
                row, column = divmod(visible_index, columns)
                card_rect = pygame.Rect(
                    self.match_interaction.hand_area.left + column * (card_width + gap_x),
                    self.match_interaction.hand_area.top + row * (card_height + gap_y),
                    card_width,
                    card_height,
                )
                bonus = BONUS_CARD_CATALOG.get(card.card_id) if offensive else None
                definition = (
                    bonus
                    if bonus is not None
                    else catalog[card.card_id]
                )
                label = definition.name.upper()
                fill = (
                    pygame.Color("#344536")
                    if card.copy_id == self.match_interaction.dragging_card_id
                    else _MATCH_PANEL
                )
                button_index = len(buttons)
                focused = self.focus_index == button_index
                hovered = self.hover_index == button_index
                pressed = self.pressed_index == button_index
                pygame.draw.rect(surface, fill, card_rect, border_radius=5)
                pygame.draw.rect(
                    surface,
                    _MATCH_FOCUS if focused or hovered else _MATCH_PANEL_EDGE,
                    card_rect,
                    width=2 if focused or hovered or pressed
                    or card.copy_id == self.match_interaction.dragging_card_id else 1,
                    border_radius=5,
                )
                draw_text(
                    surface,
                    _fit_text(label, self._small_font, card_rect.width - 12),
                    (card_rect.left + 6, card_rect.top + 3),
                    self._small_font,
                    _MATCH_CHALK,
                )
                if bonus is not None:
                    defensive_draw = bonus.action in (
                        FootballBonusCardAction.DEFENSIVE_DRAW,
                        FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD,
                    )
                    defensive_deck = match.team_a_defense_deck
                    can_draw_defensive_card = (
                        defensive_deck is not None
                        and bool(
                            defensive_deck.draw_pile
                            or defensive_deck.discard_pile
                        )
                    )
                    effect = {
                        FootballBonusCardAction.OFFENSIVE_DRAW:
                            ("DRAW 1 OFFENSIVE CARD", "10s / NO SNAP"),
                        FootballBonusCardAction.DEFENSIVE_DRAW:
                            ("DRAW 1 DEFENSIVE SCHEME", "10s / NO SNAP"),
                        FootballBonusCardAction.OPPONENT_DISCARD:
                            ("DRAW 1 / DISCARD OPPONENT", "10s / NO SNAP"),
                        FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD:
                            ("DRAW OFFENSE / DISCARD OPPONENT", "10s / NO SNAP"),
                        FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD:
                            ("DRAW DEFENSE / DISCARD OPPONENT", "10s / NO SNAP"),
                        FootballBonusCardAction.CHALLENGE:
                            ("RESTORE LAST PLAY", "NO TIME / NO SNAP"),
                    }[bonus.action]
                    draw_text(
                        surface,
                        _fit_text(effect[0], self._small_font, card_rect.width - 12),
                        (card_rect.left + 6, card_rect.top + 20),
                        self._small_font,
                        _MATCH_MUTED,
                    )
                    if bonus.action is FootballBonusCardAction.CHALLENGE:
                        enabled = state.challenge_available
                        clock_line = (
                            effect[1]
                            if enabled
                            else "AVAILABLE AFTER YOUR NEXT PLAY"
                        )
                    elif defensive_draw and not can_draw_defensive_card:
                        enabled = False
                        clock_line = "NO DEFENSIVE CARD TO DRAW"
                    else:
                        enabled = True
                        clock_line = effect[1]
                    draw_text(
                        surface,
                        _fit_text(clock_line, self._small_font, card_rect.width - 12),
                        (card_rect.left + 6, card_rect.top + 37),
                        self._small_font,
                        _MATCH_BRASS,
                    )
                else:
                    contributor_label = ", ".join(
                        _POSITION_LABELS[position] for position in definition.contributors
                    )
                    draw_text(
                        surface,
                        _fit_text(
                            f"{definition.family.label.upper()} / {contributor_label}",
                            self._small_font,
                            card_rect.width - 12,
                        ),
                        (card_rect.left + 6, card_rect.top + 20),
                        self._small_font,
                        _MATCH_MUTED,
                    )
                    enabled = True
                if bonus is None and offensive and match.current_drive_defensive_scheme is not None:
                    estimate = calculate_match_play_estimate(
                        match,
                        definition.action,
                    )
                    upgrades = (
                        match.team_a_coach_upgrades
                        if match.possession is FootballTeamSide.TEAM_A
                        else match.team_b_coach_upgrades
                    )
                    live_clock_seconds = adjusted_offensive_play_clock_seconds(
                        definition.clock_seconds,
                        upgrades,
                    )
                    preview = (
                        f"LIVE ~{estimate.expected_yards:.1f} YDS"
                        f" / 1ST {estimate.first_down_probability(match.yards_to_go):.0%}"
                        f" / LIVE NORMAL CLOCK {live_clock_seconds}s"
                    )
                    draw_text(
                        surface,
                        _fit_text(preview, self._small_font, card_rect.width - 12),
                        (card_rect.left + 6, card_rect.top + 37),
                        self._small_font,
                        _MATCH_BRASS,
                    )
                elif bonus is None and not offensive:
                    draw_text(
                        surface,
                        _fit_text(
                            f"COUNTERS: {definition.family.label.upper()}",
                            self._small_font,
                            card_rect.width - 12,
                        ),
                        (card_rect.left + 6, card_rect.top + 37),
                        self._small_font,
                        _MATCH_BRASS,
                    )
                if enabled:
                    self.match_interaction.card_rects[card.copy_id] = card_rect
                buttons.append(
                    Button(
                        label,
                        lambda copy_id=card.copy_id: self.choose_card(copy_id),
                        card_rect,
                        enabled=enabled,
                        variant="hand-card",
                    )
                )
        else:
            self.match_interaction.hand_max_scroll = 0
            self.match_interaction.hand_scroll = 0
            fallback_label = (
                "FALLBACK / INSIDE RUN"
                if offensive
                else "FALLBACK / RUN FIT"
            )
            fallback_rect = pygame.Rect(
                self.match_interaction.hand_area.left + 2,
                self.match_interaction.hand_area.top + 2,
                min(280, self.match_interaction.hand_area.width - 4),
                min(48, self.match_interaction.hand_area.height - 2),
            )
            buttons.append(
                Button(
                    fallback_label,
                    lambda: self.choose_fallback(offensive),
                    fallback_rect,
                )
            )

        if self.match_interaction.hand_max_scroll:
            draw_text(
                surface,
                f"Scroll hand  /  {self.match_interaction.hand_scroll + 1} of "
                f"{self.match_interaction.hand_max_scroll + 1}",
                (self.match_interaction.hand_area.right - 150, hand_top - 2),
                self._small_font,
                _MATCH_MUTED,
            )
        return buttons

    def draw_call_button(
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
