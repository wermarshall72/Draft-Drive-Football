"""Player draft: the draft tracker plus three candidate cards in the shared navy-stadium kit.

The header matches coach selection. The sidebar lists every pick in draft order with
that position's coach bonus, and drafted rows show coached power and the partner link.
Each candidate card shows a portrait (Heisman pose while active), base and coached
power, the partnership with a callout for an already-drafted partner, and the
planned (inactive) perk details.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

import pygame

from src.engine.football import FootballPlayer, FootballPosition
from src.engine.football_appearance import FootballPlayerAppearance, POSITION_ART
from src.engine.football_coaches import OFFENSIVE_POSITIONS
from src.engine.football_controller import FootballGameControllerState
from src.engine.football_player_catalog import coached_player_power, player_type_for_id
from src.engine.football_team_builder import (
    PLAYER_DRAFT_ORDER, FootballPlayerCandidate, FootballTeamBuilderState,
)
from src.ui.football_coach_perks import modifier_text
from src.ui.football_display import _POSITION_LABELS, player_perk_text
from src.ui.football_draft_interaction import PlayerInspection
from src.ui.football_ui_kit import (
    MATCH_DIM, MATCH_GOOD, MATCH_INK, MATCH_MUTED, MATCH_PANEL, MATCH_PANEL_DEEP, MATCH_PANEL_EDGE,
    MATCH_PANEL_EDGE_SOFT, MATCH_PANEL_HIGH, MATCH_TEXT, MODIFIER_NEGATIVE, MODIFIER_NEUTRAL,
    MODIFIER_POSITIVE, blit_text, fit_wrapped, mix, plain_font, stadium_backdrop, team_accent,
)
from src.ui.player_art import draw_draft_player
from src.ui.stat_icons import stat_icon
from src.ui.text import fit_text
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button

SIDEBAR_TITLE = "BUILD YOUR ROSTER"
PLANNED_LABEL = "PLANNED / INACTIVE"
NO_PARTNER = "No partner"
PARTNER_EXPLANATION = "+10% when both contribute to a play"

BODY_TOP = 96
BODY_BOTTOM = 704
SIDEBAR = pygame.Rect(20, BODY_TOP, 282, BODY_BOTTOM - BODY_TOP)
CARDS_LEFT = 316
CARDS_RIGHT = 1260
CARD_GAP = 12

# Tracker rows inside the sidebar.
_STAFF_TOP = 44
_ROWS_TOP = 76
_ROW_HEIGHT = 60
_ROW_GAP = 5
_CHIP_WIDTH = 50

# Offsets inside a candidate card.
_NAME_TOP = 10
_POSITION_TOP = 40
_PORTRAIT_TOP = 60
_PORTRAIT_HEIGHT = 154
_STATS_TOP = 222
_STATS_HEIGHT = 64
_PARTNER_TOP = 296
_PERK_TOP = 364
_PERK_SIZES = (14, 13, 12, 11)
_BUTTON_HEIGHT = 40
_BUTTON_BOTTOM_GAP = 16


def modifier_color(value: float) -> pygame.Color:
    return MODIFIER_POSITIVE if value > 0 else MODIFIER_NEGATIVE if value < 0 else MODIFIER_NEUTRAL


def power_text(value: float) -> str:
    """Power as the Depth Chart displays it (8-decimal rounding, no trailing zeros)."""
    return f"{round(value, 8):g}"


def position_coach_modifier(builder: FootballTeamBuilderState, position: FootballPosition) -> float:
    """The selected staff's modifier for ``position`` (offense coach for offense, else defense)."""
    pair = builder.selected_coach_pair
    if pair is None:
        return 0.0
    coach = pair.offense if position in OFFENSIVE_POSITIONS else pair.defense
    return coach.position_modifiers.get(position, 0.0)


def draft_coached_power(builder: FootballTeamBuilderState, player: FootballPlayer) -> float:
    """Coached power with the engine's own math, matching the Depth Chart's Modified Stats."""
    return coached_player_power(player, position_coach_modifier(builder, player.position))


