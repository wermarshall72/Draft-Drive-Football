"""Match-screen perk pieces: the ready/used tray, Read Keys, and the Green Dog panel.

Everything reads the match state and the pure perk history; nothing here changes
rules. The tray shows one chip per perk the human's roster carries (limited ones
with a READY / USED / ARMED / IDLE dot), a hover tooltip, and a click popup with
the full rules. The Read Keys panel shows the rival's offensive hand while the
human picks a scheme; the Green Dog panel shows the active scheme and the hand
schemes it may be swapped for (the decision buttons live in the outcome strip).
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from src.engine.football import (
    FootballMatchState,
    FootballPlayerPerkKind,
    FootballPosition,
    FootballTeamSide,
)
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)
from src.engine.football_perk_context import opponent, perk_history, team_perks
from src.engine.football_player_catalog import FootballPerkLimit, FootballPlayerPerk
from src.ui.football_card_art import (
    bonus_card_art, draw_card_art, play_card_art, scheme_card_art,
)
from src.ui.football_match_events import play_family_kind
from src.ui.football_match_field import PLAY_LINE_COLORS
from src.ui.football_ui_kit import (
    MATCH_DIM, MATCH_FOCUS, MATCH_GOLD, MATCH_GOOD, MATCH_INK, MATCH_MUTED, MATCH_PANEL,
    MATCH_PANEL_DEEP, MATCH_PANEL_EDGE, MATCH_PANEL_EDGE_SOFT, MATCH_PANEL_HIGH, MATCH_TEXT,
    blit_text, match_font, plain_font,
)
from src.ui.football_player_perks import POSITION_SHORT
from src.ui.text import fit_text

READY, USED, ARMED, IDLE = "READY", "USED", "ARMED", "IDLE"
READ_KEYS_TITLE = "READ KEYS"
GREEN_DOG_TITLE = "GREEN DOG"
STATUS_COLORS = {READY: MATCH_GOOD, ARMED: MATCH_GOLD, USED: MATCH_DIM, IDLE: MATCH_DIM}
_SCOPES = {FootballPerkLimit.DRIVE: "drive", FootballPerkLimit.HALF: "half", FootballPerkLimit.GAME: "game"}


@dataclass(frozen=True)
class PerkStatus:
    position: FootballPosition
    perk: FootballPlayerPerk
    status: str  # READY, USED, ARMED, or IDLE


def limited_perk_statuses(match: FootballMatchState, side: FootballTeamSide) -> list[PerkStatus]:
    """Each limited perk the team carries and whether it can still fire."""
    history = perk_history(match)
    statuses = []
    order = list(FootballPosition)
    for kind, (position, perk) in sorted(
        team_perks(match, side).items(), key=lambda item: order.index(item[1][0])
    ):
        if kind is FootballPlayerPerkKind.BAIT_AND_JUMP:
            # Once per half, paid off by a charge from the rival's Deep catches.
            if history.used(kind, side, "half"):
                status = USED
            elif history.deep_charge(opponent(side), armed_by_completion=True, whole_game=True):
                status = ARMED
            else:
                status = IDLE
            statuses.append(PerkStatus(position, perk, status))
        elif perk.limit in _SCOPES:
            used = history.used(kind, side, _SCOPES[perk.limit])
            statuses.append(PerkStatus(position, perk, USED if used else READY))
        elif perk.limit is FootballPerkLimit.CHARGE:  # Shot Setup
            armed = history.deep_charge(side, armed_by_completion=False, whole_game=False)
            statuses.append(PerkStatus(position, perk, ARMED if armed else IDLE))
    return statuses


def perk_status_for(match: FootballMatchState | None, side: FootballTeamSide,
                    kind: FootballPlayerPerkKind) -> str | None:
    if match is None:
        return None
    return next(
        (item.status for item in limited_perk_statuses(match, side) if item.perk.kind is kind), None
    )


# -- the perk tray ---------------------------------------------------------------------

OFFENSE_POSITIONS = (
    FootballPosition.QB, FootballPosition.RB, FootballPosition.WR, FootballPosition.O_LINE,
)
TRAY_LABEL = "PERKS"
TRAY_CHIP_WIDTH = 46
TRAY_CHIP_HEIGHT = 22
TRAY_CHIP_GAP = 5
TRAY_ROW_GAP = 4
TRAY_FONT_SIZE = 13
ALWAYS_ON = "ALWAYS ON"


@dataclass(frozen=True)
class TrayPerk:
    """One chip: a drafted specialist's perk, with a status when it is limited."""

    position: FootballPosition
    perk: FootballPlayerPerk
    status: str | None  # READY, USED, ARMED, or IDLE; None for always-on perks

    @property
    def key(self) -> tuple[str, str]:
        return ("perk-chip", self.perk.kind.value)


