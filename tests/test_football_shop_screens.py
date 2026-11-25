"""Redesigned shop landing, inspect panels, and the restyled Depth Chart."""

from dataclasses import replace
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.engine.football import FootballPosition, FootballTeamSide
from src.engine.football_controller import FootballRunPhase
from src.engine.football_shop import (
    COACH_UPGRADE_CATALOG,
    PLAYER_UPGRADE_CATALOG,
    FootballShopRarity,
    FootballShopSection,
    FootballShopSectionState,
    FootballShopSlotState,
    FootballUpgradeDuration,
    FootballUpgradeStat,
    _play_scheme_catalog,
)
from src.ui import football_depth_chart as depth_module
from src.ui import football_inspect as inspect_module
from src.ui import football_shop_view as shop_module
from src.ui.football_coach_upgrade_details import COACH_UPGRADE_SHORT_LINES
from src.ui.football_inspect import HOVER_DELAY_MS
from src.ui.football_shop_view import SHORT_HINT, ShopCardButton
from src.ui.football_ui_kit import RARITY_COLORS, rarity_color, text_audit

from test_football_desktop import (
    _activate,
    _assert_text_fits,
    _draft_to_shop,
    _force_result,
    _new_desktop,
    _new_desktop_with_removal_offer,
    _play_first_match_card,
    _start_run,
    _surface,
)

PLAYS = _play_scheme_catalog()
PLAY_CARDS = [card for card in PLAYS if card.card_id.startswith("play:")]
SCHEME_CARDS = [card for card in PLAYS if card.card_id.startswith("scheme:")]
BONUS_CARDS = [card for card in PLAYS if card.bonus_card is not None]
REMOVAL = next(card for card in PLAYS if card.is_removal)
COACHES = {card.card_id: card for card in COACH_UPGRADE_CATALOG}
STAT_WORDS = ("power", "stamina", "volatility", "temporary", "permanent")


def _shop_desktop(tmp_path: Path, **kwargs):
    desktop = _new_desktop(tmp_path, **kwargs)
    _start_run(desktop)
    _draft_to_shop(desktop)
    return desktop


def _player_card(position=FootballPosition.QB, stat=FootballUpgradeStat.POWER,
                 rarity=FootballShopRarity.COMMON, duration=FootballUpgradeDuration.PERMANENT):
    return next(card for card in PLAYER_UPGRADE_CATALOG
                if card.upgrade.position is position and card.upgrade.stat is stat
                and card.rarity is rarity and card.upgrade.duration is duration)


def _slot(section, number, card=None, *, purchased=False, unlocked=True, cost=None, can=False, reason=None):
    return FootballShopSlotState(section, number, unlocked, card, purchased, cost, can, reason)


def _set_slots(desktop, players, coaches, plays, *, ap=12, message=None):
    """Render-only shop state with chosen offers (purchases still go to the controller)."""
    screen = desktop.run_screen
    state = screen.state
    sections = (
        FootballShopSectionState(FootballShopSection.PLAYER_UPGRADES, "PLAYER UPGRADES", tuple(players), True),
        FootballShopSectionState(FootballShopSection.PLAYS_SCHEMES, "PLAYS / SCHEMES", tuple(plays), True),
        FootballShopSectionState(FootballShopSection.COACH_UPGRADES, "COACH UPGRADES", tuple(coaches), True),
    )
    shop = replace(state.shop, sections=sections, remaining_ap=ap, game_number=4)
    screen.state = replace(state, shop=shop, transition_message=message)
    return shop


def _every_kind(desktop, *, ap=12, message=None):
    P, C, S = (FootballShopSection.PLAYER_UPGRADES, FootballShopSection.COACH_UPGRADES,
               FootballShopSection.PLAYS_SCHEMES)
    return _set_slots(
        desktop,
        [_slot(P, 1, _player_card(), purchased=True),
         _slot(P, 2, _player_card(FootballPosition.SAFETIES, FootballUpgradeStat.STAMINA,
                                  FootballShopRarity.UNCOMMON, FootballUpgradeDuration.TEMPORARY)),
         _slot(P, 3, _player_card(FootballPosition.LINEBACKERS, FootballUpgradeStat.VOLATILITY,
                                  FootballShopRarity.RARE)),
         _slot(P, 4, unlocked=False, cost=4, can=ap >= 4,
               reason=None if ap >= 4 else "Need 4 AP to unlock this slot.")],
        [_slot(C, 1, COACHES["vertical_threat"]),
         _slot(C, 2, unlocked=False, cost=6, reason="Need 6 AP to unlock this slot.")],
        [_slot(S, 1, PLAY_CARDS[0]), _slot(S, 2, SCHEME_CARDS[5]), _slot(S, 3, BONUS_CARDS[5]),
         _slot(S, 4, REMOVAL), _slot(S, 5, unlocked=False, cost=4, can=ap >= 4),
         _slot(S, 6, unlocked=False, cost=5, reason="Unlock slot 5 first.")],
        ap=ap, message=message,
    )


def _draw(desktop):
    surface = _surface()
    desktop.router.draw(surface)
    return surface


def _cards(desktop, section=None):
    _draw(desktop)
    return [button for button in desktop.run_screen.buttons
            if isinstance(button, ShopCardButton) and button.card_id is not None
            and (section is None or button.section is section)]


def _click(desktop, point):
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(pygame.event.Event(event_type, {"pos": point, "button": 1}))


def _move(desktop, point):
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": point, "rel": (0, 0), "buttons": (0, 0, 0)}))


def _key(desktop, key):
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": key, "mod": 0}))


def _clock(desktop):
    now = [0]
    desktop.run_screen._shop_view().clock = lambda: now[0]
    desktop.run_screen.shop_review.inspect.clock = lambda: now[0]
    return now


def _texts(desktop):
    with text_audit() as records:
        _draw(desktop)
    return records


# -- purchasing --------------------------------------------------------------------

