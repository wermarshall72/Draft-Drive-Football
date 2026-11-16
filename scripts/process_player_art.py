"""Convert the supplied green-screen PNGs into packaged draft sprite layers.

Pass the source paths in QB, RB, WR, lineman, linebacker, defensive-back,
Heisman order. This offline asset-preparation tool does not require Pillow.
"""

import sys
from pathlib import Path

import pygame


KEYS = ("quarterback", "running_back", "wide_receiver", "lineman", "linebacker",
        "defensive_back", "heisman")
BALLS = ((170, 140, 290, 235), (265, 315, 380, 390), (515, 120, 630, 220),
         None, None, None, (270, 315, 360, 385))
PANTS_TOP = (390, 390, 390, 380, 395, 385, 365)
HELMET_TOP_END = (181, 181, 181, 217, 205, 181, 181)
OUTPUT = Path(__file__).resolve().parents[1] / "src/ui/assets/draft_players"
CROP = pygame.Rect(145, 110, 500, 540)


def inside(x: int, y: int, box: tuple[int, int, int, int] | None) -> bool:
    return box is not None and box[0] <= x < box[2] and box[1] <= y < box[3]


def process(path: str, index: int) -> None:
    source = pygame.image.load(path)
    if source.get_size() != (768, 768):
        raise ValueError(f"{path}: expected a 768x768 source image")
    layers = [pygame.Surface(CROP.size, pygame.SRCALPHA, 32) for _ in range(4)]
    for y in range(CROP.top, CROP.bottom):
        for x in range(CROP.left, CROP.right):
            r, g, b, _ = source.get_at((x, y))
            point = (x - CROP.left, y - CROP.top)
            # The grass is muted green; only remove the saturated green screen.
            if (g > (100 if y < 540 else 175)
                    and g > r * 1.4 and g > b * 1.4):
                continue
            football = inside(x, y, BALLS[index])
            if ((not football or index in (1, 6))
                    and b > r * 1.12 and b > g * 1.5
                    and b > 48 and r > 20):
                shade = min(255, round(max(r, b) * 1.8))
                layers[1].set_at(point, (shade, shade, shade, 255))
            elif ((not football or (index in (1, 6) and g > r * 0.65))
                  and y < 600 and r > 80 and g > 45
                  and r > g * 1.15 and g > b * 1.18):
                shade = min(255, round(g * 1.35))
                layers[3].set_at(point, (shade, shade, shade, 255))
            elif (not football and max(r, g, b) - min(r, g, b) < 38
                  and min(r, g, b) > 105
                  and ((PANTS_TOP[index] <= y < 515 and 220 < x < 510)
                       or (y < HELMET_TOP_END[index] and 380 < x < 525))):
                shade = round((r + g + b) / 3)
                layers[2].set_at(point, (shade, shade, shade, 255))
            else:
                layers[0].set_at(point, (r, g, b, 255))
    for name, layer in zip(("base", "primary", "secondary", "skin"), layers):
        pygame.image.save(layer, OUTPUT / f"{KEYS[index]}_{name}.png")


if __name__ == "__main__":
    if len(sys.argv) != len(KEYS) + 1:
        raise SystemExit(__doc__)
    for index, path in enumerate(sys.argv[1:]):
        process(path, index)
