"""Compact, read-only view of the current run's staff and roster."""

from collections.abc import Callable
from functools import lru_cache

import pygame

from src.engine.football import FootballPlayer, FootballPosition
from src.engine.football_coaches import coaches_for_assignment
from src.engine.football_controller import FootballGameControllerState
from src.engine.football_player_catalog import player_type_for_id
from src.engine.football_shop import (
    FootballUpgradeDuration, FootballUpgradeStat, player_upgrade_effect_text,
    player_upgrade_stat_value,
)
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.ui.coach_art import draw_coach_portrait
from src.ui.coach_fonts import staff_font
from src.ui.football_coach_upgrade_details import coach_upgrade_detail_sections
from src.ui.football_coach_view import coach_perk_text
from src.ui.football_display import _POSITION_LABELS, player_partnership_text, player_perk_text
from src.ui.football_player_draft_view import _draft_percentage
from src.ui.football_player_upgrade_details import VOLATILITY_SPREAD_EXPLANATION, stat_change, stat_value
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.player_art import draw_draft_player
from src.ui.text import draw_complete_wrapped_text, wrap_text_lines
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_text

_PANEL = pygame.Color("#0e2b47")
_CARD = pygame.Color("#10263d")
_EDGE = pygame.Color("#507397")
_TEXT = pygame.Color("#eef5ff")
_MUTED = pygame.Color("#c1d0df")
_POSITIVE = pygame.Color("#9fe4ad")
_NEGATIVE = pygame.Color("#ff9d98")
_NEUTRAL = pygame.Color("#c1cbd5")
_PERK_BOX = pygame.Color("#34485b")
_PERK_EDGE = pygame.Color("#62798c")
_PERK_TEXT = pygame.Color("#f1f5f9")


@lru_cache(maxsize=8)
def _font(size: int, bold: bool = False) -> pygame.font.Font:
    return staff_font(size, semibold=bold)


@lru_cache(maxsize=32)
def _rounded_surface(size: tuple[int, int], fill: tuple[int, int, int],
                     edge: tuple[int, int, int], radius: int) -> pygame.Surface:
    scale = 2
    bounds = pygame.Rect(0, 0, size[0] * scale, size[1] * scale)
    image = pygame.Surface(bounds.size, pygame.SRCALPHA)
    pygame.draw.rect(image, fill, bounds, border_radius=radius * scale)
    pygame.draw.rect(image, edge, bounds, width=scale, border_radius=radius * scale)
    return pygame.transform.smoothscale(image, size)


def _rounded_box(surface: pygame.Surface, rect: pygame.Rect, fill: pygame.Color,
                 edge: pygame.Color, radius: int = 6) -> None:
    surface.blit(_rounded_surface(rect.size, tuple(fill[:3]), tuple(edge[:3]), radius),
                 rect.topleft)


def modified_player_stats(state: FootballGameControllerState, position: FootballPosition) -> tuple[float, float, float]:
    """Return no-fatigue contribution power and effective volatility/stamina."""
    shop = state.shop
    if shop is None:
        raise RuntimeError("The controller did not provide the active shop state.")
    return shop.coached_player_stats(shop.roster, position)


def _text_height(text: str, font: pygame.font.Font, width: int, gap: int = 0) -> int:
    return len(wrap_text_lines(text, font, width)) * (font.get_height() + gap) - gap


def _player_details(player: FootballPlayer) -> tuple[str, str | None, str]:
    player_type = player_type_for_id(player.player_type_id) if player.player_type_id else None
    partner, explanation = player_partnership_text(player_type)
    return partner, explanation, player_perk_text(player_type)


def _compact_player_details(player: FootballPlayer) -> str:
    player_type = player_type_for_id(player.player_type_id) if player.player_type_id else None
    partner, explanation = player_partnership_text(player_type)
    perk = player_type.perk if player_type is not None else None
    summary = (
        f"PLANNED / INACTIVE\nPerk: {perk.name}\nTrigger: {perk.trigger}\nEffect: {perk.effect}"
        if perk is not None else "Perk: None"
    )
    return "\n".join(filter(None, (partner, explanation, summary)))


