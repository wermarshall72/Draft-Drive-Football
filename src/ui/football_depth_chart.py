"""Compact, read-only view of the current run's staff and roster."""

import math
from collections.abc import Callable
from functools import lru_cache

import pygame

from src.engine.football import FootballPlayer, FootballPosition, FootballTeamSide
from src.engine.football_coaches import coaches_for_assignment
from src.engine.football_controller import FootballGameControllerState
from src.engine.football_player_catalog import player_type_for_id
from src.engine.football_shop import (
    FootballUpgradeDuration, FootballUpgradeStat, player_upgrade_stat_value,
)
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.ui.coach_art import draw_coach_portrait
from src.ui.football_coach_upgrade_details import (
    coach_upgrade_area, coach_upgrade_detail_sections, coach_upgrade_short_line,
)
from src.ui.football_coach_perks import coach_perk_short, modifier_text
from src.ui.football_display import _POSITION_LABELS, player_partnership_text, player_perk_text
from src.ui.football_player_draft_view import _draft_percentage, draw_perk_heading, perk_heading_extra
from src.ui.football_player_perks import limit_label, partner_tag, perk_card_line, perk_rules
from src.ui.football_match_perks import perk_status_for
from src.ui.football_player_upgrade_details import stat_value
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.player_art import draw_draft_player
from src.ui.text import wrap_text_lines
from src.ui.theme import Theme
from src.ui.widgets import Button
from src.ui.football_ui_kit import (
    MATCH_DANGER, MATCH_DIM, MATCH_FOCUS, MATCH_GOLD, MATCH_INK, MATCH_MUTED, MATCH_PANEL, MATCH_PANEL_DEEP,
    MATCH_PANEL_EDGE, MATCH_PANEL_EDGE_SOFT, MATCH_PANEL_HIGH, MATCH_TEXT, PaintedButton,
    asset_icon, blit_text, draw_popup_button, draw_popup_panel, draw_stat_value, draw_veil, fit_wrapped,
    match_font, mix, plain_font, rarity_color, rarity_label, smooth_icon, team_accent,
    MODIFIER_NEGATIVE as _NEGATIVE, MODIFIER_NEUTRAL as _NEUTRAL, MODIFIER_POSITIVE as _POSITIVE,
)
from src.ui.stat_icons import stat_icon
from src.ui.text import fit_text



def modified_player_stats(state: FootballGameControllerState, position: FootballPosition) -> tuple[float, float, float]:
    """Return no-fatigue contribution power and effective volatility/stamina."""
    shop = state.shop
    if shop is None:
        raise RuntimeError("The controller did not provide the active shop state.")
    return shop.coached_player_stats(shop.roster, position)


def _player_details(player: FootballPlayer) -> tuple[str, str | None, str]:
    player_type = player_type_for_id(player.player_type_id) if player.player_type_id else None
    partner, explanation = player_partnership_text(player_type)
    return partner, explanation, player_perk_text(player_type)


class DepthChartButton(PaintedButton):
    """Depth Chart controls use the shared match-strip button style."""


def _comparison(value: float, base: float, *, lower_is_better: bool, percentage: bool) -> tuple[str, pygame.Color]:
    delta = round(value - base, 8)
    beneficial = -delta if lower_is_better else delta
    color = _POSITIVE if beneficial > 0 else _NEGATIVE if beneficial < 0 else _NEUTRAL
    displayed = _draft_percentage(round(value, 8)) if percentage else f"{round(value, 8):g}"
    return displayed, color


def _kit_panel(surface: pygame.Surface, rect: pygame.Rect, title: str, accent: pygame.Color,
               note: str | None = None) -> None:
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=12)
    pygame.draw.rect(surface, MATCH_PANEL, rect, border_radius=12)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, rect, 2, border_radius=12)
    pygame.draw.rect(surface, accent, (rect.left + 12, rect.top + 11, 4, 16), border_radius=2)
    title_rect = blit_text(surface, plain_font(17), title, MATCH_TEXT, rect, topleft=(rect.left + 22, rect.top + 8))
    if note:
        font = plain_font(12)
        box = pygame.Rect(title_rect.right + 12, rect.top + 6, rect.right - title_rect.right - 26, 24)
        blit_text(surface, font, fit_text(note, font, box.width), MATCH_GOLD, box,
                  midright=(box.right, box.centery))


