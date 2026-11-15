"""Read-only shop reviews and the explicit owned-card removal presentation."""

from collections.abc import Callable

import pygame

from src.engine.football import FootballPosition
from src.engine.football_coaches import FootballCoachSide, coaches_for_assignment
from src.engine.football_controller import FootballGameControllerState
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG, OFFENSIVE_PLAY_CATALOG, FootballPlayDefinition,
)
from src.engine.football_player_catalog import player_type_for_id
from src.engine.football_shop import MIN_PLAYBOOK_DECK_SIZE, FootballShopState
from src.engine.football_simulator import calculate_standardized_play_estimate
from src.ui.football_display import _POSITION_LABELS, _coach_perk_summary
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.text import fit_text as _fit_text
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text


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
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        state: FootballGameControllerState,
    ) -> list[Button]:
        shop = state.shop
        if shop is None:
            raise RuntimeError("The controller did not provide the active shop state.")

        draw_text(
            surface,
            "DEPTH CHART  /  CURRENT RUN SNAPSHOT  /  SCROLL FOR DETAILS",
            (content.left + 2, content.top + 2),
            self._label_font,
            self.theme.text,
        )
        offense_coach, defense_coach = coaches_for_assignment(
            shop.roster.coach_assignment
        )
        gap = 12
        body_rect = pygame.Rect(
            content.left,
            content.top + 28,
            content.width,
            content.height - 78,
        )
        coach_height = 142
        coach_width = (body_rect.width - gap) // 2
        player_row_height = 92
        player_panel_height = 36 + 4 * player_row_height
        upgrade_row_height = 42
        upgrade_height = 52 + max(1, len(shop.purchased_upgrades)) * upgrade_row_height
        coach_top = body_rect.top
        player_top = coach_top + coach_height + 12
        upgrade_top = player_top + player_panel_height + 12
        total_content_height = upgrade_top - body_rect.top + upgrade_height
        self.interaction.depth_max_scroll = max(
            0, total_content_height - body_rect.height
        )
        self.interaction.depth_scroll = min(
            self.interaction.depth_scroll, self.interaction.depth_max_scroll
        )
        offset = body_rect.top - self.interaction.depth_scroll
        previous_clip = surface.get_clip()
        surface.set_clip(body_rect)
        for index, (profile, side) in enumerate(
            (
                (offense_coach, FootballCoachSide.OFFENSE),
                (defense_coach, FootballCoachSide.DEFENSE),
            )
        ):
            rect = pygame.Rect(
                body_rect.left + index * (coach_width + gap),
                offset,
                coach_width,
                coach_height,
            )
            draw_panel(surface, rect, self.theme, fill=self.theme.panel)
            name = profile.name if profile is not None else f"No {side.value} coach"
            draw_text(
                surface,
                _fit_text(
                    f"{side.value.upper()}  /  {name}",
                    self._label_font,
                    rect.width - 24,
                ),
                (rect.left + 12, rect.top + 9),
                self._label_font,
                self.theme.text,
            )
            modifiers = (
                "   ".join(
                    f"{_POSITION_LABELS[position]} {value:+.0%}"
                    for position, value in profile.position_modifiers.items()
                )
                if profile is not None
                else "No position modifiers."
            )
            draw_wrapped_text(
                surface,
                f"POSITION MODIFIERS  /  {modifiers}",
                pygame.Rect(rect.left + 12, rect.top + 34, rect.width - 24, 42),
                self._small_font,
                self.theme.secondary_accent,
                line_gap=2,
            )
            perk_text = (
                f"COACH PERK  /  {_coach_perk_summary(profile)}"
                if profile is not None
                else "COACH PERK  /  None"
            )
            draw_wrapped_text(
                surface,
                perk_text,
                pygame.Rect(rect.left + 12, rect.top + 78, rect.width - 24, 56),
                self._small_font,
                self.theme.muted,
                line_gap=2,
            )

        player_width = (content.width - gap) // 2
        groups = (
            (
                "OFFENSE",
                (
                    FootballPosition.QB,
                    FootballPosition.RB,
                    FootballPosition.WR,
                    FootballPosition.O_LINE,
                ),
            ),
            (
                "DEFENSE",
                (
                    FootballPosition.D_LINE,
                    FootballPosition.LINEBACKERS,
                    FootballPosition.CORNERBACKS,
                    FootballPosition.SAFETIES,
                ),
            ),
        )
        for column, (heading, positions) in enumerate(groups):
            rect = pygame.Rect(
                body_rect.left + column * (player_width + gap),
                offset + player_top - coach_top,
                player_width,
                player_panel_height,
            )
            draw_panel(surface, rect, self.theme, fill=self.theme.panel)
            draw_text(
                surface,
                heading,
                (rect.left + 12, rect.top + 8),
                self._label_font,
                self.theme.text,
            )
            row_top = rect.top + 31
            row_height = player_row_height
            for row, position in enumerate(positions):
                player = shop.roster.players[position]
                player_type = (
                    player_type_for_id(player.player_type_id)
                    if player.player_type_id is not None
                    else None
                )
                type_name = player_type.name if player_type is not None else "Basic"
                partnership = (
                    f"Conditional +10% with {_POSITION_LABELS[player_type.partner_position]}"
                    if player_type is not None
                    and player_type.partner_position is not None
                    else "No partnership"
                )
                perk = (
                    f"PLANNED / INACTIVE  /  {player_type.perk.name}: "
                    f"{player_type.perk.effect}"
                    if player_type is not None and player_type.perk is not None
                    else "PLANNED / INACTIVE  /  No player perk."
                )
                row_rect = pygame.Rect(
                    rect.left + 10,
                    row_top + row * row_height,
                    rect.width - 20,
                    row_height - 2,
                )
                if row % 2:
                    pygame.draw.rect(surface, self.theme.panel_alt, row_rect, border_radius=5)
                draw_text(
                    surface,
                    _fit_text(
                        f"{_POSITION_LABELS[position]}  /  {player.name}  /  {type_name}",
                        self._small_font,
                        row_rect.width - 12,
                    ),
                    (row_rect.left + 6, row_rect.top + 3),
                    self._small_font,
                    self.theme.text,
                )
                stats = (
                    f"POWER {player.power:.1f}  VOL {player.volatility:.2f}  "
                    f"STA {player.stamina:.2f}  /  {partnership}"
                )
                draw_text(
                    surface,
                    _fit_text(stats, self._small_font, row_rect.width - 12),
                    (row_rect.left + 6, row_rect.top + 19),
                    self._small_font,
                    self.theme.secondary_accent,
                )
                draw_wrapped_text(
                    surface,
                    perk,
                    pygame.Rect(
                        row_rect.left + 6,
                        row_rect.top + 35,
                        row_rect.width - 12,
                        row_rect.height - 38,
                    ),
                    self._small_font,
                    self.theme.muted,
                    line_gap=1,
                )

        upgrade_rect = pygame.Rect(
            body_rect.left,
            offset + upgrade_top - coach_top,
            body_rect.width,
            upgrade_height,
        )
        draw_panel(surface, upgrade_rect, self.theme, fill=self.theme.panel)
        draw_text(
            surface,
            "PURCHASED UPGRADE HISTORY  /  CURRENT STATS ABOVE INCLUDE THESE",
            (upgrade_rect.left + 12, upgrade_rect.top + 8),
            self._small_font,
            self.theme.text,
        )
        if shop.purchased_upgrades:
            for index, upgrade in enumerate(shop.purchased_upgrades):
                row_rect = pygame.Rect(
                    upgrade_rect.left + 10,
                    upgrade_rect.top + 30 + index * upgrade_row_height,
                    upgrade_rect.width - 20,
                    upgrade_row_height,
                )
                draw_wrapped_text(
                    surface,
                    f"{upgrade.name}  /  {_POSITION_LABELS[upgrade.position]} "
                    f"{upgrade.stat.value.upper()} +{upgrade.amount:g}: "
                    f"{upgrade.description}",
                    row_rect,
                    self._small_font,
                    self.theme.secondary_accent,
                    line_gap=1,
                )
        else:
            draw_text(
                surface,
                "No player upgrades purchased.",
                (upgrade_rect.left + 12, upgrade_rect.top + 30),
                self._small_font,
                self.theme.muted,
            )
        surface.set_clip(previous_clip)
        return [Button("BACK TO SHOP", self.leave, pygame.Rect(content.right - 210, content.bottom - 40, 210, 34), variant="primary")]

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
                        f"{definition.clock_seconds}s"
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

