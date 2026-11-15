"""Pre-match shop presentation and card purchase controls."""

from collections.abc import Callable

import pygame

from src.engine.football_decks import FootballPlayDefinition, FootballSchemeDefinition
from src.engine.football_shop import (
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
    FootballShopSlotState,
    FootballShopState,
)
from src.engine.football_simulator import calculate_standardized_play_estimate
from src.ui.football_coach_upgrade_details import coach_upgrade_detail_sections
from src.ui.football_display import _POSITION_LABELS
from src.ui.text import (
    draw_complete_wrapped_text,
    fit_text as _fit_text,
    wrap_text_lines,
)
from src.ui.theme import Theme
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text

_RARITY_COLORS = {
    FootballShopRarity.COMMON: pygame.Color("#a8b2a1"),
    FootballShopRarity.UNCOMMON: pygame.Color("#68c58a"),
    FootballShopRarity.RARE: pygame.Color("#df786d"),
    FootballShopRarity.VERY_RARE: pygame.Color("#c18be8"),
}


class FootballShopView:
    def __init__(
        self, theme: Theme, small_font: pygame.font.Font, label_font: pygame.font.Font,
        move_next_day: Callable[[], None], open_depth_chart: Callable[[], None],
        open_playbook: Callable[[], None], finish: Callable[[], None],
        unlock: Callable[[FootballShopSection, int], None],
        purchase: Callable[[FootballShopSection, str, bool], None],
        dismiss_details: Callable[[], None],
    ) -> None:
        self.theme = theme
        self._small_font = small_font
        self._label_font = label_font
        self.move_next_day = move_next_day
        self.open_depth_chart = open_depth_chart
        self.open_playbook = open_playbook
        self.finish = finish
        self.unlock = unlock
        self.purchase = purchase
        self.dismiss_details = dismiss_details
        self._coach_detail_rect: pygame.Rect | None = None
        self._coach_detail_sections: tuple[str, ...] = ()
        self._active_coach_card_id: str | None = None

    def draw(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        shop: FootballShopState | None,
        transition_message: str | None = None,
    ) -> list[Button]:
        if shop is None:
            raise RuntimeError("The controller did not provide the active shop state.")
        self._coach_detail_rect = None
        self._coach_detail_sections = ()
        if self._active_coach_card_id is not None:
            card = next(
                (
                    slot.card
                    for slot in shop.section(
                        FootballShopSection.COACH_UPGRADES
                    ).slots
                    if slot.card is not None
                    and slot.card.card_id == self._active_coach_card_id
                ),
                None,
            )
            if card is None:
                self._active_coach_card_id = None
            else:
                pygame.draw.rect(surface, self.theme.canvas, content)
                close_button = self._draw_coach_details(
                    surface, content, card
                )
                return [close_button]
        draw_text(
            surface,
            "THREE SHOPS  /  ONE SHARED AP BUDGET",
            (content.left + 2, content.top + 2),
            self._label_font,
            self.theme.text,
        )
        points_label = (
            f"{shop.remaining_ap} ACTION POINTS"
            + (
                f"  /  NEXT SHOP +{shop.future_shop_ap_bonus} AP"
                if shop.future_shop_ap_bonus
                else ""
            )
        )
        points_width = self._label_font.size(points_label)[0] + 24
        points_rect = pygame.Rect(
            content.right - points_width,
            content.top - 2,
            points_width,
            28,
        )
        pygame.draw.rect(surface, self.theme.panel_alt, points_rect, border_radius=7)
        draw_text(
            surface,
            points_label,
            (points_rect.left + 12, points_rect.top + 7),
            self._small_font,
            self.theme.secondary_accent,
        )
        draw_text(
            surface,
            transition_message or "Unspent AP expires when you finish the shop.",
            (content.left + 2, content.top + 27),
            self._small_font,
            self.theme.secondary_accent if transition_message else self.theme.muted,
        )
        gap = 10
        panel_top = content.top + 50
        panel_bottom = content.bottom - 56
        panel_width = (content.width - gap * 2) // 3
        panel_height = max(1, panel_bottom - panel_top)
        buttons: list[Button] = []
        for section_index, section_id in enumerate(FootballShopSection):
            section = shop.section(section_id)
            panel = pygame.Rect(
                content.left + section_index * (panel_width + gap),
                panel_top,
                panel_width,
                panel_height,
            )
            draw_panel(surface, panel, self.theme, fill=self.theme.panel)
            draw_text(
                surface,
                section.title,
                (panel.left + 12, panel.top + 11),
                self._label_font,
                self.theme.text,
            )
            if not section.catalog_available:
                status = (
                    "No play/scheme cards yet."
                    if section_id is FootballShopSection.PLAYS_SCHEMES
                    else "No coach upgrades yet."
                    if section_id is FootballShopSection.COACH_UPGRADES
                    else "No eligible player upgrades."
                )
                draw_text(
                    surface,
                    status,
                    (panel.left + 12, panel.top + 31),
                    self._small_font,
                    self.theme.muted,
                )
            row_top = panel.top + 54
            row_bottom = panel.bottom - 10
            row_height = max(1, (row_bottom - row_top) // len(section.slots))
            for slot_index, slot in enumerate(section.slots):
                row = pygame.Rect(
                    panel.left + 8,
                    row_top + slot_index * row_height,
                    panel.width - 16,
                    max(1, row_height - 5),
                )
                self.draw_slot(
                    surface,
                    row,
                    slot,
                    buttons,
                    shop,
                )

        footer_top = content.bottom - 44
        reroll_rect = pygame.Rect(
            content.left,
            footer_top,
            220,
            36,
        )
        buttons.append(
            Button(
                "MOVE TO NEXT DAY  /  1 AP",
                self.move_next_day,
                reroll_rect,
                enabled=shop.remaining_ap >= 1,
                variant="quiet",
            )
        )
        review_width = 142
        review_gap = 8
        review_left = content.left + 230
        buttons.append(
            Button(
                "DEPTH CHART",
                self.open_depth_chart,
                pygame.Rect(review_left, footer_top, review_width, 36),
                variant="quiet",
            )
        )
        buttons.append(
            Button(
                "PLAYBOOK",
                self.open_playbook,
                pygame.Rect(
                    review_left + review_width + review_gap,
                    footer_top,
                    review_width,
                    36,
                ),
                variant="quiet",
            )
        )
        finish_rect = pygame.Rect(
            content.right - 260,
            footer_top,
            260,
            36,
        )
        buttons.append(
            Button(
                "FINISH SHOP / START MATCH",
                self.finish,
                finish_rect,
                variant="primary",
            )
        )
        return buttons

    def draw_slot(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        slot: FootballShopSlotState,
        buttons: list[Button],
        shop: FootballShopState,
    ) -> None:
        remaining_ap = shop.remaining_ap
        card = slot.card
        purchased = slot.purchased
        fill = self.theme.panel_alt if purchased else self.theme.panel
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        pygame.draw.rect(surface, self.theme.border_soft, rect, width=1, border_radius=6)
        text_left = rect.left + 8
        is_coach_upgrade = (
            card is not None and card.coach_upgrade_effect is not None
        )
        button_width = 62 if is_coach_upgrade else min(94, max(68, rect.width // 4))
        button_rect = pygame.Rect(
            rect.right - button_width - 5,
            rect.centery - 14,
            button_width,
            28,
        )
        detail_rect = pygame.Rect(
            button_rect.left - 78,
            button_rect.top,
            72,
            button_rect.height,
        )
        text_width = max(1, button_rect.left - text_left - 8)
        if is_coach_upgrade:
            text_width = max(1, detail_rect.left - text_left - 8)

        if not slot.unlocked:
            cost = slot.unlock_cost
            draw_text(
                surface,
                f"SLOT {slot.slot_number}  /  LOCKED",
                (text_left, rect.top + 5),
                self._small_font,
                self.theme.text,
            )
            if slot.disabled_reason:
                draw_text(
                    surface,
                    _fit_text(slot.disabled_reason, self._small_font, text_width),
                    (text_left, rect.top + 25),
                    self._small_font,
                    self.theme.muted,
                )
            buttons.append(
                Button(
                    f"UNLOCK {cost} AP" if cost is not None else "LOCKED",
                    lambda section=slot.section, number=slot.slot_number: self.unlock(section, number),
                    button_rect,
                    enabled=slot.can_unlock,
                    variant="quiet",
                )
            )
            return

        if card is None:
            draw_text(
                surface,
                f"SLOT {slot.slot_number}  /  EMPTY",
                (text_left, rect.top + 5),
                self._small_font,
                self.theme.text,
            )
            reason = slot.disabled_reason or "No eligible cards."
            draw_text(
                surface,
                _fit_text(reason, self._small_font, text_width),
                (text_left, rect.top + 25),
                self._small_font,
                self.theme.muted,
            )
            return

        rarity_label = card.rarity.value.replace("_", " ").upper()
        football_card = card.football_card
        compact = rect.height < 75
        tiny = rect.height < 50
        neutral_yards = (
            calculate_standardized_play_estimate(
                football_card.action
            ).expected_yards
            if isinstance(football_card, FootballPlayDefinition)
            else None
        )
        card_label = card.name
        if isinstance(football_card, FootballPlayDefinition):
            if tiny:
                card_label = (
                    f"{card.name} / {rarity_label} {card.cost} AP"
                )
            elif compact:
                card_label = (
                    f"{card.name} / {football_card.family.label.upper()}"
                )
        elif isinstance(football_card, FootballSchemeDefinition):
            if tiny:
                card_label = (
                    f"{card.name} / {rarity_label} {card.cost} AP"
                )
            elif compact:
                card_label = f"{card.name} / {football_card.family.label.upper()}"
        draw_text(
            surface,
            _fit_text(card_label, self._small_font, text_width),
            (text_left, rect.top + (3 if compact else 4)),
            self._small_font,
            self.theme.text,
        )
        if not tiny:
            draw_text(
                surface,
                _fit_text(
                    f"{rarity_label}  /  {card.cost} AP",
                    self._small_font,
                    text_width,
                ),
                (text_left, rect.top + (17 if compact else 23)),
                self._small_font,
                _RARITY_COLORS[card.rarity],
            )
        if purchased:
            reason = "PURCHASED"
        elif card.cost > remaining_ap:
            reason = f"NEED {card.cost - remaining_ap} MORE AP"
        elif slot.disabled_reason:
            reason = slot.disabled_reason
        elif card.upgrade is not None:
            reason = f"{card.upgrade.stat.value.upper()}  /  {_POSITION_LABELS[card.upgrade.position]}"
        elif isinstance(football_card, FootballPlayDefinition):
            contributors = ", ".join(
                _POSITION_LABELS[position] for position in football_card.contributors
            )
            if compact and neutral_yards is not None:
                reason = (
                    f"{contributors.replace(', ', '/')} / "
                    f"NEUTRAL ~{neutral_yards:.1f} / "
                    f"BASE {football_card.clock_seconds}s"
                    if not tiny
                    else f"{football_card.family.label.upper()} / "
                    f"NEUTRAL ~{neutral_yards:.1f} / "
                    f"BASE {football_card.clock_seconds}s"
                )
            else:
                reason = f"{football_card.family.label.upper()} / {contributors}"
        elif isinstance(football_card, FootballSchemeDefinition):
            contributors = ", ".join(
                _POSITION_LABELS[position] for position in football_card.contributors
            )
            reason = (
                f"{contributors.replace(', ', '/')} / COUNTERS: "
                f"{football_card.family.label.upper()}"
                if compact and not tiny
                else f"{football_card.family.label.upper()} / COUNTERS: "
                f"{football_card.family.label.upper()}"
                if tiny
                else f"{football_card.family.label.upper()} / {contributors}"
            )
        else:
            reason = _fit_text(card.description, self._small_font, text_width)
        if rect.height >= (34 if tiny else 42 if compact else 58):
            reason_top = rect.top + (18 if tiny else 30 if compact else 41)
            if is_coach_upgrade:
                status = (
                    "PURCHASED"
                    if purchased
                    else slot.disabled_reason
                    or (
                        f"NEED {card.cost - remaining_ap} MORE AP"
                        if card.cost > remaining_ap
                        else "READY TO BUY"
                    )
                )
                draw_text(
                    surface,
                    _fit_text(status, self._small_font, text_width),
                    (text_left, reason_top),
                    self._small_font,
                    self.theme.muted if purchased else self.theme.secondary_accent,
                )
                draw_text(
                    surface,
                    "FOCUS DETAILS",
                    (text_left, reason_top + 17),
                    self._small_font,
                    self.theme.muted if purchased else self.theme.text,
                )
            else:
                draw_text(
                    surface,
                    _fit_text(reason, self._small_font, text_width),
                    (text_left, reason_top),
                    self._small_font,
                    self.theme.secondary_accent if not purchased else self.theme.muted,
                )
        if (
            rect.height >= 75
            and isinstance(football_card, FootballPlayDefinition)
            and neutral_yards is not None
        ):
            draw_text(
                surface,
                _fit_text(
                    f"NEUTRAL ~{neutral_yards:.1f} YDS / "
                    f"BASE {football_card.clock_seconds}s",
                    self._small_font,
                    text_width,
                ),
                (text_left, rect.top + 58),
                self._small_font,
                self.theme.muted,
            )
            if rect.height >= 92:
                draw_text(
                    surface,
                    _fit_text(
                        football_card.description,
                        self._small_font,
                        text_width,
                    ),
                    (text_left, rect.top + 75),
                    self._small_font,
                    self.theme.muted,
                )
        elif rect.height >= 75 and isinstance(football_card, FootballSchemeDefinition):
            draw_text(
                surface,
                _fit_text(
                    f"COUNTERS: {football_card.family.label.upper()}",
                    self._small_font,
                    text_width,
                ),
                (text_left, rect.top + 58),
                self._small_font,
                self.theme.muted,
            )
            if rect.height >= 92:
                draw_text(
                    surface,
                    _fit_text(
                        football_card.description,
                        self._small_font,
                        text_width,
                    ),
                    (text_left, rect.top + 75),
                    self._small_font,
                    self.theme.muted,
                )
        button_label = (
            "PURCHASED"
            if purchased
            else f"NEED {card.cost - remaining_ap} AP"
            if card.cost > remaining_ap
            else "CHOOSE IN PLAYBOOK"
            if card.is_removal and shop.pending_removal is card
            else "SELECT CARD"
            if card.is_removal and not slot.disabled_reason
            else "UNAVAILABLE"
            if slot.disabled_reason
            else "BUY"
        )

        if is_coach_upgrade:
            buttons.append(
                Button(
                    "DETAILS",
                    lambda card_id=card.card_id: self.open_coach_details(card_id),
                    detail_rect,
                    enabled=True,
                    variant="quiet",
                )
            )
        buttons.append(
            Button(
                button_label,
                lambda section=slot.section, card_id=card.card_id,
                is_removal=card.is_removal: self.purchase(section, card_id, is_removal),
                button_rect,
                enabled=(
                    not purchased
                    and card.cost <= remaining_ap
                    and slot.disabled_reason is None
                    and shop.pending_removal is None
                ),
                variant="primary" if not purchased else "quiet",
            )
        )

    @property
    def coach_details_open(self) -> bool:
        return self._active_coach_card_id is not None

    @property
    def coach_details_rect(self) -> pygame.Rect | None:
        return self._coach_detail_rect

    def open_coach_details(self, card_id: str) -> None:
        self._active_coach_card_id = card_id

    def close_coach_details(self) -> None:
        self._active_coach_card_id = None
        self._coach_detail_rect = None
        self._coach_detail_sections = ()

    def _draw_coach_details(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        card: FootballShopCard,
    ) -> Button:
        sections = coach_upgrade_detail_sections(card)
        panel_width = min(content.width - 24, 980)
        inner_width = panel_width - 24
        title_lines = wrap_text_lines(sections[0], self._label_font, inner_width)
        body_lines = tuple(
            line
            for section in sections[1:]
            for line in wrap_text_lines(section, self._small_font, inner_width)
        )
        title_height = len(title_lines) * (self._label_font.get_height() + 2)
        body_height = len(body_lines) * (self._small_font.get_height() + 2)
        panel_height = title_height + body_height + 68
        panel_rect = pygame.Rect(
            content.centerx - panel_width // 2,
            content.centery - panel_height // 2,
            panel_width,
            panel_height,
        )
        panel_rect.clamp_ip(content)
        self._coach_detail_rect = panel_rect
        self._coach_detail_sections = sections
        draw_panel(surface, panel_rect, self.theme, fill=self.theme.panel_alt)
        y = panel_rect.top + 10
        draw_complete_wrapped_text(
            surface,
            sections[0],
            pygame.Rect(panel_rect.left + 12, y, inner_width, title_height),
            self._label_font,
            self.theme.text,
            line_gap=2,
        )
        y += title_height + 4
        draw_complete_wrapped_text(
            surface,
            "\n".join(sections[1:]),
            pygame.Rect(
                panel_rect.left + 12,
                y,
                inner_width,
                body_height,
            ),
            self._small_font,
            self.theme.text,
            line_gap=2,
        )
        close_rect = pygame.Rect(
            panel_rect.right - 152,
            panel_rect.bottom - 38,
            140,
            28,
        )
        return Button(
            "CLOSE DETAILS",
            self.dismiss_details,
            close_rect,
            variant="primary",
        )