def _staff_card(surface: pygame.Surface, rect: pygame.Rect, side: str, coach, theme: Theme) -> None:
    pygame.draw.rect(surface, MATCH_PANEL_HIGH, rect, border_radius=9)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=9)
    inner = rect.inflate(-20, -16)
    blit_text(surface, plain_font(11), side, MATCH_MUTED,
              inner, topleft=inner.topleft)
    name = coach.name.upper() if coach is not None else "NO COACH"
    blit_text(surface, plain_font(17), fit_text(name, plain_font(17), inner.width - FLIP_SIZE - 6), MATCH_TEXT,
              inner, topleft=(inner.left, inner.top + 14))
    # The short perk line needs one compact strip; the portrait and modifiers get the rest.
    perk = pygame.Rect(inner.left, inner.bottom - 46, inner.width, 46)
    portrait_height = max(64, min(132, perk.top - 10 - (inner.top + 40)))
    portrait = pygame.Rect(inner.left, inner.top + 40, 96, portrait_height)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, portrait, border_radius=8)
    if coach is not None:
        draw_coach_portrait(surface, portrait.inflate(-6, -4), coach.coach_id, theme.primary)
    items = tuple(coach.position_modifiers.items()) if coach is not None else ()
    row_step = min(28, portrait.height // 4)
    mods = pygame.Rect(portrait.right + 12, 0, inner.right - portrait.right - 12, row_step * 4)
    mods.centery = portrait.centery
    row_font = plain_font(15)
    for row, (position, value) in enumerate(items[:4]):
        y = mods.top + row * row_step + (row_step - 23) // 2
        color = _POSITIVE if value > 0 else _NEGATIVE if value < 0 else _NEUTRAL
        blit_text(surface, plain_font(13, False), fit_text(_POSITION_LABELS[position], plain_font(13, False), mods.width - 52),
                  MATCH_MUTED, mods, topleft=(mods.left, y + 2))
        blit_text(surface, row_font, modifier_text(value), color, mods, topright=(mods.right, y))
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, perk, border_radius=6)
    blit_text(surface, plain_font(10), "COACH PERK", MATCH_MUTED, perk, topleft=(perk.left + 8, perk.top + 5))
    box = pygame.Rect(perk.left + 8, perk.top + 20, perk.width - 16, perk.height - 24)
    font, lines = fit_wrapped(coach_perk_short(coach), box.width, (13, 12, 11), 1)
    blit_text(surface, font, lines[0], MATCH_TEXT, perk, topleft=(box.left, box.top))


def _draw_staff(surface: pygame.Surface, rect: pygame.Rect, state: FootballGameControllerState,
                theme: Theme, interaction: ShopReviewInteraction | None = None,
                flips: list[Button] | None = None) -> int:
    shop = state.shop
    if shop is None:
        raise RuntimeError("The controller did not provide the active shop state.")
    coaches = coaches_for_assignment(shop.roster.coach_assignment)
    _kit_panel(surface, rect, "COACHING STAFF", team_accent(theme.primary))
    top = rect.top + 36
    height = (rect.bottom - 10 - top - 10) // 2
    for index, (side, coach) in enumerate(zip(("OFFENSE", "DEFENSE"), coaches)):
        card = pygame.Rect(rect.left + 10, top + index * (height + 10), rect.width - 20, height)
        key = ("coach", side)
        _flippable(
            surface, card, key, interaction,
            lambda target, r, side=side, coach=coach: _staff_card(target, r, side, coach, theme),
            lambda target, r, live=True, side=side, coach=coach: _staff_back(
                target, r, side, coach, shop, interaction if live else None),
            id(shop),
        )
        if flips is not None and interaction is not None:
            flips.append(_flip_button(f"FLIP {side} COACH", key, card, interaction))
    return rect.height


def _match_wording(text: str, in_match: bool) -> str:
    """During a match the pending temporary upgrades are the ones in effect."""
    if not in_match:
        return text
    return (text.replace("PENDING NEXT MATCH", "ACTIVE THIS MATCH").replace("next match", "this match")
            .replace("NEXT MATCH", "THIS MATCH"))


def _pending_badges(shop, position: FootballPosition) -> list[tuple[str, str]]:
    totals: dict[FootballUpgradeStat, float] = {}
    for upgrade in shop.pending_player_upgrades:
        if upgrade.position is position:
            totals[upgrade.stat] = totals.get(upgrade.stat, 0) + upgrade.amount
    badges = []
    for stat, amount in totals.items():
        if stat is FootballUpgradeStat.POWER:
            badges.append(("power", f"+{amount:g}"))
        elif stat is FootballUpgradeStat.STAMINA:
            badges.append(("stamina", f"+{round(amount * 100, 4):g}%"))
        else:
            badges.append(("volatility", f"-{round(amount * 100, 4):g}%"))
    return badges


