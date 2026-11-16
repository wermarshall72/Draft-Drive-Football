import pygame
import pytest

from src.engine.football import FootballPosition
from src.engine.football_appearance import FootballPlayerAppearance, POSITION_ART
from src.ui import player_art
from src.ui.player_art import SKIN_TONES, _player_layers, _tinted_player


def test_position_art_mapping() -> None:
    assert dict(POSITION_ART) == {
        FootballPosition.QB: "quarterback",
        FootballPosition.RB: "running_back",
        FootballPosition.WR: "wide_receiver",
        FootballPosition.O_LINE: "lineman",
        FootballPosition.D_LINE: "lineman",
        FootballPosition.LINEBACKERS: "linebacker",
        FootballPosition.CORNERBACKS: "defensive_back",
        FootballPosition.SAFETIES: "defensive_back",
    }


@pytest.mark.parametrize("key", (*dict.fromkeys(POSITION_ART.values()), "heisman"))
def test_packaged_layers_preserve_background_grass_and_isolate_tints(key: str) -> None:
    layers = _player_layers(key)
    masks = [pygame.mask.from_surface(layer) for layer in layers]
    assert all(mask.count() > 0 for mask in masks)
    for i, mask in enumerate(masks):
        assert not mask.get_at((0, 0))
        for other in masks[i + 1:]:
            assert mask.overlap(other, (0, 0)) is None

    grass = (255, 500)
    assert masks[0].get_at(grass)
    assert not any(mask.get_at(grass) for mask in masks[1:])
    primary, secondary, skin = (20, 70, 180), (245, 180, 30), SKIN_TONES[1]
    image = _tinted_player(primary, secondary, skin, key)
    alternatives = (
        _tinted_player((200, 30, 50), secondary, skin, key),
        _tinted_player(primary, (40, 200, 80), skin, key),
        _tinted_player(primary, secondary, SKIN_TONES[5], key),
    )
    assert all(image.get_at(grass) == other.get_at(grass) for other in alternatives)
    for mask, other in zip(masks[1:], alternatives):
        point = mask.centroid()
        # A centroid can lie outside an irregular mask; use an actual mask point.
        if not mask.get_at(point):
            point = next((x, y) for y in range(mask.get_size()[1])
                         for x in range(mask.get_size()[0]) if mask.get_at((x, y)))
        assert image.get_at(point) != other.get_at(point)


def test_appearance_rejects_bad_data() -> None:
    with pytest.raises(ValueError):
        FootballPlayerAppearance("unknown", (0, 0, 0), (0, 0, 0), (0, 0, 0))
    with pytest.raises(ValueError):
        FootballPlayerAppearance("quarterback", (256, 0, 0), (0, 0, 0), (0, 0, 0))


@pytest.mark.parametrize("position", tuple(FootballPosition))
def test_hover_pose_uses_supplied_heisman_without_changing_appearance(
    position: FootballPosition, monkeypatch,
) -> None:
    appearance = FootballPlayerAppearance(
        POSITION_ART[position], SKIN_TONES[4], (20, 70, 180), (245, 180, 30)
    )
    calls = []
    original = player_art._tinted_player

    def capture(primary, secondary, skin, asset_key):
        calls.append((primary, secondary, skin, asset_key))
        return original(primary, secondary, skin, asset_key)

    monkeypatch.setattr(player_art, "_tinted_player", capture)
    surface = pygame.Surface((220, 220))
    player_art.draw_draft_player(surface, surface.get_rect(), appearance)
    player_art.draw_draft_player(surface, surface.get_rect(), appearance, True)
    assert calls == [
        (appearance.primary, appearance.secondary, appearance.skin, appearance.asset_key),
        (appearance.primary, appearance.secondary, appearance.skin, "heisman"),
    ]


@pytest.mark.parametrize("key,point", [
    ("quarterback", (70, 70)),
    ("running_back", (170, 235)),
    ("wide_receiver", (430, 50)),
])
def test_football_remains_in_untinted_base(key: str, point: tuple[int, int]) -> None:
    base, *masks = _player_layers(key)
    assert base.get_at(point).a
    assert not any(mask.get_at(point).a for mask in masks)


@pytest.mark.parametrize("key,jersey,ball,lace,hand", [
    ("running_back", ((225, 210), (230, 220), (230, 245)),
     (155, 230), (170, 223), (155, 265)),
    ("heisman", ((205, 215),), (155, 230), (160, 220), (150, 265)),
])
def test_jersey_near_ball_is_tinted_without_recoloring_ball(
    key: str, jersey: tuple[tuple[int, int], ...], ball: tuple[int, int],
    lace: tuple[int, int], hand: tuple[int, int],
) -> None:
    base, primary, secondary, skin = _player_layers(key)
    colors = ((20, 210, 40), (200, 30, 50), (25, 50, 180))
    for point in jersey:
        assert primary.get_at(point).a
        assert not base.get_at(point).a
    for point in (ball, lace):
        assert base.get_at(point).a
        assert not any(mask.get_at(point).a for mask in (primary, secondary, skin))
    assert skin.get_at(hand).a
    images = [_tinted_player(color, (60, 110, 120), SKIN_TONES[2], key) for color in colors]
    for point in jersey:
        assert len({tuple(image.get_at(point)) for image in images}) == len(colors)
    for point in (ball, lace, hand):
        assert all(image.get_at(point) == images[0].get_at(point) for image in images)