@dataclass(frozen=True)
class TrackerRow:
    """What one draft tracker row shows."""

    position: FootballPosition
    modifier: float
    chip: str  # the coach bonus, e.g. "+20%"
    status: str  # "drafted", "current", or "up_next"
    name: str | None = None
    power: str | None = None  # coached power, e.g. "55"
    partner: str | None = None  # partner position label, None for basic players
    partner_drafted: bool = False


def tracker_row(builder: FootballTeamBuilderState, position: FootballPosition) -> TrackerRow:
    modifier = position_coach_modifier(builder, position)
    drafted = builder.selected_players.get(position)
    if drafted is None:
        status = "current" if position is builder.required_position else "up_next"
        return TrackerRow(position, modifier, modifier_text(modifier), status)
    partner = _player_type(drafted).partner_position
    return TrackerRow(
        position, modifier, modifier_text(modifier), "drafted", drafted.name,
        power_text(draft_coached_power(builder, drafted)),
        _partner_label(partner) if partner is not None else None,
        partner is not None and partner in builder.selected_players,
    )


def partner_callout(builder: FootballTeamBuilderState, player: FootballPlayer) -> tuple[str, bool] | None:
    """The card's partner line: ('Pairs with X (WR)', True), ('WR pick still to come', False), or None."""
    partner = _player_type(player).partner_position
    if partner is None:
        return None
    drafted = builder.selected_players.get(partner)
    if drafted is None:
        return f"{_partner_label(partner)} pick still to come", False
    return f"Pairs with {drafted.name} ({_partner_label(partner)})", True


def pair_card_rects(count: int) -> list[pygame.Rect]:
    width = (CARDS_RIGHT - CARDS_LEFT - CARD_GAP * (count - 1)) // max(1, count)
    return [pygame.Rect(CARDS_LEFT + i * (width + CARD_GAP), BODY_TOP, width, BODY_BOTTOM - BODY_TOP)
            for i in range(count)]


def tracker_row_rects() -> dict[FootballPosition, pygame.Rect]:
    return {
        position: pygame.Rect(SIDEBAR.left + 12, SIDEBAR.top + _ROWS_TOP + index * (_ROW_HEIGHT + _ROW_GAP),
                              SIDEBAR.width - 24, _ROW_HEIGHT)
        for index, position in enumerate(PLAYER_DRAFT_ORDER)
    }


def draft_button_rect(card: pygame.Rect) -> pygame.Rect:
    return pygame.Rect(card.left + 12, card.bottom - _BUTTON_BOTTOM_GAP - _BUTTON_HEIGHT,
                       card.width - 24, _BUTTON_HEIGHT)


def _partner_label(position: FootballPosition) -> str:
    """The partner position as the partnership line spells it ('WR', 'O-line')."""
    return _draft_position_label(position)


def _draw_arrow(surface: pygame.Surface, left: int, centery: int, color: pygame.Color) -> int:
    """A small right arrow (the kit font has no arrow glyph); returns its right edge."""
    pygame.draw.line(surface, color, (left, centery), (left + 11, centery), 2)
    pygame.draw.polygon(surface, color, ((left + 9, centery - 4), (left + 14, centery), (left + 9, centery + 4)))
    return left + 14


def _draw_check(surface: pygame.Surface, left: int, centery: int, color: pygame.Color) -> int:
    """A small check mark; returns its right edge."""
    pygame.draw.lines(surface, color, False,
                      ((left, centery), (left + 3, centery + 3), (left + 9, centery - 4)), 2)
    return left + 10