def tray_perks(match: FootballMatchState, side: FootballTeamSide = FootballTeamSide.TEAM_A) -> list[TrayPerk]:
    """Every perk the team's roster carries, in position order (Basic players have none)."""
    limited = {item.perk.kind: item.status for item in limited_perk_statuses(match, side)}
    order = list(FootballPosition)
    return [
        TrayPerk(position, perk, limited.get(kind))
        for kind, (position, perk) in sorted(
            team_perks(match, side).items(), key=lambda item: order.index(item[1][0])
        )
    ]


def tray_layout(rect: pygame.Rect, perks: list[TrayPerk]) -> tuple[pygame.Rect, list[pygame.Rect]]:
    """The PERKS label rect and one chip rect per perk: offense on top, defense below."""
    label_font = plain_font(10)
    label = pygame.Rect((0, 0), label_font.size(TRAY_LABEL))
    label.midleft = (rect.left, rect.centery)
    left = label.right + 6
    rows = (rect.top, rect.top + TRAY_CHIP_HEIGHT + TRAY_ROW_GAP)
    counts = [0, 0]
    chips = []
    for item in perks:
        row = 0 if item.position in OFFENSE_POSITIONS else 1
        x = left + counts[row] * (TRAY_CHIP_WIDTH + TRAY_CHIP_GAP)
        counts[row] += 1
        chips.append(pygame.Rect(x, rows[row], TRAY_CHIP_WIDTH, TRAY_CHIP_HEIGHT))
    return label, chips


def draw_perk_tray(
    surface: pygame.Surface,
    rect: pygame.Rect,
    match: FootballMatchState,
    side: FootballTeamSide = FootballTeamSide.TEAM_A,
    *,
    focused: int | None = None,
    hovered: int | None = None,
    open_index: int | None = None,
) -> list[tuple[TrayPerk, pygame.Rect]]:
    """Position chips for every perk; limited ones carry a status dot. Returns (perk, rect)."""
    perks = tray_perks(match, side)
    if not perks:
        return []
    label_rect, chip_rects = tray_layout(rect, perks)
    blit_text(surface, plain_font(10), TRAY_LABEL, MATCH_MUTED, label_rect.inflate(2, 2),
              center=label_rect.center)
    font = plain_font(TRAY_FONT_SIZE)
    for index, (item, chip) in enumerate(zip(perks, chip_rects)):
        text = POSITION_SHORT[item.position]
        lit = index in (hovered, open_index)
        pygame.draw.rect(surface, MATCH_PANEL_HIGH if lit else MATCH_PANEL_DEEP, chip, border_radius=8)
        if item.status is None:
            # Always on: a neutral chip, no dot.
            pygame.draw.rect(surface, MATCH_PANEL_EDGE, chip, 1, border_radius=8)
            blit_text(surface, font, text, MATCH_TEXT, chip, center=chip.center)
        else:
            color = STATUS_COLORS[item.status]
            live = item.status in (READY, ARMED)
            pygame.draw.rect(surface, color if live else MATCH_PANEL_EDGE_SOFT, chip, 1, border_radius=8)
            pygame.draw.circle(surface, color, (chip.left + 11, chip.centery), 4)
            blit_text(surface, font, text, MATCH_TEXT if live else MATCH_MUTED, chip,
                      midleft=(chip.left + 19, chip.centery))
        if index == focused:
            pygame.draw.rect(surface, MATCH_FOCUS, chip.inflate(4, 4), 2, border_radius=10)
    return list(zip(perks, chip_rects))


def tray_status_text(item: TrayPerk) -> str:
    return item.status if item.status is not None else ALWAYS_ON


