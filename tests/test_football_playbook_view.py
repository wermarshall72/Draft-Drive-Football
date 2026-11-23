from dataclasses import replace
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.engine.football import (
    FootballCardCopy,
    FootballCoach,
    FootballPlayer,
    FootballPosition,
    FootballRoster,
    FootballSpecialTeams,
)
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)
from src.engine.football_shop import (
    PLAYBOOK_CARD_RARITIES,
    FootballShop,
    FootballShopCard,
    FootballShopRarity,
    FootballShopSection,
)
from src.profile import TeamProfile
from src.ui import football_review_view as review_module
from src.ui.football_inspect import HOVER_DELAY_MS
from src.ui.football_review_view import FootballReviewView
from src.ui.football_ui_kit import rarity_color, text_audit
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.layout import LOGICAL_SIZE
from src.ui.screens import Screen
from src.ui.theme import Theme


def _roster() -> FootballRoster:
    return FootballRoster(
        team_name="Review Owls",
        players={
            position: FootballPlayer(
                name=f"Review {position.value}",
                position=position,
                power=10,
                volatility=0,
                stamina=1,
            )
            for position in FootballPosition
        },
        coach=FootballCoach("Review Coach"),
        special_teams=FootballSpecialTeams("Review Special Teams"),
    )


def _theme(primary: str = "navy", secondary: str = "gold") -> Theme:
    return Theme.from_profile(
        TeamProfile("8ac3b6a3-2975-4db4-b4b2-e2779087e73d", "Review Owls", primary, secondary)
    )


def _view(theme: Theme, interaction: ShopReviewInteraction) -> FootballReviewView:
    if not pygame.font.get_init():
        pygame.font.init()
    return FootballReviewView(
        theme,
        pygame.font.Font(None, 14),
        pygame.font.Font(None, 18),
        interaction,
        lambda: None,
        lambda _copy_id: None,
    )


def _shop_with_copies():
    shop = FootballShop(_roster(), 17).state
    bonus_copies = tuple(
        FootballCardCopy(f"bonus-copy:{card_id}", card_id)
        for card_id in BONUS_CARD_CATALOG
    )
    offensive_deck = (
        *shop.offensive_deck,
        *bonus_copies,
        FootballCardCopy("purchased:rb-run", "rb_run"),
    )
    defensive_deck = (
        *shop.defensive_deck,
        FootballCardCopy("purchased:scheme-rb-run", "rb_run"),
    )
    owned_plays = {card.card_id for card in offensive_deck}
    owned_schemes = {card.card_id for card in defensive_deck}
    return replace(
        shop,
        offensive_deck=(
            *offensive_deck,
            *(
                FootballCardCopy(f"catalog-play:{card_id}", card_id)
                for card_id in OFFENSIVE_PLAY_CATALOG
                if card_id not in owned_plays
            ),
        ),
        defensive_deck=(
            *defensive_deck,
            *(
                FootballCardCopy(f"catalog-scheme:{card_id}", card_id)
                for card_id in DEFENSIVE_SCHEME_CATALOG
                if card_id not in owned_schemes
            ),
        ),
    )


def _interleaved_copies(shop) -> tuple[FootballCardCopy, ...]:
    result: list[FootballCardCopy] = []
    for index in range(max(len(shop.offensive_deck), len(shop.defensive_deck))):
        if index < len(shop.offensive_deck):
            result.append(shop.offensive_deck[index])
        if index < len(shop.defensive_deck):
            result.append(shop.defensive_deck[index])
    return tuple(result)


def _render(
    view: FootballReviewView,
    shop,
    *,
    surface: pygame.Surface | None = None,
    content: pygame.Rect | None = None,
):
    surface = surface or pygame.Surface(LOGICAL_SIZE)
    content = content or pygame.Rect(20, 16, 1240, 688)
    buttons = view.draw_playbook(surface, content, shop)
    return surface, content, buttons


def _cards(buttons):
    return [button for button in buttons if button.variant == "playbook-card"]


def _visible_ids(view, shop):
    return [button.copy_id for button in _cards(_render(view, shop)[2])]