class FootballPlayerDraftView:
    def __init__(
        self, theme: Theme, inspection: PlayerInspection, focus_index: int,
        choose_player: Callable[[FootballPosition, FootballPlayerCandidate, FootballPlayerAppearance], None],
        team_name: str = "",
    ) -> None:
        self.theme = theme
        self.player_inspection = inspection
        self.focus_index = focus_index
        self.choose_player = choose_player
        self.team_name = team_name
        self.accent = team_accent(theme.primary)
        self.tracker_rects: dict[FootballPosition, pygame.Rect] = {}
        self._perk_size = _PERK_SIZES[0]

    # -- header ------------------------------------------------------------------

    def draw_backdrop(self, surface: pygame.Surface, state: FootballGameControllerState | None = None) -> None:
        surface.blit(stadium_backdrop(surface.get_size()), (0, 0))
        if state is None:
            return
        builder = state.team_builder
        position = builder.required_position
        current = _POSITION_LABELS[position] if position is not None else "COMPLETE"
        header = pygame.Rect(20, 16, 1100, 70)
        title = blit_text(surface, plain_font(32), f"DRAFT POOL · {current}", MATCH_TEXT, header,
                          topleft=(header.left, header.top))
        pygame.draw.rect(surface, self.accent, (title.right + 10, title.centery - 2, 34, 4), border_radius=2)
        sub_y = header.top + 46
        swatch = pygame.Rect(header.left, sub_y + 1, 12, 12)
        pygame.draw.rect(surface, self.theme.primary, swatch, border_radius=3)
        pygame.draw.rect(surface, mix(self.accent, MATCH_TEXT, 0.4), swatch, 1, border_radius=3)
        sub_font = plain_font(14)
        pick = min(len(builder.selected_players) + 1, len(PLAYER_DRAFT_ORDER))
        tail = f"  ·  Pick {pick} of {len(PLAYER_DRAFT_ORDER)}"
        name = fit_text((self.team_name or "Your team").upper(), sub_font, 420)
        name_rect = blit_text(surface, sub_font, name, MATCH_TEXT, header, topleft=(swatch.right + 8, sub_y - 2))
        blit_text(surface, sub_font, tail, MATCH_MUTED, header, topleft=(name_rect.right, sub_y - 2))

    # -- body --------------------------------------------------------------------

    def draw(self, surface: pygame.Surface, content: pygame.Rect,
             state: FootballGameControllerState) -> list[Button]:
        builder = state.team_builder
        offers = tuple(candidate for candidate in builder.current_offer
                       if isinstance(candidate, FootballPlayerCandidate))
        if len(offers) != len(builder.current_offer):
            raise RuntimeError("The controller returned a non-player draft offer.")
        self.player_inspection.set_offers(offers)
        cards = pair_card_rects(len(offers))
        self.player_inspection.card_rects = cards
        active = self.player_inspection.active_index(self.focus_index)
        self.player_inspection.partner_row = None
        if active is not None and 0 <= active < len(offers):
            self.player_inspection.partner_row = _player_type(offers[active].player).partner_position
        self._draw_sidebar(surface, builder)

        # One perk text size for all three cards, so the row reads evenly.
        self._perk_size = min((_perk_size(_player_type(c.player), _perk_text_rect(rect)) for c, rect
                               in zip(offers, cards)), default=_PERK_SIZES[0])
        buttons: list[Button] = []
        self.player_inspection.portraits = []
        for index, (candidate, rect) in enumerate(zip(offers, cards)):
            appearance = FootballPlayerAppearance(
                POSITION_ART[candidate.position], self.player_inspection.skin_tones[index],
                tuple(self.theme.primary[:3]), tuple(self.theme.secondary[:3]),
            )
            self._draw_card(surface, rect, candidate, appearance, builder, active == index)
            buttons.append(Button(
                f"DRAFT {candidate.position.value}",
                lambda player=candidate, art=appearance: self.choose_player(player.position, player, art),
                draft_button_rect(rect), variant="draft-select",
            ))
        return buttons

    def _panel(self, surface: pygame.Surface, rect: pygame.Rect, *, active: bool = False) -> None:
        pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=12)
        pygame.draw.rect(surface, mix(MATCH_PANEL, self.accent, 0.06) if active else MATCH_PANEL,
                         rect, border_radius=12)
        if active:
            # A light keyline keeps dark team colors visible against navy.
            pygame.draw.rect(surface, mix(self.accent, MATCH_TEXT, 0.25), rect, 3, border_radius=12)
        else:
            pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, rect, 2, border_radius=12)
        pygame.draw.rect(surface, self.accent, (rect.left + 12, rect.top + 13, 4, 16), border_radius=2)

    # -- sidebar: staff and draft tracker ------------------------------------------

    def _draw_sidebar(self, surface: pygame.Surface, builder: FootballTeamBuilderState) -> None:
        rect = SIDEBAR
        self._panel(surface, rect)
        blit_text(surface, plain_font(17), SIDEBAR_TITLE, MATCH_TEXT, rect, topleft=(rect.left + 22, rect.top + 10))
        box = rect.inflate(-28, 0)
        staff_y = rect.top + _STAFF_TOP
        label_font = plain_font(11)
        label = blit_text(surface, label_font, "STAFF", MATCH_MUTED, rect, midleft=(box.left, staff_y + 8))
        pair = builder.selected_coach_pair
        names = f"{pair.offense.name} · {pair.defense.name}" if pair is not None else "No staff"
        names_font = plain_font(13)
        names_left = label.right + 10
        blit_text(surface, names_font, fit_text(names, names_font, box.right - names_left), MATCH_TEXT, rect,
                  midleft=(names_left, staff_y + 8))
        pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (box.left, rect.top + _ROWS_TOP - 10),
                         (box.right, rect.top + _ROWS_TOP - 10))
        self.tracker_rects = tracker_row_rects()
        for position, row in self.tracker_rects.items():
            self._draw_tracker_row(surface, row, position, builder)

    def _draw_tracker_row(self, surface: pygame.Surface, row: pygame.Rect, position: FootballPosition,
                          builder: FootballTeamBuilderState) -> None:
        info = tracker_row(builder, position)
        drafted = info.status == "drafted"
        current = info.status == "current"
        partner_lit = position is self.player_inspection.partner_row
        fill = MATCH_PANEL_HIGH if drafted else (
            mix(MATCH_PANEL_DEEP, self.accent, 0.08) if current else MATCH_PANEL_DEEP)
        pygame.draw.rect(surface, fill, row, border_radius=8)
        if current:
            pygame.draw.rect(surface, mix(self.accent, MATCH_TEXT, 0.25), row, 2, border_radius=8)
        elif partner_lit:
            pygame.draw.rect(surface, mix(self.accent, MATCH_PANEL_EDGE, 0.6), row, 1, border_radius=8)
        else:
            pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, row, 1, border_radius=8)
        if partner_lit:
            pygame.draw.rect(surface, self.accent, (row.left + 3, row.top + 9, 3, row.height - 18), border_radius=2)

        chip = pygame.Rect(row.right - 10 - _CHIP_WIDTH, 0, _CHIP_WIDTH, 22)
        chip.centery = row.centery
        pygame.draw.rect(surface, MATCH_PANEL_DEEP if drafted else MATCH_PANEL, chip, border_radius=6)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, chip, 1, border_radius=6)
        blit_text(surface, plain_font(13), info.chip, modifier_color(info.modifier), chip, center=chip.center)

        text = pygame.Rect(row.left + 12, row.top, chip.left - 8 - (row.left + 12), row.height)
        line1 = row.top + 9
        line2_center = row.top + 41
        label_rect = blit_text(surface, plain_font(14), _POSITION_LABELS[position],
                               MATCH_TEXT if drafted or current else MATCH_MUTED, text, topleft=(text.left, line1))
        small = plain_font(12)
        if current:
            tag_font = plain_font(10)
            tag = pygame.Rect(text.left, 0, tag_font.size("CURRENT PICK")[0] + 14, 18)
            tag.centery = line2_center
            pygame.draw.rect(surface, mix(MATCH_PANEL_DEEP, self.accent, 0.18), tag, border_radius=9)
            pygame.draw.rect(surface, mix(self.accent, MATCH_TEXT, 0.25), tag, 1, border_radius=9)
            blit_text(surface, tag_font, "CURRENT PICK", MATCH_TEXT, tag, center=tag.center)
            return
        if not drafted:
            blit_text(surface, small, "UP NEXT", MATCH_DIM, text, midleft=(text.left, line2_center))
            return
        name_font = plain_font(14, False)
        name_left = label_rect.right + 8
        blit_text(surface, name_font, fit_text(info.name, name_font, text.right - name_left), MATCH_TEXT, text,
                  topleft=(name_left, line1))
        power = blit_text(surface, small, f"PWR {info.power}", modifier_color(info.modifier), text,
                          midleft=(text.left, line2_center))
        x = power.right + 10
        if info.partner is None:
            blit_text(surface, small, fit_text(NO_PARTNER, small, text.right - x), MATCH_DIM, text,
                      midleft=(x, line2_center))
            return
        if info.partner_drafted:
            x = _draw_check(surface, x, line2_center, MATCH_GOOD) + 4
        blit_text(surface, small, fit_text(f"Partner {info.partner}", small, text.right - x),
                  MATCH_TEXT if info.partner_drafted else MATCH_DIM, text, midleft=(x, line2_center))

    # -- candidate cards -----------------------------------------------------------

    def _draw_card(self, surface: pygame.Surface, rect: pygame.Rect, candidate: FootballPlayerCandidate,
                   appearance: FootballPlayerAppearance, builder: FootballTeamBuilderState,
                   active: bool) -> None:
        self._panel(surface, rect, active=active)
        inner = rect.inflate(-24, 0)
        name_box = pygame.Rect(rect.left + 22, rect.top + _NAME_TOP - 4, rect.right - 12 - (rect.left + 22), 30)
        name_font, lines = fit_wrapped(candidate.name, name_box.width, (22, 20, 18, 16), 1)
        blit_text(surface, name_font, lines[0], MATCH_TEXT, name_box, midleft=(name_box.left, name_box.centery))
        blit_text(surface, plain_font(11), _POSITION_LABELS[candidate.position], MATCH_MUTED, inner,
                  topleft=(rect.left + 22, rect.top + _POSITION_TOP))

        portrait = pygame.Rect(inner.left, rect.top + _PORTRAIT_TOP, inner.width, _PORTRAIT_HEIGHT)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, portrait, border_radius=8)
        pygame.draw.rect(surface, self.accent, (portrait.left + 12, portrait.bottom - 5, portrait.width - 24, 3),
                         border_radius=2)
        art = portrait.inflate(-12, -10)
        draw_draft_player(surface, art, appearance, active)
        self.player_inspection.portraits.append((art, appearance, active))

        self._draw_stats(surface, pygame.Rect(inner.left, rect.top + _STATS_TOP, inner.width, _STATS_HEIGHT),
                         candidate.player, builder)
        self._draw_partnership(surface, pygame.Rect(inner.left, rect.top + _PARTNER_TOP, inner.width,
                                                    _PERK_TOP - _PARTNER_TOP - 6),
                               candidate.player, builder)
        self._draw_perk(surface, _perk_box(rect), _player_type(candidate.player))

    def _draw_stats(self, surface: pygame.Surface, strip: pygame.Rect, player: FootballPlayer,
                    builder: FootballTeamBuilderState) -> None:
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, strip, border_radius=7)
        power_width = round(strip.width * 0.44)
        rest = (strip.width - power_width) // 2
        columns = (
            pygame.Rect(strip.left, strip.top, power_width, strip.height),
            pygame.Rect(strip.left + power_width, strip.top, rest, strip.height),
            pygame.Rect(strip.left + power_width + rest, strip.top, strip.width - power_width - rest, strip.height),
        )
        for column in columns[1:]:
            pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (column.left, column.top + 8),
                             (column.left, column.bottom - 8))
        label_font = plain_font(10)
        value_font = plain_font(18)
        label_y = strip.top + 12
        value_y = strip.top + 32
        tag_y = strip.top + 52
        for column, stat, label in zip(columns, ("power", "volatility", "stamina"),
                                       ("POWER", "VOLATILITY", "STAMINA")):
            icon = stat_icon(stat, 12)
            left = column.left + 9
            surface.blit(icon, icon.get_rect(midleft=(left, label_y)))
            blit_text(surface, label_font, label, MATCH_MUTED, column, midleft=(left + icon.get_width() + 3, label_y))

        modifier = position_coach_modifier(builder, player.position)
        power_column = columns[0]
        tag_font = plain_font(10)
        tag_text = f"{modifier_text(modifier)} COACH"
        tag = pygame.Rect(0, 0, tag_font.size(tag_text)[0] + 10, 15)
        tag.midleft = (power_column.left + 6, tag_y)
        pygame.draw.rect(surface, MATCH_PANEL, tag, border_radius=8)
        blit_text(surface, tag_font, tag_text, modifier_color(modifier), tag, center=tag.center)

        base = f"{player.power:g}"
        coached = power_text(draft_coached_power(builder, player))
        left = power_column.left + 9
        base_rect = blit_text(surface, value_font, base, MATCH_TEXT, power_column, midleft=(left, value_y))
        if coached != base:
            arrow_right = _draw_arrow(surface, base_rect.right + 6, value_y, MATCH_MUTED)
            blit_text(surface, value_font, coached, modifier_color(modifier), power_column,
                      midleft=(arrow_right + 6, value_y))
        for column, value in zip(columns[1:], (player.volatility, player.stamina)):
            blit_text(surface, value_font, _draft_percentage(value), MATCH_TEXT, column,
                      midleft=(column.left + 9, value_y))

    def _draw_partnership(self, surface: pygame.Surface, box: pygame.Rect, player: FootballPlayer,
                          builder: FootballTeamBuilderState) -> None:
        partner = _player_type(player).partner_position
        heading = plain_font(15)
        if partner is None:
            blit_text(surface, heading, NO_PARTNER, MATCH_MUTED, box, topleft=(box.left, box.top))
            return
        label = blit_text(surface, plain_font(11), "PARTNER", MATCH_MUTED, box, topleft=(box.left, box.top + 3))
        blit_text(surface, heading, _partner_label(partner), MATCH_TEXT, box, topleft=(label.right + 8, box.top))
        small = plain_font(13, False)
        blit_text(surface, small, PARTNER_EXPLANATION, MATCH_MUTED, box, topleft=(box.left, box.top + 21))
        callout = pygame.Rect(box.left, box.top + 42, box.width, 22)
        text, linked = partner_callout(builder, player)
        if not linked:
            blit_text(surface, small, fit_text(text, small, callout.width), MATCH_DIM, box,
                      midleft=(callout.left, callout.centery))
            return
        pygame.draw.rect(surface, mix(MATCH_PANEL_DEEP, MATCH_GOOD, 0.12), callout, border_radius=6)
        pygame.draw.rect(surface, mix(MATCH_GOOD, MATCH_PANEL_DEEP, 0.5), callout, 1, border_radius=6)
        x = _draw_check(surface, callout.left + 8, callout.centery, MATCH_GOOD) + 6
        font = plain_font(13)
        blit_text(surface, font, fit_text(text, font, callout.right - 8 - x), MATCH_TEXT, callout,
                  midleft=(x, callout.centery))

    def _draw_perk(self, surface: pygame.Surface, box: pygame.Rect, player_type) -> None:
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, box, border_radius=8)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, box, 1, border_radius=8)
        inner = _perk_text_rect_in(box)
        planned, paragraphs = _perk_paragraphs(player_type)
        if planned:
            tag_font = plain_font(10)
            tag = pygame.Rect(inner.left, inner.top - _PERK_TAG_SPACE, tag_font.size(PLANNED_LABEL)[0] + 14, 18)
            pygame.draw.rect(surface, MATCH_PANEL, tag, border_radius=9)
            pygame.draw.rect(surface, MATCH_DIM, tag, 1, border_radius=9)
            blit_text(surface, tag_font, PLANNED_LABEL, MATCH_MUTED, tag, center=tag.center)
        else:
            inner.top -= _PERK_TAG_SPACE
        # The shared size fits every card; a card whose text alone runs longer shrinks itself.
        size = min(self._perk_size, _perk_size(player_type, _perk_text_rect_in(box)))
        y = inner.top
        for text in paragraphs:
            font, lines = fit_wrapped(text, inner.width, (size,), 99)
            for line in lines:
                blit_text(surface, font, line, MATCH_TEXT, box, topleft=(inner.left, y))
                y += font.get_height()

    # -- buttons -----------------------------------------------------------------

    def draw_button(self, surface: pygame.Surface, button: Button, index: int, *, pressed: bool) -> None:
        active = self.player_inspection.active_index(self.focus_index) == index
        rect = button.rect.move(0, 2) if pressed and button.enabled else button.rect
        if self.player_inspection.keyboard and button.focused:
            pygame.draw.rect(surface, MATCH_TEXT, rect.inflate(6, 6), 2, border_radius=10)
        if active:
            fill = self.accent
            edge = mix(self.accent, MATCH_TEXT, 0.35)
        else:
            fill = MATCH_PANEL_HIGH
            edge = MATCH_PANEL_EDGE
        pygame.draw.rect(surface, fill, rect, border_radius=8)
        pygame.draw.rect(surface, edge, rect, 2, border_radius=8)
        position = FootballPosition(button.label.removeprefix("DRAFT ").strip())
        blit_text(surface, plain_font(16), f"DRAFT {_POSITION_LABELS[position]}",
                  readable_ink(fill) if active else MATCH_TEXT, rect, center=rect.center)