def _detail_sections(player: FootballPlayer) -> tuple[tuple[str, ...], tuple[str, ...]]:
    player_type = player_type_for_id(player.player_type_id) if player.player_type_id else None
    partner, explanation = player_partnership_text(player_type)
    perk = player_type.perk if player_type is not None else None
    partnership = tuple(filter(None, (partner, explanation)))
    if perk is None:
        return partnership, ("Perk: None",)
    return partnership, (
        "PLANNED / INACTIVE", f"Perk: {perk.name}",
        f"Trigger: {perk.trigger}", f"Effect: {perk.effect}",
    )


def _section_height(lines: tuple[str, ...], width: int, bold_lines: int) -> int:
    return sum(_text_height(line, _font(11, index < bold_lines), width)
               for index, line in enumerate(lines))


def _draw_section(surface: pygame.Surface, lines: tuple[str, ...], rect: pygame.Rect,
                  bold_lines: int, bold_color: pygame.Color, color: pygame.Color) -> None:
    if _section_height(lines, rect.width, bold_lines) > rect.height:
        raise ValueError("Depth chart section does not fit in its rectangle.")
    y = rect.top
    for index, line in enumerate(lines):
        font = _font(11, index < bold_lines)
        height = _text_height(line, font, rect.width)
        draw_complete_wrapped_text(surface, line, pygame.Rect(rect.left, y, rect.width, height),
                                   font, bold_color if index < bold_lines else color, line_gap=0)
        y += height


class DepthChartButton(Button):
    """Depth Chart controls share a navy finish and a high-contrast focus ring."""

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, theme: Theme, *,
             hovered: bool = False, pressed: bool = False) -> None:
        rect = self.rect.move(0, 1) if pressed and self.enabled else self.rect
        fill = pygame.Color("#234b70" if self.focused or hovered else "#173652")
        edge = pygame.Color("#9cc2df" if self.focused or hovered else "#507397")
        if self.focused and self.enabled:
            pygame.draw.rect(surface, "#e6f4ff", rect.inflate(6, 6), 2, border_radius=8)
        _rounded_box(surface, rect, fill, edge, 6)
        pygame.draw.line(surface, theme.primary_accent,
                         (rect.left + 8, rect.bottom - 3), (rect.right - 8, rect.bottom - 3))
        label_font = _font(14, True)
        label = label_font.render(self.label, True, _TEXT if self.enabled else _MUTED)
        max_width = max(1, rect.width - 18)
        if label.get_width() > max_width:
            height = max(1, round(label.get_height() * max_width / label.get_width()))
            label = pygame.transform.smoothscale(label, (max_width, height))
        surface.blit(label, label.get_rect(center=rect.center))


def _comparison(value: float, base: float, *, lower_is_better: bool, percentage: bool) -> tuple[str, pygame.Color]:
    delta = round(value - base, 8)
    beneficial = -delta if lower_is_better else delta
    color = _POSITIVE if beneficial > 0 else _NEGATIVE if beneficial < 0 else _NEUTRAL
    displayed = _draft_percentage(round(value, 8)) if percentage else f"{round(value, 8):g}"
    return f"({displayed})", color


def _draw_stat(surface: pygame.Surface, x: int, y: int, label: str, base: float,
               current: float, modified: bool, percentage: bool) -> None:
    font = _font(12)
    bold = _font(12, True)
    value = _draft_percentage(round(base, 8)) if percentage else f"{base:g}"
    text = f"{label} {value}"
    draw_text(surface, text, (x, y), font, _TEXT)
    if modified:
        change, color = _comparison(current, base, lower_is_better=label == "VOLATILITY",
                                    percentage=percentage)
        draw_text(surface, change, (x + font.size(text)[0] + 3, y), bold, color)


