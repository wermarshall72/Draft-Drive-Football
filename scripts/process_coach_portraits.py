"""Prepare user-supplied green-screen coach portraits for the desktop draft.

Run with the nine source paths in coach catalog order, followed by an output
directory. The magenta clothing is separated into a shaded, tintable mask.
"""

import sys
from pathlib import Path

import pygame

NAMES = (
    "ground_and_pound", "option_spread", "air_raid", "pro_style",
    "run_stop", "pressure_blitz", "coverage", "ball_hawk", "balanced",
)

# The source portraits have green grass as well as a green backdrop. Above
# these source-image rows, dark green edge pixels are backdrop spill; below
# them, the darker green shades can be part of the grass.
GRASS_TOP = {
    "ground_and_pound": 600,
    "option_spread": 590,
    "air_raid": 615,
    "pro_style": 560,
    "run_stop": 605,
    "pressure_blitz": 620,
    "coverage": 590,
    "ball_hawk": 600,
    "balanced": 635,
}


def is_background(r: int, g: int, b: int, y: int, name: str) -> bool:
    if g > 150 and g > r * 2.4 and g > b * 2.4:
        return True
    return y < GRASS_TOP[name] and g > 12 and g > r * 2 and g > b * 2


def process(source: Path, destination: Path) -> None:
    image = pygame.image.load(source)
    if image.get_size() != (768, 768):
        raise ValueError(f"Unexpected portrait size: {source}")
    base = pygame.Surface(image.get_size(), pygame.SRCALPHA)
    mask = pygame.Surface(image.get_size(), pygame.SRCALPHA)
    for y in range(image.get_height()):
        for x in range(image.get_width()):
            r, g, b, a = image.get_at((x, y))
            if is_background(r, g, b, y, destination.name):
                # The blitz coach's thin microphone boom is dark green from
                # background contamination; retain its dark pixels, not the spill.
                if (destination.name == "pressure_blitz"
                        and 437 <= x <= 462 and 166 <= y <= 188 and g < 100):
                    shade = min(r, b)
                    base.set_at((x, y), (shade, shade, shade, a))
                continue
            # Restrict the color key to the upper body, excluding the clipboard.
            clothing = (y < 430 and r > 55 and b > 45
                        and r > g * 1.5 and b > g * 1.4
                        and not (destination.name == "pro_style"
                                 and 290 < x < 355 and 315 < y < 410))
            if clothing:
                shade = max(r, b)
                mask.set_at((x, y), (shade, shade, shade, a))
            else:
                base.set_at((x, y), (r, g, b, a))
    combined = base.copy()
    combined.blit(mask, (0, 0))
    components = pygame.mask.from_surface(combined).connected_components()
    for component in components:
        if component.count() <= 12:
            for rect in component.get_bounding_rects():
                for y in range(rect.top, rect.bottom):
                    for x in range(rect.left, rect.right):
                        if component.get_at((x, y)):
                            base.set_at((x, y), (0, 0, 0, 0))
                            mask.set_at((x, y), (0, 0, 0, 0))
    bounds = base.get_bounding_rect().union(mask.get_bounding_rect())
    pygame.image.save(base.subsurface(bounds), destination.with_name(destination.name + "_base.png"))
    pygame.image.save(mask.subsurface(bounds), destination.with_name(destination.name + "_primary.png"))


if __name__ == "__main__":
    if len(sys.argv) != 11:
        raise SystemExit("Pass nine portrait paths and the output directory.")
    output = Path(sys.argv[-1])
    output.mkdir(parents=True, exist_ok=True)
    for name, path in zip(NAMES, sys.argv[1:-1]):
        process(Path(path), output / name)
