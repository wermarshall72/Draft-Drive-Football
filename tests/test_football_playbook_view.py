from collections import Counter
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
from src.ui.football_card_art import bonus_card_art, play_card_art, scheme_card_art
from src.ui.football_review_view import (
    FootballReviewView,
    _RARITY_COLORS,
    _category_border_color,
)
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.layout import LOGICAL_SIZE
from src.ui.screens import Screen
from src.ui.text import wrap_text_lines
from src.ui.theme import Theme, relative_luminance


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


def _capture_view(monkeypatch, view, shop, interaction):
    import src.ui.football_review_view as review_module

    texts: list[tuple[str, pygame.Rect]] = []
    wrapped: list[tuple[str, pygame.Rect]] = []
    art: list[tuple[str, pygame.Rect]] = []
    original_text = review_module.draw_text
    original_wrapped = review_module.draw_complete_wrapped_text
    original_art = review_module.draw_card_art

    def capture_text(surface, text, position, font, color):
        texts.append((text, pygame.Rect(position, font.size(text))))
        original_text(surface, text, position, font, color)

    def capture_wrapped(surface, text, rect, font, color, *, line_gap=2):
        wrapped.append((text, pygame.Rect(rect)))
        return original_wrapped(
            surface, text, rect, font, color, line_gap=line_gap
        )

    def capture_art(surface, filename, rect):
        art.append((filename, pygame.Rect(rect)))
        return original_art(surface, filename, rect)

    monkeypatch.setattr(review_module, "draw_text", capture_text)
    monkeypatch.setattr(review_module, "draw_complete_wrapped_text", capture_wrapped)
    monkeypatch.setattr(review_module, "draw_card_art", capture_art)

    def render():
        texts.clear()
        wrapped.clear()
        art.clear()
        result = _render(view, shop)
        return result, tuple(texts), tuple(wrapped), tuple(art)

    return render


def _cycle_filter_with_mouse(screen: Screen, button_index: int) -> None:
    button = screen.buttons[button_index]
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        screen.handle_event(
            pygame.event.Event(
                event_type,
                {"pos": button.rect.center, "button": 1},
            )
        )


def test_playbook_uses_catalog_rarities_and_presents_every_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop = _shop_with_copies()
    interaction = ShopReviewInteraction(mode="playbook")
    view = _view(_theme(), interaction)
    render = _capture_view(monkeypatch, view, shop, interaction)
    all_texts: list[str] = []
    all_text_bounds: list[tuple[str, pygame.Rect]] = []
    all_wrapped: list[str] = []
    all_art: list[str] = []

    _render(view, shop, surface=pygame.Surface(LOGICAL_SIZE))
    for row in range(interaction.playbook_max_scroll + 1):
        (surface, _, _), texts, wrapped, art = render()
        all_texts.extend(text for text, _ in texts)
        all_text_bounds.extend((text, rect) for text, rect in texts)
        all_wrapped.extend(text for text, _ in wrapped)
        all_art.extend(filename for filename, _ in art)
        visible_entries = _interleaved_copies(shop)[
            row * 2 : (row + interaction.playbook_page_size) * 2
        ]
        card_width = (1240 - 12) // 2
        card_height = 148
        for index, copy in enumerate(visible_entries):
            card_row, column = divmod(index, 2)
            card_left = 20 + column * (card_width + 12)
            card_top = 16 + 74 + 48 + 16 + card_row * (card_height + 10)
            badge_sample = (card_left + card_width - 102, card_top + 32)
            rarity = PLAYBOOK_CARD_RARITIES[copy.card_id]
            assert surface.get_at(badge_sample)[:3] == tuple(
                _RARITY_COLORS[rarity][:3]
            )
        if row < interaction.playbook_max_scroll:
            interaction.handle_scroll(
                pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1})
            )

    copy_labels = [text for text in all_texts if "COPY " in text]
    assert "PLAYBOOK" in all_texts
    assert "View your deck of plays" in all_texts
    assert any(
        text == "Power Toss"
        and rect.width == view._card_title_font._font.size("Power Toss")[0]
        for text, rect in all_text_bounds
    )
    assert "Remove One Card" not in all_texts
    assert {"COMMON", "UNCOMMON", "RARE", "VERY RARE"} <= set(all_texts)
    assert any("COPY 1 OF 2" in text for text in copy_labels)
    assert any("COPY 2 OF 2" in text for text in copy_labels)
    assert all(PLAYBOOK_CARD_RARITIES[key] is FootballShopRarity.COMMON
               for key in OFFENSIVE_PLAY_CATALOG)
    assert all(PLAYBOOK_CARD_RARITIES[key] is FootballShopRarity.COMMON
               for key in DEFENSIVE_SCHEME_CATALOG)
    assert {
        PLAYBOOK_CARD_RARITIES[key]
        for key in BONUS_CARD_CATALOG
    } == {
        FootballShopRarity.UNCOMMON,
        FootballShopRarity.RARE,
        FootballShopRarity.VERY_RARE,
    }

    for definition in OFFENSIVE_PLAY_CATALOG.values():
        assert definition.name in all_texts
        assert definition.description in all_wrapped
        assert play_card_art(definition.family) in all_art
    for definition in DEFENSIVE_SCHEME_CATALOG.values():
        assert definition.name in all_texts
        assert definition.description in all_wrapped
        assert scheme_card_art(definition.family) in all_art
    for definition in BONUS_CARD_CATALOG.values():
        assert definition.name in all_texts
        assert definition.description in all_wrapped
        assert bonus_card_art(definition.action) in all_art
    assert Counter(all_art)[play_card_art(OFFENSIVE_PLAY_CATALOG["rb_run"].family)] >= 7


