import tomllib
from pathlib import Path

import pygame

from src.engine.football import (
    DEFENSIVE_SCHEME_FAMILIES,
    FOOTBALL_PLAY_MATCHUPS,
    FOOTBALL_SCHEME_MATCHUPS,
    OFFENSIVE_PLAY_FAMILIES,
    FootballBonusCardAction,
    FootballCardFamily,
    FootballPosition,
)
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)
from src.ui.football_card_art import (
    BONUS_CARD_ART,
    CARD_ART_DIR,
    FAMILY_CARD_ART,
    REMOVE_ONE_CARD_ART,
    bonus_card_art,
    draw_card_art,
    play_card_art,
    scheme_card_art,
)

ROOT = Path(__file__).parents[1]

_EXPECTED_MATCHUPS = {
    FootballCardFamily.RB_RUN: (
        (FootballPosition.O_LINE, FootballPosition.RB),
        (FootballPosition.D_LINE, FootballPosition.LINEBACKERS),
    ),
    FootballCardFamily.SCREEN_PASS: (
        (FootballPosition.O_LINE, FootballPosition.WR),
        (FootballPosition.D_LINE, FootballPosition.CORNERBACKS),
    ),
    FootballCardFamily.PA_PASS: (
        (FootballPosition.QB, FootballPosition.RB),
        (FootballPosition.SAFETIES, FootballPosition.LINEBACKERS),
    ),
    FootballCardFamily.SHORT_PASS: (
        (FootballPosition.RB, FootballPosition.WR),
        (FootballPosition.LINEBACKERS, FootballPosition.CORNERBACKS),
    ),
    FootballCardFamily.MEDIUM_PASS: (
        (FootballPosition.QB, FootballPosition.O_LINE),
        (FootballPosition.SAFETIES, FootballPosition.D_LINE),
    ),
    FootballCardFamily.DEEP_PASS: (
        (FootballPosition.QB, FootballPosition.WR),
        (FootballPosition.SAFETIES, FootballPosition.CORNERBACKS),
    ),
}

_EXPECTED_FAMILY_ART = {
    FootballCardFamily.RB_RUN: ("offense_rb_run.png", "defense_rb_run.png"),
    FootballCardFamily.SCREEN_PASS: (
        "offense_screen_pass.png",
        "defense_screen_pass.png",
    ),
    FootballCardFamily.PA_PASS: ("offense_pa_pass.png", "defense_pa_pass.png"),
    FootballCardFamily.SHORT_PASS: (
        "offense_short_pass.png",
        "defense_short_pass.png",
    ),
    FootballCardFamily.MEDIUM_PASS: (
        "offense_medium_pass.png",
        "defense_medium_pass.png",
    ),
    FootballCardFamily.DEEP_PASS: ("offense_deep_pass.png", "defense_deep_pass.png"),
}

_EXPECTED_BONUS_ART = {
    FootballBonusCardAction.OFFENSIVE_DRAW: "bonus_offensive_draw.png",
    FootballBonusCardAction.DEFENSIVE_DRAW: "bonus_defensive_draw.png",
    FootballBonusCardAction.OPPONENT_DISCARD: "bonus_opponent_discard.png",
    FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD:
        "bonus_offensive_draw_discard.png",
    FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD:
        "bonus_defensive_draw_discard.png",
    FootballBonusCardAction.CHALLENGE: "bonus_challenge.png",
}


def test_family_art_matches_existing_contributor_matchups_and_all_named_cards() -> None:
    assert dict(FAMILY_CARD_ART) == _EXPECTED_FAMILY_ART
    assert dict(OFFENSIVE_PLAY_FAMILIES) == {
        definition.action: definition.family
        for definition in OFFENSIVE_PLAY_CATALOG.values()
    }
    assert dict(DEFENSIVE_SCHEME_FAMILIES) == {
        definition.action: definition.family
        for definition in DEFENSIVE_SCHEME_CATALOG.values()
    }
    for family, (offense, defense) in _EXPECTED_MATCHUPS.items():
        assert FOOTBALL_PLAY_MATCHUPS[family] == (offense, defense)
        assert FOOTBALL_SCHEME_MATCHUPS[family] == (defense,)
        assert FAMILY_CARD_ART[family] == _EXPECTED_FAMILY_ART[family]

    for definition in OFFENSIVE_PLAY_CATALOG.values():
        assert play_card_art(definition.family) == _EXPECTED_FAMILY_ART[
            definition.family
        ][0]
    for definition in DEFENSIVE_SCHEME_CATALOG.values():
        assert scheme_card_art(definition.family) == _EXPECTED_FAMILY_ART[
            definition.family
        ][1]