def _panel(surface: pygame.Surface, rect: pygame.Rect) -> None:
    _rounded_box(surface, rect, _PANEL, _EDGE, 8)
    pygame.draw.line(surface, "#355d7d",
                     (rect.left + 10, rect.top + 2), (rect.right - 10, rect.top + 2))
    pygame.draw.line(surface, "#081a2e",
                     (rect.left + 10, rect.bottom - 3), (rect.right - 10, rect.bottom - 3))


def _draw_staff(surface: pygame.Surface, rect: pygame.Rect,
                state: FootballGameControllerState, theme: Theme) -> int:
    shop = state.shop
    if shop is None:
        raise RuntimeError("The controller did not provide the active shop state.")
    coaches = coaches_for_assignment(shop.roster.coach_assignment)
    font = _font(14)
    title_font = _font(16, True)
    inner = rect.width - 24
    names = [f"{side} / {coach.name}" if coach else f"{side} / No coach"
             for side, coach in zip(("OFFENSE", "DEFENSE"), coaches)]
    name_height = max(_text_height(name, title_font, inner) for name in names)
    modifiers = [
        tuple(coach.position_modifiers.items()) if coach else ()
        for coach in coaches
    ]
    modifier_width = inner - 100
    modifier_height = max(
        (_text_height(f"{_POSITION_LABELS[pos]} {value:+.0%}", font, modifier_width)
         for items in modifiers for pos, value in items), default=font.get_height()
    )
    perks = [f"PERK / {coach_perk_text(coach)}" if coach else "PERK / No perk."
             for coach in coaches]
    perk_height = max(_text_height(perk, font, inner - 12) for perk in perks)
    section_height = name_height + max(96, 4 * (modifier_height + 2)) + perk_height + 34
    needed = 36 + 2 * section_height + 8
    actual = rect.copy()
    actual.height = max(rect.height, needed)
    _panel(surface, actual)
    pygame.draw.rect(surface, theme.primary, (rect.left + 2, rect.top + 6, 3, 21), border_radius=1)
    draw_text(surface, "COACHING STAFF", (rect.left + 12, rect.top + 8), title_font, _TEXT)
    section_height = max(section_height, (actual.height - 44) // 2)
    for index, coach in enumerate(coaches):
        x = rect.left + 12
        name_y = rect.top + 34 + index * section_height
        portrait_y = name_y + name_height + 4
        mods_y = portrait_y + 3
        perk_y = portrait_y + max(96, 4 * (modifier_height + 2)) + 6
        if index:
            pygame.draw.line(surface, _EDGE, (x, name_y - 6), (rect.right - 12, name_y - 6))
        draw_complete_wrapped_text(surface, names[index],
            pygame.Rect(x, name_y, inner, name_height), title_font, _TEXT, line_gap=0)
        if coach is not None:
            draw_coach_portrait(surface, pygame.Rect(x + 4, portrait_y, 88, 88),
                                coach.coach_id, theme.primary)
        for row, (position, value) in enumerate(modifiers[index]):
            color = _POSITIVE if value > 0 else _NEGATIVE if value < 0 else _NEUTRAL
            draw_complete_wrapped_text(surface, f"{_POSITION_LABELS[position]} {value:+.0%}",
                pygame.Rect(x + 100, mods_y + row * (modifier_height + 2), modifier_width, modifier_height),
                font, color, line_gap=0)
        perk_box = pygame.Rect(x, perk_y, inner, perk_height + 8)
        _rounded_box(surface, perk_box, _PERK_BOX, _PERK_EDGE, 5)
        draw_complete_wrapped_text(surface, perks[index],
            pygame.Rect(x + 6, perk_y + 4, inner - 12, perk_height), font, _PERK_TEXT, line_gap=0)
    return actual.height


def _draw_roster(surface: pygame.Surface, rect: pygame.Rect, state: FootballGameControllerState,
                 interaction: ShopReviewInteraction) -> int:
    shop = state.shop
    if shop is None:
        raise RuntimeError("The controller did not provide the active shop state.")
    font = _font(12)
    gap = 4
    columns = 2 if rect.width >= 680 else 1
    card_width = (rect.width - 16 - gap * (columns - 1)) // columns
    art_width = 56
    stats_width = 135
    for position in PLAYER_DRAFT_ORDER:
        starting = state.drafted_players[position]
        current = modified_player_stats(state, position)
        for label, base, value, percentage in (
            ("POWER", starting.power, current[0], False),
            ("VOLATILITY", starting.volatility, current[1], True),
            ("STAMINA", starting.stamina, current[2], True),
        ):
            base_text = _draft_percentage(round(base, 8)) if percentage else f"{base:g}"
            change, _ = _comparison(value, base, lower_is_better=label == "VOLATILITY",
                                    percentage=percentage)
            stats_width = max(stats_width, font.size(f"{label} {base_text}")[0] +
                              3 + _font(12, True).size(change)[0])
    detail_width = card_width - 16 - art_width - stats_width - 12
    rows = (len(PLAYER_DRAFT_ORDER) + columns - 1) // columns
    heights = []
    for row in range(rows):
        positions = PLAYER_DRAFT_ORDER[row * columns:(row + 1) * columns]
        heights.append(max(
            128, *(
                _section_height(_detail_sections(shop.roster.players[pos])[0], detail_width - 8, 1)
                + _section_height(_detail_sections(shop.roster.players[pos])[1], detail_width - 16, 2)
                + 18
                   for pos in positions)
        ))
    heights = [max(heights)] * rows
    needed = 32 + sum(heights) + gap * (rows - 1) + 4
    actual = rect.copy()
    actual.height = max(rect.height, needed)
    _panel(surface, actual)
    draw_text(surface, "TEAM DEPTH CHART", (rect.left + 12, rect.top + 8), _font(16, True), _TEXT)
    if shop.pending_player_upgrades:
        pending_text = f"{len(shop.pending_player_upgrades)} PENDING NEXT MATCH / DETAILS"
        draw_text(surface, pending_text,
                  (rect.right - 12 - font.size(pending_text)[0], rect.top + 10), font, _MUTED)
    top = rect.top + 30
    for row, height in enumerate(heights):
        for column, position in enumerate(PLAYER_DRAFT_ORDER[row * columns:(row + 1) * columns]):
            player = shop.roster.players[position]
            card = pygame.Rect(rect.left + 8 + column * (card_width + gap), top, card_width, height)
            _rounded_box(surface, card, _CARD, pygame.Color("#416788"), 6)
            pygame.draw.line(surface, "#284e6d",
                             (card.left + 9, card.top + 2), (card.right - 9, card.top + 2))
            name_width = art_width + stats_width + 4
            name = f"{_POSITION_LABELS[position]} / {player.name}"
            name_height = _text_height(name, _font(13, True), name_width)
            draw_complete_wrapped_text(surface, name,
                pygame.Rect(card.left + 8, card.top + 6, name_width, name_height),
                _font(13, True), _TEXT, line_gap=0)
            art = pygame.Rect(card.left + 8, card.top + name_height + 12, art_width, min(76, card.height - name_height - 20))
            appearance = state.player_appearances.get(position)
            if appearance is not None:
                draw_draft_player(surface, art, appearance)
            else:
                draw_complete_wrapped_text(surface, "No artwork selected", art, font, _MUTED, line_gap=0)
            start = state.drafted_players[position]
            values = modified_player_stats(state, position) if interaction.modified_stats else (
                start.power, start.volatility, start.stamina)
            stat_x = card.left + 8 + art_width + 6
            for index, (label, base, current, percentage) in enumerate((
                ("POWER", start.power, values[0], False),
                ("VOLATILITY", start.volatility, values[1], True),
                ("STAMINA", start.stamina, values[2], True),
            )):
                _draw_stat(surface, stat_x, card.top + name_height + 14 + index * 19,
                           label, base, current, interaction.modified_stats, percentage)
            detail_x = card.left + 8 + art_width + stats_width + 12
            partnership, perk = _detail_sections(player)
            partner_height = _section_height(partnership, detail_width - 8, 1)
            partner_rect = pygame.Rect(detail_x + 4, card.top + 4, detail_width - 8, partner_height)
            _draw_section(surface, partnership, partner_rect, 1, _TEXT, _MUTED)
            perk_box = pygame.Rect(detail_x, partner_rect.bottom + 2, detail_width, card.bottom - partner_rect.bottom - 6)
            _rounded_box(surface, perk_box, _PERK_BOX, _PERK_EDGE, 5)
            _draw_section(surface, perk, perk_box.inflate(-12, -8), 2, _PERK_TEXT, _PERK_TEXT)
        top += height + gap
    return actual.height


def _draw_details(surface: pygame.Surface, rect: pygame.Rect,
                  state: FootballGameControllerState) -> int:
    shop = state.shop
    if shop is None:
        raise RuntimeError("The controller did not provide the active shop state.")
    font = _font(15)
    width = rect.width - 32
    rows = []
    for upgrade in shop.purchased_upgrades:
        if upgrade.duration is FootballUpgradeDuration.PERMANENT:
            rows.append(f"{upgrade.name}: {upgrade.description}")
    next_roster = shop.next_match_roster
    pending_groups = {}
    for upgrade in shop.pending_player_upgrades:
        key = (upgrade.position, upgrade.stat)
        pending_groups.setdefault(key, []).append(upgrade)
    for (position, stat), upgrades in pending_groups.items():
        before = player_upgrade_stat_value(shop.roster.players[position], stat)
        after = player_upgrade_stat_value(next_roster.players[position], stat)
        effective_before = shop.coached_player_stat(shop.roster, position, stat)
        effective_after = shop.coached_player_stat(next_roster, position, stat)
        nominal = player_upgrade_effect_text(stat, sum(upgrade.amount for upgrade in upgrades))
        rows.append(
            f"PENDING NEXT MATCH / {_POSITION_LABELS[position]} {stat.value.upper()} "
            f"({len(upgrades)} purchases)\n"
            f"Nominal total: {nominal}. Raw run roster {stat_value(stat, before)} -> "
            f"raw next match {stat_value(stat, after)}; change {stat_change(stat, after - before)}. "
            f"Coached next match {stat_value(stat, effective_before)} -> "
            f"{stat_value(stat, effective_after)}; change {stat_change(stat, effective_after - effective_before)}. "
            "Power excludes fatigue, partnership and scheme. "
            "Stamina max 100%; volatility min 0%. Not permanent."
            + (" Changes in % are percentage points." if stat is not FootballUpgradeStat.POWER else "")
            + (f" {VOLATILITY_SPREAD_EXPLANATION}" if stat is FootballUpgradeStat.VOLATILITY else "")
        )
        for upgrade in upgrades:
            rows.append(f"PENDING NEXT MATCH / {upgrade.name}: {upgrade.description}")
    for card in shop.owned_coach_upgrades:
        sections = coach_upgrade_detail_sections(card)
        rows.append("\n".join((f"COACH / {sections[0]}", *sections[1:])))
    if not rows:
        rows.append("No run upgrades purchased.")
    rows.append("PLAYER PERKS / PLANNED AND INACTIVE")
    for position in PLAYER_DRAFT_ORDER:
        player = shop.roster.players[position]
        rows.append(f"{_POSITION_LABELS[position]} / {player.name}\n{_player_details(player)[2]}")
    height = 40 + sum(_text_height(text, font, width, 2) + 10 for text in rows) + 8
    actual = rect.copy()
    actual.height = max(rect.height, height)
    _panel(surface, actual)
    draw_text(surface, "PURCHASED RUN UPGRADES AND PLAYER PERK DETAILS",
              (rect.left + 12, rect.top + 8), _font(16, True), _TEXT)
    y = rect.top + 36
    for text in rows:
        h = _text_height(text, font, width, 2)
        _rounded_box(surface, pygame.Rect(rect.left + 7, y - 3, rect.width - 14, h + 6),
                     _CARD, pygame.Color("#315775"), 5)
        draw_complete_wrapped_text(surface, text, pygame.Rect(rect.left + 12, y, width, h),
                                   font, _MUTED, line_gap=2)
        y += h + 10
    return actual.height


def draw_depth_chart(
    surface: pygame.Surface, content: pygame.Rect, state: FootballGameControllerState,
    theme: Theme, font: pygame.font.Font, heading_font: pygame.font.Font,
    interaction: ShopReviewInteraction, leave: Callable[[], None],
) -> list[Button]:
    if state.shop is None:
        raise RuntimeError("The controller did not provide the active shop state.")
    title_font = _font(27, True)
    pygame.draw.line(surface, "#234966", (content.left, content.top + 50),
                     (content.right, content.top + 50))
    pygame.draw.line(surface, theme.primary, (content.left, content.top + 50),
                     (content.left + 76, content.top + 50), 2)
    draw_text(surface, "COLLEGE FOOTBALL / DEPTH CHART", (content.left, content.top),
              title_font, _TEXT)
    team = f"{state.shop.roster.team_name.upper()}  /  CURRENT RUN SNAPSHOT"
    draw_text(surface, team, (content.left + 2, content.top + 33), _font(13), _MUTED)
    body = pygame.Rect(content.left, content.top + 56, content.width, max(1, content.height - 111))
    if interaction.depth_viewport_size != body.size:
        interaction.depth_scroll = 0
        interaction.depth_viewport_size = body.size
    clip = surface.get_clip()
    surface.set_clip(body.clip(clip))
    y = body.top - interaction.depth_scroll
    if interaction.depth_details:
        total_height = _draw_details(surface, pygame.Rect(body.left, y, body.width, body.height), state)
    elif body.width < 720:
        staff_rect = pygame.Rect(body.left, y, body.width, 1)
        staff_height = _draw_staff(surface, staff_rect, state, theme)
        roster_rect = pygame.Rect(body.left, y + staff_height + 10, body.width, 1)
        total_height = staff_height + 10 + _draw_roster(surface, roster_rect, state, interaction)
    else:
        staff_width = max(240, min(300, round(body.width * 0.25)))
        staff_rect = pygame.Rect(body.left, y, staff_width, body.height)
        roster_rect = pygame.Rect(staff_rect.right + 10, y, body.width - staff_width - 10, body.height)
        total_height = max(_draw_staff(surface, staff_rect, state, theme),
                           _draw_roster(surface, roster_rect, state, interaction))
    interaction.depth_max_scroll = max(0, total_height - body.height)
    interaction.depth_scroll = min(interaction.depth_scroll, interaction.depth_max_scroll)
    surface.set_clip(clip)
    footer_y = content.bottom - 42
    label = ("MODIFIED STATS / SHOW STARTING STATS" if interaction.modified_stats
             else "STARTING STATS / SHOW MODIFIED STATS")
    detail_label = "BACK TO DEPTH CHART" if interaction.depth_details else "UPGRADES / PERK DETAILS"
    back_width = min(170, max(110, content.width // 5))
    available = content.width - back_width - 20
    toggle_width = min(300, available * 6 // 11)
    details_width = min(250, available - toggle_width)
    buttons = [
        DepthChartButton(label, interaction.toggle_stats, pygame.Rect(content.left, footer_y, toggle_width, 32)),
        DepthChartButton(detail_label, interaction.toggle_depth_details,
               pygame.Rect(content.left + toggle_width + 10, footer_y, details_width, 32)),
        DepthChartButton("BACK TO SHOP", leave, pygame.Rect(content.right - back_width, footer_y, back_width, 32)),
    ]
    hint = ("Scroll: wheel / Page Up / Page Down" if interaction.depth_max_scroll else
            "Modified power excludes partnership, fatigue and scheme; "
            "pending effects are separate and shown in details.")
    draw_text(surface, hint, (content.left + 2, content.bottom - 9), _font(11), _MUTED)
    return buttons
