"""Pre-match shop presentation and card purchase controls."""

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import pygame

from src.engine.football import FootballCoachUpgradeKind, FootballPosition
from src.engine.football_coaches import coaches_for_assignment
from src.engine.football_controller import FootballGameControllerState
from src.engine.football_decks import FootballPlayDefinition, FootballSchemeDefinition
from src.engine.football_shop import (
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
    FootballShopSlotState,
    FootballShopState,
    FootballUpgradeDuration,
    FootballUpgradeStat,
)
from src.engine.football_simulator import calculate_standardized_play_estimate
from src.ui.football_coach_upgrade_details import coach_upgrade_detail_sections
from src.ui.football_card_art import (
    REMOVE_ONE_CARD_ART,
    bonus_card_art,
    draw_card_art,
    play_card_art,
    scheme_card_art,
)
from src.ui.coach_art import draw_coach_portrait
from src.ui.coach_fonts import staff_font
from src.ui.football_display import _POSITION_LABELS
from src.ui.player_art import draw_draft_player
from src.ui.text import (
    draw_complete_wrapped_text,
    fit_text as _fit_text,
    wrap_text_lines,
)
from src.ui.theme import Theme, readable_ink
from src.ui.widgets import Button, draw_panel, draw_text, draw_wrapped_text

_RARITY_COLORS = {
    FootballShopRarity.COMMON: pygame.Color("#a8b2a1"),
    FootballShopRarity.UNCOMMON: pygame.Color("#68c58a"),
    FootballShopRarity.RARE: pygame.Color("#df786d"),
    FootballShopRarity.VERY_RARE: pygame.Color("#c18be8"),
}

_INSET_FILL = pygame.Color("#34485b")
_INSET_EDGE = pygame.Color("#62798c")
_NEUTRAL_SLOT_EDGE = pygame.Color("#507397")
_RARITY_OUTLINE_COLORS = {
    FootballShopRarity.COMMON: pygame.Color("#abb6c2"),
    FootballShopRarity.UNCOMMON: pygame.Color("#68c58a"),
    FootballShopRarity.RARE: pygame.Color("#65b5ff"),
    FootballShopRarity.VERY_RARE: pygame.Color("#c18be8"),
}
_COMPACT_POSITION_LABELS = {
    FootballPosition.QB: "QB",
    FootballPosition.RB: "RB",
    FootballPosition.WR: "WR",
    FootballPosition.O_LINE: "OL",
    FootballPosition.D_LINE: "DL",
    FootballPosition.LINEBACKERS: "LB",
    FootballPosition.CORNERBACKS: "CB",
    FootballPosition.SAFETIES: "S",
}
_DURATION_ICONS = {
    FootballUpgradeDuration.TEMPORARY: "upgrade_temporary.png",
    FootballUpgradeDuration.PERMANENT: "upgrade_permanent.png",
}


@lru_cache(maxsize=2)
def _duration_icon(duration: FootballUpgradeDuration) -> pygame.Surface:
    image = pygame.image.load(Path(__file__).parent / "assets" / _DURATION_ICONS[duration])
    height = staff_font(14).get_height()
    width = max(1, round(image.get_width() * height / image.get_height()))
    return pygame.transform.scale(image, (width, height))