def test_bonus_and_shop_only_service_art_matches_supplied_tiles() -> None:
    assert dict(BONUS_CARD_ART) == _EXPECTED_BONUS_ART
    assert set(BONUS_CARD_ART) == {
        definition.action for definition in BONUS_CARD_CATALOG.values()
    }
    assert all(
        bonus_card_art(definition.action) == _EXPECTED_BONUS_ART[definition.action]
        for definition in BONUS_CARD_CATALOG.values()
    )
    assert REMOVE_ONE_CARD_ART == "shop_remove_one_card.png"
    assert "remove_one_card" not in BONUS_CARD_CATALOG


def test_packaged_art_is_transparent_visible_and_uses_neutral_frames() -> None:
    filenames = {*_EXPECTED_BONUS_ART.values(), REMOVE_ONE_CARD_ART}
    filenames.update(
        filename
        for pair in _EXPECTED_FAMILY_ART.values()
        for filename in pair
    )
    assert len(filenames) == 19
    for filename in filenames:
        image = pygame.image.load(CARD_ART_DIR / filename)
        assert image.get_at((0, 0)).a == 0
        assert image.get_at((image.get_width() - 1, image.get_height() - 1)).a == 0
        pixels = [
            image.get_at((x, y))
            for y in range(image.get_height())
            for x in range(image.get_width())
        ]
        assert any(pixel.a > 0 for pixel in pixels)
        assert sum(
            pixel.a > 0 and tuple(pixel)[:3] == (80, 115, 151)
            for pixel in pixels
        ) > 500
        assert not any(
            pixel.a > 0
            and pixel.g > pixel.r * 1.3
            and pixel.g > pixel.b * 1.15
            and pixel.g > 55
            for pixel in pixels
        )
        assert not any(
            pixel.a > 0
            and pixel.r > 120
            and pixel.b > 120
            and pixel.g < 100
            and pixel.r > pixel.g * 1.5
            and pixel.b > pixel.g * 1.5
            for pixel in pixels
        )


def test_card_art_packaging_and_scaling_preserve_pixels() -> None:
    package_data = tomllib.loads((ROOT / "pyproject.toml").read_text())[
        "tool"
    ]["setuptools"]["package-data"]["src.ui"]
    assert "assets/football_cards/*.png" in package_data

    source = pygame.image.load(CARD_ART_DIR / REMOVE_ONE_CARD_ART)
    surface = pygame.Surface((100, 100), pygame.SRCALPHA, 32)
    destination = draw_card_art(surface, REMOVE_ONE_CARD_ART, pygame.Rect(10, 10, 80, 60))
    assert pygame.Rect(10, 10, 80, 60).contains(destination)
    source_pixels = {
        tuple(source.get_at((x, y)))
        for y in range(source.get_height())
        for x in range(source.get_width())
    }
    assert {
        tuple(surface.get_at((x, y)))
        for y in range(destination.top, destination.bottom)
        for x in range(destination.left, destination.right)
    } <= source_pixels


def test_play_action_defense_tile_includes_safety_plus_linebacker_glyph() -> None:
    image = pygame.image.load(CARD_ART_DIR / "defense_pa_pass.png")

    def is_ink(x: int, y: int) -> bool:
        color = image.get_at((x, y))
        return color.a > 0 and max(color.r, color.g, color.b) < 55

    horizontal_stroke = [x for x in range(50, 105) if is_ink(x, 163)]
    vertical_stroke = [y for y in range(138, 188) if is_ink(77, y)]
    assert horizontal_stroke[0] < 60 and horizontal_stroke[-1] > 95
    assert vertical_stroke[0] < 148 and vertical_stroke[-1] > 178