def test_purchased_copies_of_starter_play_and_scheme_remain_common(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    play = OFFENSIVE_PLAY_CATALOG["rb_run"]
    scheme = DEFENSIVE_SCHEME_CATALOG["rb_run"]
    catalog = tuple(
        FootballShopCard(
            card_id=f"{kind}:{definition.card_id}",
            name=definition.name,
            description=definition.description,
            section=FootballShopSection.PLAYS_SCHEMES,
            rarity=FootballShopRarity.COMMON,
            cost=2,
            eligible=lambda _roster: True,
            effect=lambda roster: roster,
            football_card=definition,
        )
        for kind, definition in (("play", play), ("scheme", scheme))
    )
    shop = FootballShop(
        _roster(),
        29,
        catalogs={FootballShopSection.PLAYS_SCHEMES: catalog},
    )
    for card_id in ("play:rb_run", "scheme:rb_run"):
        for attempt in range(4):
            offered = any(
                slot.card is not None and slot.card.card_id == card_id
                for slot in shop.state.section(
                    FootballShopSection.PLAYS_SCHEMES
                ).slots
            )
            if offered:
                shop.buy_card(FootballShopSection.PLAYS_SCHEMES, card_id)
                break
            assert attempt < 3
            shop.move_to_next_day()

    owned = shop.state
    assert any(copy.copy_id.startswith("human:purchased:") for copy in owned.offensive_deck)
    assert any(copy.copy_id.startswith("human:purchased:") for copy in owned.defensive_deck)
    assert PLAYBOOK_CARD_RARITIES[play.card_id] is FootballShopRarity.COMMON
    assert PLAYBOOK_CARD_RARITIES[scheme.card_id] is FootballShopRarity.COMMON

    interaction = ShopReviewInteraction(mode="playbook")
    view = _view(_theme(), interaction)
    render = _capture_view(monkeypatch, view, owned, interaction)
    _render(view, owned, surface=pygame.Surface(LOGICAL_SIZE))
    labels: list[str] = []
    for page in range(interaction.playbook_max_scroll + 1):
        (surface, _, _), texts, _, _ = render()
        labels.extend(text for text, _ in texts if "COPY " in text)
        visible = _interleaved_copies(owned)[
            page * 2 : (page + interaction.playbook_page_size) * 2
        ]
        for index, copy in enumerate(visible):
            row, column = divmod(index, 2)
            card_width = (1240 - 12) // 2
            left = 20 + column * (card_width + 12)
            top = 16 + 74 + 48 + 16 + row * 158
            sample = (left + card_width - 102, top + 32)
            assert surface.get_at(sample)[:3] == tuple(
                _RARITY_COLORS[FootballShopRarity.COMMON][:3]
            )
        if page < interaction.playbook_max_scroll:
            interaction.handle_scroll(
                pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1})
            )

    assert any("OFFENSIVE PLAY" in label and "COPY 1 OF 2" in label for label in labels)
    assert any("OFFENSIVE PLAY" in label and "COPY 2 OF 2" in label for label in labels)
    assert any("DEFENSIVE SCHEME" in label and "COPY 1 OF 2" in label for label in labels)
    assert any("DEFENSIVE SCHEME" in label and "COPY 2 OF 2" in label for label in labels)