def tray_tooltip_lines(item: TrayPerk) -> tuple[str, str, str]:
    """(perk name, 'QB · WITH RB · 1/DRIVE · READY', card line), all from the wording module."""
    from src.ui.football_player_perks import limit_label, partner_tag, perk_card_line

    meta = [POSITION_SHORT[item.position]]
    meta += [text for text in (partner_tag(item.perk), limit_label(item.perk)) if text]
    meta.append(tray_status_text(item))
    return item.perk.name.upper(), " · ".join(meta), perk_card_line(item.perk)


def draw_tray_tooltip(surface: pygame.Surface, item: TrayPerk, anchor: pygame.Rect, top: int) -> pygame.Rect:
    """A compact two-row tooltip just under the scoreboard, left-aligned to its chip."""
    name, meta, line = tray_tooltip_lines(item)
    name_font, meta_font, line_font = plain_font(14), plain_font(12), plain_font(13, False)
    gap = 12
    first = name_font.size(name)[0] + gap + meta_font.size(meta)[0]
    width = max(first, line_font.size(line)[0]) + 28
    rect = pygame.Rect(anchor.left - 12, top, width, 50)
    rect.right = min(rect.right, surface.get_width() - 12)
    rect.left = max(rect.left, 12)
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=10)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=10)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=10)
    name_rect = blit_text(surface, name_font, name, MATCH_GOLD, rect, topleft=(rect.left + 14, rect.top + 6))
    color = STATUS_COLORS.get(item.status, MATCH_MUTED) if item.status in (READY, ARMED) else MATCH_MUTED
    blit_text(surface, meta_font, meta, color, rect, midleft=(name_rect.right + gap, name_rect.centery + 1))
    blit_text(surface, line_font, line, MATCH_TEXT, rect, topleft=(rect.left + 14, rect.top + 27))
    return rect


PERK_POPUP_WIDTH = 400
PERK_POPUP_CLOSE = "[ESC] CLOSE"


def draw_perk_popup(surface: pygame.Surface, item: TrayPerk, match: FootballMatchState,
                    topleft: tuple[int, int], side: FootballTeamSide = FootballTeamSide.TEAM_A) -> pygame.Rect:
    """The full rules, partner, limit, and status, drawn like a Depth Chart card back."""
    from src.engine.football_player_catalog import player_type_for_id
    from src.ui.football_display import _POSITION_LABELS, player_partnership_text
    from src.ui.football_player_draft_view import draw_perk_heading, perk_heading_extra
    from src.ui.football_player_perks import perk_rules
    from src.ui.text import wrap_text_lines

    pad_x, pad_y = 12, 10
    inner_width = PERK_POPUP_WIDTH - pad_x * 2
    rules_font = plain_font(13, False)
    lines = wrap_text_lines(perk_rules(item.perk), rules_font, inner_width)
    extra = perk_heading_extra(item.perk, item.status, inner_width)
    height = pad_y * 2 + 18 + 18 + extra + 8 + len(lines) * rules_font.get_height() + 10 + 20
    rect = pygame.Rect(topleft, (PERK_POPUP_WIDTH, height))
    rect.right = min(rect.right, surface.get_width() - 12)
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 3), border_radius=9)
    pygame.draw.rect(surface, MATCH_PANEL_HIGH, rect, border_radius=9)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=9)
    inner = rect.inflate(-pad_x * 2, -pad_y * 2)
    roster = match.team_a if side is FootballTeamSide.TEAM_A else match.team_b
    player = roster.players[item.position]
    player_type = player_type_for_id(player.player_type_id) if player.player_type_id else None
    owner = player_type.name.upper() if player_type is not None else player.name.upper()
    header_font = plain_font(11)
    blit_text(surface, header_font, fit_text(f"{_POSITION_LABELS[item.position]} · {owner}",
                                             header_font, inner.width - 80),
              MATCH_MUTED, inner, topleft=inner.topleft)
    blit_text(surface, plain_font(10), PERK_POPUP_CLOSE, MATCH_DIM, inner, topright=inner.topright)
    heading = pygame.Rect(inner.left, inner.top + 18, inner.width, 18)
    y = draw_perk_heading(surface, heading, item.perk, item.status) + 8
    for index, line in enumerate(lines):
        blit_text(surface, rules_font, line, MATCH_TEXT, inner,
                  topleft=(inner.left, y + index * rules_font.get_height()))
    partner, _ = player_partnership_text(player_type)
    chip_font = plain_font(11)
    chips = (f"PARTNER  {partner.removeprefix('Partner: ').upper()}",
             f"STATUS  {tray_status_text(item)}")
    x = inner.left
    for index, text in enumerate(chips):
        chip = pygame.Rect(x, inner.bottom - 20, chip_font.size(text)[0] + 14, 20)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, chip, border_radius=10)
        color = MATCH_TEXT
        if index == 1 and item.status is not None:
            color = STATUS_COLORS[item.status] if item.status in (READY, ARMED) else MATCH_MUTED
        blit_text(surface, chip_font, text, color, chip.inflate(2, 2), center=chip.center)
        x = chip.right + 6
    return rect


