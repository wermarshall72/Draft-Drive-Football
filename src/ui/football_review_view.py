"""Read-only shop reviews and the explicit owned-card removal presentation."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import pygame

from src.engine.football import FootballCardCopy, FootballPosition
from src.engine.football_controller import FootballGameControllerState
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
    FootballBonusCardDefinition,
    FootballPlayDefinition,
    FootballSchemeDefinition,
)
from src.engine.football_shop import (
    MIN_PLAYBOOK_DECK_SIZE,
    PLAYBOOK_CARD_RARITIES,
    FootballShopRarity,
    FootballShopState,
)
from src.engine.football_simulator import calculate_standardized_play_estimate
from src.ui.coach_fonts import staff_font
from src.ui.football_card_art import (
    bonus_card_art,
    draw_card_art,
    play_card_art,
    scheme_card_art,
)
from src.ui.football_depth_chart import draw_depth_chart
from src.ui.football_display import _POSITION_LABELS
from src.ui.football_shop_review import PlaybookCategory, ShopReviewInteraction
from src.ui.text import draw_complete_wrapped_text, wrap_text_lines
from src.ui.stat_icons import without_stat_icons
from src.ui.theme import Theme, readable_ink, relative_luminance
from src.ui.widgets import Button, draw_panel, draw_text

_PLAYBOOK_FILL = pygame.Color("#13283d")
_RARITY_COLORS = {
    FootballShopRarity.COMMON: pygame.Color("#a8b2a1"),
    FootballShopRarity.UNCOMMON: pygame.Color("#68c58a"),
    FootballShopRarity.RARE: pygame.Color("#df786d"),
    FootballShopRarity.VERY_RARE: pygame.Color("#c18be8"),
}
_RARITY_LABELS = {
    None: "ALL RARITIES",
    FootballShopRarity.COMMON: "COMMON",
    FootballShopRarity.UNCOMMON: "UNCOMMON",
    FootballShopRarity.RARE: "RARE",
    FootballShopRarity.VERY_RARE: "VERY RARE",
}
_CATEGORY_LABELS = {
    "all": "ALL CATEGORIES",
    "offense": "OFFENSE",
    "defense": "DEFENSE",
    "special": "SPECIAL",
}


@dataclass(frozen=True)
class _PlaybookEntry:
    copy: FootballCardCopy
    category: Literal["offense", "defense", "special"]
    definition: FootballPlayDefinition | FootballSchemeDefinition | FootballBonusCardDefinition
    contributors: tuple[FootballPosition, ...]
    rarity: FootballShopRarity


def _playbook_entries(shop: FootballShopState) -> list[_PlaybookEntry]:
    offense_entries: list[_PlaybookEntry] = []
    for card in shop.offensive_deck:
        if card.card_id in BONUS_CARD_CATALOG:
            definition = BONUS_CARD_CATALOG[card.card_id]
            category: Literal["offense", "defense", "special"] = "special"
            contributors: tuple[FootballPosition, ...] = ()
        else:
            definition = OFFENSIVE_PLAY_CATALOG[card.card_id]
            category = "offense"
            contributors = definition.contributors
        offense_entries.append(
            _PlaybookEntry(
                card,
                category,
                definition,
                contributors,
                PLAYBOOK_CARD_RARITIES[card.card_id],
            )
        )
    defense_entries: list[_PlaybookEntry] = []
    for card in shop.defensive_deck:
        definition = DEFENSIVE_SCHEME_CATALOG[card.card_id]
        defense_entries.append(
            _PlaybookEntry(
                card,
                "defense",
                definition,
                definition.contributors,
                PLAYBOOK_CARD_RARITIES[card.card_id],
            )
        )

    entries: list[_PlaybookEntry] = []
    for index in range(max(len(offense_entries), len(defense_entries))):
        if index < len(offense_entries):
            entries.append(offense_entries[index])
        if index < len(defense_entries):
            entries.append(defense_entries[index])
    return entries


def _category_border_color(color: pygame.Color, background: pygame.Color) -> pygame.Color:
    """Keep the selected team hue while lifting low-contrast borders."""
    background_luminance = relative_luminance(background)
    target = readable_ink(background)
    current = pygame.Color(color)
    for step in range(1, 9):
        luminance = relative_luminance(current)
        ratio = (max(luminance, background_luminance) + 0.05) / (
            min(luminance, background_luminance) + 0.05
        )
        if ratio >= 2.5:
            return current
        amount = step / 8
        current = pygame.Color(
            round(color.r + (target.r - color.r) * amount),
            round(color.g + (target.g - color.g) * amount),
            round(color.b + (target.b - color.b) * amount),
        )
    return current


def _draw_dashed_border(
    surface: pygame.Surface,
    rect: pygame.Rect,
    colors: tuple[pygame.Color, pygame.Color],
) -> None:
    inner = rect.inflate(-4, -4)
    dash_length = 9
    step = 15
    dash_index = 0
    for start, end in (
        ((inner.left, inner.top), (inner.right, inner.top)),
        ((inner.right, inner.top), (inner.right, inner.bottom)),
        ((inner.right, inner.bottom), (inner.left, inner.bottom)),
        ((inner.left, inner.bottom), (inner.left, inner.top)),
    ):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = max(abs(dx), abs(dy))
        for offset in range(0, length, step):
            finish = min(length, offset + dash_length)
            first = (
                round(start[0] + dx * offset / length),
                round(start[1] + dy * offset / length),
            )
            last = (
                round(start[0] + dx * finish / length),
                round(start[1] + dy * finish / length),
            )
            pygame.draw.line(
                surface,
                colors[dash_index % len(colors)],
                first,
                last,
                3,
            )
            dash_index += 1


class FootballReviewView:
    def __init__(
        self, theme: Theme, small_font: pygame.font.Font, label_font: pygame.font.Font,
        interaction: ShopReviewInteraction, leave: Callable[[], None],
        remove: Callable[[str], None],
    ) -> None:
        self.theme = theme
        self._small_font = small_font
        self._label_font = label_font
        self.interaction = interaction
        self.leave = leave
        self.remove = remove
        self._title_font = staff_font(26, semibold=True)
        self._card_title_font = staff_font(20, semibold=True)
        self._meta_font = staff_font(14, semibold=True)
        self._detail_font = staff_font(13)
        self._description_font = staff_font(14)
        self._badge_font = staff_font(12, semibold=True)

    def draw_depth_chart(
        self, surface: pygame.Surface, content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> list[Button]:
        return draw_depth_chart(
            surface, content, state, self.theme, self._small_font,
            self._label_font, self.interaction, self.leave,
        )

    def draw_playbook(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        shop: FootballShopState | None,
    ) -> list[Button]:
        if shop is None:
            raise RuntimeError("The controller did not provide the active shop state.")
        removal = shop.pending_removal
        pending = removal is not None
        entries = _playbook_entries(shop)
        filtered = [
            entry
            for entry in entries
            if (
                self.interaction.playbook_category == "all"
                or entry.category == self.interaction.playbook_category
            )
            and (
                self.interaction.playbook_position is None
                or self.interaction.playbook_position in entry.contributors
            )
            and (
                self.interaction.playbook_rarity is None
                or entry.rarity is self.interaction.playbook_rarity
            )
        ]
        title_y = content.top + 2
        draw_text(
            surface,
            "PLAYBOOK",
            (content.left + 2, title_y),
            self._title_font,
            self.theme.text,
        )
        draw_text(
            surface,
            "View your deck of plays",
            (content.left + 3, title_y + 34),
            self._label_font,
            self.theme.muted,
        )
        if removal is not None:
            message = pygame.Rect(content.right - 386, content.top + 2, 384, 58)
            draw_panel(surface, message, self.theme, fill=self.theme.panel)
            draw_text(
                surface,
                "REMOVAL MODE",
                (message.left + 12, message.top + 7),
                self._meta_font,
                self.theme.secondary_accent,
            )
            draw_text(
                surface,
                f"Select a copy to remove · {removal.cost} AP on confirmation",
                (message.left + 12, message.top + 29),
                self._detail_font,
                self.theme.text,
            )

        filter_top = content.top + 74
        toolbar = pygame.Rect(content.left, filter_top, content.width, 48)
        draw_panel(surface, toolbar, self.theme, fill=self.theme.panel)
        filter_gap = 12
        filter_width = (toolbar.width - 2 * filter_gap - 20) // 3
        filter_left = toolbar.left + 10
        category_label = (
            f"CATEGORY: {_CATEGORY_LABELS[self.interaction.playbook_category]}"
        )
        position_label = (
            "POSITION: ALL POSITIONS"
            if self.interaction.playbook_position is None
            else f"POSITION: {_POSITION_LABELS[self.interaction.playbook_position].upper()}"
        )
        rarity_label = f"RARITY: {_RARITY_LABELS[self.interaction.playbook_rarity]}"
        filter_actions = (
            (
                category_label,
                self.interaction.cycle_playbook_category,
                self.interaction.playbook_category != "all",
            ),
            (
                position_label,
                self.interaction.cycle_playbook_position,
                self.interaction.playbook_position is not None,
            ),
            (
                rarity_label,
                self.interaction.cycle_playbook_rarity,
                self.interaction.playbook_rarity is not None,
            ),
        )
        buttons: list[Button] = []
        for index, (label, action, active) in enumerate(filter_actions):
            buttons.append(
                Button(
                    label,
                    action,
                    pygame.Rect(
                        filter_left + index * (filter_width + filter_gap),
                        toolbar.top + 6,
                        filter_width,
                        toolbar.height - 12,
                    ),
                    variant="primary" if active else "quiet",
                )
            )

        list_top = toolbar.bottom + 16
        footer_top = content.bottom - 42
        list_bottom = footer_top - 12
        list_height = max(1, list_bottom - list_top)
        card_gap_x = 12
        card_gap_y = 10
        card_width = (content.width - card_gap_x) // 2
        card_height = min(148, max(104, (list_height - 2 * card_gap_y) // 3))
        visible_rows = max(
            1,
            (list_height + card_gap_y) // (card_height + card_gap_y),
        )
        primary_border = _category_border_color(self.theme.primary, _PLAYBOOK_FILL)
        secondary_border = _category_border_color(
            self.theme.secondary, _PLAYBOOK_FILL
        )
        total_rows = (len(filtered) + 1) // 2
        self.interaction.playbook_page_size = visible_rows
        self.interaction.playbook_max_scroll = max(0, total_rows - visible_rows)
        self.interaction.playbook_scroll = min(
            self.interaction.playbook_scroll,
            self.interaction.playbook_max_scroll,
        )
        visible_start = self.interaction.playbook_scroll * 2
        visible_entries = filtered[visible_start : visible_start + visible_rows * 2]
        deck_sizes = {
            "offense": len(shop.offensive_deck),
            "special": len(shop.offensive_deck),
            "defense": len(shop.defensive_deck),
        }
        counts = Counter(
            (entry.category, entry.copy.card_id) for entry in entries
        )
        copy_numbers: dict[str, int] = {}
        seen: Counter[tuple[str, str]] = Counter()
        for entry in entries:
            copy_key = (entry.category, entry.copy.card_id)
            seen[copy_key] += 1
            copy_numbers[entry.copy.copy_id] = seen[copy_key]

        for index, entry in enumerate(visible_entries):
            row_index, column = divmod(index, 2)
            row = pygame.Rect(
                content.left + column * (card_width + card_gap_x),
                list_top + row_index * (card_height + card_gap_y),
                card_width,
                card_height,
            )
            pygame.draw.rect(
                surface,
                self.theme.shadow,
                row.move(0, 3),
                border_radius=10,
            )
            pygame.draw.rect(surface, _PLAYBOOK_FILL, row, border_radius=10)
            pygame.draw.rect(
                surface,
                self.theme.border_soft,
                row,
                width=1,
                border_radius=10,
            )
            if entry.category == "special":
                _draw_dashed_border(
                    surface, row, (primary_border, secondary_border)
                )
                category_label_text = "SPECIAL CARD"
            elif entry.category == "offense":
                pygame.draw.rect(
                    surface,
                    primary_border,
                    row.inflate(-2, -2),
                    width=3,
                    border_radius=9,
                )
                category_label_text = "OFFENSIVE PLAY"
            else:
                pygame.draw.rect(
                    surface,
                    secondary_border,
                    row.inflate(-2, -2),
                    width=4,
                    border_radius=9,
                )
                category_label_text = "DEFENSIVE SCHEME"

            if entry.category == "special":
                art_name = bonus_card_art(entry.definition.action)
                detail = ""
                copy_type = "PLAYABLE BONUS"
                description = entry.definition.description
            elif entry.category == "offense":
                assert isinstance(entry.definition, FootballPlayDefinition)
                art_name = play_card_art(entry.definition.family)
                contributors = ", ".join(
                    _POSITION_LABELS[position]
                    for position in entry.definition.contributors
                )
                expected_yards = calculate_standardized_play_estimate(
                    entry.definition.action
                ).expected_yards
                detail = (
                    f"{contributors}  ·  NEUTRAL ~{expected_yards:.1f} YDS  ·  "
                    f"BASE {entry.definition.clock_seconds}s"
                )
                copy_type = entry.definition.family.label.upper()
                description = entry.definition.description
            else:
                assert isinstance(entry.definition, FootballSchemeDefinition)
                art_name = scheme_card_art(entry.definition.family)
                contributors = ", ".join(
                    _POSITION_LABELS[position]
                    for position in entry.definition.contributors
                )
                detail = (
                    f"{contributors}  ·  {entry.definition.family.label.upper()}  /  "
                    f"COUNTERS {entry.definition.family.label.upper()}"
                )
                copy_type = entry.definition.family.label.upper()
                description = entry.definition.description

            art_rect = pygame.Rect(row.left + 12, row.centery - 39, 78, 78)
            draw_card_art(surface, art_name, art_rect)
            text_left = row.left + 102
            side_width = 116
            text_width = row.right - side_width - 14 - text_left
            draw_text(
                surface,
                entry.definition.name,
                (text_left, row.top + 10),
                without_stat_icons(self._card_title_font),
                self.theme.text,
            )
            copy_label = (
                f"{category_label_text}  ·  {copy_type}  ·  COPY "
                f"{copy_numbers[entry.copy.copy_id]} OF "
                f"{counts[(entry.category, entry.copy.card_id)]}"
            )
            draw_text(
                surface,
                copy_label,
                (text_left, row.top + 36),
                self._meta_font,
                (
                    self.theme.secondary_accent
                    if entry.category == "special"
                    else primary_border
                    if entry.category == "offense"
                    else secondary_border
                ),
            )

            details_y = row.top + 56
            if detail:
                detail_lines = wrap_text_lines(
                    detail, self._detail_font, text_width
                )
                detail_height = len(detail_lines) * (
                    self._detail_font.get_height() + 1
                )
                draw_complete_wrapped_text(
                    surface,
                    detail,
                    pygame.Rect(text_left, details_y, text_width, detail_height),
                    self._detail_font,
                    self.theme.muted,
                    line_gap=1,
                )
                description_y = details_y + detail_height + 3
            else:
                description_y = details_y
            description_rect = pygame.Rect(
                text_left,
                description_y,
                text_width,
                row.bottom - 9 - description_y,
            )
            draw_complete_wrapped_text(
                surface,
                description,
                description_rect,
                self._description_font,
                self.theme.text,
                line_gap=1,
            )

            rarity_color = _RARITY_COLORS[entry.rarity]
            rarity_label = entry.rarity.value.replace("_", " ").upper()
            badge = pygame.Rect(row.right - 108, row.top + 19, 96, 27)
            pygame.draw.rect(
                surface,
                rarity_color,
                badge,
                border_radius=7,
            )
            pygame.draw.rect(
                surface,
                self.theme.canvas_lift,
                badge,
                width=1,
                border_radius=7,
            )
            rarity_text_width = self._badge_font.size(rarity_label)[0]
            draw_text(
                surface,
                rarity_label,
                (
                    badge.centerx - rarity_text_width // 2,
                    badge.centery - self._badge_font.get_height() // 2,
                ),
                self._badge_font,
                readable_ink(rarity_color),
            )
            if pending:
                can_remove = deck_sizes[entry.category] > MIN_PLAYBOOK_DECK_SIZE
                buttons.append(
                    Button(
                        "REMOVE",
                        lambda copy_id=entry.copy.copy_id: self.remove(copy_id),
                        pygame.Rect(row.right - 108, row.bottom - 40, 96, 28),
                        enabled=can_remove,
                        variant="quiet",
                    )
                )

        if not filtered:
            empty_rect = pygame.Rect(
                content.left + 12,
                list_top + 8,
                content.width - 24,
                list_height - 16,
            )
            draw_panel(surface, empty_rect, self.theme, fill=self.theme.panel)
            empty_title = "No cards match these filters."
            empty_title_width = self._card_title_font.size(empty_title)[0]
            draw_text(
                surface,
                empty_title,
                (empty_rect.centerx - empty_title_width // 2, empty_rect.centery - 25),
                self._card_title_font,
                self.theme.text,
            )
            empty_hint = "Try another category, position, or rarity."
            empty_hint_width = self._label_font.size(empty_hint)[0]
            draw_text(
                surface,
                empty_hint,
                (empty_rect.centerx - empty_hint_width // 2, empty_rect.centery + 8),
                self._label_font,
                self.theme.muted,
            )

        buttons.append(
            Button(
                "CANCEL SELECTION" if pending else "BACK TO SHOP",
                self.leave,
                pygame.Rect(content.right - 212, footer_top, 212, 36),
                variant="primary",
            )
        )
        count_text = (
            f"{len(filtered)} OWNED COPIES  ·  MOUSE WHEEL / PAGE UP / PAGE DOWN TO BROWSE"
        )
        if pending:
            count_text += "  ·  EACH DECK KEEPS AT LEAST 4 CARDS"
        draw_text(
            surface,
            count_text,
            (content.left + 2, footer_top + 11),
            self._small_font,
            self.theme.muted,
        )
        return buttons