class _ShopCardButton(Button):
    def draw(
        self, surface: pygame.Surface, font: pygame.font.Font, theme: Theme, *,
        hovered: bool = False, pressed: bool = False,
    ) -> None:
        super().draw(surface, font, theme, hovered=hovered, pressed=pressed)
        if self.enabled and (self.focused or hovered):
            rect = self.rect.move(0, 2) if pressed else self.rect
            pygame.draw.rect(surface, "#101820", rect.inflate(-2, -2), 1, border_radius=7)
            pygame.draw.rect(surface, "#ffffff", rect.inflate(-4, -4), 1, border_radius=6)


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
        run_state: FootballGameControllerState | None = None,
        team_name: str = "Team",
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
        title_font = staff_font(26, semibold=True)
        draw_text(surface, "COACHING SHOP", (content.left, content.top),
                  title_font, pygame.Color("#eef5ff"))
        draw_text(surface, "THREE SHOPS  /  ONE SHARED AP BUDGET",
                  (content.left, content.top + 32), self._small_font, pygame.Color("#c1d0df"))
        points_label = f"{shop.remaining_ap} ACTION POINTS"
        if shop.future_shop_ap_bonus:
            points_label += f"  /  NEXT SHOP +{shop.future_shop_ap_bonus} AP"
        points_font = staff_font(19, semibold=True)
        badge_width = points_font.size(points_label)[0] + 30
        badge = pygame.Rect(content.right - badge_width, content.top, badge_width, 44)
        pygame.draw.rect(surface, "#102e4c", badge, border_radius=8)
        pygame.draw.rect(surface, "#507397", badge, 1, border_radius=8)
        draw_text(surface, points_label, (badge.left + 15, badge.top + 10),
                  points_font, pygame.Color("#eef5ff"))
        day = f"GAME {shop.game_number} / SHOP DAY {shop.day}"
        draw_text(surface, day, (badge.left - self._label_font.size(day)[0] - 18, content.top + 14),
                  self._label_font, pygame.Color("#c1d0df"))
        gap = 12
        top = content.top + 56
        bottom = content.bottom - 74
        left_width = (content.width - gap) // 2
        left = pygame.Rect(content.left, top, left_width, bottom - top)
        right = pygame.Rect(left.right + gap, top, content.right - left.right - gap, left.height)
        player_panel = pygame.Rect(left.left, left.top, left.width, 226)
        coach_panel = pygame.Rect(left.left, player_panel.bottom + gap,
                                  left.width, left.bottom - player_panel.bottom - gap)
        buttons: list[Button] = []
        for panel, section_id in ((player_panel, FootballShopSection.PLAYER_UPGRADES),
                                  (coach_panel, FootballShopSection.COACH_UPGRADES),
                                  (right, FootballShopSection.PLAYS_SCHEMES)):
            self._panel(surface, panel, shop.section(section_id).title)
            slots = shop.section(section_id).slots
            columns = 4 if section_id is FootballShopSection.PLAYER_UPGRADES else 2
            rows = 3 if section_id is FootballShopSection.PLAYS_SCHEMES else 1
            inner = pygame.Rect(panel.left + 8, panel.top + 35, panel.width - 16, panel.height - 43)
            card_gap = 6
            width = (inner.width - card_gap * (columns - 1)) // columns
            height = (inner.height - card_gap * (rows - 1)) // rows
            for index, slot in enumerate(slots):
                rect = pygame.Rect(inner.left + (index % columns) * (width + card_gap),
                                   inner.top + (index // columns) * (height + card_gap),
                                   width, height)
                self._landing_slot(surface, rect, slot, buttons, shop, run_state, team_name)

        message = transition_message or "Unspent AP expires when you finish the shop."
        draw_text(surface, message, (content.left, content.bottom - 67),
                  self._small_font, pygame.Color("#c1d0df"))
        footer_top = content.bottom - 44
        reroll_rect = pygame.Rect(content.left, footer_top, 205, 36)
        buttons.append(
            Button(
                "MOVE TO NEXT DAY  /  1 AP",
                self.move_next_day,
                reroll_rect,
                enabled=shop.remaining_ap >= 1,
                variant="quiet",
            )
        )
        review_width = 132
        review_gap = 8
        review_left = content.left + 213
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
            content.right - 390,
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

    def _panel(self, surface: pygame.Surface, rect: pygame.Rect, title: str) -> None:
        pygame.draw.rect(surface, "#0e2b47", rect, border_radius=8)
        pygame.draw.rect(surface, "#507397", rect, 1, border_radius=8)
        pygame.draw.rect(surface, self.theme.primary, (rect.left + 2, rect.top + 7, 3, 21), border_radius=1)
        draw_text(surface, title, (rect.left + 12, rect.top + 8),
                  staff_font(19, semibold=True), pygame.Color("#eef5ff"))
        if title == "PLAYS / SCHEMES":
            note = "YARDAGE: STANDARDIZED NEUTRAL ESTIMATE"
            font = staff_font(13, semibold=True)
            draw_text(surface, note, (rect.right - font.size(note)[0] - 12, rect.top + 11),
                      font, pygame.Color("#c1d0df"))

    @staticmethod
    def _inset(surface: pygame.Surface, rect: pygame.Rect) -> None:
        pygame.draw.rect(surface, _INSET_FILL, rect, border_radius=5)
        pygame.draw.rect(surface, _INSET_EDGE, rect, 1, border_radius=5)

    def _landing_slot(
        self, surface: pygame.Surface, rect: pygame.Rect, slot: FootballShopSlotState,
        buttons: list[Button], shop: FootballShopState,
        run_state: FootballGameControllerState | None, team_name: str,
    ) -> None:
        pygame.draw.rect(surface, "#10263d" if not slot.purchased else "#263c4e", rect, border_radius=6)
        edge = (
            _RARITY_OUTLINE_COLORS.get(slot.card.rarity, _NEUTRAL_SLOT_EDGE)
            if slot.unlocked and slot.card is not None
            else _NEUTRAL_SLOT_EDGE
        )
        pygame.draw.rect(surface, edge, rect, 2 if slot.unlocked and slot.card is not None else 1,
                         border_radius=6)
        small = staff_font(14)
        bold = staff_font(15, semibold=True)
        text = pygame.Color("#eef5ff")
        muted = pygame.Color("#c1d0df")
        button_rect = pygame.Rect(rect.left + 7, rect.bottom - 34, rect.width - 14, 27)
        if not slot.unlocked:
            draw_text(surface, f"SLOT {slot.slot_number} / LOCKED", (rect.left + 7, rect.top + 8), small, text)
            reason = slot.disabled_reason or "Unlock this slot."
            self._wrapped(surface, reason, pygame.Rect(rect.left + 7, rect.top + 29,
                          rect.width - 14, rect.height - 68), small, muted)
            buttons.append(_ShopCardButton(
                f"UNLOCK {slot.unlock_cost} AP" if slot.unlock_cost is not None else "LOCKED",
                lambda section=slot.section, number=slot.slot_number: self.unlock(section, number),
                button_rect, enabled=slot.can_unlock, variant="quiet"))
            return
        card = slot.card
        if card is None:
            draw_text(surface, f"SLOT {slot.slot_number} / EMPTY", (rect.left + 7, rect.top + 8), small, muted)
            self._wrapped(surface, slot.disabled_reason or "No eligible cards.",
                          pygame.Rect(rect.left + 7, rect.top + 29, rect.width - 14, rect.height - 36),
                          small, muted)
            return

        if slot.section is FootballShopSection.PLAYER_UPGRADES:
            art = pygame.Rect(rect.left + 8, rect.top + 4, rect.width - 16, 40)
            pygame.draw.rect(surface, "#1c3e5b", art, border_radius=5)
            if card.upgrade is not None and run_state is not None:
                appearance = run_state.player_appearances.get(card.upgrade.position)
                if appearance is not None:
                    draw_draft_player(surface, art, appearance)
            if card.upgrade is not None:
                label = _POSITION_LABELS[card.upgrade.position]
                upgrade = card.upgrade
                sign = "-" if upgrade.stat is FootballUpgradeStat.VOLATILITY else "+"
                amount = (f"{upgrade.amount:g}" if upgrade.stat is FootballUpgradeStat.POWER
                          else f"{upgrade.amount * 100:g}%")
                effect = f"{upgrade.stat.value.upper()} {sign}{amount}"
                duration = upgrade.duration.value.upper()
            else:
                label, effect = card.name, card.description
                duration = ""
            self._wrapped(surface, label, pygame.Rect(rect.left + 7, rect.top + 45,
                          rect.width - 14, 20), bold, text)
            duration_x = rect.left + 7
            if card.upgrade is not None:
                icon = _duration_icon(card.upgrade.duration)
                surface.blit(icon, (duration_x, rect.top + 66))
                duration_x += icon.get_width() + 4
            self._wrapped(surface, duration, pygame.Rect(duration_x, rect.top + 66,
                          rect.right - 7 - duration_x, small.get_height()), small, muted)
            info = pygame.Rect(rect.left + 7, rect.top + 87, rect.width - 14, 38)
            self._inset(surface, info)
            detail_font = staff_font(14, semibold=True)
            # Icons add width; step the font down rather than clip the effect.
            for detail_size in (13, 12):
                if detail_font.size(effect)[0] <= info.width - 8:
                    break
                detail_font = staff_font(detail_size, semibold=True)
            self._wrapped(surface, effect, pygame.Rect(info.left + 4,
                          info.centery - detail_font.get_height() // 2,
                          info.width - 8, detail_font.get_height()), detail_font, text)
            draw_text(surface, f"{card.rarity.value.replace('_', ' ').upper()} / {card.cost} AP",
                      (rect.left + 7, rect.top + 128), small, muted)
        elif slot.section is FootballShopSection.COACH_UPGRADES:
            art = pygame.Rect(rect.left + 7, rect.top + 7, 48, 48)
            self._coach_art(surface, art, card, shop, team_name)
            title_rect = pygame.Rect(art.right + 6, rect.top + 7, rect.right - art.right - 13, 36)
            self._wrapped(surface, card.name, title_rect, bold, text)
            draw_text(surface, f"{card.rarity.value.replace('_', ' ').upper()} / {card.cost} AP",
                      (art.right + 6, rect.top + 42), small, muted)
            effect = card.coach_upgrade_effect
            duration = "One-time / unique." if effect and effect.kind is FootballCoachUpgradeKind.BYE_WEEK else "Run-long / unique."
            body = f"{card.description} {duration}"
            info = pygame.Rect(rect.left + 7, rect.top + 60, rect.width - 14, rect.height - 101)
            self._inset(surface, info)
            body_rect = info.inflate(-8, -4)
            body_font = small
            if len(wrap_text_lines(body, body_font, body_rect.width)) * body_font.get_height() > body_rect.height:
                body_font = staff_font(13)
            self._wrapped(surface, body, body_rect, body_font, text)
            details_rect = pygame.Rect(rect.left + 7, rect.bottom - 34, 80, 27)
            button_rect.left = details_rect.right + 6
            button_rect.width = rect.right - 7 - button_rect.left
            buttons.append(_ShopCardButton("DETAILS", lambda card_id=card.card_id: self.open_coach_details(card_id),
                                  details_rect, variant="quiet"))
        else:
            art = pygame.Rect(rect.left + 7, 0, 70, 70)
            art.centery = rect.centery
            football_card = card.football_card
            if card.is_removal:
                art_name = REMOVE_ONE_CARD_ART
            elif card.bonus_card is not None:
                art_name = bonus_card_art(card.bonus_card.action)
            elif isinstance(football_card, FootballPlayDefinition):
                art_name = play_card_art(football_card.family)
            elif isinstance(football_card, FootballSchemeDefinition):
                art_name = scheme_card_art(football_card.family)
            else:
                raise ValueError(f"No artwork is mapped for shop card: {card.card_id}")
            draw_card_art(surface, art_name, art)
            x = art.right + 7
            self._wrapped(surface, "Remove One Card" if card.is_removal else card.name,
                pygame.Rect(x, rect.top + 5, rect.right - x - 6, 36), bold, text)
            if isinstance(football_card, (FootballPlayDefinition, FootballSchemeDefinition)):
                contributors = " / ".join(_COMPACT_POSITION_LABELS[p] for p in football_card.contributors)
                lines = [f"POSITIONS: {contributors}",
                         f"PLAY TYPE: {football_card.family.label.upper()}"]
                if isinstance(football_card, FootballPlayDefinition):
                    yards = calculate_standardized_play_estimate(football_card.action).expected_yards
                    lines += [f"EXPECTED YARDAGE: ~{yards:.1f} YDS",
                              f"TIME: {football_card.clock_seconds}s"]
                else:
                    lines += [f"COUNTERS: {football_card.family.label.upper()}"]
            else:
                lines = ["CARD REMOVAL" if card.is_removal else card.description]
                if slot.disabled_reason:
                    lines.append(slot.disabled_reason)
            info = pygame.Rect(x, rect.top + 39, rect.right - x - 6, rect.height - 77)
            self._inset(surface, info)
            info_rect = info.inflate(-8, -8)
            if isinstance(football_card, (FootballPlayDefinition, FootballSchemeDefinition)):
                attribute_font = staff_font(13)
                if len(lines) * attribute_font.get_height() > info_rect.height:
                    raise ValueError(f"Shop attributes do not fit: {card.name}")
                for index, line in enumerate(lines):
                    if attribute_font.size(line)[0] > info_rect.width:
                        raise ValueError(f"Shop attribute does not fit: {line}")
                    draw_text(surface, line, (info_rect.left, info_rect.top + index * attribute_font.get_height()),
                              attribute_font, text)
            else:
                self._wrapped(surface, "\n".join(lines), info_rect, small, text)
            button_rect.width = 116
            button_rect.left = rect.right - 123
            draw_text(surface, f"{card.rarity.value.replace('_', ' ').upper()} / {card.cost} AP",
                      (rect.left + 8, rect.bottom - 28), small, text)
        label = ("PURCHASED" if slot.purchased else
                 f"NEED {card.cost - shop.remaining_ap} AP" if card.cost > shop.remaining_ap else
                 "UNAVAILABLE" if slot.disabled_reason else
                 "SELECT CARD" if card.is_removal else "BUY")
        buttons.append(_ShopCardButton(label,
            lambda section=slot.section, card_id=card.card_id, removal=card.is_removal:
                self.purchase(section, card_id, removal),
            button_rect, enabled=not slot.purchased and card.cost <= shop.remaining_ap
            and slot.disabled_reason is None and shop.pending_removal is None,
            variant="primary" if not slot.purchased else "quiet"))

    @staticmethod
    def _wrapped(surface: pygame.Surface, value: str, rect: pygame.Rect,
                 font: pygame.font.Font, color: pygame.Color) -> None:
        lines = wrap_text_lines(value, font, rect.width)
        if len(lines) * font.get_height() > rect.height:
            raise ValueError(f"Shop text does not fit: {value}")
        for index, line in enumerate(lines):
            draw_text(surface, line, (rect.left, rect.top + index * font.get_height()), font, color)

    def _coach_art(self, surface: pygame.Surface, rect: pygame.Rect, card: FootballShopCard,
                   shop: FootballShopState, team_name: str) -> None:
        effect = card.coach_upgrade_effect
        assert effect is not None
        offensive = {
            FootballCoachUpgradeKind.OFFENSE_POWER_BOOST, FootballCoachUpgradeKind.OFFENSE_VOLATILITY_REDUCTION,
            FootballCoachUpgradeKind.OFFENSE_STAMINA_BOOST, FootballCoachUpgradeKind.OFFENSIVE_PLAY_CLOCK_DELTA,
            FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA, FootballCoachUpgradeKind.INTERCEPTION_RISK_REDUCTION,
        }
        defensive = {
            FootballCoachUpgradeKind.DEFENSE_POWER_BOOST, FootballCoachUpgradeKind.DEFENSE_VOLATILITY_REDUCTION,
            FootballCoachUpgradeKind.DEFENSE_STAMINA_BOOST, FootballCoachUpgradeKind.DEFENSIVE_FAMILY_YARDAGE_REDUCTION,
        }
        coaches = coaches_for_assignment(shop.roster.coach_assignment)
        coach = coaches[0] if effect.kind in offensive else coaches[1] if effect.kind in defensive else None
        if coach is not None:
            pygame.draw.rect(surface, "#1c3e5b", rect, border_radius=5)
            draw_coach_portrait(surface, rect, coach.coach_id, self.theme.primary)
        else:
            pygame.draw.circle(surface, self.theme.primary, rect.center, min(rect.size) // 2)
            letter = staff_font(24, semibold=True).render(team_name.strip()[:1].upper() or "T", True,
                                                         readable_ink(self.theme.primary))
            surface.blit(letter, letter.get_rect(center=rect.center))

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
                _RARITY_COLORS.get(card.rarity, _NEUTRAL_SLOT_EDGE),
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
                    "SELECT DETAILS",
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