def _fit_card_line(text: str, width: int, height: int) -> tuple[pygame.font.Font, tuple[str, ...]]:
    """The largest size whose wrapped card line (at most two lines) fits ``height``."""
    for size in (11, 10, 9):
        max_lines = min(2, height // plain_font(size).get_height())
        if max_lines >= 1:
            font, lines = fit_wrapped(text, width, (size,), max_lines)
            if len(wrap_text_lines(text, font, width)) <= max_lines:
                return font, lines
    return fit_wrapped(text, width, (9,), max(1, min(2, height // plain_font(9).get_height())))


def _perk_status(state: FootballGameControllerState, perk, in_match: bool) -> str | None:
    if perk is None or not in_match or state.match is None:
        return None
    return perk_status_for(state.match, FootballTeamSide.TEAM_A, perk.kind)


def _heading_extra(state: FootballGameControllerState, position: FootballPosition, in_match: bool,
                   width: int) -> int:
    """Extra height the position's perk heading needs when its tags stack."""
    player = state.shop.roster.players[position]
    perk = player_type_for_id(player.player_type_id).perk if player.player_type_id else None
    if perk is None:
        return 0
    return perk_heading_extra(perk, _perk_status(state, perk, in_match), width)


def _roster_card(surface: pygame.Surface, card: pygame.Rect, position: FootballPosition,
                 state: FootballGameControllerState, interaction: ShopReviewInteraction,
                 theme: Theme | None, in_match: bool = False, heading_extra: int | None = None) -> None:
    shop = state.shop
    player = shop.roster.players[position]
    pygame.draw.rect(surface, MATCH_INK, card.move(0, 3), border_radius=9)
    pygame.draw.rect(surface, MATCH_PANEL_HIGH, card, border_radius=9)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, card, 2, border_radius=9)
    inner = card.inflate(-16, -16)
    player_type = player_type_for_id(player.player_type_id) if player.player_type_id else None
    perk = player_type.perk if player_type is not None else None
    status = _perk_status(state, perk, in_match)
    if heading_extra is None:
        heading_extra = _heading_extra(state, position, in_match, inner.width)
    # A long perk name stacks its tags on a second row; the artwork gives up that room
    # (down to the flip button's height) so the card line keeps its two lines.
    tile_height = max(28 if heading_extra else 40, min(100, card.height - 210) - heading_extra)
    tile = pygame.Rect(inner.left, inner.top, inner.width, tile_height)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, tile, border_radius=7)
    if theme is not None:
        pygame.draw.rect(surface, team_accent(theme.primary), (tile.left + 10, tile.bottom - 5, tile.width - 20, 3),
                         border_radius=2)
    appearance = state.player_appearances.get(position)
    if appearance is not None:
        draw_draft_player(surface, tile.inflate(-8, -8), appearance)
    else:
        blit_text(surface, plain_font(11), "NO ARTWORK", MATCH_DIM, tile, center=tile.center)
    _draw_pending_chips(surface, tile, _pending_badges(shop, position))
    y = tile.bottom + 6
    blit_text(surface, plain_font(11), _POSITION_LABELS[position], MATCH_MUTED, inner, topleft=(inner.left, y))
    name_font = plain_font(16)
    blit_text(surface, name_font, fit_text(player.name.upper(), name_font, inner.width), MATCH_TEXT, inner,
              topleft=(inner.left, y + 14))
    y += 40
    start = state.drafted_players[position]
    values = modified_player_stats(state, position) if interaction.modified_stats else (
        start.power, start.volatility, start.stamina)
    stats = pygame.Rect(inner.left, y, inner.width, 72)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, stats, border_radius=6)
    for index, (stat, base, current, percentage) in enumerate((
        ("power", start.power, values[0], False),
        ("volatility", start.volatility, values[1], True),
        ("stamina", start.stamina, values[2], True),
    )):
        row = pygame.Rect(stats.left + 8, stats.top + 3 + index * 22, stats.width - 16, 22)
        base_text = _draft_percentage(round(base, 8)) if percentage else f"{base:g}"
        draw_stat_value(surface, stat, base_text, row, size=15, midleft=row.midleft)
        if interaction.modified_stats:
            shown, color = _comparison(current, base, lower_is_better=stat == "volatility",
                                       percentage=percentage)
            blit_text(surface, plain_font(15), f"-> {shown}", color, row, midright=row.midright)
    y = stats.bottom + 6
    partner, _explanation = player_partnership_text(player_type)
    partner_label = partner.removeprefix("Partner: ").upper()
    chip_font = plain_font(11)
    chip_text = f"PARTNER  {partner_label}"
    chip = pygame.Rect(inner.left, y, min(inner.width, chip_font.size(chip_text)[0] + 14), 20)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, chip, border_radius=10)
    blit_text(surface, chip_font, fit_text(chip_text, chip_font, chip.width - 10), MATCH_TEXT, chip,
              center=chip.center)
    perk_row = pygame.Rect(inner.left, chip.bottom + 5, inner.width, 16)
    if perk is None:
        blit_text(surface, chip_font, "NO PERK", MATCH_MUTED, perk_row, midleft=(perk_row.left + 2, perk_row.centery))
        return
    heading_bottom = draw_perk_heading(surface, perk_row, perk, status)
    line_box = pygame.Rect(inner.left, heading_bottom + 2, inner.width, max(10, card.bottom - 6 - heading_bottom - 2))
    font, lines = _fit_card_line(perk_card_line(perk), line_box.width - 4, line_box.height)
    for index, line in enumerate(lines):
        blit_text(surface, font, line, MATCH_TEXT, line_box,
                  topleft=(line_box.left + 2, line_box.top + index * font.get_height()))


def pending_chip_layout(widths: list[int], available: int, plus_width: Callable[[int], int],
                        gap: int = 4) -> int:
    """How many chips fit before a "+N" chip; all of them when they fit outright."""
    if sum(widths) + gap * max(0, len(widths) - 1) <= available:
        return len(widths)
    for count in range(len(widths) - 1, -1, -1):
        used = sum(widths[:count]) + gap * count + plus_width(len(widths) - count)
        if used <= available:
            return count
    return 0


