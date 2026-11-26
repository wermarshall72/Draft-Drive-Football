"""Hover/focus inspect panels for shop offers, Playbook cards, and draft coaches.

A card opens its panel after a short hover or keyboard-focus delay and closes when
the pointer or focus moves away; Esc hides a visible panel. Panels never take
clicks, and they sit beside their card so the card's own button is never covered.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass, field

import pygame

from src.engine.football import FootballCoachUpgradeKind
from src.engine.football_coaches import FootballCoachProfile
from src.engine.football_decks import (
    FootballBonusCardDefinition,
    FootballPlayDefinition,
    FootballSchemeDefinition,
)
from src.engine.football_shop import (
    FootballShopCard,
    FootballShopState,
    FootballUpgrade,
    FootballUpgradeDuration,
    FootballUpgradeStat,
)
from src.engine.football_simulator import calculate_standardized_play_estimate
from src.ui.football_coach_perks import coach_perk_rules, coach_perk_short, modifier_text
from src.ui.football_coach_upgrade_details import coach_upgrade_detail_sections
from src.ui.football_display import _POSITION_LABELS
from src.ui.football_player_upgrade_details import stat_value
from src.ui.football_ui_kit import (
    MATCH_FOCUS,
    MATCH_INK,
    MATCH_MUTED,
    MATCH_PANEL_DEEP,
    MATCH_PANEL_EDGE,
    MATCH_PANEL_EDGE_SOFT,
    MATCH_PANEL_HIGH,
    MATCH_TEXT,
    blit_text,
    fit_wrapped,
    match_font,
    plain_font,
    rarity_color,
    rarity_label,
)
from src.ui.text import wrap_text_lines

PANEL_WIDTH = 340
PANEL_MAX_HEIGHT = 470
HOVER_DELAY_MS = 450
# Keys that move keyboard focus; only these hand panels from the pointer to focus.
FOCUS_KEYS = frozenset({pygame.K_TAB, pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT})
_PAD = 16
_ART = 64


ArtPainter = Callable[[pygame.Surface, pygame.Rect], None]


@dataclass(frozen=True)
class InspectContent:
    title: str
    rarity: object | None
    cost: int | None
    # (heading, text) rows; a third True item draws the text as a gold highlight.
    sections: tuple[tuple, ...]
    art: ArtPainter | None = field(default=None, compare=False)
    tag: str | None = None


class InspectState:
    """Which card's panel is open, independent of how cards are drawn."""

    def __init__(self, clock: Callable[[], int] = pygame.time.get_ticks) -> None:
        self.clock = clock
        self.keyboard = False
        self.shown_key: Hashable | None = None
        self.panel_rect: pygame.Rect | None = None
        self.overlay: tuple | None = None
        self._active_key: Hashable | None = None
        self._since = 0
        self._dismissed: Hashable | None = None

    def reset(self) -> None:
        self.overlay = None
        self.shown_key = None
        self.panel_rect = None
        self._active_key = None
        self._dismissed = None

    def update(self, hover_key: Hashable | None, focus_key: Hashable | None) -> Hashable | None:
        """The key whose panel shows this frame, or None."""
        active = hover_key if hover_key is not None else (focus_key if self.keyboard else None)
        now = self.clock()
        if active != self._active_key:
            self._active_key = active
            self._since = now
            self._dismissed = None
        if active is None or active == self._dismissed:
            return None
        if now - self._since >= HOVER_DELAY_MS:
            return active
        return None

    def prepare(self, contents: dict, hover_key: Hashable | None,
                focus_key: Hashable | None) -> None:
        """Choose this frame's panel from ``contents`` {key: (content, anchor)}."""
        self.overlay = None
        self.shown_key = None
        self.panel_rect = None
        key = self.update(hover_key, focus_key)
        if key is None:
            return
        if key not in contents:
            self.reset()
            return
        content, anchor = contents[key]
        self.overlay = (content, anchor)
        self.shown_key = key

    def paint(self, surface: pygame.Surface) -> None:
        """Draw the prepared panel above everything else on the screen."""
        if self.overlay is None:
            return
        content, anchor = self.overlay
        bounds = pygame.Rect(12, 12, surface.get_width() - 24, surface.get_height() - 24)
        self.panel_rect = draw_inspect_panel(surface, anchor, content, bounds)

    def dismiss(self) -> None:
        """Hide the visible panel until the pointer or focus moves to another card."""
        self._dismissed = self._active_key
        self.overlay = None
        self.shown_key = None

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Track pointer/keyboard mode; Esc hides a visible panel (True when it did).

        Other keys (I included) never open, close, or move a panel.
        """
        if event.type == pygame.MOUSEMOTION:
            self.keyboard = False
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and self.shown_key is not None:
                self.dismiss()
                return True
            if event.key in FOCUS_KEYS:
                self.keyboard = True
        return False


def _body_layout(content: InspectContent, width: int, size: int) -> list[tuple[pygame.font.Font, str, pygame.Color, int]]:
    """(font, line, color, gap-before) rows for the sections at ``size``."""
    rows: list[tuple[pygame.font.Font, str, pygame.Color, int]] = []
    head_font = plain_font(11)
    body_font = match_font(size, False)
    strong = plain_font(size + 1)
    for index, (heading, text, *accent) in enumerate(content.sections):
        # A section without a heading continues the one above it.
        gap = 0 if index == 0 else (8 if heading else 3)
        if accent and accent[0]:
            if heading:
                rows.append((head_font, heading.upper(), MATCH_MUTED, gap))
                gap = 1
            for line in wrap_text_lines(text, strong, width):
                rows.append((strong, line, MATCH_FOCUS, gap))
                gap = 0
            continue
        if heading:
            rows.append((head_font, heading.upper(), MATCH_MUTED, gap))
            gap = 1
        for line in wrap_text_lines(text, body_font, width):
            rows.append((body_font, line, MATCH_TEXT, gap))
            gap = 0
    return rows


def layout_panel(anchor: pygame.Rect, content: InspectContent,
                 bounds: pygame.Rect) -> tuple[pygame.Rect, list, pygame.font.Font, tuple[str, ...], int]:
    inner_width = PANEL_WIDTH - 2 * _PAD
    title_width = inner_width - (_ART + 12 if content.art else 0)
    title_font, title_lines = fit_wrapped(content.title.upper(), title_width, (20, 18, 16, 14), 3)
    header = max(_ART if content.art else 0,
                 len(title_lines) * title_font.get_height() + (16 if content.tag else 0)
                 + (22 if content.rarity is not None or content.cost is not None else 6))
    for size in (14, 13, 12, 11):
        rows = _body_layout(content, inner_width, size)
        body = sum(font.get_height() + gap for font, _line, _color, gap in rows)
        height = _PAD + header + 14 + body + _PAD
        if height <= PANEL_MAX_HEIGHT:
            break
    rect = pygame.Rect(0, 0, PANEL_WIDTH, height)
    if anchor.centerx < bounds.centerx:
        rect.left = anchor.right + 14
        if rect.right > bounds.right:
            rect.right = anchor.left - 14
    else:
        rect.right = anchor.left - 14
        if rect.left < bounds.left:
            rect.left = anchor.right + 14
    rect.top = anchor.top
    rect.clamp_ip(bounds)
    return rect, rows, title_font, title_lines, header


def draw_inspect_panel(
    surface: pygame.Surface,
    anchor: pygame.Rect,
    content: InspectContent,
    bounds: pygame.Rect,
) -> pygame.Rect:
    rect, rows, title_font, title_lines, header = layout_panel(anchor, content, bounds)
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 6), border_radius=14)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=14)
    edge = rarity_color(content.rarity) if content.rarity is not None else MATCH_PANEL_EDGE
    pygame.draw.rect(surface, edge, rect, 2, border_radius=14)
    x = rect.left + _PAD
    y = rect.top + _PAD
    if content.art is not None:
        art = pygame.Rect(x, y, _ART, _ART)
        pygame.draw.rect(surface, MATCH_PANEL_HIGH, art, border_radius=8)
        content.art(surface, art.inflate(-6, -6))
        x = art.right + 12
    text_box = pygame.Rect(x, y, rect.right - _PAD - x, header)
    ty = y
    for line in title_lines:
        blit_text(surface, title_font, line, MATCH_TEXT, text_box, topleft=(x, ty))
        ty += title_font.get_height()
    if content.tag:
        tag_font = plain_font(11)
        blit_text(surface, tag_font, content.tag.upper(), MATCH_MUTED, text_box, topleft=(x, ty + 2))
        ty += 16
    if content.rarity is not None or content.cost is not None:
        meta_font = plain_font(13)
        meta_x = x
        if content.rarity is not None:
            drawn = blit_text(surface, meta_font, rarity_label(content.rarity), rarity_color(content.rarity),
                              text_box, topleft=(meta_x, ty + 4))
            meta_x = drawn.right + 8
        if content.cost is not None:
            blit_text(surface, meta_font, f"{content.cost} AP", MATCH_FOCUS, text_box, topleft=(meta_x, ty + 4))
    y = rect.top + _PAD + header + 6
    pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (rect.left + _PAD, y), (rect.right - _PAD, y))
    y += 8
    body = pygame.Rect(rect.left + _PAD, y, rect.width - 2 * _PAD, rect.bottom - y)
    for font, line, color, gap in rows:
        y += gap
        blit_text(surface, font, line, color, body, topleft=(body.left, y))
        y += font.get_height()
    return rect


# -- content builders ---------------------------------------------------------------

def _rarity_cost_line(rarity: object, cost: int | None) -> str:
    text = rarity_label(rarity).title()
    return f"{text}  /  {cost} AP" if cost is not None else text


def player_upgrade_effect(upgrade: FootballUpgrade) -> tuple[str, str]:
    """(stat key, compact value) shown on cards: '+1', '+10%', '-2%'."""
    if upgrade.stat is FootballUpgradeStat.POWER:
        return "power", f"+{upgrade.amount:g}"
    if upgrade.stat is FootballUpgradeStat.STAMINA:
        return "stamina", f"+{round(upgrade.amount * 100, 4):g}%"
    return "volatility", f"-{round(upgrade.amount * 100, 4):g}%"


def player_upgrade_inspect(card: FootballShopCard, shop: FootballShopState | None,
                           art: ArtPainter | None = None) -> InspectContent:
    upgrade = card.upgrade
    assert upgrade is not None
    _stat, value = player_upgrade_effect(upgrade)
    stat_name = upgrade.stat.value.title()
    position = position_name(upgrade.position)
    temporary = upgrade.duration is FootballUpgradeDuration.TEMPORARY
    sections: list[tuple[str, str]] = [
        ("Effect", f"{position}: {value} {stat_name}"
                   + (" (percentage points)" if upgrade.stat is not FootballUpgradeStat.POWER else "")),
        ("Duration", "Temporary: lasts for the next completed match only. A Bye Week does not use it up."
         if temporary else "Permanent: lasts for the rest of the run."),
    ]
    cap = {
        FootballUpgradeStat.STAMINA: "Stamina is capped at 100%.",
        FootballUpgradeStat.VOLATILITY: "Volatility cannot drop below 0%.",
    }.get(upgrade.stat)
    if cap:
        sections.append(("Limit", cap))
    if shop is not None:
        projection = shop.project_player_upgrade(upgrade).next_match
        sections.append((
            "Next match",
            f"{stat_name} {stat_value(upgrade.stat, projection.before)} -> "
            f"{stat_value(upgrade.stat, projection.after)} (before coach bonuses)",
        ))
    return InspectContent(f"{position} {stat_name} upgrade", card.rarity, card.cost, tuple(sections),
                          art, tag="Temporary upgrade" if temporary else "Permanent upgrade")


def coach_upgrade_inspect(card: FootballShopCard, art: ArtPainter | None = None) -> InspectContent:
    sections = coach_upgrade_detail_sections(card)
    rows = []
    for text in sections[1:-1]:
        heading, _, body = text.partition(": ")
        rows.append((heading, body) if body else ("", text))
    effect = card.coach_upgrade_effect
    tag = "One-time event" if effect is not None and effect.kind is FootballCoachUpgradeKind.BYE_WEEK else "Coach upgrade"
    return InspectContent(sections[0], card.rarity, card.cost, tuple(rows), art, tag=tag)


def position_name(position) -> str:
    label = _POSITION_LABELS[position]
    return label if len(label) <= 2 else label.title()


def _contributors(definition: FootballPlayDefinition | FootballSchemeDefinition) -> str:
    return ", ".join(position_name(p) for p in definition.contributors)


def play_inspect(definition: FootballPlayDefinition, rarity: object | None, cost: int | None,
                 art: ArtPainter | None = None, extra: tuple[tuple[str, str], ...] = ()) -> InspectContent:
    yards = calculate_standardized_play_estimate(definition.action).expected_yards
    return InspectContent(definition.name, rarity, cost, (
        ("Play", definition.description),
        ("Contributors", _contributors(definition)),
        ("Expected yards", f"~{yards:.1f} yards (standardized neutral estimate)"),
        ("Clock", f"{definition.clock_seconds} seconds (incomplete passes use 5)"),
        *extra,
    ), art, tag=f"Offensive play / {definition.family.label}")


def scheme_inspect(definition: FootballSchemeDefinition, rarity: object | None, cost: int | None,
                   art: ArtPainter | None = None, extra: tuple[tuple[str, str], ...] = ()) -> InspectContent:
    return InspectContent(definition.name, rarity, cost, (
        ("Defense call", definition.description),
        ("Stops", f"{definition.family.label} plays"),
        ("Contributors", _contributors(definition)),
        *extra,
    ), art, tag="Defense call")


def bonus_inspect(definition: FootballBonusCardDefinition, rarity: object | None, cost: int | None,
                  art: ArtPainter | None = None, extra: tuple[tuple[str, str], ...] = ()) -> InspectContent:
    return InspectContent(definition.name, rarity, cost, (("Effect", definition.description), *extra),
                          art, tag="Bonus card")


def removal_inspect(card: FootballShopCard, reason: str | None,
                    art: ArtPainter | None = None) -> InspectContent:
    rows = [("Service", card.description),
            ("How it works", "Pay to open your Playbook, then pick the exact copy to remove. "
                             "Each deck keeps at least 4 cards.")]
    if reason:
        rows.append(("Unavailable", reason))
    return InspectContent(card.name, card.rarity, card.cost, tuple(rows), art, tag="Shop service")


def coach_modifier_line(coach: FootballCoachProfile) -> str:
    """Two modifiers per line in the coach's own order, e.g. 'QB +20%  ·  O-LINE +10%'."""
    parts = [f"{_POSITION_LABELS[position]} {modifier_text(value)}"
             for position, value in coach.position_modifiers.items()]
    return "\n".join("  \u00b7  ".join(parts[i:i + 2]) for i in range(0, len(parts), 2))


def coach_inspect(coach: FootballCoachProfile, art: ArtPainter | None = None) -> InspectContent:
    """Draft coach: side, position modifiers, short perk line, and the full rules."""
    return InspectContent(
        coach.name, None, None,
        (("Coach perk", coach_perk_short(coach), True),
         ("Position modifiers", coach_modifier_line(coach)),
         ("Full rules", coach_perk_rules(coach))),
        art, tag=f"{coach.side.value.title()} coach",
    )


def coach_pair_inspect(pair_number: int, offense: FootballCoachProfile,
                       defense: FootballCoachProfile) -> InspectContent:
    """Both coaches of a keyboard-focused pair: name, short perk line, full rules."""
    sections: list[tuple] = []
    for coach in (offense, defense):
        sections.append((f"{coach.side.value} \u00b7 {coach.name}", coach_perk_short(coach), True))
        sections.append(("", coach_perk_rules(coach)))
    return InspectContent(f"Pair {pair_number:02d} staff", None, None, tuple(sections),
                          tag="Offense and defense coaches")