def _all_ids(view, shop, interaction):
    """Every copy matching the filters, across all scroll positions."""
    interaction.playbook_scroll = 0
    seen = _visible_ids(view, shop)
    while interaction.playbook_scroll < interaction.playbook_max_scroll:
        interaction.playbook_scroll += 1
        seen += _visible_ids(view, shop)
    interaction.playbook_scroll = 0
    return list(dict.fromkeys(seen))


def _cycle_filter_with_mouse(screen: Screen, label_prefix: str) -> None:
    button = next(b for b in screen.buttons if b.label.startswith(label_prefix))
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        screen.handle_event(pygame.event.Event(event_type, {"pos": button.rect.center, "button": 1}))


def test_playbook_presents_every_owned_copy_with_catalog_rarities() -> None:
    shop = _shop_with_copies()
    interaction = ShopReviewInteraction(mode="playbook")
    view = _view(_theme(), interaction)
    ids = _all_ids(view, shop, interaction)
    assert ids == [copy.copy_id for copy in _interleaved_copies(shop)]
    labels = []
    original = review_module.blit_text

    def capture(surface, font, text, color, container, **anchor):
        labels.append((text, pygame.Color(color)))
        return original(surface, font, text, color, container, **anchor)

    review_module.blit_text = capture
    try:
        surface, _content, buttons = _render(view, shop)
        for button in _cards(buttons):
            button.draw(surface, None, None, hovered=False, pressed=False)
    finally:
        review_module.blit_text = original
    for button in _cards(_render(view, shop)[2]):
        rarity = PLAYBOOK_CARD_RARITIES[button.card_id]
        assert (rarity.value.replace("_", " ").upper(), rarity_color(rarity)) in labels


@pytest.mark.parametrize("rarity", list(FootballShopRarity))
def test_card_border_matches_rarity_label_color_and_rare_is_blue(rarity: FootballShopRarity) -> None:
    shop = _shop_with_copies()
    interaction = ShopReviewInteraction(mode="playbook", playbook_rarity=rarity)
    view = _view(_theme(), interaction)
    surface, _content, buttons = _render(view, shop)
    for button in buttons:
        if button.variant != "playbook-card":
            continue
        button.draw(surface, None, None, hovered=False, pressed=False)
        assert surface.get_at((button.rect.left, button.rect.centery))[:3] == tuple(rarity_color(rarity)[:3])
    assert rarity_color(FootballShopRarity.RARE) == pygame.Color("#65b5ff")
    assert not hasattr(review_module, "_RARITY_COLORS")


def test_purchased_copies_of_starter_play_and_scheme_remain_common() -> None:
    shop = _shop_with_copies()
    assert PLAYBOOK_CARD_RARITIES["rb_run"] is FootballShopRarity.COMMON
    interaction = ShopReviewInteraction(mode="playbook", playbook_rarity=FootballShopRarity.COMMON)
    view = _view(_theme(), interaction)
    ids = _all_ids(view, shop, interaction)
    assert {"purchased:rb-run", "purchased:scheme-rb-run"} <= set(ids)


