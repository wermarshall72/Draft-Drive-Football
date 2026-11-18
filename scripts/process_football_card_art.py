"""Slice supplied football card-art sheets into transparent UI assets."""

from __future__ import annotations

import argparse
from pathlib import Path

import pygame

OUTPUT_DIR = Path(__file__).parents[1] / "src" / "ui" / "assets" / "football_cards"

OFFENSIVE_TILES = {
    "offense_rb_run.png": (21, 19, 291, 259),
    "offense_screen_pass.png": (303, 19, 573, 259),
    "offense_pa_pass.png": (21, 263, 291, 500),
    "offense_short_pass.png": (303, 504, 573, 742),
    "offense_medium_pass.png": (21, 504, 291, 742),
    "offense_deep_pass.png": (303, 263, 573, 500),
    "defense_rb_run.png": (585, 19, 856, 259),
    "defense_screen_pass.png": (868, 19, 1134, 259),
    "defense_pa_pass.png": (585, 263, 856, 500),
    "defense_short_pass.png": (868, 263, 1134, 500),
    "defense_medium_pass.png": (585, 504, 856, 742),
    "defense_deep_pass.png": (868, 504, 1134, 742),
}

BONUS_TILES = {
    "bonus_offensive_draw.png": (17, 69, 298, 367),
    "bonus_defensive_draw.png": (302, 69, 575, 367),
    "shop_remove_one_card.png": (578, 69, 857, 367),
    "bonus_opponent_discard.png": (860, 69, 1139, 367),
    "bonus_offensive_draw_discard.png": (29, 393, 397, 692),
    "bonus_defensive_draw_discard.png": (401, 393, 753, 692),
    "bonus_challenge.png": (755, 393, 1126, 692),
}

_NEUTRAL_FRAME = (80, 115, 151)


def _is_background(color: tuple[int, int, int, int]) -> bool:
    red, green, blue, _ = color
    return green > red * 1.3 and green > blue * 1.15 and green > 55


def _is_magenta_frame(color: tuple[int, int, int, int]) -> bool:
    red, green, blue, _ = color
    return (
        red > 65
        and blue > 90
        and red > green * 1.1
        and blue > green * 1.1
    )


def _slice_sheet(
    source: pygame.Surface,
    tiles: dict[str, tuple[int, int, int, int]],
    output_dir: Path,
) -> None:
    for filename, (left, top, right, bottom) in tiles.items():
        tile = pygame.Surface((right - left, bottom - top), pygame.SRCALPHA, 32)
        for y in range(tile.get_height()):
            for x in range(tile.get_width()):
                color = source.get_at((left + x, top + y))
                if _is_background(color):
                    tile.set_at((x, y), (0, 0, 0, 0))
                elif (
                    min(
                        x,
                        y,
                        tile.get_width() - 1 - x,
                        tile.get_height() - 1 - y,
                    ) <= 30
                    and _is_magenta_frame(color)
                ):
                    tile.set_at((x, y), (*_NEUTRAL_FRAME, color.a))
                else:
                    tile.set_at((x, y), color)
        pygame.image.save(tile, output_dir / filename)


def process_artwork(offensive_sheet: Path, bonus_sheet: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _slice_sheet(
        pygame.image.load(offensive_sheet),
        OFFENSIVE_TILES,
        output_dir,
    )
    _slice_sheet(
        pygame.image.load(bonus_sheet),
        BONUS_TILES,
        output_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("offensive_sheet", type=Path)
    parser.add_argument("bonus_sheet", type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    process_artwork(args.offensive_sheet, args.bonus_sheet, args.output_dir)


if __name__ == "__main__":
    main()
