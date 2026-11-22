"""Outcome strip: the latest result plus fourth-down, conversion, and Challenge calls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from src.engine.football import (
    FootballBonusCardAction,
    FootballConversionAction,
    FootballFourthDownAction,
)
from src.engine.football_controller import FootballGameControllerState, FootballHumanDecision
from src.engine.football_decks import OFFENSIVE_PLAY_CATALOG
from src.engine.football_simulator import field_goal_distance_for_position
from src.ui.football_card_art import bonus_card_art, draw_card_art
from src.ui.football_match_events import Outcome, OutcomeEmphasis, PlayLineKind
from src.ui.football_match_playback import EVENT_DURATION_MS
from src.ui.football_match_palette import (
    MATCH_DANGER, MATCH_DIM, MATCH_FOCUS, MATCH_GOLD, MATCH_INK, MATCH_MUTED,
    MATCH_PANEL, MATCH_PANEL_DEEP, MATCH_PANEL_EDGE, MATCH_PANEL_EDGE_SOFT,
    MATCH_PANEL_HIGH, MATCH_TEXT, OUTCOME_OTHER, OUTCOME_PASS, OUTCOME_RUN,
    blit_text, match_font, mix, plain_font,
)
from src.ui.text import fit_text
from src.ui.widgets import Button

STRIP_HEIGHT = 64

OUTCOME_COLORS = {
    PlayLineKind.RUN: OUTCOME_RUN,
    PlayLineKind.PASS: OUTCOME_PASS,
    PlayLineKind.OTHER: OUTCOME_OTHER,
}

HEADLINE_SIZES = (32, 28, 24, 20)


@dataclass(frozen=True)
class StripAction:
    label: str
    callback: Callable[[], None]
    variant: str = "strip"  # "strip", "strip-primary", "strip-challenge", "strip-skip"
    enabled: bool = True


@dataclass(frozen=True)
class StripCallbacks:
    fourth_down: Callable[[FootballFourthDownAction], None]
    conversion: Callable[[FootballConversionAction, str | None], None]
    challenge: Callable[[bool], None]
    challenge_touchdown: Callable[[], None]


def decision_actions(
    state: FootballGameControllerState, callbacks: StripCallbacks
) -> tuple[str, list[StripAction]]:
    """The prompt and buttons for decisions that are not card plays."""
    match = state.match
    decision = state.human_decision
    if match is None:
        return "", []
    if decision is FootballHumanDecision.FOURTH_DOWN:
        distance = field_goal_distance_for_position(match.offense_field_position)
        return "4TH DOWN · MAKE THE CALL", [
            StripAction(
                "GO FOR IT",
                lambda: callbacks.fourth_down(FootballFourthDownAction.GO_FOR_IT),
                "strip-primary",
            ),
            StripAction("PUNT", lambda: callbacks.fourth_down(FootballFourthDownAction.PUNT)),
            StripAction(
                f"FIELD GOAL · {distance:.0f} YDS",
                lambda: callbacks.fourth_down(FootballFourthDownAction.FIELD_GOAL),
            ),
        ]
    if decision is FootballHumanDecision.CONVERSION:
        actions = [
            StripAction(
                "EXTRA POINT",
                lambda: callbacks.conversion(FootballConversionAction.EXTRA_POINT, None),
                "strip-primary",
            )
        ]
        deck = match.team_a_offense_deck
        has_play = deck is not None and any(
            card.card_id in OFFENSIVE_PLAY_CATALOG for card in deck.hand
        )
        prompt = "KICK THE PAT, OR PLAY A CARD FOR 2"
        if not has_play:
            prompt = "TOUCHDOWN · CHOOSE THE CONVERSION"
            actions.append(
                StripAction(
                    "2-PT · BASIC RUN",
                    lambda: callbacks.conversion(FootballConversionAction.TWO_POINT, None),
                )
            )
        if state.challenge_available:
            actions.append(
                StripAction("CHALLENGE TD", callbacks.challenge_touchdown, "strip-challenge")
            )
        return prompt, actions
    if decision is FootballHumanDecision.CHALLENGE:
        return "CHALLENGE THE LAST PLAY?", [
            StripAction("CHALLENGE", lambda: callbacks.challenge(True), "strip-challenge"),
            StripAction("DECLINE", lambda: callbacks.challenge(False)),
        ]
    return "", []


def status_prompt(state: FootballGameControllerState) -> str:
    decision = state.human_decision
    if decision is FootballHumanDecision.OFFENSIVE_PLAY:
        return "YOUR BALL · PLAY AN OFFENSE CARD"
    if decision is FootballHumanDecision.DEFENSIVE_SCHEME:
        return "SET YOUR DEFENSE FOR THIS DRIVE"
    return ""


def draw_outcome_strip(
    surface: pygame.Surface,
    rect: pygame.Rect,
    outcome: Outcome | None,
    *,
    prompt: str,
    actions: list[StripAction],
    playback_label: str | None,
    elapsed_ms: int,
) -> list[pygame.Rect]:
    """Draw the strip and return one rect per entry in ``actions``."""
    emphasis = outcome.emphasis if outcome is not None else OutcomeEmphasis.NORMAL
    color = OUTCOME_COLORS[outcome.kind] if outcome is not None else OUTCOME_OTHER
    edge = {
        OutcomeEmphasis.NORMAL: MATCH_PANEL_EDGE,
        OutcomeEmphasis.SCORE: MATCH_GOLD,
        OutcomeEmphasis.TURNOVER: MATCH_DANGER,
    }[emphasis]
    fill = MATCH_PANEL
    if emphasis is not OutcomeEmphasis.NORMAL and elapsed_ms < EVENT_DURATION_MS:
        pulse = max(0.0, 1 - elapsed_ms / EVENT_DURATION_MS)
        fill = mix(MATCH_PANEL, edge, 0.28 * pulse)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=10)
    pygame.draw.rect(surface, fill, rect.inflate(-4, -4), border_radius=9)
    pygame.draw.rect(surface, edge, rect, 3 if emphasis is not OutcomeEmphasis.NORMAL else 2,
                     border_radius=10)
    bar = pygame.Rect(rect.left + 8, rect.top + 9, 7, rect.height - 18)
    pygame.draw.rect(surface, color, bar, border_radius=3)

    # Right side: decision buttons, playback controls, or a prompt.
    button_rects: list[pygame.Rect] = []
    right = rect.right - 10
    if actions:
        widths = [_action_width(action) for action in actions]
        total = sum(widths) + 10 * (len(actions) - 1)
        x = right - total
        for action, width in zip(actions, widths):
            button_rects.append(pygame.Rect(x, rect.top + 10, width, rect.height - 20))
            x += width + 10
        right = right - total - 14
    if prompt or playback_label:
        text = playback_label or prompt
        font = match_font(14)
        # Keep at least ~360px for the headline; the prompt gets the rest.
        max_width = max(140, right - (bar.right + 14) - 360)
        text = fit_text(text, font, max_width)
        prompt_box = pygame.Rect(right - max_width, rect.top, max_width, rect.height)
        prompt_rect = blit_text(
            surface, font, text, MATCH_FOCUS if prompt and not playback_label else MATCH_MUTED,
            prompt_box, midright=(right, rect.centery),
        )
        right = prompt_rect.left - 18

    left = bar.right + 14
    headline_width = max(60, right - left)
    headline_box = pygame.Rect(left, rect.top, headline_width, rect.height)
    if outcome is None:
        title_font = plain_font(26)
        blit_text(surface, title_font, fit_text("OPENING DRIVE", title_font, headline_width),
                  OUTCOME_OTHER, headline_box, topleft=(left, rect.top + 6))
        detail_font = plain_font(14, False)
        blit_text(surface, detail_font, fit_text("Waiting for the first snap", detail_font, headline_width),
                  MATCH_MUTED, headline_box, topleft=(left + 1, rect.bottom - 23))
        return button_rects
    headline_font = plain_font(HEADLINE_SIZES[-1])
    for size in HEADLINE_SIZES:
        candidate = plain_font(size)
        if candidate.size(outcome.headline)[0] <= headline_width:
            headline_font = candidate
            break
    headline = fit_text(outcome.headline, headline_font, headline_width)
    if emphasis is not OutcomeEmphasis.NORMAL:
        surface.blit(headline_font.render(headline, True, MATCH_INK), (left + 2, rect.top + 6))
    blit_text(surface, headline_font, headline, color, headline_box, topleft=(left, rect.top + 4))
    detail_font = plain_font(14)
    detail = fit_text(outcome.detail, detail_font, headline_width)
    blit_text(surface, detail_font, detail, MATCH_MUTED, headline_box,
              topleft=(left + 1, rect.bottom - 23))
    return button_rects


def _action_width(action: StripAction) -> int:
    font = match_font(16)
    extra = 44 if action.variant == "strip-challenge" else 0
    return max(118, font.size(action.label)[0] + 36 + extra)


def draw_strip_button(
    surface: pygame.Surface,
    button: Button,
    *,
    shortcut: int | None,
    focused: bool,
    hovered: bool,
    pressed: bool,
) -> None:
    rect = button.rect.move(0, 2) if pressed else button.rect
    primary = button.variant == "strip-primary"
    if not button.enabled:
        fill, edge, ink = MATCH_PANEL_DEEP, MATCH_PANEL_EDGE_SOFT, MATCH_DIM
    elif primary:
        fill = MATCH_FOCUS if focused or hovered else mix(MATCH_FOCUS, MATCH_PANEL, 0.12)
        edge, ink = MATCH_FOCUS, MATCH_INK
    else:
        fill = MATCH_PANEL_HIGH if focused or hovered else MATCH_PANEL_DEEP
        edge = MATCH_FOCUS if focused else MATCH_PANEL_EDGE
        ink = MATCH_TEXT
    if focused and button.enabled:
        pygame.draw.rect(surface, MATCH_TEXT, rect.inflate(6, 6), 2, border_radius=10)
    pygame.draw.rect(surface, fill, rect, border_radius=8)
    pygame.draw.rect(surface, edge, rect, 2, border_radius=8)
    label_left = rect.left + 14
    if button.variant == "strip-challenge":
        art = pygame.Rect(rect.left + 8, rect.top + 6, 34, rect.height - 12)
        draw_card_art(surface, bonus_card_art(FootballBonusCardAction.CHALLENGE), art)
        label_left = art.right + 8
    font = match_font(16)
    width = rect.right - label_left - 10
    text = fit_text(button.label, font, width)
    if button.variant == "strip-challenge":
        blit_text(surface, font, text, ink, rect, midleft=(label_left, rect.centery))
    else:
        blit_text(surface, font, text, ink, rect, center=rect.center)
    if shortcut is not None and button.enabled:
        key = match_font(10).render(str(shortcut), True, ink if primary else MATCH_MUTED)
        surface.blit(key, (rect.right - key.get_width() - 5, rect.top + 2))