_PERK_TAG_SPACE = 24


def _perk_box(card: pygame.Rect) -> pygame.Rect:
    inner = card.inflate(-24, 0)
    top = card.top + _PERK_TOP
    return pygame.Rect(inner.left, top, inner.width, draft_button_rect(card).top - 8 - top)


def _perk_text_rect_in(box: pygame.Rect) -> pygame.Rect:
    """The perk text area below the PLANNED / INACTIVE tag."""
    inner = box.inflate(-20, -14)
    return pygame.Rect(inner.left, inner.top + _PERK_TAG_SPACE, inner.width, inner.height - _PERK_TAG_SPACE)


def _perk_text_rect(card: pygame.Rect) -> pygame.Rect:
    return _perk_text_rect_in(_perk_box(card))


def _perk_paragraphs(player_type) -> tuple[bool, list[str]]:
    paragraphs = player_perk_text(player_type).split("\n")
    if paragraphs[0] == PLANNED_LABEL:
        return True, paragraphs[1:]
    return False, paragraphs


def _perk_size(player_type, rect: pygame.Rect) -> int:
    """The largest perk text size whose wrapped lines fit ``rect``."""
    _planned, paragraphs = _perk_paragraphs(player_type)
    for size in _PERK_SIZES:
        lines = sum(len(fit_wrapped(text, rect.width, (size,), 99)[1]) for text in paragraphs)
        if lines * plain_font(size).get_height() <= rect.height:
            return size
    return _PERK_SIZES[-1]


def _player_type(player: FootballPlayer):
    if player.player_type_id is None:
        raise RuntimeError("Drafted players must have a catalog player type.")
    return player_type_for_id(player.player_type_id)


def _draft_percentage(value: float) -> str:
    percentage = format(Decimal(str(value)) * 100, "f")
    if "." in percentage:
        percentage = percentage.rstrip("0").rstrip(".")
    return f"{percentage}%"


def _draft_position_label(position: FootballPosition) -> str:
    labels = {
        FootballPosition.QB: "QB",
        FootballPosition.RB: "RB",
        FootballPosition.WR: "WR",
        FootballPosition.O_LINE: "O-line",
        FootballPosition.D_LINE: "D-line",
        FootballPosition.LINEBACKERS: "Linebackers",
        FootballPosition.CORNERBACKS: "Cornerbacks",
        FootballPosition.SAFETIES: "Safeties",
    }
    return labels[position]