def _draw_pending_chips(surface: pygame.Surface, tile: pygame.Rect, badges: list[tuple[str, str]]) -> None:
    """Pending temporary upgrades as chips; a "+N" chip counts any that do not fit."""
    if not badges:
        return
    font = plain_font(13)
    icon = asset_icon("upgrade_temporary.png", 14)
    widths = [icon.get_width() + stat_icon(stat, 14).get_width() + font.size(value)[0] + 16
              for stat, value in badges]
    plus_width = lambda hidden: font.size(f"+{hidden}")[0] + 14  # noqa: E731
    available = tile.width - 8 - FLIP_SIZE - 6
    shown = pending_chip_layout(widths, available, plus_width)
    x = tile.left + 4
    for (stat, value), width in zip(badges[:shown], widths):
        stat_img = stat_icon(stat, 14)
        chip = pygame.Rect(x, tile.top + 4, width, 20)
        pygame.draw.rect(surface, MATCH_INK, chip, border_radius=6)
        pygame.draw.rect(surface, MATCH_GOLD, chip, 1, border_radius=6)
        surface.blit(icon, icon.get_rect(midleft=(chip.left + 4, chip.centery)))
        surface.blit(stat_img, stat_img.get_rect(midleft=(chip.left + 8 + icon.get_width(), chip.centery)))
        blit_text(surface, font, value, MATCH_GOLD, chip,
                  midleft=(chip.left + 12 + icon.get_width() + stat_img.get_width(), chip.centery))
        x = chip.right + 4
    hidden = len(badges) - shown
    if hidden:
        chip = pygame.Rect(x, tile.top + 4, plus_width(hidden), 20)
        pygame.draw.rect(surface, MATCH_GOLD, chip, border_radius=6)
        blit_text(surface, font, f"+{hidden}", MATCH_INK, chip, center=chip.center)


