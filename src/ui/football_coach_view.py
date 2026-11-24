"""Coach selection: three staff pairs in the shared navy-stadium kit style.

Each pair card shows two coach columns (portrait, name, side, position modifiers),
one short perk line per coach, and a SELECT PAIR button. Hovering a coach opens the
shared inspect panel with its full perk rules; a keyboard-focused pair shows both.
"""

from collections.abc import Callable

import pygame

from src.engine.football_coaches import FootballCoachProfile
from src.engine.football_controller import FootballGameControllerState
from src.ui.coach_art import draw_coach_portrait
from src.ui.football_coach_perks import coach_perk_short, modifier_text
from src.ui.football_display import _POSITION_LABELS
from src.ui.football_draft_interaction import CoachInspection
from src.ui.football_inspect import InspectContent, coach_inspect, coach_pair_inspect
from src.ui.football_ui_kit import (
    MATCH_INK, MATCH_MUTED, MATCH_PANEL, MATCH_PANEL_DEEP, MATCH_PANEL_EDGE, MATCH_PANEL_EDGE_SOFT,
    MATCH_PANEL_HIGH, MATCH_TEXT, MODIFIER_NEGATIVE, MODIFIER_NEUTRAL, MODIFIER_POSITIVE, blit_text,
    fit_wrapped, mix, plain_font, stadium_backdrop, team_accent,
)
from src.ui.text import fit_text
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button

TITLE = "SELECT YOUR COACHES"
SUBTITLE = "Pick one staff for the run"
SELECT_LABEL = "SELECT PAIR"
SIDEBAR_TITLE = "COACHING IMPACT"
SIDEBAR_POINTS = (
    ("POSITION BOOSTS", "Each coach raises or lowers specific positions."),
    ("COACH PERK", "One special effect per coach."),
    ("FOR THE RUN", "Your staff can't be changed later."),
)
SIDEBAR_HINT = "Choose one pair"
SIDEBAR_KEYS = (("TAB", "Next pair"), ("ENTER", "Select pair"))

BODY_TOP = 96
BODY_BOTTOM = 704
SIDEBAR = pygame.Rect(20, BODY_TOP, 224, BODY_BOTTOM - BODY_TOP)
CARDS_LEFT = 258
CARDS_RIGHT = 1260
CARD_GAP = 12

# Offsets inside a pair card.
_PORTRAIT_TOP = 42
_PORTRAIT_HEIGHT = 184
_NAME_TOP = 234
_SIDE_TOP = 257
_MODS_TOP = 282
_MOD_ROW = 26
_DIVIDER = 398
_PERKS_HEAD = 408
_PERK_TOP = 430
_PERK_ROW = 38
_PERK_GAP = 8
_BUTTON_HEIGHT = 40
_BUTTON_BOTTOM_GAP = 16

_SIDE_TAGS = {"offense": "OFF", "defense": "DEF"}


def modifier_color(value: float) -> pygame.Color:
    return MODIFIER_POSITIVE if value > 0 else MODIFIER_NEGATIVE if value < 0 else MODIFIER_NEUTRAL


def pair_card_rects(count: int) -> list[pygame.Rect]:
    width = (CARDS_RIGHT - CARDS_LEFT - CARD_GAP * (count - 1)) // max(1, count)
    return [pygame.Rect(CARDS_LEFT + i * (width + CARD_GAP), BODY_TOP, width, BODY_BOTTOM - BODY_TOP)
            for i in range(count)]


def _column_rects(card: pygame.Rect) -> tuple[pygame.Rect, pygame.Rect]:
    inner = card.inflate(-24, 0)
    half = (inner.width - 12) // 2
    top = card.top + _PORTRAIT_TOP
    height = _MODS_TOP + 4 * _MOD_ROW - _PORTRAIT_TOP
    return (pygame.Rect(inner.left, top, half, height),
            pygame.Rect(inner.right - half, top, half, height))


def _perk_rects(card: pygame.Rect) -> tuple[pygame.Rect, pygame.Rect]:
    inner = card.inflate(-24, 0)
    return tuple(pygame.Rect(inner.left, card.top + _PERK_TOP + row * (_PERK_ROW + _PERK_GAP),
                             inner.width, _PERK_ROW) for row in range(2))


