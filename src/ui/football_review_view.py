"""Read-only shop reviews and the explicit owned-card removal presentation."""

from collections.abc import Callable

import pygame

from src.engine.football_controller import FootballGameControllerState
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG, OFFENSIVE_PLAY_CATALOG, FootballPlayDefinition,
)
from src.engine.football_shop import MIN_PLAYBOOK_DECK_SIZE, FootballShopState
from src.engine.football_simulator import calculate_standardized_play_estimate
from src.ui.football_depth_chart import draw_depth_chart
from src.ui.football_display import _POSITION_LABELS
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.text import fit_text as _fit_text
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_panel, draw_text


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
        pending = shop.pending_removal is not None
        heading = (
            "PLAYBOOK  /  SELECT ONE OWNED COPY TO REMOVE"
            if pending
            else "PLAYBOOK  /  OWNED CARDS, NOT THE CURRENT MATCH HAND"
        )
        draw_text(
            surface,
            heading,
            (content.left + 2, content.top + 2),
            self._label_font,
            self.theme.text,
        )
        columns = (
            ("OFFENSE", shop.offensive_deck, OFFENSIVE_PLAY_CATALOG),
            ("DEFENSE", shop.defensive_deck, DEFENSIVE_SCHEME_CATALOG),
        )
        gap = 12
        top = content.top + 30
        footer_top = content.bottom - 48
        panel_height = max(1, footer_top - top)
        panel_width = (content.width - gap) // 2
        row_top_offset = 46
        row_height = 56
        visible_rows = max(1, (panel_height - row_top_offset - 8) // row_height)
        self.interaction.playbook_max_scroll = max(
            0, max(len(cards) for _, cards, _ in columns) - visible_rows
        )
        self.interaction.playbook_scroll = min(self.interaction.playbook_scroll, self.interaction.playbook_max_scroll)
        buttons: list[Button] = []
        for column, (title, cards, catalog) in enumerate(columns):
            rect = pygame.Rect(
                content.left + column * (panel_width + gap),
                top,
                panel_width,
                panel_height,
            )
            draw_panel(surface, rect, self.theme, fill=self.theme.panel)
            minimum = "  /  MIN 4"
            draw_text(
                surface,
                f"{title}  /  {len(cards)} CARDS{minimum}",
                (rect.left + 12, rect.top + 10),
                self._label_font,
                self.theme.text,
            )
            counts: dict[str, int] = {}
            for card in cards:
                counts[card.card_id] = counts.get(card.card_id, 0) + 1
            seen: dict[str, int] = {}
            start_index = self.interaction.playbook_scroll
            for card in cards[:start_index]:
                seen[card.card_id] = seen.get(card.card_id, 0) + 1
            for visible_index, card in enumerate(
                cards[start_index : start_index + visible_rows]
            ):
                index = start_index + visible_index
                seen[card.card_id] = seen.get(card.card_id, 0) + 1
                definition = catalog[card.card_id]
                label = (
                    f"{definition.name}  /  {definition.family.label.upper()}  /  COPY "
                    f"{seen[card.card_id]} OF "
                    f"{counts[card.card_id]}"
                )
                row = pygame.Rect(
                    rect.left + 8,
                    rect.top + row_top_offset + visible_index * row_height,
                    rect.width - 16,
                    row_height - 3,
                )
                pygame.draw.rect(
                    surface,
                    self.theme.panel_alt if index % 2 else self.theme.panel,
                    row,
                    border_radius=5,
                )
                remove_width = 72 if pending else 0
                text_width = row.width - remove_width - 16
                draw_text(
                    surface,
                    _fit_text(label, self._small_font, text_width),
                    (row.left + 7, row.top + 3),
                    self._small_font,
                    self.theme.text,
                )
                contributors = ", ".join(
                    _POSITION_LABELS[position]
                    for position in definition.contributors
                )
                if isinstance(definition, FootballPlayDefinition):
                    neutral_yards = calculate_standardized_play_estimate(
                        definition.action
                    ).expected_yards
                    detail = (
                        f"{contributors} / NEUTRAL ~{neutral_yards:.1f} YDS / "
                        f"BASE {definition.clock_seconds}s"
                    )
                else:
                    detail = (
                        f"{contributors} / COUNTERS {definition.family.label.upper()}"
                    )
                draw_text(
                    surface,
                    _fit_text(detail, self._small_font, text_width),
                    (row.left + 7, row.top + 21),
                    self._small_font,
                    self.theme.muted,
                )
                draw_text(
                    surface,
                    _fit_text(
                        definition.description,
                        self._small_font,
                        text_width,
                    ),
                    (row.left + 7, row.top + 38),
                    self._small_font,
                    self.theme.muted,
                )
                if pending:
                    can_remove = len(cards) > MIN_PLAYBOOK_DECK_SIZE
                    buttons.append(
                        Button(
                            "REMOVE",
                            lambda copy_id=card.copy_id: self.remove(copy_id),
                            pygame.Rect(
                                row.right - remove_width,
                                row.top + 7,
                                remove_width - 2,
                                28,
                            ),
                            enabled=can_remove,
                            variant="quiet",
                        )
                    )
        if self.interaction.playbook_max_scroll:
            draw_text(
                surface,
                f"Scroll to browse / {self.interaction.playbook_scroll + 1} of "
                f"{self.interaction.playbook_max_scroll + 1}",
                (content.left + 2, content.top + 16),
                self._small_font,
                self.theme.muted,
            )
        buttons.append(
            Button(
                "CANCEL SELECTION" if pending else "BACK TO SHOP",
                self.leave,
                pygame.Rect(content.right - 210, content.bottom - 40, 210, 34),
                variant="primary",
            )
        )
        return buttons