def _mini_card(surface: pygame.Surface, rect: pygame.Rect, card_id: str, *, offensive: bool,
               caption: str | None = None, highlight: bool = False) -> None:
    """A small card face: band, art tile, and name (plus an optional caption above)."""
    if offensive and card_id in BONUS_CARD_CATALOG:
        name, band, art = BONUS_CARD_CATALOG[card_id].name, MATCH_GOLD, bonus_card_art(
            BONUS_CARD_CATALOG[card_id].action)
    elif offensive:
        definition = OFFENSIVE_PLAY_CATALOG[card_id]
        name, band, art = definition.name, PLAY_LINE_COLORS[play_family_kind(definition.family)], \
            play_card_art(definition.family)
    else:
        definition = DEFENSIVE_SCHEME_CATALOG[card_id]
        name, band, art = definition.name, PLAY_LINE_COLORS[play_family_kind(definition.family)], \
            scheme_card_art(definition.family)
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 3), border_radius=8)
    pygame.draw.rect(surface, MATCH_PANEL_HIGH, rect, border_radius=8)
    pygame.draw.rect(surface, MATCH_FOCUS if highlight else MATCH_PANEL_EDGE, rect,
                     3 if highlight else 2, border_radius=8)
    pygame.draw.rect(surface, band, (rect.left + 6, rect.top + 5, rect.width - 12, 3), border_radius=2)
    tile = pygame.Rect(rect.left + 8, rect.top + 12, rect.width - 16, max(30, rect.height - 46))
    draw_card_art(surface, art, tile)
    font = plain_font(11)
    blit_text(surface, font, fit_text(name.upper(), font, rect.width - 8), MATCH_TEXT, rect,
              midtop=(rect.centerx, tile.bottom + 5))
    if offensive and card_id in OFFENSIVE_PLAY_CATALOG:
        family = OFFENSIVE_PLAY_CATALOG[card_id].family.label.upper()
    elif not offensive:
        family = f"STOPS {DEFENSIVE_SCHEME_CATALOG[card_id].family.label.upper()}"
    else:
        family = "BONUS CARD"
    small = plain_font(9, False)
    blit_text(surface, small, fit_text(family, small, rect.width - 8), MATCH_MUTED, rect,
              midtop=(rect.centerx, tile.bottom + 20))
    if caption:
        tag_font = plain_font(9)
        tag = pygame.Rect(0, 0, tag_font.size(caption)[0] + 12, 15)
        tag.midbottom = (rect.centerx, rect.top + 1)
        pygame.draw.rect(surface, MATCH_FOCUS if highlight else MATCH_PANEL, tag, border_radius=7)
        blit_text(surface, tag_font, caption, MATCH_INK if highlight else MATCH_MUTED, tag, center=tag.center)


def _overlay_panel(surface: pygame.Surface, rect: pygame.Rect, title: str, subtitle: str) -> pygame.Rect:
    """The match popup style, compact enough to sit over the field."""
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 5), border_radius=14)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=14)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=14)
    title_font = plain_font(20)
    title_rect = blit_text(surface, title_font, title, MATCH_GOLD, rect, topleft=(rect.left + 18, rect.top + 10))
    subtitle_font = match_font(12, False)
    blit_text(surface, subtitle_font, fit_text(subtitle, subtitle_font, rect.right - title_rect.right - 32),
              MATCH_MUTED, rect, midleft=(title_rect.right + 14, title_rect.centery + 1))
    pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (rect.left + 16, rect.top + 42),
                     (rect.right - 16, rect.top + 42))
    return pygame.Rect(rect.left + 16, rect.top + 52, rect.width - 32, rect.height - 62)