def test_shop_purchase_and_finish_start_the_match(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    controller = desktop.football_controller
    shop = controller.state.shop
    assert shop.remaining_ap == 12
    first = _cards(desktop, FootballShopSection.PLAYER_UPGRADES)[0]
    assert first.label == f"{shop.offer[0].cost} AP" and first.purchasable
    _click(desktop, first.hit_rect.center)
    purchased = controller.state.shop
    assert purchased.remaining_ap == 12 - shop.offer[0].cost
    assert purchased.purchased_upgrades == (shop.offer[0],)
    second = _cards(desktop, FootballShopSection.PLAYER_UPGRADES)[1]
    _click(desktop, second.hit_rect.center)
    assert len(controller.state.shop.purchased_upgrades) == 2

    _activate(desktop, "FINISH SHOP / START MATCH")
    state = controller.state
    assert state.phase is FootballRunPhase.MATCH
    assert state.shop.finished and state.match.team_a.team_name == "Test Owls"


def test_clicking_a_card_outside_its_price_button_never_buys(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    controller = desktop.football_controller
    card = _cards(desktop, FootballShopSection.PLAYER_UPGRADES)[0]
    assert not card.hit_rect.collidepoint(card.rect.midtop[0], card.rect.top + 20)
    _click(desktop, (card.rect.centerx, card.rect.top + 20))
    assert not controller.state.shop.purchased_upgrades
    _click(desktop, card.hit_rect.center)
    assert len(controller.state.shop.purchased_upgrades) == 1


def test_header_footer_reroll_unlock_and_keyboard_purchase(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    controller = desktop.football_controller
    texts = {text for text, _rect, _container in _texts(desktop)}
    assert {"SHOP", "12", "AP", "PLAYER UPGRADES", "COACH UPGRADES", "PLAYS & SCHEMES", SHORT_HINT} <= texts
    assert "AFTER GAME 3" in texts
    assert not any("THREE SHOPS" in text or "STANDARDIZED NEUTRAL" in text or text == "BUY" for text in texts)

    screen = desktop.run_screen
    card = _cards(desktop, FootballShopSection.PLAYER_UPGRADES)[0]
    screen._focus(screen.buttons.index(card))
    _key(desktop, pygame.K_RETURN)
    after_purchase = controller.state.shop
    assert len(after_purchase.purchased_upgrades) == 1
    _activate(desktop, "NEXT DAY · 1 AP")
    after_reroll = controller.state.shop
    assert after_reroll.day == 2
    assert after_reroll.remaining_ap == 11 - after_purchase.purchased_upgrades[0].cost
    _activate(desktop, "UNLOCK 4 AP", index=0)
    unlocked = controller.state.shop
    assert unlocked.section(FootballShopSection.PLAYER_UPGRADES).slots[3].unlocked
    assert unlocked.remaining_ap == after_reroll.remaining_ap - 4
    _activate(desktop, "FINISH SHOP / START MATCH", keyboard=True)
    assert controller.state.phase is FootballRunPhase.MATCH


def test_tab_reaches_every_card_including_unaffordable_and_purchased(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    _every_kind(desktop, ap=1)
    _draw(desktop)
    screen = desktop.run_screen
    visited = set()
    for _ in range(len(screen.buttons) + 2):
        _key(desktop, pygame.K_TAB)
        _draw(desktop)
        visited.add(screen.focus_index)
    cards = [index for index, button in enumerate(screen.buttons)
             if isinstance(button, ShopCardButton) and button.card_id is not None]
    assert set(cards) <= visited
    labels = {button.label for button in screen.buttons}
    assert {"NEXT DAY · 1 AP", "DEPTH CHART", "PLAYBOOK", "FINISH SHOP / START MATCH", "PAUSE"} <= labels


def test_price_buttons_show_cost_purchased_and_dimmed_states(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    controller = desktop.football_controller
    _every_kind(desktop, ap=2)
    cards = {button.card_id: button for button in _cards(desktop)}
    purchased = cards[_player_card().card_id]
    assert purchased.label == "PURCHASED" and not purchased.purchasable
    affordable = cards[_player_card(FootballPosition.SAFETIES, FootballUpgradeStat.STAMINA,
                                    FootballShopRarity.UNCOMMON, FootballUpgradeDuration.TEMPORARY).card_id]
    assert affordable.label == "2 AP" and affordable.purchasable
    expensive = cards[_player_card(FootballPosition.LINEBACKERS, FootballUpgradeStat.VOLATILITY,
                                   FootballShopRarity.RARE).card_id]
    coach = cards["vertical_threat"]
    for button in (expensive, coach):
        assert button.label == f"{button.label.split()[0]} AP" and not button.purchasable
        assert button.enabled  # still focusable for inspection
    before = controller.state.shop
    coach.action()
    expensive.action()
    assert controller.state.shop == before
    unlocks = [button for button in desktop.run_screen.buttons
               if isinstance(button, ShopCardButton) and button.card_id is None]
    assert {button.label for button in unlocks} >= {"UNLOCK 4 AP", "UNLOCK 6 AP", "UNLOCK 5 AP"}
    assert not any(button.enabled for button in unlocks)
    texts = {text for text, _r, _c in _texts(desktop)}
    assert {"NEED 2 MORE AP", "NEED 4 MORE AP", "UNLOCK SLOT 5 FIRST"} <= texts


def test_pending_removal_disables_every_purchase(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    _every_kind(desktop)
    screen = desktop.run_screen
    screen.state = replace(screen.state, shop=replace(screen.state.shop, pending_removal=REMOVAL))
    assert not any(button.purchasable for button in _cards(desktop))
    assert not next(b for b in screen.buttons if b.label == "NEXT DAY · 1 AP").enabled


def test_same_frame_double_click_only_unlocks_once(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    controller = desktop.football_controller
    _draw(desktop)
    unlock = next(b for b in desktop.run_screen.buttons if b.label == "UNLOCK 4 AP")
    for _ in range(2):
        _click(desktop, unlock.hit_rect.center)
    shop = controller.state.shop
    assert shop.remaining_ap == 8 and not shop.purchased_cards
    assert shop.section(FootballShopSection.PLAYER_UPGRADES).slots[3].unlocked
    _draw(desktop)
    assert desktop.run_screen.buttons


def test_shop_at_zero_ap_stays_open_until_explicit_finish(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    controller = desktop.football_controller
    for _ in range(12):
        _activate(desktop, "NEXT DAY · 1 AP")
    assert controller.state.shop.remaining_ap == 0
    _draw(desktop)
    buttons = {button.label: button for button in desktop.run_screen.buttons}
    assert not buttons["NEXT DAY · 1 AP"].enabled
    assert buttons["FINISH SHOP / START MATCH"].enabled
    _activate(desktop, "FINISH SHOP / START MATCH")
    assert controller.state.phase is FootballRunPhase.MATCH


def _reach_game_four(desktop, monkeypatch, cards):
    controller = desktop.football_controller
    controller._shop_catalogs = {FootballShopSection.COACH_UPGRADES: cards}
    _draft_to_shop(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_A)
    for _ in range(3):
        _activate(desktop, "FINISH SHOP / START MATCH")
        _play_first_match_card(desktop)
        _activate(desktop, "OPEN NEXT GAME SHOP")
    return controller


@pytest.mark.parametrize("purchase_bye", (False, True))
def test_coach_unlock_and_bye_week_through_shop_router(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, purchase_bye: bool,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    controller = _reach_game_four(desktop, monkeypatch, (COACHES["bye_week"],))
    _draw(desktop)
    unlock = next(b for b in desktop.run_screen.buttons
                  if isinstance(b, ShopCardButton) and b.section is FootballShopSection.COACH_UPGRADES
                  and b.slot_number == 1)
    assert unlock.label == "UNLOCK 4 AP" and unlock.enabled
    _click(desktop, unlock.hit_rect.center)
    _draw(desktop)
    second = next(b for b in desktop.run_screen.buttons if b.label == "UNLOCK 6 AP")
    assert second.enabled
    if not purchase_bye:
        desktop.run_screen._focus(desktop.run_screen.buttons.index(second))
        _key(desktop, pygame.K_RETURN)
        assert controller.state.shop.section(FootballShopSection.COACH_UPGRADES).slots[1].unlocked
        assert not controller.state.shop.owned_coach_upgrades
        return
    bye = next(b for b in desktop.run_screen.buttons
               if isinstance(b, ShopCardButton) and b.card_id == "bye_week")
    assert bye.label == "6 AP" and bye.purchasable
    for _ in range(2):
        _click(desktop, bye.hit_rect.center)
    state = controller.state
    assert state.game_number == 5 and state.skipped_games == (4,)
    assert state.wins == 3 and state.losses == 0 and state.shop.remaining_ap == 12
    records = _texts(desktop)
    joined = " ".join(text for text, _r, _c in records)
    assert "Bye Week skipped scheduled game 4" in joined
    _assert_text_fits(records)


def test_coach_cards_show_portrait_name_and_short_line_only(tmp_path: Path, monkeypatch) -> None:
    desktop = _shop_desktop(tmp_path)
    portraits = []
    original = shop_module.draw_coach_portrait
    monkeypatch.setattr(shop_module, "draw_coach_portrait",
                        lambda surface, rect, coach_id, primary: portraits.append(coach_id)
                        or original(surface, rect, coach_id, primary))
    ids = list(COACHES)
    C = FootballShopSection.COACH_UPGRADES
    for first, second in zip(ids[::2], ids[1::2]):
        _set_slots(desktop, [], [_slot(C, 1, COACHES[first]), _slot(C, 2, COACHES[second])], [])
        portraits.clear()
        records = _texts(desktop)
        _assert_text_fits(records)
        joined = " ".join(text for text, _r, _c in records)
        for card_id in (first, second):
            card = COACHES[card_id]
            assert card.name.upper().split()[0] in joined
            short = COACH_UPGRADE_SHORT_LINES[card_id]
            assert short.split()[0] in joined
            assert card.description[:40] not in joined
        assert "DETAILS" not in {b.label for b in desktop.run_screen.buttons}
        assert portraits  # every coach upgrade shows staff art, team-wide ones show both coaches


def test_coach_short_lines_cover_the_whole_catalog() -> None:
    assert set(COACH_UPGRADE_SHORT_LINES) == set(COACHES)
    assert all(line.strip() for line in COACH_UPGRADE_SHORT_LINES.values())


def test_player_cards_use_icons_and_no_stat_or_duration_words(tmp_path: Path, monkeypatch) -> None:
    desktop = _shop_desktop(tmp_path)
    stats, icons = [], []
    original_stat = shop_module.draw_stat_value
    original_icon = shop_module.asset_icon

    def capture_stat(surface, stat, value, container, **kwargs):
        stats.append((stat, value))
        return original_stat(surface, stat, value, container, **kwargs)

    def capture_icon(filename, height):
        icons.append(filename)
        return original_icon(filename, height)

    monkeypatch.setattr(shop_module, "draw_stat_value", capture_stat)
    monkeypatch.setattr(shop_module, "asset_icon", capture_icon)
    P = FootballShopSection.PLAYER_UPGRADES
    catalog = list(PLAYER_UPGRADE_CATALOG)
    for start in range(0, len(catalog), 4):
        group = catalog[start:start + 4]
        _set_slots(desktop, [_slot(P, i + 1, card) for i, card in enumerate(group)], [], [])
        stats.clear()
        icons.clear()
        records = _texts(desktop)
        _assert_text_fits(records)
        assert not any(word in text.lower() for text, _r, _c in records for word in STAT_WORDS)
        expected = []
        for card in group:
            upgrade = card.upgrade
            if upgrade.stat is FootballUpgradeStat.POWER:
                expected.append(("power", f"+{upgrade.amount:g}"))
            elif upgrade.stat is FootballUpgradeStat.STAMINA:
                expected.append(("stamina", f"+{round(upgrade.amount * 100, 4):g}%"))
            else:
                expected.append(("volatility", f"-{round(upgrade.amount * 100, 4):g}%"))
        assert stats == expected
        assert icons == [f"upgrade_{card.upgrade.duration.value}.png" for card in group]


def test_rarity_palette_is_shared_and_rare_is_blue() -> None:
    assert RARITY_COLORS["rare"] == pygame.Color("#65b5ff")
    assert shop_module.__dict__.get("_RARITY_COLORS") is None
    assert [rarity_color(r) for r in FootballShopRarity] == [
        pygame.Color("#abb6c2"), pygame.Color("#68c58a"), pygame.Color("#65b5ff"), pygame.Color("#c18be8")]


@pytest.mark.parametrize("rarity", list(FootballShopRarity))
def test_card_border_and_inspect_rarity_text_share_the_rarity_color(
    tmp_path: Path, monkeypatch, rarity: FootballShopRarity,
) -> None:
    desktop = _shop_desktop(tmp_path)
    P, S = FootballShopSection.PLAYER_UPGRADES, FootballShopSection.PLAYS_SCHEMES
    play = next((c for c in PLAYS if c.rarity is rarity and not c.is_removal), REMOVAL)
    _set_slots(desktop, [_slot(P, 1, _player_card(rarity=rarity))], [], [_slot(S, 1, play)])
    surface = _draw(desktop)
    for button in _cards(desktop):
        x, y = button.rect.left, button.rect.centery
        assert surface.get_at((x, y))[:3] == tuple(rarity_color(button_rarity(button, desktop))[:3])
    colors = []
    original = inspect_module.blit_text

    def capture(surface, font, text, color, container, **anchor):
        colors.append((text, pygame.Color(color)))
        return original(surface, font, text, color, container, **anchor)

    monkeypatch.setattr(inspect_module, "blit_text", capture)
    now = _clock(desktop)
    card = _cards(desktop, P)[0]
    _move(desktop, card.rect.center)
    _draw(desktop)
    now[0] += HOVER_DELAY_MS + 1
    _draw(desktop)
    label = rarity.value.replace("_", " ").upper()
    assert (label, rarity_color(rarity)) in colors


def button_rarity(button, desktop):
    for section in desktop.run_screen.state.shop.sections:
        for slot in section.slots:
            if slot.card is not None and slot.card.card_id == button.card_id:
                return slot.card.rarity
    raise AssertionError(button.card_id)


# -- inspect panels ----------------------------------------------------------------

def _hover_open(desktop, button, now):
    _move(desktop, button.rect.center)
    _draw(desktop)
    now[0] += HOVER_DELAY_MS + 1
    return _draw(desktop)


def test_inspect_opens_after_hover_delay_and_closes_for_every_card_type(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    _every_kind(desktop)
    view = desktop.run_screen._shop_view()
    now = _clock(desktop)
    cards = _cards(desktop)
    kinds = {button.card_id for button in cards}
    assert {"vertical_threat", PLAY_CARDS[0].card_id, SCHEME_CARDS[5].card_id,
            BONUS_CARDS[5].card_id, REMOVAL.card_id} <= kinds
    for button in cards:
        _move(desktop, button.rect.center)
        _draw(desktop)
        assert not view.inspect_open  # waits for the delay
        now[0] += HOVER_DELAY_MS + 1
        with text_audit() as records:
            _draw(desktop)
        assert view.inspect_open and view.inspect.shown_key == button.inspect_key
        panel = view.inspect.panel_rect
        assert panel is not None and not panel.colliderect(button.rect)
        assert not panel.colliderect(button.hit_rect)
        _assert_text_fits(records)
        _move(desktop, (640, 6))  # mouse-out
        _draw(desktop)
        assert not view.inspect_open


def test_inspect_content_has_full_rules_for_each_card_type(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    _every_kind(desktop)
    view = desktop.run_screen._shop_view()
    now = _clock(desktop)
    expected = {
        "vertical_threat": ("Effect", "Duration", "Uniqueness"),
        _player_card(FootballPosition.SAFETIES, FootballUpgradeStat.STAMINA, FootballShopRarity.UNCOMMON,
                     FootballUpgradeDuration.TEMPORARY).card_id: ("next completed match", "capped at 100%"),
        _player_card(FootballPosition.LINEBACKERS, FootballUpgradeStat.VOLATILITY,
                     FootballShopRarity.RARE).card_id: ("rest of the run", "cannot drop below 0%"),
        PLAY_CARDS[0].card_id: ("standardized neutral estimate", "Contributors", PLAY_CARDS[0].description[:20]),
        SCHEME_CARDS[5].card_id: ("Counters", SCHEME_CARDS[5].description[:20]),
        BONUS_CARDS[5].card_id: (BONUS_CARDS[5].description[:20],),
        REMOVAL.card_id: ("exact copy", "at least 4"),
    }
    for button in _cards(desktop):
        if button.card_id not in expected:
            continue
        with text_audit() as records:
            _hover_open(desktop, button, now)
        joined = " ".join(text for text, _r, _c in records)
        # Panel lines wrap, so check each phrase on the unwrapped content too.
        content = view.inspect.overlay[0]
        full = " ".join([content.title, *(f"{h} {t}" for h, t in content.sections)])
        for phrase in expected[button.card_id]:
            assert phrase in full, (button.card_id, phrase)
        assert content.title.upper().split()[0] in joined
        _move(desktop, (640, 6))
        _draw(desktop)


def test_i_key_does_nothing_and_escape_hides_panel_before_pausing(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    _every_kind(desktop)
    view = desktop.run_screen._shop_view()
    now = _clock(desktop)
    screen = desktop.run_screen
    card = _cards(desktop, FootballShopSection.COACH_UPGRADES)[0]
    # No panel showing: I opens nothing, even after the delay would have passed.
    _key(desktop, pygame.K_i)
    _draw(desktop)
    assert not view.inspect_open
    # Panel showing: I neither closes nor changes it, and adds no buttons.
    _hover_open(desktop, card, now)
    labels = [b.label for b in screen.buttons]
    _key(desktop, pygame.K_i)
    with text_audit() as records:
        _draw(desktop)
    assert view.inspect_open and view.inspect.shown_key == card.inspect_key
    assert [b.label for b in screen.buttons] == labels and "CLOSE [ESC]" not in labels
    assert not {"PRESS I TO PIN", "CLOSE [ESC]"} & {text for text, _r, _c in records}
    # Esc hides the visible panel first; the next Esc pauses.
    _key(desktop, pygame.K_ESCAPE)
    _draw(desktop)
    assert not view.inspect_open and not screen.pause.is_open
    _key(desktop, pygame.K_ESCAPE)
    assert screen.pause.is_open
    _draw(desktop)
    assert not view.inspect_open


def test_keyboard_focus_opens_inspect_after_the_delay(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    view = desktop.run_screen._shop_view()
    now = _clock(desktop)
    _draw(desktop)
    _key(desktop, pygame.K_TAB)
    _draw(desktop)
    assert not view.inspect_open
    now[0] += HOVER_DELAY_MS + 1
    _draw(desktop)
    focused = desktop.run_screen.buttons[desktop.run_screen.focus_index]
    assert view.inspect_open and view.inspect.shown_key == focused.inspect_key


def test_inspect_never_blocks_buying_the_hovered_card(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    controller = desktop.football_controller
    view = desktop.run_screen._shop_view()
    now = _clock(desktop)
    card = _cards(desktop, FootballShopSection.PLAYER_UPGRADES)[0]
    _hover_open(desktop, card, now)
    assert view.inspect_open
    _move(desktop, card.hit_rect.center)
    _click(desktop, card.hit_rect.center)
    assert len(controller.state.shop.purchased_upgrades) == 1


def test_hover_panel_never_takes_clicks_on_cards_beneath_it(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    controller = desktop.football_controller
    view = desktop.run_screen._shop_view()
    now = _clock(desktop)
    cards = _cards(desktop)
    for first in cards:
        _hover_open(desktop, first, now)
        panel = view.inspect.panel_rect
        covered = [b for b in _cards(desktop) if b is not first and b.enabled and b.purchasable
                   and panel.collidepoint(b.hit_rect.center)]
        if covered:
            break
    assert covered, "expected a hover panel over another card's price button"
    before = controller.state.shop
    _click(desktop, covered[0].hit_rect.center)
    assert controller.state.shop != before


def test_buying_a_play_keeps_it_purchased_with_an_added_ribbon(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    controller = desktop.football_controller
    now = _clock(desktop)
    play = next(b for b in _cards(desktop, FootballShopSection.PLAYS_SCHEMES)
                if b.purchasable and b.card_id.split(":")[0] in ("play", "scheme"))
    owned = len(controller.state.shop.offensive_deck) + len(controller.state.shop.defensive_deck)
    _click(desktop, play.hit_rect.center)
    assert len(controller.state.shop.offensive_deck) + len(controller.state.shop.defensive_deck) == owned + 1
    texts = {text for text, _r, _c in _texts(desktop)}
    assert "ADDED TO PLAYBOOK" in texts
    same = next(b for b in desktop.run_screen.buttons
                if isinstance(b, ShopCardButton) and b.section is play.section and b.slot_number == play.slot_number)
    assert same.card_id == play.card_id and same.label == "PURCHASED" and not same.purchasable
    _activate(desktop, "NEXT DAY · 1 AP")
    rerolled = next(b for b in _cards(desktop, FootballShopSection.PLAYS_SCHEMES) if b.slot_number == play.slot_number)
    assert rerolled.label != "PURCHASED"
    now[0] += 5000
    assert "ADDED TO PLAYBOOK" not in {text for text, _r, _c in _texts(desktop)}


@pytest.mark.parametrize(("team", "primary", "secondary"), (
    ("Northern Saskatchewan Polytechnic Huskies", "silver", "navy"),
    ("Midnight", "navy", "silver"),
    ("Lemon Grove", "yellow", "green"),
    ("Test Owls", "crimson", "gold"),
))
def test_every_card_kind_fits_for_long_names_and_team_colors(
    tmp_path: Path, team: str, primary: str, secondary: str,
) -> None:
    desktop = _shop_desktop(tmp_path, team_name=team, primary=primary, secondary=secondary)
    message = ("Bye Week skipped scheduled game 6 without a win or loss. "
               "Next up: the shop before scheduled game 7.")
    _every_kind(desktop, message=message)
    _assert_text_fits(_texts(desktop))
    S = FootballShopSection.PLAYS_SCHEMES
    pool = PLAY_CARDS + SCHEME_CARDS + BONUS_CARDS
    for start in range(0, len(pool), 6):
        group = pool[start:start + 6]
        _set_slots(desktop, [], [], [_slot(S, i + 1, card) for i, card in enumerate(group)])
        records = _texts(desktop)
        _assert_text_fits(records)
        names = " ".join(text for text, _r, _c in records)
        assert all(card.name.upper().split()[0] in names for card in group)


# -- Depth Chart -------------------------------------------------------------------

def _capture_depth_text(monkeypatch):
    texts = []
    original = depth_module.blit_text

    def capture(surface, font, text, color, container, **anchor):
        texts.append(text)
        return original(surface, font, text, color, container, **anchor)

    monkeypatch.setattr(depth_module, "blit_text", capture)
    return texts


def test_depth_chart_shows_art_staff_and_toggles(tmp_path: Path, monkeypatch) -> None:
    desktop = _shop_desktop(tmp_path)
    art, portraits = [], []
    original_art, original_portrait = depth_module.draw_draft_player, depth_module.draw_coach_portrait
    monkeypatch.setattr(depth_module, "draw_draft_player",
                        lambda s, r, a, active=False: art.append(a) or original_art(s, r, a, active))
    monkeypatch.setattr(depth_module, "draw_coach_portrait",
                        lambda s, r, c, p: portraits.append(c) or original_portrait(s, r, c, p))
    _activate(desktop, "DEPTH CHART")
    screen = desktop.run_screen
    assert screen.shop_review.mode == "depth"
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    texts = {text for text, _r, _c in records}
    assert {"DEPTH CHART", "TEST OWLS", "CURRENT RUN", "COACHING STAFF", "ROSTER", "TEAM UPGRADES"} <= texts
    assert len(art) == 8 and len(portraits) == 2
    labels = [b.label for b in screen.buttons]
    assert labels[:4] == ["STARTING STATS", "MODIFIED STATS", "BACK TO SHOP", "TEAM UPGRADES"]
    flips = [label for label in labels if label.startswith("FLIP ")]
    assert flips == ["FLIP OFFENSE COACH", "FLIP DEFENSE COACH", *(
        f"FLIP {label}" for label in ("QB", "RB", "WR", "O-LINE", "D-LINE", "LINEBACKERS", "CORNERBACKS", "SAFETIES"))]
    assert "UPGRADES & PERKS" not in labels and "PAUSE" in labels
    _activate(desktop, "MODIFIED STATS")
    assert screen.shop_review.modified_stats
    _activate(desktop, "MODIFIED STATS")
    assert screen.shop_review.modified_stats  # selecting the active side keeps it
    _activate(desktop, "STARTING STATS")
    assert not screen.shop_review.modified_stats
    _activate(desktop, "BACK TO SHOP")
    assert screen.shop_review.mode is None


def test_flip_arrow_rotates_cards_to_their_backs_and_back(tmp_path: Path) -> None:
    from src.ui.football_shop_review import FLIP_MS

    desktop = _shop_desktop(tmp_path)
    _activate(desktop, "DEPTH CHART")
    interaction = desktop.run_screen.shop_review
    now = [1000]
    interaction.clock = lambda: now[0]
    _draw(desktop)
    flip = next(b for b in desktop.run_screen.buttons if b.label == "FLIP QB")
    card_left = flip.rect.right + 8 - 0
    _click(desktop, flip.rect.center)
    key = ("player", "QB")
    assert interaction.flip_progress(key) == (True, 0.0)
    # Halfway through, the card is squeezed to a sliver around its center.
    now[0] += FLIP_MS // 2
    surface = _draw(desktop)
    assert interaction.flip_progress(key)[1] == pytest.approx(0.5, abs=0.01)
    del card_left, surface
    now[0] += FLIP_MS
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    texts = [text for text, _r, _c in records]
    assert "UPGRADES" in texts and "PARTNER" in texts and "PERK" in texts
    assert not any("PLANNED" in text or "INACTIVE" in text for text in texts)
    # Keyboard: Enter on the focused arrow turns it back to the front.
    screen = desktop.run_screen
    flip = next(b for b in screen.buttons if b.label == "FLIP QB")
    screen._focus(screen.buttons.index(flip))
    _key(desktop, pygame.K_RETURN)
    assert interaction.flip_progress(key)[0] is False
    for coach in ("OFFENSE", "DEFENSE"):
        _activate(desktop, f"FLIP {coach} COACH")
        assert interaction.flip_progress(("coach", coach))[0] is True
    now[0] += FLIP_MS * 2
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    texts = [text for text, _r, _c in records]
    assert "OFFENSE UPGRADES" in texts and "DEFENSE UPGRADES" in texts and "COACH PERK" in texts
    interaction.open_depth_chart()
    assert interaction.flip_progress(key) == (False, 1.0)


def _expected_back_lines(rows, card: pygame.Rect) -> list:
    width = card.width - 16 - depth_module.BACK_GUTTER
    expected = []
    for line in depth_module._back_lines(rows, width):
        expected.append((line[2], line[3]) if line[0] == "stat" else line[2])
    return expected


def _scroll_through_back(desktop, interaction, key) -> tuple[set, set]:
    """Wheel through one flipped back; returns (texts seen fitting, (value, label) pairs seen)."""
    _draw(desktop)
    card, max_scroll, _page = interaction.back_areas[key]
    _move(desktop, card.center)
    seen, pairs = set(), set()
    previous = None
    for _ in range(200):
        with text_audit() as records:
            _draw(desktop)
        _assert_text_fits(records)
        inside = [(text, rect) for text, rect, _c in records if card.contains(rect)]
        seen.update(text for text, _rect in inside)
        by_row = {}
        for text, rect in inside:
            by_row.setdefault(rect.centery, []).append(text)
        for texts in by_row.values():
            pairs.update((a, b) for a in texts for b in texts if a != b)
        if interaction.back_scroll.get(key, 0) == previous:
            break
        previous = interaction.back_scroll.get(key, 0)
        desktop.router.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1}))
    assert interaction.back_scroll.get(key, 0) == max_scroll
    return seen, pairs


def _assert_back_complete(desktop, interaction, key, rows):
    seen, pairs = _scroll_through_back(desktop, interaction, key)
    card = interaction.back_areas[key][0]
    for item in _expected_back_lines(rows, card):
        if isinstance(item, tuple):
            assert item in pairs, (key, item)
        else:
            assert item in seen, (key, item)


def _worst_case(desktop):
    state = desktop.football_controller.state
    qb = [c.upgrade for c in PLAYER_UPGRADE_CATALOG
          if c.upgrade.position is FootballPosition.QB and c.rarity is FootballShopRarity.COMMON]
    permanent = tuple(u for u in qb if u.duration is FootballUpgradeDuration.PERMANENT)
    temporary = tuple(u for u in qb if u.duration is FootballUpgradeDuration.TEMPORARY)
    coaches = tuple(COACHES[i] for i in ("two_minute_drill", "rhythm_install", "fourth_quarter_conditioning",
                                         "tempo_install", "huddle_up", "vertical_threat", "ball_security_clinic"))
    assert len(permanent) == len(temporary) == 3
    return replace(state, shop=replace(state.shop, run_purchased_upgrades=permanent + temporary,
                                       pending_player_upgrades=temporary, owned_coach_upgrades=coaches))


def _flip_now(interaction, *keys):
    interaction.clock = lambda: 10**7
    for key in keys:
        interaction.flips[key] = (True, 0)


def test_worst_case_backs_show_every_upgrade_partner_and_full_perk(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    state = _worst_case(desktop)
    desktop.run_screen.state = state
    _activate(desktop, "DEPTH CHART")
    interaction = desktop.run_screen.shop_review
    _flip_now(interaction, ("player", "QB"), ("coach", "OFFENSE"))
    _draw(desktop)
    assert interaction.back_areas[("player", "QB")][1] > 0  # it really overflows
    qb_rows = depth_module.player_back_rows(state, FootballPosition.QB, False)
    assert sum(row[0] == "stat" for row in qb_rows) == 6
    perk = next(row[1] for row in qb_rows if row[0] == "name")
    assert any(row[0] == "small" and row[1].endswith(".") for row in qb_rows)
    _assert_back_complete(desktop, interaction, ("player", "QB"), qb_rows)
    seen, _pairs = _scroll_through_back(desktop, interaction, ("player", "QB"))
    assert {"PARTNER", "PERK", perk} <= seen

    coach = depth_module.coaches_for_assignment(state.shop.roster.coach_assignment)[0]
    coach_rows = depth_module.coach_back_rows("OFFENSE", coach, state.shop)
    assert [r[1] for r in coach_rows if r[0] == "name"] == [
        "TWO-MINUTE DRILL", "RHYTHM INSTALL", "FOURTH-QUARTER CONDITIONING", "TEMPO INSTALL",
        "HUDDLE UP", "VERTICAL THREAT", "BALL-SECURITY CLINIC"]
    _assert_back_complete(desktop, interaction, ("coach", "OFFENSE"), coach_rows)


def test_overflowing_back_shows_more_hint_and_scrolls_by_keyboard(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    desktop.run_screen.state = _worst_case(desktop)
    _activate(desktop, "DEPTH CHART")
    interaction = desktop.run_screen.shop_review
    _flip_now(interaction, ("player", "QB"))
    texts = {text for text, _r, _c in _texts(desktop)}
    assert "MORE" in texts
    screen = desktop.run_screen
    flip = next(b for b in screen.buttons if b.label == "FLIP QB")
    screen._focus(screen.buttons.index(flip))
    _draw(desktop)
    _key(desktop, pygame.K_PAGEDOWN)
    assert interaction.back_scroll[("player", "QB")] > 0 and interaction.depth_scroll == 0
    _key(desktop, pygame.K_END)
    _draw(desktop)
    assert interaction.back_scroll[("player", "QB")] == interaction.back_areas[("player", "QB")][1]
    assert "MORE" not in {text for text, _r, _c in _texts(desktop)}
    _key(desktop, pygame.K_HOME)
    assert interaction.back_scroll[("player", "QB")] == 0
    # The flip arrow stays put and still turns the card back over.
    assert flip.rect == next(b for b in screen.buttons if b.label == "FLIP QB").rect
    _key(desktop, pygame.K_RETURN)
    assert interaction.flip_progress(("player", "QB"))[0] is False


def test_worst_case_backs_are_complete_in_the_match_popup(tmp_path: Path) -> None:
    from test_football_desktop import _skip_match_playback, _start_match

    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _skip_match_playback(desktop)
    state = _worst_case(desktop)
    desktop.run_screen.state = state
    _activate(desktop, "PAUSE")
    _activate(desktop, "DEPTH CHART")
    interaction = desktop.run_screen.match_screen.popup.review
    _flip_now(interaction, ("player", "QB"), ("coach", "OFFENSE"))
    rows = depth_module.player_back_rows(state, FootballPosition.QB, True)
    assert sum(row[0] == "stat" and row[3] == "THIS MATCH" for row in rows) == 3
    _assert_back_complete(desktop, interaction, ("player", "QB"), rows)
    coach = depth_module.coaches_for_assignment(state.shop.roster.coach_assignment)[0]
    _assert_back_complete(desktop, interaction, ("coach", "OFFENSE"),
                          depth_module.coach_back_rows("OFFENSE", coach, state.shop))


def test_front_pending_chips_never_hide_a_count(tmp_path: Path, monkeypatch) -> None:
    desktop = _shop_desktop(tmp_path)
    state = desktop.football_controller.state
    for count in (1, 2, 3):
        temporary = tuple(
            c.upgrade for c in PLAYER_UPGRADE_CATALOG
            if c.upgrade.position is FootballPosition.QB and c.rarity is FootballShopRarity.COMMON
            and c.upgrade.duration is FootballUpgradeDuration.TEMPORARY)[:count]
        desktop.run_screen.state = replace(state, shop=replace(state.shop, pending_player_upgrades=temporary))
        desktop.run_screen.shop_review.open_depth_chart()
        calls = []
        original = depth_module.blit_text
        monkeypatch.setattr(depth_module, "blit_text", lambda surface, font, text, color, container, **anchor:
                            calls.append((text, pygame.Color(color), pygame.Rect(container)))
                            or original(surface, font, text, color, container, **anchor))
        _draw(desktop)
        monkeypatch.setattr(depth_module, "blit_text", original)
        chips = [c for c in calls if c[2].height == 20 and c[1] == depth_module.MATCH_GOLD]
        extra = [c for c in calls if c[2].height == 20 and c[1] == depth_module.MATCH_INK]
        hidden = int(extra[0][0].lstrip("+")) if extra else 0
        assert len(chips) + hidden == count and len(extra) <= 1
        assert not extra or extra[0][0] == f"+{hidden}"
    assert depth_module.pending_chip_layout([70, 70, 70], 169, lambda n: 30) == 1
    assert depth_module.pending_chip_layout([70, 70], 169, lambda n: 30) == 2
    assert depth_module.pending_chip_layout([200], 169, lambda n: 30) == 0


def test_every_card_back_is_complete_with_many_upgrades(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path, team_name="Northern Saskatchewan Polytechnic Huskies")
    state = desktop.football_controller.state
    upgrades = tuple(card.upgrade for card in PLAYER_UPGRADE_CATALOG if card.rarity is FootballShopRarity.RARE)
    permanent = tuple(u for u in upgrades if u.duration is FootballUpgradeDuration.PERMANENT)
    temporary = tuple(u for u in upgrades if u.duration is FootballUpgradeDuration.TEMPORARY)
    shop = replace(state.shop, run_purchased_upgrades=permanent + temporary, pending_player_upgrades=temporary,
                   owned_coach_upgrades=tuple(COACH_UPGRADE_CATALOG))
    candidate = replace(state, shop=shop)
    desktop.run_screen.state = candidate
    _activate(desktop, "DEPTH CHART")
    interaction = desktop.run_screen.shop_review
    coaches = depth_module.coaches_for_assignment(shop.roster.coach_assignment)
    for position in FootballPosition:
        key = ("player", position.value)
        _flip_now(interaction, key)
        _assert_back_complete(desktop, interaction, key,
                              depth_module.player_back_rows(candidate, position, False))
    for side, coach in zip(("OFFENSE", "DEFENSE"), coaches):
        key = ("coach", side)
        _flip_now(interaction, key)
        _assert_back_complete(desktop, interaction, key, depth_module.coach_back_rows(side, coach, shop))


def test_card_back_rows_cover_upgrades_partner_perk_and_coach_split(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    state = desktop.football_controller.state
    qb = replace(state.shop.roster.players[FootballPosition.QB], stamina=0.85)
    roster = replace(state.shop.roster, players={**state.shop.roster.players, FootballPosition.QB: qb})
    temp = _player_card(FootballPosition.QB, FootballUpgradeStat.STAMINA,
                        duration=FootballUpgradeDuration.TEMPORARY).upgrade
    perm = _player_card(FootballPosition.QB, FootballUpgradeStat.POWER).upgrade
    owned = tuple(COACHES[i] for i in ("fourth_quarter_conditioning", "iron_lungs", "field_goal_lab", "bye_week"))
    shop = replace(state.shop, roster=roster, owned_coach_upgrades=owned,
                   pending_player_upgrades=(temp, temp), run_purchased_upgrades=(perm, temp, temp))
    candidate = replace(state, shop=shop)
    rows = depth_module.player_back_rows(candidate, FootballPosition.QB, False)
    assert ("stat", "stamina", "+20%", "NEXT MATCH x2", depth_module.MATCH_GOLD) in rows
    assert ("stat", "power", "+1", "REST OF RUN", depth_module._POSITIVE) in rows
    smalls = [row[1] for row in rows if row[0] == "small"]
    assert "Run 85% -> 100% · coached 95% -> 100% · max 100%" in smalls
    assert any(row == ("head", "PARTNER") for row in rows)
    assert any(row[0] == "small" and row[1].endswith(".") for row in rows)
    in_match = depth_module.player_back_rows(candidate, FootballPosition.QB, True)
    assert any(row[0] == "stat" and row[3] == "THIS MATCH x2" for row in in_match)
    coaches = depth_module.coaches_for_assignment(shop.roster.coach_assignment)
    offense = depth_module.coach_back_rows("OFFENSE", coaches[0], shop)
    defense = depth_module.coach_back_rows("DEFENSE", coaches[1], shop)
    assert [r[1] for r in offense if r[0] == "name"] == ["FOURTH-QUARTER CONDITIONING"]
    assert [r[1] for r in defense if r[0] == "name"] == ["IRON LUNGS"]
    assert [card.card_id for card in depth_module.team_upgrades(shop)] == ["field_goal_lab", "bye_week"]
    empty = depth_module.player_back_rows(state, FootballPosition.RB, False)
    assert ("small", "No upgrades yet.") in empty


def test_team_upgrades_popup_opens_from_the_info_button_and_closes(tmp_path: Path) -> None:
    desktop = _shop_desktop(tmp_path)
    state = desktop.football_controller.state
    shop = replace(state.shop, owned_coach_upgrades=tuple(COACHES[i] for i in (
        "field_goal_lab", "booster_club_drive", "punt_return_lane", "two_minute_drill")))
    desktop.run_screen.state = replace(state, shop=shop)
    _activate(desktop, "DEPTH CHART")
    screen = desktop.run_screen
    _activate(desktop, "TEAM UPGRADES")
    assert screen.shop_review.team_popup
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    texts = [text for text, _r, _c in records]
    assert {"TEAM UPGRADES", "FIELD-GOAL LAB", "BOOSTER CLUB DRIVE", "PUNT RETURN LANE"} <= set(texts)
    assert "TWO-MINUTE DRILL" not in texts  # offensive upgrades live on the offense coach card
    assert [b.label for b in screen.buttons] == ["CLOSE [ESC]"]
    _key(desktop, pygame.K_ESCAPE)
    assert not screen.shop_review.team_popup and screen.shop_review.mode == "depth"
    _activate(desktop, "TEAM UPGRADES")
    _activate(desktop, "CLOSE [ESC]")
    assert not screen.shop_review.team_popup
    desktop.run_screen.state = replace(state, shop=replace(state.shop, owned_coach_upgrades=()))
    _activate(desktop, "TEAM UPGRADES")
    texts = {text for text, _r, _c in _texts(desktop)}
    assert "NO TEAM UPGRADES YET" in texts


def test_depth_chart_modified_values_use_comparison_colors(tmp_path: Path, monkeypatch) -> None:
    desktop = _shop_desktop(tmp_path)
    state = desktop.football_controller.state
    coach = COACHES["two_minute_drill"]
    desktop.run_screen.state = replace(state, shop=replace(state.shop, owned_coach_upgrades=(coach,)))
    _activate(desktop, "DEPTH CHART")
    _activate(desktop, "MODIFIED STATS")
    texts = _capture_depth_text(monkeypatch)
    _draw(desktop)
    for position in FootballPosition:
        power = depth_module.modified_player_stats(desktop.run_screen.state, position)[0]
        assert f"-> {power:g}" in texts
    value, color = depth_module._comparison(51, 50, lower_is_better=False, percentage=False)
    assert (value, color) == ("51", depth_module._POSITIVE)
    assert depth_module._comparison(0.12, 0.10, lower_is_better=True, percentage=True)[1] == depth_module._NEGATIVE


def test_depth_chart_small_viewport_scrolls(tmp_path: Path) -> None:
    from src.ui.football_review_view import FootballReviewView

    desktop = _shop_desktop(tmp_path)
    interaction = desktop.run_screen.shop_review
    interaction.open_depth_chart()
    review = FootballReviewView(desktop.theme, desktop.run_screen._small_font, desktop.run_screen._label_font,
                                interaction, lambda: None, lambda _copy: None)
    review.draw_depth_chart(_surface(), pygame.Rect(20, 15, 1240, 690), desktop.football_controller.state)
    assert interaction.depth_max_scroll == 0
    review.draw_depth_chart(_surface(), pygame.Rect(20, 15, 600, 500), desktop.football_controller.state)
    assert interaction.depth_max_scroll > 0
    interaction.handle_scroll(pygame.event.Event(pygame.MOUSEWHEEL, {"y": -1, "x": 0}))
    assert interaction.depth_scroll > 0


def test_temporary_upgrade_is_pending_in_shop_and_active_in_the_match_popup(tmp_path: Path, monkeypatch) -> None:
    desktop = _shop_desktop(tmp_path)
    controller = desktop.football_controller
    card = _player_card(FootballPosition.QB, FootballUpgradeStat.VOLATILITY,
                        duration=FootballUpgradeDuration.TEMPORARY)
    controller._shop._offers[FootballShopSection.PLAYER_UPGRADES][0] = card
    before = controller.state
    controller.buy_shop_card(FootballShopSection.PLAYER_UPGRADES, card.card_id)
    desktop.run_screen.state = controller.state
    texts = _capture_depth_text(monkeypatch)
    _activate(desktop, "DEPTH CHART")
    _draw(desktop)
    assert "1 PENDING NEXT MATCH" in texts
    _activate(desktop, "BACK TO SHOP")
    _activate(desktop, "FINISH SHOP / START MATCH")
    started = controller.state
    assert started.match.team_a.players[FootballPosition.QB].volatility == pytest.approx(
        max(0, before.shop.roster.players[FootballPosition.QB].volatility - card.upgrade.amount))
    _activate(desktop, "PAUSE")
    _activate(desktop, "DEPTH CHART")
    texts.clear()
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    assert "THIS MATCH · READ ONLY" in texts and "1 ACTIVE THIS MATCH" in texts
    assert not any("PENDING" in text for text in texts)
    review = desktop.run_screen.match_screen.popup.review
    review.clock = lambda: 10**7
    _activate(desktop, "FLIP QB")
    review.clock = lambda: 10**8
    texts.clear()
    _draw(desktop)
    assert "THIS MATCH" in texts
    _activate(desktop, "TEAM UPGRADES")
    assert review.team_popup
    _key(desktop, pygame.K_ESCAPE)
    assert not review.team_popup and desktop.run_screen.match_screen.popup.kind == "depth"
    _activate(desktop, "CLOSE [ESC]")
    assert desktop.run_screen.match_screen.popup.kind == "pause"


# -- Remove One Card ---------------------------------------------------------------

def _buy_removal(desktop):
    card = next(b for b in _cards(desktop) if b.card_id == "test-removal")
    assert card.label == "2 AP"
    _click(desktop, card.hit_rect.center)


def test_playbook_removal_can_be_cancelled_or_confirmed_in_the_ui(tmp_path: Path) -> None:
    desktop = _new_desktop_with_removal_offer(tmp_path)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    before = controller.state.shop
    _buy_removal(desktop)
    assert desktop.run_screen.shop_review.mode == "playbook"
    _draw(desktop)
    assert "PAUSE" in {button.label for button in desktop.run_screen.buttons}
    pending = controller.state.shop
    assert pending.pending_removal is not None and pending.remaining_ap == before.remaining_ap
    texts = {text for text, _r, _c in _texts(desktop)}
    assert any("REMOVAL MODE" in text for text in texts)
    _activate(desktop, "CANCEL SELECTION")
    cancelled = controller.state.shop
    assert cancelled.pending_removal is None and cancelled.remaining_ap == before.remaining_ap

    _buy_removal(desktop)
    _draw(desktop)
    remove = next(b for b in desktop.run_screen.buttons if b.label == "REMOVE" and b.removable)
    assert remove.copy_id == before.offensive_deck[0].copy_id
    _click(desktop, remove.hit_rect.center)
    removed = controller.state.shop
    assert removed.pending_removal is None
    assert removed.remaining_ap == before.remaining_ap - 2
    assert removed.offensive_deck == before.offensive_deck[1:]
    assert removed.defensive_deck == before.defensive_deck


def test_review_escape_cancels_pending_removal_without_spending_ap(tmp_path: Path) -> None:
    desktop = _new_desktop_with_removal_offer(tmp_path)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    before = controller.state.shop
    _buy_removal(desktop)
    assert controller.state.shop.pending_removal is not None
    _key(desktop, pygame.K_ESCAPE)
    after = controller.state.shop
    assert after.pending_removal is None and after.remaining_ap == before.remaining_ap
    assert after.offensive_deck == before.offensive_deck
    assert desktop.run_screen.shop_review.mode is None and not desktop.run_screen.pause.is_open


def test_header_names_the_next_opponent_without_reaching_the_banner(tmp_path: Path) -> None:
    from src.engine.football_ai_teams import AI_TEAM_CATALOG
    from src.ui.football_ui_kit import plain_font

    desktop = _shop_desktop(tmp_path)
    screen = desktop.run_screen
    rival = screen.state.opponent_team
    assert rival is not None and rival is screen.state.regular_season_teams[0]
    texts = [text for text, _rect, _container in _texts(desktop)]
    assert "NEXT" in texts and rival.name.upper() in texts

    font = plain_font(18)
    widest = max(AI_TEAM_CATALOG, key=lambda team: font.size(team.name.upper())[0])
    screen.state = replace(screen.state, opponent_team=widest,
                           transition_message="A long message banner fills the header.")
    records = _texts(desktop)
    title = next(rect for text, rect, _c in records if text == "SHOP")
    name = next(rect for text, rect, _c in records if text.startswith(widest.name.upper()[:6]))
    assert name.right <= title.left + 420