def test_filters_cycle_by_mouse_and_keyboard_and_combine_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop = _shop_with_copies()
    interaction = ShopReviewInteraction(mode="playbook")
    theme = _theme()
    view = _view(theme, interaction)
    render = _capture_view(monkeypatch, view, shop, interaction)
    _, _, initial_buttons = _render(
        view, shop, surface=pygame.Surface(LOGICAL_SIZE)
    )
    screen = Screen(theme, lambda _screen: None, lambda: None)
    screen.buttons = initial_buttons

    _cycle_filter_with_mouse(screen, 0)
    assert interaction.playbook_category == "offense"
    _, texts, _, art = render()
    assert all("OFFENSIVE PLAY" in text for text, _ in texts if "COPY " in text)
    assert all("bonus_" not in filename and "defense_" not in filename for filename, _ in art)

    screen.buttons = _render(view, shop, surface=pygame.Surface(LOGICAL_SIZE))[2]
    _cycle_filter_with_mouse(screen, 0)
    assert interaction.playbook_category == "defense"
    _, texts, _, art = render()
    assert all("DEFENSIVE SCHEME" in text for text, _ in texts if "COPY " in text)
    assert all(filename.startswith("defense_") for filename, _ in art)

    screen.buttons = _render(view, shop, surface=pygame.Surface(LOGICAL_SIZE))[2]
    screen.focus_index = 0
    screen.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    assert interaction.playbook_category == "special"
    _, texts, wrapped, art = render()
    assert len(art) == len(BONUS_CARD_CATALOG)
    assert all("SPECIAL CARD" in text for text, _ in texts if "COPY " in text)
    assert {name for name, _ in wrapped} >= {
        definition.description for definition in BONUS_CARD_CATALOG.values()
    }
    assert not any("YDS" in text or "BASE " in text for text, _ in texts)

    screen.buttons = _render(
        view, shop, surface=pygame.Surface(LOGICAL_SIZE)
    )[2]
    _cycle_filter_with_mouse(screen, 1)
    assert interaction.playbook_position is FootballPosition.QB
    screen.buttons = _render(
        view, shop, surface=pygame.Surface(LOGICAL_SIZE)
    )[2]
    screen.focus_index = 2
    screen.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN})
    )
    assert interaction.playbook_rarity is FootballShopRarity.COMMON
    active_buttons = _render(
        view, shop, surface=pygame.Surface(LOGICAL_SIZE)
    )[2]
    assert [button.variant for button in active_buttons[:3]] == [
        "primary",
        "primary",
        "primary",
    ]

    interaction.playbook_category = "all"
    interaction.playbook_position = None
    interaction.playbook_rarity = None
    interaction.playbook_position = FootballPosition.QB
    _, texts, _, art = render()
    expected_qb_art = {
        play_card_art(definition.family)
        for definition in OFFENSIVE_PLAY_CATALOG.values()
        if FootballPosition.QB in definition.contributors
    } | {
        scheme_card_art(definition.family)
        for definition in DEFENSIVE_SCHEME_CATALOG.values()
        if FootballPosition.QB in definition.contributors
    }
    assert set(name for name, _ in art) == expected_qb_art
    assert all("SPECIAL CARD" not in text for text, _ in texts)

    interaction.playbook_category = "special"
    interaction.playbook_position = FootballPosition.RB
    _, texts, _, art = render()
    assert not art
    assert "No cards match these filters." in {text for text, _ in texts}

    interaction.playbook_position = None
    interaction.playbook_rarity = FootballShopRarity.VERY_RARE
    _, texts, wrapped, art = render()
    expected_very_rare = {
        bonus_card_art(definition.action)
        for definition in BONUS_CARD_CATALOG.values()
        if PLAYBOOK_CARD_RARITIES[definition.card_id]
        is FootballShopRarity.VERY_RARE
    }
    assert set(name for name, _ in art) == expected_very_rare
    assert all("SPECIAL CARD" in text for text, _ in texts if "COPY " in text)
    assert len(wrapped) == len(expected_very_rare)

    interaction.playbook_category = "offense"
    interaction.playbook_position = FootballPosition.QB
    interaction.playbook_rarity = FootballShopRarity.COMMON
    _, texts, _, art = render()
    expected_common_qb_art = {
        play_card_art(definition.family)
        for definition in OFFENSIVE_PLAY_CATALOG.values()
        if FootballPosition.QB in definition.contributors
    }
    assert set(name for name, _ in art) == expected_common_qb_art
    assert all("OFFENSIVE PLAY" in text for text, _ in texts if "COPY " in text)


