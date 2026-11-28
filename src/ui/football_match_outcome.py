"""Outcome strip: the latest result plus fourth-down, conversion, and Challenge calls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from collections import Counter

from src.engine.football import (
    FootballBonusCardAction,
    FootballCardFamily,
    FootballConversionAction,
    FootballFourthDownAction,
)
from src.engine.football_controller import FootballGameControllerState, FootballHumanDecision
from src.engine.football_decks import DEFENSIVE_SCHEME_CATALOG, OFFENSIVE_PLAY_CATALOG
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
    variant: str = "strip"  # "strip", "strip-primary", "strip-challenge"
    enabled: bool = True


@dataclass(frozen=True)
class StripCallbacks:
    fourth_down: Callable[[FootballFourthDownAction], None]
    conversion: Callable[[FootballConversionAction, str | None], None]
    challenge: Callable[[bool], None]
    challenge_touchdown: Callable[[], None]
    green_dog: Callable[[str | None], None] = lambda _copy_id: None


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
    if decision is FootballHumanDecision.GREEN_DOG:
        return green_dog_actions(match, callbacks)
    return "", []


GREEN_DOG_PROMPT = "GREEN DOG · SWAP?"
GREEN_DOG_KEEP = "KEEP"


def green_dog_actions(match, callbacks: StripCallbacks) -> tuple[str, list[StripAction]]:
    """Keep the active scheme (primary) or swap in a hand scheme.

    Two swap buttons at most keep the strip readable; every hand scheme is also
    clickable in the hand and reachable with the number keys.
    """
    active = match.current_drive_defensive_scheme
    deck = match.team_a_defense_deck
    keep = f"{GREEN_DOG_KEEP} {DEFENSIVE_SCHEME_CATALOG[active.value].name.upper()}" if active else GREEN_DOG_KEEP
    actions = [StripAction(keep, lambda: callbacks.green_dog(None), "strip-primary")]
    seen: set[str] = set()
    for card in deck.hand if deck is not None else ():
        if card.card_id in seen or len(actions) >= 3:
            continue
        seen.add(card.card_id)
        name = DEFENSIVE_SCHEME_CATALOG[card.card_id].name.upper()
        actions.append(StripAction(
            f"SWAP · {name}", lambda copy_id=card.copy_id: callbacks.green_dog(copy_id),
        ))
    return GREEN_DOG_PROMPT, actions


def status_prompt(state: FootballGameControllerState) -> str:
    decision = state.human_decision
    if decision is FootballHumanDecision.OFFENSIVE_PLAY:
        return "YOUR BALL · PLAY AN OFFENSE CARD"
    if decision is FootballHumanDecision.DEFENSIVE_SCHEME:
        return DEFENSE_PROMPT
    return ""


DEFENSE_PROMPT = "PICK ONE DEFENSE FOR THIS DRIVE"
DEFENSE_SUBLINE = "It stays until they score, punt, or turn it over"


def scouting_line(match) -> str | None:
    """'SCOUTING · HOUNDS LEAN DEEP PASS' from the rival's whole owned offensive deck.

    Counts every owned play copy (never the current hand alone): the family with the
    most copies, or the two tied for most. Three or more tied show no lean; an empty
    deck shows nothing.
    """
    deck = match.team_b_offense_deck if match is not None else None
    if deck is None:
        return None
    counts = Counter(
        OFFENSIVE_PLAY_CATALOG[card.card_id].family
        for card in deck.owned if card.card_id in OFFENSIVE_PLAY_CATALOG
    )
    if not counts:
        return None
    rival = match.team_b.team_name.strip().upper()
    most = max(counts.values())
    leaders = [family for family in FootballCardFamily if counts.get(family) == most]
    if len(leaders) > 2:
        return f"SCOUTING · {rival} SHOW NO CLEAR LEAN"
    lean = " OR ".join(family.label.upper() for family in leaders)
    return f"SCOUTING · {rival} LEAN {lean}"


def prompt_lines(state: FootballGameControllerState) -> tuple[str, ...]:
    """Lines stacked under the strip prompt: the defense call's sub-line and scouting."""
    if state.human_decision is not FootballHumanDecision.DEFENSIVE_SCHEME:
        return ()
    scouting = scouting_line(state.match)
    return (DEFENSE_SUBLINE,) + ((scouting,) if scouting else ())