def test_filters_cycle_by_mouse_and_keyboard_and_combine_correctly() -> None:
    shop = _shop_with_copies()
    interaction = ShopReviewInteraction(mode="playbook")
    theme = _theme()
    view = _view(theme, interaction)
    screen = Screen(theme, lambda _screen: None, lambda: None)
    screen.buttons = _render(view, shop)[2]
    _cycle_filter_with_mouse(screen, "CATEGORY")
    assert interaction.playbook_category == "offense"
    offense = set(_all_ids(view, shop, interaction))
    assert offense == {c.copy_id for c in shop.offensive_deck if c.card_id not in BONUS_CARD_CATALOG}

    screen.buttons = _render(view, shop)[2]
    _cycle_filter_with_mouse(screen, "CATEGORY")
    assert interaction.playbook_category == "defense"
    assert set(_all_ids(view, shop, interaction)) == {c.copy_id for c in shop.defensive_deck}

    screen.buttons = _render(view, shop)[2]
    screen.focus_index = next(i for i, b in enumerate(screen.buttons) if b.label.startswith("CATEGORY"))
    screen.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    assert interaction.playbook_category == "special"
    special = _all_ids(view, shop, interaction)
    assert sorted(special) == sorted(f"bonus-copy:{card_id}" for card_id in BONUS_CARD_CATALOG)

    screen.buttons = _render(view, shop)[2]
    _cycle_filter_with_mouse(screen, "POSITION")
    assert interaction.playbook_position is FootballPosition.QB
    screen.buttons = _render(view, shop)[2]
    screen.focus_index = next(i for i, b in enumerate(screen.buttons) if b.label.startswith("RARITY"))
    screen.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    assert interaction.playbook_rarity is FootballShopRarity.COMMON
    active = [b.variant for b in _render(view, shop)[2] if b.label.split(" ")[0] in ("CATEGORY", "POSITION", "RARITY")]
    assert active == ["kit-toggle-on"] * 3

    interaction.playbook_category = "all"
    interaction.playbook_rarity = None
    interaction.playbook_position = FootballPosition.QB
    qb = set(_all_ids(view, shop, interaction))
    expected = {
        copy.copy_id for copy in shop.offensive_deck
        if copy.card_id in OFFENSIVE_PLAY_CATALOG and copy.card_id not in BONUS_CARD_CATALOG
        and FootballPosition.QB in OFFENSIVE_PLAY_CATALOG[copy.card_id].contributors
    } | {
        copy.copy_id for copy in shop.defensive_deck
        if FootballPosition.QB in DEFENSIVE_SCHEME_CATALOG[copy.card_id].contributors
    }
    assert qb == expected

    interaction.playbook_category = "special"
    interaction.playbook_position = FootballPosition.RB
    with text_audit() as records:
        buttons = _render(view, shop)[2]
    assert not _cards(buttons)
    assert "NO CARDS MATCH THESE FILTERS" in {text for text, _r, _c in records}

    interaction.playbook_position = None
    interaction.playbook_rarity = FootballShopRarity.VERY_RARE
    very_rare = set(_all_ids(view, shop, interaction))
    assert very_rare == {
        f"bonus-copy:{card_id}" for card_id in BONUS_CARD_CATALOG
        if PLAYBOOK_CARD_RARITIES[card_id] is FootballShopRarity.VERY_RARE
    }


def test_playbook_filters_reset_scroll_and_keyboard_scroll_clamps() -> None:
    shop = _shop_with_copies()
    base_shop = FootballShop(_roster(), 17).state
    interaction = ShopReviewInteraction(mode="playbook")
    view = _view(_theme(), interaction)
    _render(view, shop)
    assert interaction.playbook_max_scroll > 0
    interaction.handle_scroll(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_END}))
    assert interaction.playbook_scroll == interaction.playbook_max_scroll
    interaction.cycle_playbook_category()
    assert interaction.playbook_category == "offense" and interaction.playbook_scroll == 0
    _render(view, shop)
    interaction.handle_scroll(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_PAGEDOWN}))
    assert interaction.playbook_scroll == min(interaction.playbook_page_size, interaction.playbook_max_scroll)
    interaction.handle_scroll(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_HOME}))
    assert interaction.playbook_scroll == 0
    interaction.handle_scroll(pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1}))
    assert interaction.playbook_scroll == 1
    _render(view, base_shop)
    assert interaction.playbook_max_scroll == 0 and interaction.playbook_scroll == 0


def test_removal_mode_targets_exact_copies_and_respects_the_deck_minimum() -> None:
    base = FootballShop(_roster(), 17).state
    shop = replace(
        base,
        offensive_deck=(*base.offensive_deck, FootballCardCopy("purchased:rb-run", "rb_run")),
        defensive_deck=base.defensive_deck[:4],
        pending_removal=FootballShopCard(
            card_id="remove", name="Remove One Card", description="Remove one card.",
            section=FootballShopSection.PLAYS_SCHEMES, rarity=FootballShopRarity.RARE, cost=2,
            eligible=lambda _r: True, effect=lambda r: r, is_removal=True,
        ),
    )
    removed: list[str] = []
    interaction = ShopReviewInteraction(mode="playbook")
    view = FootballReviewView(_theme(), pygame.font.Font(None, 14), pygame.font.Font(None, 18),
                              interaction, lambda: None, removed.append)
    with text_audit() as records:
        surface, _content, buttons = _render(view, shop)
        for button in _cards(buttons):
            button.draw(surface, None, None, hovered=False, pressed=False)
    assert any("REMOVAL MODE" in text for text, _r, _c in records)
    cards = _cards(buttons)
    assert all(button.label == "REMOVE" for button in cards)
    offense = [b for b in cards if b.copy_id in {c.copy_id for c in shop.offensive_deck}]
    defense = [b for b in cards if b.copy_id in {c.copy_id for c in shop.defensive_deck}]
    assert all(b.removable for b in offense) and not any(b.removable for b in defense)
    assert "DECK AT MIN" in {text for text, _r, _c in records}
    for button in defense:
        button.action()
    assert removed == []
    duplicate = next(b for b in offense if b.copy_id == "purchased:rb-run")
    assert not duplicate.hit_rect.collidepoint(duplicate.rect.midtop)
    duplicate.action()
    assert removed == ["purchased:rb-run"]
    assert next(b for b in buttons if b.label == "CANCEL SELECTION")