def test_playbook_filters_reset_scroll_and_keyboard_scroll_clamps() -> None:
    shop = _shop_with_copies()
    base_shop = FootballShop(_roster(), 17).state
    interaction = ShopReviewInteraction(mode="playbook")
    view = _view(_theme(), interaction)
    inflated_shop = replace(
        shop,
        offensive_deck=(
            *shop.offensive_deck,
            *(
                FootballCardCopy(f"extra:{index}", "rb_run")
                for index in range(20)
            ),
        ),
    )
    _render(view, inflated_shop, surface=pygame.Surface(LOGICAL_SIZE))
    assert interaction.playbook_max_scroll > 0
    interaction.handle_scroll(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_END})
    )
    assert interaction.playbook_scroll == interaction.playbook_max_scroll
    interaction.cycle_playbook_category()
    assert interaction.playbook_category == "offense"
    assert interaction.playbook_scroll == 0
    interaction.handle_scroll(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_PAGEDOWN})
    )
    assert interaction.playbook_scroll == interaction.playbook_page_size
    interaction.handle_scroll(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_HOME})
    )
    assert interaction.playbook_scroll == 0
    interaction.handle_scroll(
        pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1})
    )
    assert interaction.playbook_scroll == 1
    interaction.handle_scroll(
        pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -1})
    )
    _render(view, base_shop, surface=pygame.Surface(LOGICAL_SIZE))
    assert interaction.playbook_max_scroll == 0
    assert interaction.playbook_scroll == 0