def _draw_roster(surface: pygame.Surface, rect: pygame.Rect, state: FootballGameControllerState,
                 interaction: ShopReviewInteraction, in_match: bool = False,
                 theme: Theme | None = None, flips: list[Button] | None = None) -> int:
    shop = state.shop
    if shop is None:
        raise RuntimeError("The controller did not provide the active shop state.")
    note = None
    if shop.pending_player_upgrades:
        note = _match_wording(f"{len(shop.pending_player_upgrades)} PENDING NEXT MATCH", in_match)
    _kit_panel(surface, rect, "ROSTER", team_accent(theme.primary) if theme else MATCH_FOCUS, note)
    columns = 4 if rect.width >= 760 else 2
    rows = (len(PLAYER_DRAFT_ORDER) + columns - 1) // columns
    gap = 10
    grid = pygame.Rect(rect.left + 10, rect.top + 36, rect.width - 20, rect.height - 46)
    width = (grid.width - gap * (columns - 1)) // columns
    height = max(250, (grid.height - gap * (rows - 1)) // rows)
    # Every card trims its artwork by the same amount, so the rows stay aligned.
    heading_extra = max(_heading_extra(state, position, in_match, width - 16) for position in PLAYER_DRAFT_ORDER)
    for index, position in enumerate(PLAYER_DRAFT_ORDER):
        card = pygame.Rect(grid.left + (index % columns) * (width + gap),
                           grid.top + (index // columns) * (height + gap), width, height)
        key = ("player", position.value)
        _flippable(
            surface, card, key, interaction,
            lambda target, r, position=position: _roster_card(
                target, r, position, state, interaction, theme, in_match, heading_extra),
            lambda target, r, live=True, position=position: _roster_back(
                target, r, position, state, in_match, interaction if live else None),
            (id(state), in_match, len(state.match.match_events) if state.match is not None else 0),
        )
        if flips is not None:
            flips.append(_flip_button(f"FLIP {_POSITION_LABELS[position]}", key, card, interaction))
    return max(rect.height, 46 + rows * height + (rows - 1) * gap)




# -- flipping cards ------------------------------------------------------------------

FLIP_SIZE = 26


# Rendered faces reused while a card is turning (the state does not change mid-flip).
_FLIP_FRAMES: dict[tuple, pygame.Surface] = {}


def _flippable(surface: pygame.Surface, rect: pygame.Rect, key, interaction: ShopReviewInteraction | None,
               draw_front: Callable[[pygame.Surface, pygame.Rect], None],
               draw_back: Callable[[pygame.Surface, pygame.Rect], None], frame_token: object = None) -> None:
    """Draw a card face, or a mid-rotation frame squeezed around its vertical axis."""
    if interaction is None:
        draw_front(surface, rect)
        return
    back, progress = interaction.flip_progress(key)
    if progress >= 1:
        (draw_back if back else draw_front)(surface, rect)
        return
    showing_back = back if progress >= 0.5 else not back
    cache_key = (key, showing_back, rect.size, interaction.modified_stats, frame_token)
    frame = _FLIP_FRAMES.get(cache_key)
    if frame is None:
        if len(_FLIP_FRAMES) > 24:
            _FLIP_FRAMES.clear()
        frame = pygame.Surface((rect.width, rect.height + 4), pygame.SRCALPHA)
        local = pygame.Rect(0, 0, rect.width, rect.height)
        if showing_back:
            draw_back(frame, local, live=False)
        else:
            draw_front(frame, local)
        _FLIP_FRAMES[cache_key] = frame
    width = max(2, round(rect.width * abs(math.cos(math.pi * progress))))
    squeezed = pygame.transform.smoothscale(frame, (width, frame.get_height()))
    surface.blit(squeezed, squeezed.get_rect(midtop=(rect.centerx, rect.top)))


def _flip_button(label: str, key, card: pygame.Rect, interaction: ShopReviewInteraction) -> Button:
    rect = pygame.Rect(card.right - FLIP_SIZE - 8, card.top + 8, FLIP_SIZE, FLIP_SIZE)

    def paint(surface: pygame.Surface, button: Button, hovered: bool, pressed: bool) -> None:
        if button.focused:
            interaction.focused_flip = key  # Page Up/Down scroll this card's back
        if interaction.flip_progress(key)[1] < 1:
            return  # the arrow returns once the card has finished turning
        lit = hovered or button.focused
        target = button.rect.move(0, 1) if pressed else button.rect
        if button.focused:
            pygame.draw.circle(surface, MATCH_TEXT, target.center, FLIP_SIZE // 2 + 4, 2)
        pygame.draw.circle(surface, MATCH_INK, target.center, FLIP_SIZE // 2)
        pygame.draw.circle(surface, MATCH_GOLD if lit else MATCH_PANEL_EDGE, target.center, FLIP_SIZE // 2, 2)
        icon = smooth_icon("flip_arrows.png", FLIP_SIZE - 10)
        surface.blit(icon, icon.get_rect(center=target.center))

    return DepthChartButton(label, lambda: interaction.toggle_flip(key), rect, variant="depth-flip", painter=paint)


# -- card backs ----------------------------------------------------------------------

def _back_frame(surface: pygame.Surface, rect: pygame.Rect, eyebrow: str, title: str) -> pygame.Rect:
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 3), border_radius=9)
    pygame.draw.rect(surface, mix(MATCH_PANEL_HIGH, MATCH_PANEL_DEEP, 0.55), rect, border_radius=9)
    pygame.draw.rect(surface, MATCH_GOLD, rect, 2, border_radius=9)
    inner = rect.inflate(-16, -16)
    blit_text(surface, plain_font(10), eyebrow, MATCH_GOLD, inner, topleft=inner.topleft)
    font = plain_font(14)
    blit_text(surface, font, fit_text(title, font, inner.width - FLIP_SIZE - 6), MATCH_TEXT, inner,
              topleft=(inner.left, inner.top + 13))
    pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (inner.left, inner.top + 34), (inner.right, inner.top + 34))
    return pygame.Rect(inner.left, inner.top + 40, inner.width, inner.height - 40)


@lru_cache(maxsize=4096)
def _wrapped(text: str, font: pygame.font.Font, width: int) -> tuple[str, ...]:
    return wrap_text_lines(text, font, width)


BACK_GUTTER = 8
BACK_HINT = 18


def _line_height(line: tuple) -> int:
    return 19 if line[0] == "stat" else line[1].get_height()


def _back_lines(rows: list[tuple], width: int) -> list[tuple]:
    lines: list[tuple] = []
    for row in rows:
        kind = row[0]
        if kind == "head":
            lines.append(("text", plain_font(10), row[1], MATCH_MUTED, 6))
        elif kind == "stat":
            lines.append(row + (2,))
        else:
            font = {"name": plain_font(12), "small": plain_font(10, False),
                    "text": match_font(11, False)}[kind]
            color = row[2] if len(row) > 2 else (MATCH_MUTED if kind == "small" else MATCH_TEXT)
            for index, text in enumerate(_wrapped(row[1], font, width)):
                lines.append(("text", font, text, color, 2 if index == 0 else 0))
    if lines and lines[0][-1]:
        lines[0] = lines[0][:-1] + (0,)
    return lines


def _flow(surface: pygame.Surface, box: pygame.Rect, rows: list[tuple], scroll: int = 0) -> tuple[int, int]:
    """Draw back-of-card rows scrolled by ``scroll``; returns (clamped scroll, max scroll).

    Nothing is dropped: content taller than ``box`` scrolls, with a scroll bar and a
    MORE hint while anything remains below. Only fully visible lines are drawn.
    """
    width = box.width - BACK_GUTTER
    lines = _back_lines(rows, width)
    content = sum(_line_height(line) + line[-1] for line in lines)
    max_scroll = max(0, content - box.height)
    scroll = max(0, min(scroll, max_scroll))
    more_below = scroll < max_scroll
    visible_bottom = box.bottom - (BACK_HINT if more_below else 0)
    y = box.top - scroll
    for line in lines:
        y += line[-1]
        height = _line_height(line)
        if y >= box.top and y + height <= visible_bottom:
            if line[0] == "stat":
                _, stat, value, label, color, _gap = line
                row = pygame.Rect(box.left, y, width, 19)
                draw_stat_value(surface, stat, value, row, size=14, midleft=row.midleft)
                blit_text(surface, plain_font(10), label, color, row, midright=row.midright)
            else:
                _, font, text, color, _gap = line
                blit_text(surface, font, text, color, box, topleft=(box.left, y))
        y += height
    if max_scroll:
        track = pygame.Rect(box.right - 3, box.top, 3, box.height)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, track, border_radius=2)
        thumb_height = max(16, round(track.height * box.height / content))
        thumb_top = track.top + round((track.height - thumb_height) * scroll / max_scroll)
        pygame.draw.rect(surface, MATCH_GOLD, (track.left, thumb_top, 3, thumb_height), border_radius=2)
    if more_below:
        font = plain_font(10)
        pill = pygame.Rect(0, 0, font.size("MORE")[0] + 24, 15)
        pill.midbottom = (box.left + width // 2, box.bottom)
        pygame.draw.rect(surface, MATCH_INK, pill, border_radius=7)
        pygame.draw.rect(surface, MATCH_GOLD, pill, 1, border_radius=7)
        label = blit_text(surface, font, "MORE", MATCH_GOLD, pill.inflate(2, 2),
                          midleft=(pill.left + 6, pill.centery))
        cx, cy = label.right + 6, pill.centery
        pygame.draw.polygon(surface, MATCH_GOLD, ((cx - 4, cy - 2), (cx + 4, cy - 2), (cx, cy + 3)))
    return scroll, max_scroll


def _scrolled_back(surface: pygame.Surface, box: pygame.Rect, rows: list[tuple], card: pygame.Rect,
                   key, interaction: ShopReviewInteraction | None) -> None:
    if interaction is None:  # an off-screen rotation frame: always the top of the list
        _flow(surface, box, rows)
        return
    scroll, max_scroll = _flow(surface, box, rows, interaction.back_scroll.get(key, 0))
    interaction.back_scroll[key] = scroll
    interaction.back_areas[key] = (pygame.Rect(card), max_scroll, box.height)


def _stat_amount(stat: FootballUpgradeStat, amount: float) -> tuple[str, str]:
    if stat is FootballUpgradeStat.POWER:
        return "power", f"+{amount:g}"
    if stat is FootballUpgradeStat.STAMINA:
        return "stamina", f"+{round(amount * 100, 4):g}%"
    return "volatility", f"-{round(amount * 100, 4):g}%"


_CAPS = {FootballUpgradeStat.STAMINA: " · max 100%", FootballUpgradeStat.VOLATILITY: " · min 0%"}


def player_back_rows(state: FootballGameControllerState, position: FootballPosition,
                     in_match: bool) -> list[tuple]:
    """Rows on the back of a roster card: upgrades, partnership, and the perk's full rules."""
    shop = state.shop
    player = shop.roster.players[position]
    rows: list[tuple] = [("head", "UPGRADES")]
    permanent: dict[FootballUpgradeStat, list] = {}
    for upgrade in shop.purchased_upgrades:
        if upgrade.position is position and upgrade.duration is FootballUpgradeDuration.PERMANENT:
            permanent.setdefault(upgrade.stat, []).append(upgrade)
    pending: dict[FootballUpgradeStat, list] = {}
    for upgrade in shop.pending_player_upgrades:
        if upgrade.position is position:
            pending.setdefault(upgrade.stat, []).append(upgrade)
    start = state.drafted_players[position]
    for stat, upgrades in permanent.items():
        key, value = _stat_amount(stat, sum(u.amount for u in upgrades))
        count = f" x{len(upgrades)}" if len(upgrades) > 1 else ""
        rows.append(("stat", key, value, f"REST OF RUN{count}", _POSITIVE))
        now = player_upgrade_stat_value(player, stat)
        coached = shop.coached_player_stat(shop.roster, position, stat)
        rows.append(("small", f"Run {stat_value(stat, player_upgrade_stat_value(start, stat))} -> "
                              f"{stat_value(stat, now)} · coached {stat_value(stat, coached)}{_CAPS.get(stat, '')}"))
    next_roster = shop.next_match_roster
    for stat, upgrades in pending.items():
        key, value = _stat_amount(stat, sum(u.amount for u in upgrades))
        count = f" x{len(upgrades)}" if len(upgrades) > 1 else ""
        rows.append(("stat", key, value, ("THIS MATCH" if in_match else "NEXT MATCH") + count, MATCH_GOLD))
        before = player_upgrade_stat_value(player, stat)
        after = player_upgrade_stat_value(next_roster.players[position], stat)
        coached_before = shop.coached_player_stat(shop.roster, position, stat)
        coached_after = shop.coached_player_stat(next_roster, position, stat)
        rows.append(("small", f"Run {stat_value(stat, before)} -> {stat_value(stat, after)} · coached "
                              f"{stat_value(stat, coached_before)} -> {stat_value(stat, coached_after)}"
                              f"{_CAPS.get(stat, '')}"))
    if not permanent and not pending:
        rows.append(("small", "No upgrades yet."))
    player_type = player_type_for_id(player.player_type_id) if player.player_type_id else None
    partner, explanation = player_partnership_text(player_type)
    rows.append(("head", "PARTNER"))
    label = partner.removeprefix("Partner: ")
    rows.append(("text", f"{label}: {explanation}" if explanation else label))
    perk = player_type.perk if player_type is not None else None
    rows.append(("head", "PERK"))
    if perk is None:
        rows.append(("text", "None"))
    else:
        tags = " · ".join(text for text in (partner_tag(perk), limit_label(perk)) if text)
        rows.append(("name", f"{perk.name} · {tags}" if tags else perk.name))
        rows.append(("text", perk_card_line(perk)))
        rows.append(("small", perk_rules(perk)))
    return rows


def _roster_back(surface: pygame.Surface, card: pygame.Rect, position: FootballPosition,
                 state: FootballGameControllerState, in_match: bool,
                 interaction: ShopReviewInteraction | None = None) -> None:
    player = state.shop.roster.players[position]
    box = _back_frame(surface, card, _POSITION_LABELS[position], player.name.upper())
    _scrolled_back(surface, box, player_back_rows(state, position, in_match), card,
                   ("player", position.value), interaction)


def coach_back_rows(side: str, coach, shop) -> list[tuple]:
    rows: list[tuple] = [("head", "COACH PERK"), ("text", coach_perk_short(coach))]
    rows.append(("head", f"{side} UPGRADES"))
    owned = [card for card in shop.owned_coach_upgrades
             if card.coach_upgrade_effect is not None
             and coach_upgrade_area(card.coach_upgrade_effect.kind) == side]
    for card in owned:
        rows.append(("name", card.name.upper(), rarity_color(card.rarity)))
        rows.append(("small", coach_upgrade_short_line(card), MATCH_TEXT))
    if not owned:
        rows.append(("small", "No coach upgrades yet."))
    return rows


def _staff_back(surface: pygame.Surface, rect: pygame.Rect, side: str, coach, shop,
                interaction: ShopReviewInteraction | None = None) -> None:
    box = _back_frame(surface, rect, f"{side} COACH", coach.name.upper() if coach else "NO COACH")
    _scrolled_back(surface, box, coach_back_rows(side, coach, shop), rect, ("coach", side), interaction)


# -- team upgrades popup --------------------------------------------------------------

TEAM_AREAS = ("SPECIAL TEAMS", "PROGRAM")


def team_upgrades(shop) -> list:
    return [card for card in shop.owned_coach_upgrades
            if card.coach_upgrade_effect is not None
            and coach_upgrade_area(card.coach_upgrade_effect.kind) in TEAM_AREAS]


def _team_button(rect: pygame.Rect, count: int, interaction: ShopReviewInteraction) -> Button:
    def paint(surface: pygame.Surface, button: Button, hovered: bool, pressed: bool) -> None:
        lit = hovered or button.focused
        target = button.rect.move(0, 1) if pressed else button.rect
        if button.focused:
            pygame.draw.rect(surface, MATCH_TEXT, target.inflate(6, 6), 2, border_radius=16)
        pygame.draw.rect(surface, MATCH_PANEL_HIGH if lit else MATCH_PANEL_DEEP, target, border_radius=13)
        pygame.draw.rect(surface, MATCH_GOLD if lit else MATCH_PANEL_EDGE, target, 2, border_radius=13)
        icon = smooth_icon("info_badge.png", target.height - 8)
        surface.blit(icon, icon.get_rect(midleft=(target.left + 5, target.centery)))
        font = plain_font(12)
        label = blit_text(surface, font, "TEAM UPGRADES", MATCH_TEXT, target,
                          midleft=(target.left + 10 + icon.get_width(), target.centery))
        chip_font = plain_font(11)
        chip = pygame.Rect(0, 0, chip_font.size(str(count))[0] + 12, 16)
        chip.midleft = (label.right + 6, target.centery)
        pygame.draw.rect(surface, MATCH_GOLD if count else MATCH_DIM, chip, border_radius=8)
        blit_text(surface, chip_font, str(count), MATCH_INK, chip.inflate(2, 2), center=chip.center)

    return DepthChartButton("TEAM UPGRADES", interaction.open_team_upgrades, rect, variant="depth-info",
                            painter=paint)


def _team_rows(cards: list, width: int, size: int) -> list[tuple[pygame.font.Font, str, pygame.Color, int]]:
    rows = []
    body = match_font(size, False)
    for index, card in enumerate(cards):
        gap = 0 if index == 0 else 14
        area = coach_upgrade_area(card.coach_upgrade_effect.kind)
        rows.append((plain_font(16), card.name.upper(), MATCH_TEXT, gap))
        rows.append((plain_font(11), f"{area}  ·  {rarity_label(card.rarity)}", rarity_color(card.rarity), 1))
        rows.append((plain_font(14), coach_upgrade_short_line(card), MATCH_GOLD, 3))
        sections = coach_upgrade_detail_sections(card)
        for text in sections[1:3]:
            for line_index, line in enumerate(wrap_text_lines(text, body, width)):
                rows.append((body, line, MATCH_MUTED, 3 if line_index == 0 else 0))
    if not cards:
        rows.append((plain_font(16), "NO TEAM UPGRADES YET", MATCH_TEXT, 0))
        for line in wrap_text_lines("Special-teams, future-shop AP, and Bye Week coach upgrades appear here.",
                                    body, width):
            rows.append((body, line, MATCH_MUTED, 4))
    return rows


def _draw_team_popup(surface: pygame.Surface, content: pygame.Rect, shop,
                     interaction: ShopReviewInteraction) -> list[Button]:
    draw_veil(surface)
    cards = team_upgrades(shop)
    width = min(760, content.width - 40)
    max_height = content.height - 20
    for size in (13, 12, 11):
        rows = _team_rows(cards, width - 40, size)
        body = sum(font.get_height() + gap for font, _t, _c, gap in rows)
        height = 86 + body + 72
        if height <= max_height:
            break
    rect = pygame.Rect(0, 0, width, min(height, max_height))
    rect.center = content.center
    draw_popup_panel(surface, rect, "TEAM UPGRADES", "Special teams and program upgrades for this run")
    viewport = pygame.Rect(rect.left + 20, rect.top + 86, rect.width - 40, rect.height - 86 - 64)
    y = viewport.top
    for font, text, color, gap in rows:
        y += gap
        if y + font.get_height() > viewport.bottom:
            break
        blit_text(surface, font, text, color, viewport, topleft=(viewport.left, y))
        y += font.get_height()
    close_rect = pygame.Rect(rect.right - 20 - 170, rect.bottom - 16 - 40, 170, 40)
    close = DepthChartButton(
        "CLOSE [ESC]", interaction.close_team_upgrades, close_rect, variant="popup-primary",
        painter=lambda target, button, hovered, pressed: draw_popup_button(
            target, button, focused=button.focused, hovered=hovered, pressed=pressed),
    )
    return [close]


def draw_depth_chart(
    surface: pygame.Surface, content: pygame.Rect, state: FootballGameControllerState,
    theme: Theme, font: pygame.font.Font, heading_font: pygame.font.Font,
    interaction: ShopReviewInteraction, leave: Callable[[], None],
    *, back_label: str = "BACK TO SHOP", subtitle: str = "CURRENT RUN",
    in_match: bool = False, error: str | None = None,
) -> list[Button]:
    shop = state.shop
    if shop is None:
        raise RuntimeError("The controller did not provide the active shop state.")
    title = blit_text(surface, plain_font(30), "DEPTH CHART", MATCH_TEXT, content,
                      topleft=(content.left, content.top))
    accent = team_accent(theme.primary)
    pygame.draw.rect(surface, accent, (title.right + 10, title.centery - 2, 34, 4), border_radius=2)
    sub_font = plain_font(13)
    team = fit_text(shop.roster.team_name.upper(), sub_font, 360)
    team_rect = blit_text(surface, sub_font, team, MATCH_TEXT, content, topleft=(content.left + 18, content.top + 38))
    swatch = pygame.Rect(content.left, content.top + 40, 12, 12)
    pygame.draw.rect(surface, theme.primary, swatch, border_radius=3)
    pygame.draw.rect(surface, mix(accent, MATCH_TEXT, 0.4), swatch, 1, border_radius=3)
    chip_font = plain_font(11)
    chip = pygame.Rect(0, 0, chip_font.size(subtitle)[0] + 16, 20)
    chip.midleft = (team_rect.right + 10, team_rect.centery)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, chip, border_radius=10)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, chip, 1, border_radius=10)
    blit_text(surface, chip_font, subtitle, MATCH_MUTED, chip.inflate(2, 2), center=chip.center)
    team_rect_button = pygame.Rect(chip.right + 12, team_rect.centery - 13, 186, 26)

    footer_y = content.bottom - 42
    body = pygame.Rect(content.left, content.top + 62, content.width, max(1, footer_y - 10 - content.top - 62))
    if interaction.depth_viewport_size != body.size:
        interaction.depth_scroll = 0
        interaction.depth_viewport_size = body.size
    clip = surface.get_clip()
    surface.set_clip(body.clip(clip))
    y = body.top - interaction.depth_scroll
    flips: list[Button] = []
    interaction.back_areas.clear()
    interaction.focused_flip = None
    if body.width < 720:
        staff_height = _draw_staff(surface, pygame.Rect(body.left, y, body.width, 600), state, theme,
                                   interaction, flips)
        roster_rect = pygame.Rect(body.left, y + staff_height + 10, body.width, body.height)
        total_height = staff_height + 10 + _draw_roster(surface, roster_rect, state, interaction, in_match,
                                                       theme, flips)
    else:
        staff_width = 300
        staff_rect = pygame.Rect(body.left, y, staff_width, body.height)
        roster_rect = pygame.Rect(staff_rect.right + 10, y, body.width - staff_width - 10, body.height)
        total_height = max(_draw_staff(surface, staff_rect, state, theme, interaction, flips),
                           _draw_roster(surface, roster_rect, state, interaction, in_match, theme, flips))
    interaction.depth_max_scroll = max(0, total_height - body.height)
    interaction.depth_scroll = min(interaction.depth_scroll, interaction.depth_max_scroll)
    surface.set_clip(clip)

    def show(modified: bool) -> Callable[[], None]:
        def action() -> None:
            if interaction.modified_stats != modified:
                interaction.toggle_stats()
        return action

    back_width = 170
    buttons: list[Button] = [
        DepthChartButton("STARTING STATS", show(False), pygame.Rect(content.left, footer_y, 160, 42),
                         variant="kit" if interaction.modified_stats else "kit-toggle-on"),
        DepthChartButton("MODIFIED STATS", show(True), pygame.Rect(content.left + 166, footer_y, 160, 42),
                         variant="kit-toggle-on" if interaction.modified_stats else "kit"),
        DepthChartButton(back_label, leave, pygame.Rect(content.right - back_width, footer_y, back_width, 42),
                         variant="kit-primary" if in_match else "kit"),
        _team_button(team_rect_button, len(team_upgrades(shop)), interaction),
        *(button for button in flips if body.contains(button.rect)),
    ]
    hint = ("WHEEL / PAGE UP / PAGE DOWN TO SCROLL" if interaction.depth_max_scroll else
            "FLIP A CARD FOR ITS UPGRADES AND PERKS  ·  MODIFIED POWER EXCLUDES PARTNERSHIP, FATIGUE, AND SCHEME")
    hint_font = plain_font(11)
    hint_box = pygame.Rect(content.left + 340, footer_y, content.right - back_width - 10 - content.left - 340, 42)
    if error:
        hint = f"CHECK: {error}"
    blit_text(surface, hint_font, fit_text(hint, hint_font, hint_box.width),
              MATCH_DANGER if error else MATCH_MUTED, hint_box, center=hint_box.center)
    if interaction.team_popup:
        return _draw_team_popup(surface, content, shop, interaction)
    return buttons