@pytest.mark.parametrize("category", ("offense", "defense", "special"))
def test_inspect_panel_opens_on_hover_and_closes_for_each_card_type(category: str) -> None:
    shop = _shop_with_copies()
    interaction = ShopReviewInteraction(mode="playbook", playbook_category=category)
    now = [0]
    interaction.inspect.clock = lambda: now[0]
    view = _view(_theme(), interaction)
    buttons = _render(view, shop)[2]
    card = _cards(buttons)[0]
    view.draw_playbook(pygame.Surface(LOGICAL_SIZE), pygame.Rect(20, 16, 1240, 688), shop,
                       hover_key=card.inspect_key)
    assert interaction.inspect.overlay is None
    now[0] += HOVER_DELAY_MS + 1
    view.draw_playbook(pygame.Surface(LOGICAL_SIZE), pygame.Rect(20, 16, 1240, 688), shop,
                       hover_key=card.inspect_key)
    content = interaction.inspect.overlay[0]
    full = " ".join([content.title, *(f"{h} {t}" for h, t in content.sections)])
    definition = (BONUS_CARD_CATALOG.get(card.card_id) if category == "special" else
                  OFFENSIVE_PLAY_CATALOG.get(card.card_id) if category == "offense" else
                  DEFENSIVE_SCHEME_CATALOG[card.card_id])
    assert definition.description in full and "Copy 1 of" in full
    surface = pygame.Surface(LOGICAL_SIZE)
    with text_audit() as records:
        interaction.inspect.paint(surface)
    for text, rect, container in records:
        assert container.inflate(2, 2).contains(rect), text
    assert not interaction.inspect.panel_rect.colliderect(card.rect)
    view.draw_playbook(pygame.Surface(LOGICAL_SIZE), pygame.Rect(20, 16, 1240, 688), shop)
    assert interaction.inspect.overlay is None
    interaction.inspect.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_i}),
                                     focus_key=card.inspect_key)
    close = None
    for button in view.draw_playbook(pygame.Surface(LOGICAL_SIZE), pygame.Rect(20, 16, 1240, 688), shop):
        if button.label == "CLOSE [ESC]":
            close = button
    assert close is not None and interaction.inspect.pinned_key == card.inspect_key
    assert interaction.inspect.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    assert interaction.inspect.pinned_key is None


@pytest.mark.parametrize(("primary", "secondary"), [("navy", "gold"), ("silver", "navy"), ("yellow", "green")])
@pytest.mark.parametrize("window_size", [(1280, 720), (1000, 800), (1600, 900)])
def test_playbook_text_fits_and_cards_stay_in_bounds(primary: str, secondary: str,
                                                     window_size: tuple[int, int]) -> None:
    shop = _shop_with_copies()
    interaction = ShopReviewInteraction(mode="playbook")
    view = _view(_theme(primary, secondary), interaction)
    content = pygame.Rect(20, 16, 1240, 688)
    for scroll in range(0, 3):
        interaction.playbook_scroll = scroll
        with text_audit() as records:
            surface, _content, buttons = _render(view, shop, content=content)
            for button in buttons:
                if button.variant == "playbook-card":
                    button.draw(surface, None, None, hovered=False, pressed=False)
        for text, rect, container in records:
            assert container.inflate(2, 2).contains(rect), text
        for button in buttons:
            assert content.contains(button.rect), button.label