@pytest.mark.parametrize(
    ("primary", "secondary"),
    [
        ("coral", "salmon"),
        ("navy", "royal-blue"),
        ("silver", "gold"),
    ],
)
def test_category_borders_and_labels_remain_legible_for_team_palettes(
    primary: str,
    secondary: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.ui.football_review_view as review_module

    shop = _shop_with_copies()
    theme = _theme(primary, secondary)
    interaction = ShopReviewInteraction(mode="playbook")
    view = _view(theme, interaction)
    surface, content, _ = _render(view, shop, surface=pygame.Surface(LOGICAL_SIZE))

    offense_border = _category_border_color(theme.primary, pygame.Color("#13283d"))
    defense_border = _category_border_color(theme.secondary, pygame.Color("#13283d"))
    background_luminance = relative_luminance(pygame.Color("#13283d"))
    for color in (offense_border, defense_border):
        luminance = relative_luminance(color)
        assert (max(luminance, background_luminance) + 0.05) / (
            min(luminance, background_luminance) + 0.05
        ) >= 2.5

    texts: list[str] = []
    original_text = review_module.draw_text

    def capture_text(surface, text, position, font, color):
        texts.append(text)
        original_text(surface, text, position, font, color)

    monkeypatch.setattr(review_module, "draw_text", capture_text)
    assert content.contains(pygame.Rect(20, 16, 1240, 688))
    _render(view, shop, surface=pygame.Surface(LOGICAL_SIZE))
    assert "OFFENSIVE PLAY" in " ".join(texts)
    assert "DEFENSIVE SCHEME" in " ".join(texts)
    assert surface.get_at((100, 156))[:3] == tuple(offense_border[:3])
    assert surface.get_at((100, 158))[:3] != tuple(offense_border[:3])
    assert surface.get_at((700, 156))[:3] == tuple(defense_border[:3])
    assert surface.get_at((700, 158))[:3] == tuple(defense_border[:3])
    interaction.playbook_category = "defense"
    texts.clear()
    surface, _, _ = _render(view, shop, surface=pygame.Surface(LOGICAL_SIZE))
    assert "DEFENSIVE SCHEME" in " ".join(texts)
    assert surface.get_at((100, 156))[:3] == tuple(defense_border[:3])
    assert surface.get_at((100, 158))[:3] == tuple(defense_border[:3])
    interaction.playbook_category = "special"
    surface, _, _ = _render(view, shop, surface=pygame.Surface(LOGICAL_SIZE))
    primary_border = _category_border_color(theme.primary, pygame.Color("#13283d"))
    secondary_border = _category_border_color(theme.secondary, pygame.Color("#13283d"))
    assert surface.get_at((24, 156))[:3] == tuple(primary_border[:3])
    assert surface.get_at((34, 156))[:3] == tuple(pygame.Color("#13283d")[:3])
    assert surface.get_at((39, 156))[:3] == tuple(secondary_border[:3])


@pytest.mark.parametrize("window_size", [(1280, 720), (1000, 800), (1600, 900)])
def test_playbook_content_buttons_and_scaled_bounds(
    window_size: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop = _shop_with_copies()
    interaction = ShopReviewInteraction(mode="playbook")
    view = _view(_theme(), interaction)
    render = _capture_view(monkeypatch, view, shop, interaction)
    (surface, content, buttons), texts, wrapped, art = render()

    assert all(content.contains(rect) for _, rect in texts)
    assert all(content.contains(rect) for _, rect in wrapped)
    assert all(content.contains(rect) for _, rect in art)
    assert all(content.contains(button.rect) for button in buttons)
    assert "BACK TO SHOP" == buttons[-1].label
    assert not any(button.label == "REMOVE" for button in buttons)
    text_rects = [rect for _, rect in texts]
    for index, rect in enumerate(text_rects):
        assert not any(rect.colliderect(other) for other in text_rects[index + 1 :])
        assert not any(rect.colliderect(art_rect) for _, art_rect in art)
        assert not any(rect.colliderect(button.rect) for button in buttons)
    for _, rect in wrapped:
        assert not any(rect.colliderect(art_rect) for _, art_rect in art)
        assert not any(rect.colliderect(button.rect) for button in buttons)

    removal_offer = FootballShopCard(
        card_id="remove-one-card",
        name="Remove One Card",
        description="Select one owned card to remove.",
        section=FootballShopSection.PLAYS_SCHEMES,
        rarity=FootballShopRarity.RARE,
        cost=2,
        eligible=lambda _roster: True,
        effect=lambda roster: roster,
        is_removal=True,
    )
    pending_shop = replace(shop, pending_removal=removal_offer)
    _, _, removal_buttons = _render(
        view,
        pending_shop,
        surface=pygame.Surface(LOGICAL_SIZE),
        content=content,
    )
    assert removal_buttons[-1].label == "CANCEL SELECTION"
    assert sum(button.label == "REMOVE" for button in removal_buttons) == 6
    assert all(content.contains(button.rect) for button in removal_buttons)
    assert interaction.playbook_max_scroll > 0
    interaction.handle_scroll(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_END})
    )
    _, _, scrolled_buttons = _render(
        view,
        pending_shop,
        surface=pygame.Surface(LOGICAL_SIZE),
        content=content,
    )
    assert scrolled_buttons[-1].label == "CANCEL SELECTION"
    assert sum(button.label == "REMOVE" for button in scrolled_buttons) == 6
    interaction.playbook_category = "special"
    interaction.playbook_position = FootballPosition.QB
    _, _, empty_buttons = _render(
        view,
        pending_shop,
        surface=pygame.Surface(LOGICAL_SIZE),
        content=content,
    )
    assert empty_buttons[-1].label == "CANCEL SELECTION"
    assert not any(button.label == "REMOVE" for button in empty_buttons)

    scale = min(window_size[0] / LOGICAL_SIZE[0], window_size[1] / LOGICAL_SIZE[1])
    offset_x = (window_size[0] - round(LOGICAL_SIZE[0] * scale)) // 2
    offset_y = (window_size[1] - round(LOGICAL_SIZE[1] * scale)) // 2
    bounds = [
        rect
        for _, rect in (*texts, *wrapped, *art)
    ] + [button.rect for button in buttons]
    for rect in bounds:
        left = offset_x + round(rect.left * scale)
        right = offset_x + round(rect.right * scale)
        top = offset_y + round(rect.top * scale)
        bottom = offset_y + round(rect.bottom * scale)
        assert 0 <= left <= right <= window_size[0]
        assert 0 <= top <= bottom <= window_size[1]

    for definition in OFFENSIVE_PLAY_CATALOG.values():
        for line in wrap_text_lines(definition.description, view._description_font, 382):
            assert view._description_font.size(line)[0] <= 382