def read_keys_cards(match: FootballMatchState, side: FootballTeamSide = FootballTeamSide.TEAM_A) -> tuple[str, ...]:
    deck = getattr(match, f"{opponent(side).value}_offense_deck")
    return tuple(card.card_id for card in deck.hand) if deck is not None else ()


def has_read_keys(match: FootballMatchState, side: FootballTeamSide = FootballTeamSide.TEAM_A) -> bool:
    return FootballPlayerPerkKind.READ_KEYS in team_perks(match, side)


def draw_read_keys_panel(surface: pygame.Surface, field: pygame.Rect, match: FootballMatchState) -> pygame.Rect:
    """The rival's whole offensive hand, shown over the field while you set your defense."""
    cards = read_keys_cards(match)
    card_width, gap = 112, 12
    count = max(1, len(cards))
    width = min(field.width - 40, max(420, count * (card_width + gap) - gap + 32))
    rect = pygame.Rect(0, 0, width, min(field.height - 20, 236))
    rect.center = field.center
    content = _overlay_panel(
        surface, rect, READ_KEYS_TITLE,
        f"Rival's offensive hand · {len(cards)} card{'s' if len(cards) != 1 else ''} · [R] hide",
    )
    if not cards:
        blit_text(surface, match_font(14), "The rival's hand is empty.", MATCH_MUTED, content,
                  midleft=(content.left, content.centery))
        return rect
    card_width = min(card_width, (content.width - gap * (len(cards) - 1)) // len(cards))
    total = len(cards) * card_width + gap * (len(cards) - 1)
    x = content.centerx - total // 2
    for card_id in cards:
        _mini_card(surface, pygame.Rect(x, content.top + 6, card_width, content.height - 8),
                   card_id, offensive=True)
        x += card_width + gap
    return rect


def draw_green_dog_panel(surface: pygame.Surface, field: pygame.Rect, match: FootballMatchState) -> pygame.Rect:
    """The active scheme and the hand schemes that may replace it for the rest of the drive."""
    active = match.current_drive_defensive_scheme
    deck = match.team_a_defense_deck
    hand = tuple(card.card_id for card in deck.hand) if deck is not None else ()
    read = read_keys_cards(match) if has_read_keys(match) else ()
    card_width, gap = 108, 12
    count = 1 + len(hand)
    width = min(field.width - 40, max(520, count * (card_width + gap) + 60))
    rect = pygame.Rect(0, 0, width, min(field.height - 16, 250))
    rect.center = field.center
    subtitle = "Rival converted · keep or swap for the rest of the drive"
    content = _overlay_panel(surface, rect, GREEN_DOG_TITLE, subtitle)
    footer = 22 if read else 0
    cards_box = pygame.Rect(content.left, content.top + 12, content.width, content.height - 14 - footer)
    card_width = min(card_width, (cards_box.width - gap * count - 30) // count)
    total = count * card_width + gap * (count - 1) + 30
    x = cards_box.centerx - total // 2
    if active is not None:
        _mini_card(surface, pygame.Rect(x, cards_box.top, card_width, cards_box.height), active.value,
                   offensive=False, caption="ACTIVE", highlight=True)
    x += card_width + gap
    arrow = blit_text(surface, plain_font(13), "OR", MATCH_GOLD, cards_box,
                      center=(x + 9, cards_box.centery))
    x = arrow.right + gap
    for card_id in hand:
        _mini_card(surface, pygame.Rect(x, cards_box.top, card_width, cards_box.height), card_id,
                   offensive=False, caption="SWAP IN")
        x += card_width + gap
    if read:
        names = ", ".join(
            OFFENSIVE_PLAY_CATALOG[card_id].name if card_id in OFFENSIVE_PLAY_CATALOG
            else BONUS_CARD_CATALOG[card_id].name for card_id in read
        )
        font = plain_font(11)
        blit_text(surface, font, fit_text(f"READ KEYS · RIVAL HAND: {names.upper()}", font, content.width),
                  MATCH_TEXT, content, midbottom=(content.centerx, content.bottom))
    return rect
