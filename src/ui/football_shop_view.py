"""Pre-match shop: player, coach, and play/scheme offers in the navy-stadium style.

Every offer is one focusable card. Hover or focus lifts it; only its price button
buys it. Full rules live in the inspect panel (``football_inspect``).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

import pygame

from src.engine.football import FootballCoachUpgradeKind
from src.engine.football_coaches import coaches_for_assignment
from src.engine.football_controller import FootballGameControllerState
from src.engine.football_decks import FootballPlayDefinition, FootballSchemeDefinition
from src.engine.football_shop import (
    FootballShopCard,
    FootballShopSection,
    FootballShopSlotState,
    FootballShopState,
    FootballUpgradeDuration,
)
from src.engine.football_playoffs import game_label
from src.ui.coach_art import draw_coach_portrait
from src.ui.football_card_art import draw_card_art
from src.ui.football_card_faces import card_art_name, draw_play_card_face
from src.ui.football_coach_upgrade_details import (
    DEFENSE_KINDS as _DEFENSE_KINDS,
    OFFENSE_KINDS as _OFFENSE_KINDS,
    coach_upgrade_area,
    coach_upgrade_short_line,
)
from src.ui.football_display import _POSITION_LABELS
from src.ui.football_inspect import (
    InspectContent,
    InspectState,
    bonus_inspect,
    coach_upgrade_inspect,
    play_inspect,
    player_upgrade_effect,
    player_upgrade_inspect,
    removal_inspect,
    scheme_inspect,
)
from src.ui.football_ui_kit import (
    MATCH_DIM,
    MATCH_FOCUS,
    MATCH_GOLD,
    MATCH_GOOD,
    MATCH_INK,
    MATCH_MUTED,
    MATCH_PANEL,
    MATCH_PANEL_DEEP,
    MATCH_PANEL_EDGE_SOFT,
    MATCH_PANEL_HIGH,
    MATCH_TEXT,
    PaintedButton,
    asset_icon,
    blit_text,
    blit_wrapped,
    draw_alpha_veil,
    draw_focus_ring,
    draw_lock,
    draw_message_banner,
    draw_stat_value,
    fit_wrapped,
    kit_button,
    mix,
    plain_font,
    rarity_color,
    stadium_backdrop,
    team_accent,
)
from src.ui.text import fit_text
from src.ui.theme import Theme
from src.ui.widgets import Button

# Landing geometry on the 1280x720 logical surface (content starts at x=20, y=16).
HEADER_HEIGHT = 56
BODY_TOP = 84
BODY_BOTTOM = 640
FOOTER_TOP = 656
FOOTER_HEIGHT = 42
LEFT_WIDTH = 600
COLUMN_GAP = 16
PLAYER_PANEL_HEIGHT = 262
SECTION_GAP = 12
PANEL_HEADER = 36
LIFT = 5
ADDED_FLASH_MS = 1400

SECTION_TITLES = {
    FootballShopSection.PLAYER_UPGRADES: "PLAYER UPGRADES",
    FootballShopSection.COACH_UPGRADES: "COACH UPGRADES",
    FootballShopSection.PLAYS_SCHEMES: "PLAYS & SCHEMES",
}
SHORT_HINT = "UNSPENT AP EXPIRES AT KICKOFF"

_DURATION_ICONS = {
    FootballUpgradeDuration.TEMPORARY: "upgrade_temporary.png",
    FootballUpgradeDuration.PERMANENT: "upgrade_permanent.png",
}
def short_unlock_reason(slot: FootballShopSlotState, remaining_ap: int) -> str | None:
    """A few words for a locked slot; None when the cost button says enough."""
    reason = slot.disabled_reason
    if slot.can_unlock or reason is None:
        return None
    if reason.startswith("Available after game"):
        return reason.removeprefix("Available ").rstrip(".").upper()
    match = re.match(r"Unlock slot (\d+) first\.", reason)
    if match:
        return f"UNLOCK SLOT {match.group(1)} FIRST"
    if reason.startswith("Need ") and slot.unlock_cost is not None:
        return f"NEED {slot.unlock_cost - remaining_ap} MORE AP"
    return reason.rstrip(".").upper()


def card_price_label(slot: FootballShopSlotState) -> str:
    assert slot.card is not None
    return "PURCHASED" if slot.purchased else f"{slot.card.cost} AP"


@dataclass
class ShopCardButton(PaintedButton):
    """One shop offer or locked slot: focusable as a whole, bought via ``click_rect``."""

    section: FootballShopSection | None = None
    slot_number: int = 0
    card_id: str | None = None
    purchasable: bool = False
    inspect_key: tuple | None = None
    card_rect: pygame.Rect | None = None


class FootballShopView:
    def __init__(
        self, theme: Theme, small_font: pygame.font.Font, label_font: pygame.font.Font,
        move_next_day: Callable[[], None], open_depth_chart: Callable[[], None],
        open_playbook: Callable[[], None], finish: Callable[[], None],
        unlock: Callable[[FootballShopSection, int], None],
        purchase: Callable[[FootballShopSection, str, bool], None],
        clock: Callable[[], int] = pygame.time.get_ticks,
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
        self.clock = clock
        self.inspect = InspectState(lambda: self.clock())
        self._inspect_contents: dict[tuple, tuple[InspectContent, pygame.Rect]] = {}
        self._added: tuple[int, str, int] | None = None
        self._run_state: FootballGameControllerState | None = None
        self._shop: FootballShopState | None = None
        self._team_name = "Team"

    # -- input ---------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Esc hides a visible inspect panel; True when it did."""
        return self.inspect.handle_event(event)

    @property
    def inspect_open(self) -> bool:
        return self.inspect.overlay is not None

    def _buy(self, slot: FootballShopSlotState) -> None:
        card = slot.card
        assert card is not None
        if slot.section is FootballShopSection.PLAYS_SCHEMES and not card.is_removal:
            self._added = (slot.slot_number, card.card_id, self.clock())
        self.purchase(slot.section, card.card_id, card.is_removal)

    # -- drawing -------------------------------------------------------------------

    def draw(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        shop: FootballShopState | None,
        transition_message: str | None = None,
        run_state: FootballGameControllerState | None = None,
        team_name: str = "Team",
        *,
        hover_key: tuple | None = None,
        focus_key: tuple | None = None,
        error: bool = False,
    ) -> list[Button]:
        if shop is None:
            raise RuntimeError("The controller did not provide the active shop state.")
        self._run_state, self._shop, self._team_name = run_state, shop, team_name
        surface.blit(stadium_backdrop(surface.get_size()), (0, 0))
        self._draw_header(surface, content, shop, team_name, transition_message, error)

        left = pygame.Rect(content.left, BODY_TOP, LEFT_WIDTH, BODY_BOTTOM - BODY_TOP)
        right = pygame.Rect(left.right + COLUMN_GAP, BODY_TOP,
                            content.right - left.right - COLUMN_GAP, left.height)
        player_panel = pygame.Rect(left.left, left.top, left.width, PLAYER_PANEL_HEIGHT)
        coach_panel = pygame.Rect(left.left, player_panel.bottom + SECTION_GAP, left.width,
                                  left.bottom - player_panel.bottom - SECTION_GAP)
        buttons: list[Button] = []
        self._inspect_contents = {}
        for panel, section, columns, rows in (
            (player_panel, FootballShopSection.PLAYER_UPGRADES, 4, 1),
            (coach_panel, FootballShopSection.COACH_UPGRADES, 2, 1),
            (right, FootballShopSection.PLAYS_SCHEMES, 3, 2),
        ):
            self._draw_panel(surface, panel, SECTION_TITLES[section])
            grid = pygame.Rect(panel.left + 9, panel.top + PANEL_HEADER,
                               panel.width - 18, panel.height - PANEL_HEADER - 10)
            gap = 10
            width = (grid.width - gap * (columns - 1)) // columns
            height = (grid.height - gap * (rows - 1)) // rows
            for index, slot in enumerate(shop.section(section).slots):
                rect = pygame.Rect(grid.left + (index % columns) * (width + gap),
                                   grid.top + (index // columns) * (height + gap), width, height)
                buttons.append(self._slot_button(rect, slot, shop))

        buttons.extend(self._footer(surface, content, shop))

        self.inspect.prepare(self._inspect_contents, hover_key, focus_key)
        return buttons

    def draw_overlay(self, surface: pygame.Surface) -> None:
        """Paint the inspect panel above the cards (after buttons are drawn)."""
        self.inspect.paint(surface)

    def _draw_header(self, surface: pygame.Surface, content: pygame.Rect, shop: FootballShopState,
                     team_name: str, message: str | None, error: bool) -> None:
        title_font = plain_font(32)
        title = blit_text(surface, title_font, "SHOP", MATCH_TEXT, content,
                          topleft=(content.left, content.top))
        accent = team_accent(self.theme.primary)
        sub_y = content.top + 42
        swatch = pygame.Rect(content.left, sub_y + 1, 12, 12)
        pygame.draw.rect(surface, self.theme.primary, swatch, border_radius=3)
        pygame.draw.rect(surface, mix(accent, MATCH_TEXT, 0.4), swatch, 1, border_radius=3)
        sub_font = plain_font(14)
        tail = f"  ·  {game_label(shop.game_number, padded=False)}  ·  DAY {shop.day}"
        name_width = 380 - sub_font.size(tail)[0]
        name = fit_text(team_name.upper(), sub_font, name_width)
        name_rect = blit_text(surface, sub_font, name, MATCH_TEXT, content,
                              topleft=(swatch.right + 8, sub_y - 2))
        blit_text(surface, sub_font, tail, MATCH_MUTED, content, topleft=(name_rect.right, sub_y - 2))
        pygame.draw.rect(surface, accent, (title.right + 10, title.centery - 2, 34, 4), border_radius=2)

        number_font = plain_font(40)
        number = str(shop.remaining_ap)
        pill_font = plain_font(16)
        pill = pygame.Rect(0, 0, pill_font.size("AP")[0] + 18, 26)
        badge = pygame.Rect(0, content.top, number_font.size(number)[0] + pill.width + 40, 54)
        badge.right = content.right
        pygame.draw.rect(surface, MATCH_INK, badge.move(0, 4), border_radius=12)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, badge, border_radius=12)
        pygame.draw.rect(surface, MATCH_GOLD, badge, 2, border_radius=12)
        number_rect = blit_text(surface, number_font, number, MATCH_GOLD, badge,
                                midleft=(badge.left + 16, badge.centery))
        pill.midleft = (number_rect.right + 8, badge.centery + 2)
        pygame.draw.rect(surface, MATCH_GOLD, pill, border_radius=8)
        blit_text(surface, pill_font, "AP", MATCH_INK, pill, center=pill.center)
        right_edge = badge.left - 12
        if shop.future_shop_ap_bonus:
            chip_font = plain_font(12)
            text = f"+{shop.future_shop_ap_bonus} AP NEXT SHOP"
            chip = pygame.Rect(0, 0, chip_font.size(text)[0] + 18, 26)
            chip.midright = (right_edge, badge.centery)
            pygame.draw.rect(surface, MATCH_PANEL_DEEP, chip, border_radius=13)
            pygame.draw.rect(surface, MATCH_GOOD, chip, 2, border_radius=13)
            blit_text(surface, chip_font, text, MATCH_GOOD, chip, center=chip.center)
            right_edge = chip.left - 12
        if message:
            banner = pygame.Rect(content.left + 420, content.top + 2, right_edge - content.left - 420, 50)
            draw_message_banner(surface, banner, message, danger=error)

    def _draw_panel(self, surface: pygame.Surface, rect: pygame.Rect, title: str) -> None:
        pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=12)
        pygame.draw.rect(surface, MATCH_PANEL, rect, border_radius=12)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, rect, 2, border_radius=12)
        accent = team_accent(self.theme.primary)
        pygame.draw.rect(surface, accent, (rect.left + 12, rect.top + 11, 4, 16), border_radius=2)
        blit_text(surface, plain_font(17), title, MATCH_TEXT, rect, topleft=(rect.left + 22, rect.top + 8))

    def _footer(self, surface: pygame.Surface, content: pygame.Rect, shop: FootballShopState) -> list[Button]:
        top = FOOTER_TOP
        buttons = [
            kit_button("NEXT DAY · 1 AP", self.move_next_day, pygame.Rect(content.left, top, 176, FOOTER_HEIGHT),
                       enabled=shop.remaining_ap >= 1 and shop.pending_removal is None),
            kit_button("DEPTH CHART", self.open_depth_chart,
                       pygame.Rect(content.left + 186, top, 150, FOOTER_HEIGHT)),
            kit_button("PLAYBOOK", self.open_playbook,
                       pygame.Rect(content.left + 346, top, 150, FOOTER_HEIGHT)),
        ]
        finish_rect = pygame.Rect(content.right - 130 - 270, top, 270, FOOTER_HEIGHT)
        buttons.append(kit_button("FINISH SHOP / START MATCH", self.finish, finish_rect, variant="kit-primary"))
        hint_box = pygame.Rect(content.left + 506, top, finish_rect.left - content.left - 516, FOOTER_HEIGHT)
        hint_font = plain_font(12)
        blit_text(surface, hint_font, fit_text(SHORT_HINT, hint_font, hint_box.width), MATCH_MUTED, hint_box,
                  center=hint_box.center)
        return buttons

    # -- slots ---------------------------------------------------------------------

    def _slot_button(self, rect: pygame.Rect, slot: FootballShopSlotState,
                     shop: FootballShopState) -> ShopCardButton:
        key = (slot.section.value, slot.slot_number)
        if not slot.unlocked:
            price = self._price_rect(rect, slot.section)
            label = f"UNLOCK {slot.unlock_cost} AP" if slot.unlock_cost is not None else "LOCKED"
            return ShopCardButton(
                label,
                lambda section=slot.section, number=slot.slot_number: self.unlock(section, number),
                rect, enabled=slot.can_unlock, variant="shop-unlock", click_rect=price,
                painter=lambda surface, button, hovered, pressed, s=slot: self._paint_locked(
                    surface, button, s, shop, hovered, pressed),
                section=slot.section, slot_number=slot.slot_number, card_rect=rect,
            )
        card = slot.card
        if card is None:
            return ShopCardButton(
                "EMPTY", lambda: None, rect, enabled=False, variant="shop-empty",
                painter=lambda surface, button, hovered, pressed, s=slot: self._paint_empty(surface, button, s),
                section=slot.section, slot_number=slot.slot_number, card_rect=rect,
            )
        purchasable = (not slot.purchased and card.cost <= shop.remaining_ap
                       and slot.disabled_reason is None and shop.pending_removal is None)
        content_value = self._inspect_content(slot, shop)
        self._inspect_contents[key] = (content_value, rect)

        def action(s=slot, allowed=purchasable) -> None:
            if allowed:
                self._buy(s)

        painters = {
            FootballShopSection.PLAYER_UPGRADES: self._paint_player,
            FootballShopSection.COACH_UPGRADES: self._paint_coach,
            FootballShopSection.PLAYS_SCHEMES: self._paint_play,
        }
        return ShopCardButton(
            card_price_label(slot), action, rect, enabled=True, variant="shop-card",
            click_rect=self._price_rect(rect, slot.section),
            painter=lambda surface, button, hovered, pressed, s=slot, paint=painters[slot.section]: paint(
                surface, button, s, hovered, pressed),
            section=slot.section, slot_number=slot.slot_number, card_id=card.card_id,
            purchasable=purchasable, inspect_key=key, card_rect=rect,
        )

    @staticmethod
    def _price_rect(rect: pygame.Rect, section: FootballShopSection) -> pygame.Rect:
        if section is FootballShopSection.COACH_UPGRADES:
            return pygame.Rect(rect.left + 10, rect.bottom - 44, rect.width - 20, 34)
        return pygame.Rect(rect.left + 8, rect.bottom - 38, rect.width - 16, 30)

    def _inspect_content(self, slot: FootballShopSlotState, shop: FootballShopState) -> InspectContent:
        card = slot.card
        assert card is not None
        if card.upgrade is not None:
            return player_upgrade_inspect(card, shop, self._player_art_painter(card))
        if card.coach_upgrade_effect is not None:
            return coach_upgrade_inspect(card, lambda surface, rect, c=card: self._coach_art(surface, rect, c))
        art = self._card_art_name(card)
        painter = lambda surface, rect, name=art: draw_card_art(surface, name, rect)  # noqa: E731
        definition = card.football_card
        if card.is_removal:
            return removal_inspect(card, slot.disabled_reason, painter)
        if card.bonus_card is not None:
            return bonus_inspect(card.bonus_card, card.rarity, card.cost, painter)
        if isinstance(definition, FootballPlayDefinition):
            return play_inspect(definition, card.rarity, card.cost, painter)
        assert isinstance(definition, FootballSchemeDefinition)
        return scheme_inspect(definition, card.rarity, card.cost, painter)

    def _player_art_painter(self, card: FootballShopCard):
        run_state = self._run_state
        if card.upgrade is None or run_state is None:
            return None
        appearance = run_state.player_appearances.get(card.upgrade.position)
        if appearance is None:
            return None
        from src.ui.player_art import draw_draft_player
        return lambda surface, rect: draw_draft_player(surface, rect, appearance)

    # -- painters ------------------------------------------------------------------

    def _frame(self, surface: pygame.Surface, button: ShopCardButton, slot: FootballShopSlotState,
               hovered: bool, pressed: bool) -> tuple[pygame.Rect, bool]:
        """Lifted card rect and whether it is highlighted."""
        highlighted = hovered or (button.focused and self.inspect.keyboard)
        rect = button.rect.move(0, -LIFT if highlighted and not slot.purchased and not pressed else 0)
        if highlighted:
            draw_focus_ring(surface, rect, 9)
        return rect, highlighted

    def _paint_price(self, surface: pygame.Surface, rect: pygame.Rect, slot: FootballShopSlotState,
                     purchasable: bool, highlighted: bool, pressed: bool) -> None:
        card = slot.card
        assert card is not None
        label = card_price_label(slot)
        if pressed and purchasable:
            rect = rect.move(0, 2)
        if slot.purchased:
            fill, edge, ink = MATCH_PANEL, MATCH_PANEL_EDGE_SOFT, MATCH_MUTED
        elif purchasable:
            fill = MATCH_GOLD if highlighted else mix(MATCH_GOLD, MATCH_PANEL, 0.14)
            edge, ink = MATCH_GOLD, MATCH_INK
        else:
            fill, edge, ink = MATCH_PANEL_DEEP, MATCH_PANEL_EDGE_SOFT, MATCH_DIM
        pygame.draw.rect(surface, fill, rect, border_radius=7)
        pygame.draw.rect(surface, edge, rect, 2, border_radius=7)
        font = plain_font(16 if rect.height >= 32 else 15)
        blit_text(surface, font, label, ink, rect, center=rect.center)

    def _card_base(self, surface: pygame.Surface, rect: pygame.Rect, slot: FootballShopSlotState,
                   fill: pygame.Color | None = None) -> None:
        card = slot.card
        assert card is not None
        pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=9)
        pygame.draw.rect(surface, fill or MATCH_PANEL_HIGH, rect, border_radius=9)
        pygame.draw.rect(surface, rarity_color(card.rarity), rect, 2, border_radius=9)

    def _finish_card(self, surface: pygame.Surface, rect: pygame.Rect, slot: FootballShopSlotState,
                     button: ShopCardButton, highlighted: bool, pressed: bool) -> None:
        if slot.purchased:
            draw_alpha_veil(surface, rect, 110)
            pygame.draw.rect(surface, rarity_color(slot.card.rarity), rect, 2, border_radius=9)
        price = self._price_rect(rect, slot.section)
        self._paint_price(surface, price, slot, button.purchasable, highlighted, pressed)

    def _paint_player(self, surface: pygame.Surface, button: ShopCardButton, slot: FootballShopSlotState,
                      hovered: bool, pressed: bool) -> None:
        rect, highlighted = self._frame(surface, button, slot, hovered, pressed)
        self._card_base(surface, rect, slot)
        card = slot.card
        upgrade = card.upgrade
        assert upgrade is not None
        tile = pygame.Rect(rect.left + 8, rect.top + 10, rect.width - 16, 96)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, tile, border_radius=7)
        pygame.draw.rect(surface, team_accent(self.theme.primary),
                         (tile.left + 10, tile.bottom - 5, tile.width - 20, 3), border_radius=2)
        painter = self._player_art_painter(card)
        if painter is not None:
            painter(surface, tile.inflate(-8, -8))
        icon = asset_icon(_DURATION_ICONS[upgrade.duration], 20)
        badge = pygame.Rect(0, 0, icon.get_width() + 10, 26)
        badge.topright = (tile.right - 4, tile.top + 4)
        pygame.draw.rect(surface, MATCH_INK, badge, border_radius=8)
        surface.blit(icon, icon.get_rect(center=badge.center))
        name_box = pygame.Rect(rect.left + 6, tile.bottom + 6, rect.width - 12, 22)
        font, lines = fit_wrapped(_POSITION_LABELS[upgrade.position], name_box.width, (17, 16, 15, 14, 13), 1)
        blit_text(surface, font, lines[0], MATCH_TEXT, name_box, midtop=(name_box.centerx, name_box.top))
        cell = pygame.Rect(rect.left + 8, name_box.bottom + 4, rect.width - 16, 40)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, cell, border_radius=6)
        stat, value = player_upgrade_effect(upgrade)
        draw_stat_value(surface, stat, value, cell, size=22, center=cell.center)
        self._finish_card(surface, rect, slot, button, highlighted, pressed)

    def _paint_coach(self, surface: pygame.Surface, button: ShopCardButton, slot: FootballShopSlotState,
                     hovered: bool, pressed: bool) -> None:
        rect, highlighted = self._frame(surface, button, slot, hovered, pressed)
        card = slot.card
        effect = card.coach_upgrade_effect
        assert effect is not None
        bye = effect.kind is FootballCoachUpgradeKind.BYE_WEEK
        self._card_base(surface, rect, slot, mix(MATCH_PANEL_HIGH, MATCH_GOLD, 0.08) if bye else None)
        portrait = pygame.Rect(rect.left + 10, rect.top + 12, 104, 104)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, portrait, border_radius=8)
        self._coach_art(surface, portrait.inflate(-6, -4), card)
        text_box = pygame.Rect(portrait.right + 12, rect.top + 16, rect.right - portrait.right - 24, 100)
        area = coach_upgrade_area(effect.kind)
        area_font = plain_font(11)
        blit_text(surface, area_font, area, rarity_color(card.rarity), text_box, topleft=text_box.topleft)
        name_box = pygame.Rect(text_box.left, text_box.top + 18, text_box.width, text_box.height - 18)
        blit_wrapped(surface, card.name.upper(), name_box, (20, 18, 16, 15), MATCH_TEXT, max_lines=3,
                     align="left", line_step=0)
        cell = pygame.Rect(rect.left + 10, portrait.bottom + 10, rect.width - 20, 56)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, cell, border_radius=6)
        line = coach_upgrade_short_line(card)
        font, lines = fit_wrapped(line, cell.width - 16, (17, 16, 15, 14, 13), 2)
        total = len(lines) * font.get_height()
        y = cell.centery - total // 2
        for text in lines:
            blit_text(surface, font, text, MATCH_TEXT, cell, midtop=(cell.centerx, y))
            y += font.get_height()
        self._finish_card(surface, rect, slot, button, highlighted, pressed)

    @staticmethod
    def _card_art_name(card: FootballShopCard) -> str:
        return card_art_name(None if card.is_removal else (card.bonus_card or card.football_card))

    def _paint_play(self, surface: pygame.Surface, button: ShopCardButton, slot: FootballShopSlotState,
                    hovered: bool, pressed: bool) -> None:
        rect, highlighted = self._frame(surface, button, slot, hovered, pressed)
        card = slot.card
        definition = None if card.is_removal else (card.bonus_card or card.football_card)
        draw_play_card_face(surface, rect, definition, card.rarity, bottom_gap=44,
                            service_line="DECKS AT MINIMUM" if slot.disabled_reason else "PICK ANY COPY")
        self._finish_card(surface, rect, slot, button, highlighted, pressed)
        if self._added is not None:
            slot_number, old_card_id, since = self._added
            age = self.clock() - since
            if age > ADDED_FLASH_MS:
                self._added = None
            elif slot_number == slot.slot_number and old_card_id == card.card_id and slot.purchased:
                ribbon_font = plain_font(11)
                ribbon = pygame.Rect(0, 0, ribbon_font.size("ADDED TO PLAYBOOK")[0] + 16, 20)
                ribbon.midtop = (rect.centerx, rect.top - 9)
                pygame.draw.rect(surface, MATCH_INK, ribbon.inflate(2, 2), border_radius=6)
                pygame.draw.rect(surface, MATCH_GOOD, ribbon, border_radius=5)
                blit_text(surface, ribbon_font, "ADDED TO PLAYBOOK", MATCH_INK, ribbon.inflate(2, 2),
                          center=ribbon.center)

    def _paint_locked(self, surface: pygame.Surface, button: ShopCardButton, slot: FootballShopSlotState,
                      shop: FootballShopState, hovered: bool, pressed: bool) -> None:
        highlighted = button.enabled and (hovered or (button.focused and self.inspect.keyboard))
        rect = button.rect
        if highlighted:
            draw_focus_ring(surface, rect, 9)
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=9)
        edge = MATCH_FOCUS if highlighted else MATCH_PANEL_EDGE_SOFT
        _dashed(surface, rect, edge)
        price = self._price_rect(rect, slot.section)
        middle = pygame.Rect(rect.left, rect.top, rect.width, price.top - rect.top)
        lock_color = MATCH_MUTED if slot.can_unlock else MATCH_DIM
        draw_lock(surface, (middle.centerx, middle.centery - 14), 30, lock_color)
        caption = plain_font(12)
        blit_text(surface, caption, f"SLOT {slot.slot_number}", MATCH_MUTED, middle,
                  midtop=(middle.centerx, middle.centery + 14))
        reason = short_unlock_reason(slot, shop.remaining_ap)
        if reason:
            box = pygame.Rect(rect.left + 8, middle.centery + 30, rect.width - 16, 30)
            blit_wrapped(surface, reason, box, (11, 10), MATCH_DIM, max_lines=2)
        draw_price = price.move(0, 2) if pressed and button.enabled else price
        if button.enabled:
            fill = mix(MATCH_PANEL_HIGH, MATCH_GOLD, 0.2 if highlighted else 0.08)
            edge, ink = MATCH_GOLD, MATCH_GOLD
        else:
            fill, edge, ink = MATCH_PANEL_DEEP, MATCH_PANEL_EDGE_SOFT, MATCH_DIM
        pygame.draw.rect(surface, fill, draw_price, border_radius=7)
        pygame.draw.rect(surface, edge, draw_price, 2, border_radius=7)
        if slot.unlock_cost is None:
            blit_text(surface, plain_font(15), "LOCKED", ink, draw_price, center=draw_price.center)
            return
        font = plain_font(16 if draw_price.height >= 32 else 15)
        text = f"{slot.unlock_cost} AP"
        width = 16 + 6 + font.size(text)[0]
        left = draw_price.centerx - width // 2
        draw_lock(surface, (left + 8, draw_price.centery), 13, ink)
        blit_text(surface, font, text, ink, draw_price, midleft=(left + 22, draw_price.centery))

    def _paint_empty(self, surface: pygame.Surface, button: ShopCardButton, slot: FootballShopSlotState) -> None:
        rect = button.rect
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=9)
        _dashed(surface, rect, MATCH_PANEL_EDGE_SOFT)
        text = "SOLD OUT"
        blit_text(surface, plain_font(14), text, MATCH_MUTED, rect, center=(rect.centerx, rect.centery - 10))
        reason = (slot.disabled_reason or "").rstrip(".").upper()
        if reason:
            box = pygame.Rect(rect.left + 10, rect.centery + 4, rect.width - 20, 34)
            blit_wrapped(surface, reason, box, (11, 10), MATCH_DIM, max_lines=2)

    def _coach_art(self, surface: pygame.Surface, rect: pygame.Rect, card: FootballShopCard) -> None:
        effect = card.coach_upgrade_effect
        assert effect is not None
        shop = self._shop
        assert shop is not None
        coaches = coaches_for_assignment(shop.roster.coach_assignment)
        if effect.kind in _OFFENSE_KINDS:
            draw_coach_portrait(surface, rect, coaches[0].coach_id, self.theme.primary)
        elif effect.kind in _DEFENSE_KINDS:
            draw_coach_portrait(surface, rect, coaches[1].coach_id, self.theme.primary)
        else:
            # Team-wide upgrades show the whole staff.
            half = rect.width * 2 // 3
            draw_coach_portrait(surface, pygame.Rect(rect.left, rect.top + 6, half, rect.height - 6),
                                coaches[1].coach_id, self.theme.primary)
            draw_coach_portrait(surface, pygame.Rect(rect.right - half, rect.top, half, rect.height),
                                coaches[0].coach_id, self.theme.primary)


def _dashed(surface: pygame.Surface, rect: pygame.Rect, color: pygame.Color) -> None:
    for x in range(rect.left + 8, rect.right - 8, 12):
        pygame.draw.line(surface, color, (x, rect.top), (min(x + 6, rect.right - 8), rect.top), 2)
        pygame.draw.line(surface, color, (x, rect.bottom - 1), (min(x + 6, rect.right - 8), rect.bottom - 1), 2)
    for y in range(rect.top + 8, rect.bottom - 8, 12):
        pygame.draw.line(surface, color, (rect.left, y), (rect.left, min(y + 6, rect.bottom - 8)), 2)
        pygame.draw.line(surface, color, (rect.right - 1, y), (rect.right - 1, min(y + 6, rect.bottom - 8)), 2)

