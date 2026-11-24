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
from src.ui.football_card_art import draw_card_art
from src.ui.football_card_faces import card_art_name, draw_play_card_face
from src.ui.football_inspect import bonus_inspect, play_inspect, scheme_inspect
from src.ui.football_ui_kit import (
    MATCH_DANGER, MATCH_DIM, MATCH_INK, MATCH_MUTED, MATCH_PANEL_DEEP, MATCH_PANEL_EDGE,
    MATCH_PANEL_EDGE_SOFT, MATCH_TEXT, PaintedButton, blit_text, draw_focus_ring,
    draw_message_banner, kit_button, mix, plain_font, rarity_color, team_accent,
)
from src.ui.football_depth_chart import draw_depth_chart
from src.ui.football_display import _POSITION_LABELS
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.text import fit_text
from src.ui.theme import Theme
from src.ui.widgets import Button

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


class FootballReviewView:
    def __init__(
        self, theme: Theme, small_font: pygame.font.Font, label_font: pygame.font.Font,
        interaction: ShopReviewInteraction, leave: Callable[[], None],
        remove: Callable[[str], None],
        error: str | None = None,
    ) -> None:
        self.theme = theme
        self._small_font = small_font
        self._label_font = label_font
        self.interaction = interaction
        self.leave = leave
        self.remove = remove
        self.error = error

    def draw_depth_chart(
        self, surface: pygame.Surface, content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> list[Button]:
        return draw_depth_chart(
            surface, content, state, self.theme, self._small_font,
            self._label_font, self.interaction, self.leave, error=self.error,
        )

    def draw_playbook(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        shop: FootballShopState | None,
        *,
        hover_key: object | None = None,
        focus_key: object | None = None,
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
        accent = team_accent(self.theme.primary)
        title = blit_text(surface, plain_font(30), "PLAYBOOK", MATCH_TEXT, content,
                          topleft=(content.left, content.top))
        pygame.draw.rect(surface, accent, (title.right + 10, title.centery - 2, 34, 4), border_radius=2)
        deck_sizes = {
            "offense": len(shop.offensive_deck),
            "special": len(shop.offensive_deck),
            "defense": len(shop.defensive_deck),
        }
        chip_x = content.left
        for text in (f"OFFENSE {len(shop.offensive_deck)}", f"DEFENSE {len(shop.defensive_deck)}",
                     f"MIN {MIN_PLAYBOOK_DECK_SIZE} EACH"):
            font = plain_font(12)
            chip = pygame.Rect(chip_x, content.top + 38, font.size(text)[0] + 16, 20)
            pygame.draw.rect(surface, MATCH_PANEL_DEEP, chip, border_radius=10)
            pygame.draw.rect(surface, MATCH_PANEL_EDGE, chip, 1, border_radius=10)
            blit_text(surface, font, text, MATCH_MUTED if text.startswith("MIN") else MATCH_TEXT,
                      chip.inflate(2, 2), center=chip.center)
            chip_x = chip.right + 6
        if removal is not None:
            # Leave the top-right 120px slot (plus a gap) for the run screen's PAUSE button.
            banner = pygame.Rect(content.left + 420, content.top + 2, content.width - 420 - 130, 50)
            draw_message_banner(
                surface, banner,
                f"REMOVAL MODE · PICK THE COPY TO REMOVE · {removal.cost} AP WHEN CONFIRMED",
            )

        toolbar_top = content.top + 68
        filter_actions = (
            (f"CATEGORY · {_CATEGORY_LABELS[self.interaction.playbook_category]}",
             self.interaction.cycle_playbook_category, self.interaction.playbook_category != "all"),
            ("POSITION · ALL POSITIONS" if self.interaction.playbook_position is None
             else f"POSITION · {_POSITION_LABELS[self.interaction.playbook_position]}",
             self.interaction.cycle_playbook_position, self.interaction.playbook_position is not None),
            (f"RARITY · {_RARITY_LABELS[self.interaction.playbook_rarity]}",
             self.interaction.cycle_playbook_rarity, self.interaction.playbook_rarity is not None),
        )
        filter_buttons: list[Button] = []
        for index, (label, action, active) in enumerate(filter_actions):
            filter_buttons.append(kit_button(
                label, action, pygame.Rect(content.left + index * 262, toolbar_top, 252, 38),
                variant="kit-toggle-on" if active else "kit",
            ))

        # Cards come first in focus order; filters and Back follow.
        buttons: list[Button] = []
        list_top = toolbar_top + 52
        footer_top = content.bottom - 42
        list_bottom = footer_top - 12
        list_height = max(1, list_bottom - list_top)
        columns = 6
        card_gap_x = 10
        card_gap_y = 12
        card_width = (content.width - card_gap_x * (columns - 1)) // columns
        card_height = min(262, max(220, (list_height - card_gap_y) // 2))
        visible_rows = max(1, (list_height + card_gap_y) // (card_height + card_gap_y))
        total_rows = (len(filtered) + columns - 1) // columns
        self.interaction.playbook_page_size = visible_rows
        self.interaction.playbook_max_scroll = max(0, total_rows - visible_rows)
        self.interaction.playbook_scroll = min(
            self.interaction.playbook_scroll, self.interaction.playbook_max_scroll,
        )
        visible_start = self.interaction.playbook_scroll * columns
        visible_entries = filtered[visible_start: visible_start + visible_rows * columns]
        counts = Counter((entry.category, entry.copy.card_id) for entry in entries)
        copy_numbers: dict[str, int] = {}
        seen: Counter[tuple[str, str]] = Counter()
        for entry in entries:
            copy_key = (entry.category, entry.copy.card_id)
            seen[copy_key] += 1
            copy_numbers[entry.copy.copy_id] = seen[copy_key]
        blit_text(
            surface, plain_font(12),
            f"{len(filtered)} OWNED COPIES" + (
                f"  ·  ROWS {self.interaction.playbook_scroll + 1}-"
                f"{min(total_rows, self.interaction.playbook_scroll + visible_rows)} OF {total_rows}"
                if self.interaction.playbook_max_scroll else ""
            ),
            MATCH_MUTED, content, midright=(content.right, toolbar_top + 19),
        )

        contents: dict[object, tuple] = {}
        for index, entry in enumerate(visible_entries):
            row_index, column = divmod(index, columns)
            rect = pygame.Rect(
                content.left + column * (card_width + card_gap_x),
                list_top + row_index * (card_height + card_gap_y),
                card_width, card_height,
            )
            can_remove = pending and deck_sizes[entry.category] > MIN_PLAYBOOK_DECK_SIZE
            key = ("playbook", entry.copy.copy_id)
            art = card_art_name(entry.definition)
            painter = lambda target, r, name=art: draw_card_art(target, name, r)  # noqa: E731
            copy_text = f"Copy {copy_numbers[entry.copy.copy_id]} of {counts[(entry.category, entry.copy.card_id)]}"
            extra = (("Copy", copy_text),)
            if isinstance(entry.definition, FootballPlayDefinition):
                contents[key] = (play_inspect(entry.definition, entry.rarity, None, painter, extra), rect)
            elif isinstance(entry.definition, FootballSchemeDefinition):
                contents[key] = (scheme_inspect(entry.definition, entry.rarity, None, painter, extra), rect)
            else:
                contents[key] = (bonus_inspect(entry.definition, entry.rarity, None, painter, extra), rect)
            remove_rect = pygame.Rect(rect.left + 8, rect.bottom - 38, rect.width - 16, 30)
            buttons.append(PaintedButton(
                "REMOVE" if pending else entry.definition.name.upper(),
                (lambda copy_id=entry.copy.copy_id, allowed=can_remove:
                 self.remove(copy_id) if allowed else None),
                rect,
                variant="playbook-card",
                click_rect=remove_rect if pending else pygame.Rect(rect.left, rect.top, 0, 0),
                painter=(lambda target, button, hovered, pressed, e=entry, removable=can_remove,
                         number=copy_numbers[entry.copy.copy_id],
                         total=counts[(entry.category, entry.copy.card_id)]:
                         self._paint_card(target, button, e, hovered, pressed, pending=pending,
                                          removable=removable, number=number, total=total)),
            ))
            buttons[-1].inspect_key = key
            buttons[-1].removable = can_remove
            buttons[-1].copy_id = entry.copy.copy_id
            buttons[-1].card_id = entry.copy.card_id

        if not filtered:
            empty_rect = pygame.Rect(content.left, list_top, content.width, list_height)
            pygame.draw.rect(surface, MATCH_PANEL_DEEP, empty_rect, border_radius=12)
            pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, empty_rect, 2, border_radius=12)
            blit_text(surface, plain_font(20), "NO CARDS MATCH THESE FILTERS", MATCH_TEXT, empty_rect,
                      center=(empty_rect.centerx, empty_rect.centery - 12))
            blit_text(surface, plain_font(13, False), "Try another category, position, or rarity.",
                      MATCH_MUTED, empty_rect, center=(empty_rect.centerx, empty_rect.centery + 16))

        buttons.extend(filter_buttons)
        buttons.append(kit_button(
            "CANCEL SELECTION" if pending else "BACK TO SHOP", self.leave,
            pygame.Rect(content.right - 212, footer_top, 212, 42), variant="kit-primary",
        ))
        hint = "WHEEL / PAGE UP / PAGE DOWN TO BROWSE  ·  HOVER FOR DETAILS"
        if pending:
            hint += "  ·  EACH DECK KEEPS AT LEAST 4 CARDS"
        hint_box = pygame.Rect(content.left, footer_top, content.width - 228, 42)
        hint_font = plain_font(12)
        if self.error:
            hint, hint_color = f"CHECK: {self.error}", MATCH_DANGER
        else:
            hint_color = MATCH_MUTED
        blit_text(surface, hint_font, fit_text(hint, hint_font, hint_box.width), hint_color, hint_box,
                  midleft=(hint_box.left + 2, hint_box.centery))
        self.interaction.inspect.prepare(contents, hover_key, focus_key)
        return buttons

    def _paint_card(self, surface: pygame.Surface, button: PaintedButton, entry: "_PlaybookEntry",
                    hovered: bool, pressed: bool, *, pending: bool, removable: bool,
                    number: int, total: int) -> None:
        highlighted = hovered or (button.focused and self.interaction.inspect.keyboard)
        rect = button.rect.move(0, -5 if highlighted and not pressed else 0)
        if highlighted:
            draw_focus_ring(surface, rect, 9)
        draw_play_card_face(surface, rect, entry.definition, entry.rarity, bottom_gap=44)
        footer = pygame.Rect(rect.left + 8, rect.bottom - 38, rect.width - 16, 30)
        if total > 1:
            badge_font = plain_font(11)
            text = f"{number}/{total}"
            badge = pygame.Rect(0, 0, badge_font.size(text)[0] + 12, 18)
            badge.topleft = (rect.left + 8, rect.top + 12)
            pygame.draw.rect(surface, MATCH_INK, badge, border_radius=7)
            blit_text(surface, badge_font, text, MATCH_TEXT, badge.inflate(2, 2), center=badge.center)
        if not pending:
            label_font = plain_font(13)
            blit_text(surface, label_font, _RARITY_LABELS[entry.rarity], rarity_color(entry.rarity), footer,
                      midleft=(footer.left + 2, footer.centery))
            copy_font = plain_font(11, False)
            blit_text(surface, copy_font, f"COPY {number} OF {total}", MATCH_MUTED, footer,
                      midright=(footer.right - 2, footer.centery))
            return
        draw_rect = footer.move(0, 2) if pressed and removable else footer
        if removable:
            fill = mix(MATCH_DANGER, MATCH_PANEL_DEEP, 0.15 if highlighted else 0.3)
            edge, ink = MATCH_DANGER, MATCH_INK
        else:
            fill, edge, ink = MATCH_PANEL_DEEP, MATCH_PANEL_EDGE_SOFT, MATCH_DIM
        pygame.draw.rect(surface, fill, draw_rect, border_radius=7)
        pygame.draw.rect(surface, edge, draw_rect, 2, border_radius=7)
        blit_text(surface, plain_font(15), "REMOVE" if removable else "DECK AT MIN", ink, draw_rect,
                  center=draw_rect.center)