def select_button_rect(card: pygame.Rect) -> pygame.Rect:
    return pygame.Rect(card.left + 12, card.bottom - _BUTTON_BOTTOM_GAP - _BUTTON_HEIGHT,
                       card.width - 24, _BUTTON_HEIGHT)


class FootballCoachView:
    def __init__(
        self, theme: Theme, inspection: CoachInspection, focus_index: int,
        choose_coach: Callable[[int], None], team_name: str = "",
    ) -> None:
        self.theme = theme
        self.inspection = inspection
        self.focus_index = focus_index
        self.choose_coach = choose_coach
        self.team_name = team_name
        self.accent = team_accent(theme.primary)

    # -- header ------------------------------------------------------------------

    def draw_backdrop(self, surface: pygame.Surface) -> None:
        surface.blit(stadium_backdrop(surface.get_size()), (0, 0))
        header = pygame.Rect(20, 16, 1100, 70)
        title_font = plain_font(32)
        title = blit_text(surface, title_font, TITLE, MATCH_TEXT, header, topleft=(header.left, header.top))
        pygame.draw.rect(surface, self.accent, (title.right + 10, title.centery - 2, 34, 4), border_radius=2)
        sub_y = header.top + 46
        swatch = pygame.Rect(header.left, sub_y + 1, 12, 12)
        pygame.draw.rect(surface, self.theme.primary, swatch, border_radius=3)
        pygame.draw.rect(surface, mix(self.accent, MATCH_TEXT, 0.4), swatch, 1, border_radius=3)
        sub_font = plain_font(14)
        tail = f"  ·  {SUBTITLE}"
        name = fit_text((self.team_name or "Your team").upper(), sub_font, 420)
        name_rect = blit_text(surface, sub_font, name, MATCH_TEXT, header, topleft=(swatch.right + 8, sub_y - 2))
        blit_text(surface, sub_font, tail, MATCH_MUTED, header, topleft=(name_rect.right, sub_y - 2))

    # -- body --------------------------------------------------------------------

    def draw(self, surface: pygame.Surface, content: pygame.Rect,
             state: FootballGameControllerState) -> list[Button]:
        self._draw_sidebar(surface)
        offer = state.team_builder.coach_offer
        cards = pair_card_rects(len(offer))
        self.inspection.card_rects = cards
        self.inspection.coach_rects = []
        active = self.inspection.active_index(self.focus_index)
        # Choose this frame's panel first so the cards can highlight its coach.
        contents: dict[tuple, tuple[InspectContent, pygame.Rect]] = {}
        for index, (pair, rect) in enumerate(zip(offer, cards)):
            anchor = pygame.Rect(rect.left, rect.top + _PORTRAIT_TOP, rect.width,
                                 _PERK_TOP + 2 * _PERK_ROW + _PERK_GAP - _PORTRAIT_TOP)
            for column, perk_row, coach in zip(_column_rects(rect), _perk_rects(rect),
                                               (pair.offense, pair.defense)):
                key = ("coach", index, coach.side.value)
                self.inspection.coach_rects += [(key, column), (key, perk_row)]
                contents[key] = (coach_inspect(coach, self._portrait_painter(coach)), anchor)
            contents[("coach", index, "pair")] = (coach_pair_inspect(index + 1, pair.offense, pair.defense),
                                                  anchor)
        self.inspection.inspect.prepare(
            contents, self.inspection.hover_coach, self.inspection.focus_key(self.focus_index),
        )
        buttons: list[Button] = []
        for index, (pair, rect) in enumerate(zip(offer, cards)):
            self._draw_card(surface, rect, index, pair, active == index)
            buttons.append(Button(
                f"CHOOSE STAFF 0{index + 1}", lambda choice=index: self.choose_coach(choice),
                select_button_rect(rect), variant="coach-select",
            ))
        return buttons

    def _portrait_painter(self, coach: FootballCoachProfile):
        return lambda target, box: draw_coach_portrait(target, box, coach.coach_id, self.theme.primary)

    def _highlighted(self, key: tuple) -> bool:
        return self.inspection.hover_coach == key or self.inspection.inspect.shown_key == key

    def draw_overlay(self, surface: pygame.Surface) -> None:
        """Paint the inspect panel above the cards (after buttons are drawn)."""
        self.inspection.inspect.paint(surface)

    def _panel(self, surface: pygame.Surface, rect: pygame.Rect, title: str, *, active: bool = False) -> None:
        pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=12)
        pygame.draw.rect(surface, mix(MATCH_PANEL, self.accent, 0.06) if active else MATCH_PANEL,
                         rect, border_radius=12)
        if active:
            # A light keyline keeps dark team colors visible against navy.
            pygame.draw.rect(surface, mix(self.accent, MATCH_TEXT, 0.25), rect, 3, border_radius=12)
        else:
            pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, rect, 2, border_radius=12)
        pygame.draw.rect(surface, self.accent, (rect.left + 12, rect.top + 13, 4, 16), border_radius=2)
        blit_text(surface, plain_font(17), title, MATCH_TEXT, rect, topleft=(rect.left + 22, rect.top + 10))

    def _draw_sidebar(self, surface: pygame.Surface) -> None:
        rect = SIDEBAR
        self._panel(surface, rect, SIDEBAR_TITLE)
        box = rect.inflate(-36, 0)
        hint_top = rect.bottom - 62 - 30 * len(SIDEBAR_KEYS)
        # The three points share the space above the hint evenly.
        slot = (hint_top - 24 - (rect.top + 52)) // len(SIDEBAR_POINTS)
        label_font = plain_font(14)
        for index, (label, text) in enumerate(SIDEBAR_POINTS):
            y = rect.top + 52 + index * slot
            if index:
                pygame.draw.line(surface, mix(MATCH_PANEL_EDGE_SOFT, MATCH_PANEL, 0.3),
                                 (box.left, y - 18), (box.right, y - 18))
            pygame.draw.rect(surface, self.accent, (box.left, y + 4, 8, 8), border_radius=2)
            blit_text(surface, label_font, label, MATCH_TEXT, rect, topleft=(box.left + 16, y))
            y += 24
            font, lines = fit_wrapped(text, box.width - 16, (15, 14, 13, 12), 3)
            for line in lines:
                blit_text(surface, font, line, MATCH_MUTED, rect, topleft=(box.left + 16, y))
                y += font.get_height()
        pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (box.left, hint_top - 12), (box.right, hint_top - 12))
        blit_text(surface, plain_font(16), SIDEBAR_HINT, MATCH_TEXT, rect, topleft=(box.left, hint_top))
        key_font = plain_font(11)
        text_font = plain_font(13, False)
        y = hint_top + 32
        for keys, action in SIDEBAR_KEYS:
            cap = pygame.Rect(box.left, y, max(30, key_font.size(keys)[0] + 14), 22)
            pygame.draw.rect(surface, MATCH_PANEL_DEEP, cap, border_radius=5)
            pygame.draw.rect(surface, MATCH_PANEL_EDGE, cap, 1, border_radius=5)
            blit_text(surface, key_font, keys, MATCH_TEXT, cap, center=cap.center)
            blit_text(surface, text_font, action, MATCH_MUTED, rect, midleft=(box.left + 66, cap.centery))
            y += 30

    def _draw_card(self, surface: pygame.Surface, rect: pygame.Rect, index: int, pair,
                   active: bool) -> None:
        self._panel(surface, rect, f"PAIR 0{index + 1}", active=active)
        perk_rows = _perk_rects(rect)
        for column, coach in zip(_column_rects(rect), (pair.offense, pair.defense)):
            self._draw_coach_column(surface, column, coach,
                                    self._highlighted(("coach", index, coach.side.value)))
        pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (rect.left + 12, rect.top + _DIVIDER),
                         (rect.right - 12, rect.top + _DIVIDER))
        blit_text(surface, plain_font(11), "COACH PERKS", MATCH_MUTED, rect,
                  topleft=(rect.left + 14, rect.top + _PERKS_HEAD))
        for perk_row, coach in zip(perk_rows, (pair.offense, pair.defense)):
            self._draw_perk_row(surface, perk_row, coach,
                                self._highlighted(("coach", index, coach.side.value)))

    def _draw_coach_column(self, surface: pygame.Surface, column: pygame.Rect,
                           coach: FootballCoachProfile, hovered: bool) -> None:
        portrait = pygame.Rect(column.left, column.top, column.width, _PORTRAIT_HEIGHT)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, portrait, border_radius=8)
        if hovered:
            pygame.draw.rect(surface, MATCH_PANEL_EDGE, portrait, 1, border_radius=8)
        draw_coach_portrait(surface, portrait.inflate(-12, -10), coach.coach_id, self.theme.primary)
        top = column.top - _PORTRAIT_TOP
        name_font, lines = fit_wrapped(coach.name, column.width, (16, 15, 14, 13), 1)
        blit_text(surface, name_font, lines[0], MATCH_TEXT, column, topleft=(column.left, top + _NAME_TOP))
        blit_text(surface, plain_font(11), coach.side.value.upper(), MATCH_MUTED, column,
                  topleft=(column.left, top + _SIDE_TOP))
        label_font = plain_font(13, False)
        value_font = plain_font(15)
        for row, (position, value) in enumerate(coach.position_modifiers.items()):
            y = top + _MODS_TOP + row * _MOD_ROW
            if row:
                pygame.draw.line(surface, mix(MATCH_PANEL_EDGE_SOFT, MATCH_PANEL, 0.4),
                                 (column.left, y - 3), (column.right, y - 3))
            label = fit_text(_POSITION_LABELS[position], label_font, column.width - 50)
            blit_text(surface, label_font, label, MATCH_MUTED, column, topleft=(column.left, y + 3))
            blit_text(surface, value_font, modifier_text(value), modifier_color(value), column,
                      topright=(column.right, y + 1))

    def _draw_perk_row(self, surface: pygame.Surface, row: pygame.Rect, coach: FootballCoachProfile,
                       hovered: bool) -> None:
        pygame.draw.rect(surface, MATCH_PANEL_HIGH if hovered else MATCH_PANEL_DEEP, row, border_radius=7)
        tag_font = plain_font(11)
        tag = pygame.Rect(row.left + 8, 0, 38, 20)
        tag.centery = row.centery
        pygame.draw.rect(surface, MATCH_PANEL_HIGH if not hovered else MATCH_PANEL, tag, border_radius=5)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE, tag, 1, border_radius=5)
        blit_text(surface, tag_font, _SIDE_TAGS[coach.side.value], MATCH_MUTED, tag, center=tag.center)
        text_box = pygame.Rect(tag.right + 10, row.top, row.right - tag.right - 18, row.height)
        font, lines = fit_wrapped(coach_perk_short(coach), text_box.width, (14, 13, 12, 11), 1)
        blit_text(surface, font, lines[0], MATCH_TEXT, text_box, midleft=(text_box.left, text_box.centery))

    # -- buttons -----------------------------------------------------------------

    def draw_button(self, surface: pygame.Surface, button: Button, index: int, *,
                    pressed: bool) -> None:
        active = self.inspection.active_index(self.focus_index) == index
        rect = button.rect.move(0, 2) if pressed and button.enabled else button.rect
        if self.inspection.keyboard and button.focused:
            pygame.draw.rect(surface, MATCH_TEXT, rect.inflate(6, 6), 2, border_radius=10)
        if active:
            fill = self.accent
            edge = mix(self.accent, MATCH_TEXT, 0.35)
        else:
            fill = MATCH_PANEL_HIGH
            edge = MATCH_PANEL_EDGE
        pygame.draw.rect(surface, fill, rect, border_radius=8)
        pygame.draw.rect(surface, edge, rect, 2, border_radius=8)
        font = plain_font(16)
        blit_text(surface, font, SELECT_LABEL, readable_ink(fill) if active else MATCH_TEXT, rect,
                  center=rect.center)