CALLOUT_CYCLE_MS = 1400


def callout_text(callouts: tuple[str, ...], elapsed_ms: int) -> str | None:
    """The callout shown now: several perks on one play take turns, numbered."""
    if not callouts:
        return None
    index = (max(0, elapsed_ms) // CALLOUT_CYCLE_MS) % len(callouts)
    text = callouts[index]
    return f"{text}  {index + 1}/{len(callouts)}" if len(callouts) > 1 else text


def draw_outcome_strip(
    surface: pygame.Surface,
    rect: pygame.Rect,
    outcome: Outcome | None,
    *,
    prompt: str,
    actions: list[StripAction],
    playback_label: str | None,
    elapsed_ms: int,
    sub_lines: tuple[str, ...] = (),
) -> list[pygame.Rect]:
    """Draw the strip and return one rect per entry in ``actions``.

    ``sub_lines`` stack under the prompt (smaller, right-aligned); the second one is
    skipped when it would not fit.
    """
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
        extra = [] if playback_label else _sub_lines(sub_lines, max_width, rect.height - 8 - font.get_height())
        height = font.get_height() + sum(line_font.get_height() for _line, line_font, _c in extra)
        y = rect.centery - height // 2
        prompt_rect = blit_text(
            surface, font, text, MATCH_FOCUS if prompt and not playback_label else MATCH_MUTED,
            prompt_box, topright=(right, y),
        )
        left_edge = prompt_rect.left
        y = prompt_rect.bottom
        for line, line_font, color in extra:
            drawn = blit_text(surface, line_font, line, color, prompt_box, topright=(right, y))
            left_edge = min(left_edge, drawn.left)
            y = drawn.bottom
        right = left_edge - 18

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
    detail_width = headline_width
    callout = callout_text(outcome.callouts, elapsed_ms)
    if callout is not None:
        # Perk callout: a gold pill at the right of the detail row; it takes the whole
        # row when the detail would be squeezed below ~160px.
        callout_font = plain_font(12)
        pill_width = min(callout_font.size(callout)[0] + 18, headline_width)
        if headline_width - pill_width - 12 < 160:
            pill_width, detail_width = headline_width, 0
        else:
            detail_width = headline_width - pill_width - 12
        pill = pygame.Rect(0, 0, pill_width, 20)
        pill.bottomright = (left + headline_width, rect.bottom - 6)
        pygame.draw.rect(surface, mix(MATCH_PANEL_DEEP, MATCH_GOLD, 0.18), pill, border_radius=10)
        pygame.draw.rect(surface, MATCH_GOLD, pill, 1, border_radius=10)
        blit_text(surface, callout_font, fit_text(callout, callout_font, pill.width - 14), MATCH_GOLD,
                  pill, center=pill.center)
    if detail_width:
        detail = fit_text(outcome.detail, detail_font, detail_width)
        blit_text(surface, detail_font, detail, MATCH_MUTED, headline_box,
                  topleft=(left + 1, rect.bottom - 23))
    return button_rects


def _sub_lines(lines: tuple[str, ...], width: int, room: int) -> list[tuple[str, pygame.font.Font, pygame.Color]]:
    """(text, font, color) for the prompt's sub-lines that fit ``width`` and ``room``."""
    fitted: list[tuple[str, pygame.font.Font, pygame.Color]] = []
    for index, line in enumerate(lines):
        font = plain_font(12, index > 0)
        if font.size(line)[0] > width or font.get_height() > room:
            continue  # skip rather than truncate (scouting is optional)
        fitted.append((line, font, MATCH_MUTED if index == 0 else MATCH_TEXT))
        room -= font.get_height()
    return fitted


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

