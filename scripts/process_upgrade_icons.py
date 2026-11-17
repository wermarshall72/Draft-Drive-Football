"""Prepare the supplied hourglass and arrow green-screen images for the shop."""

import sys
from pathlib import Path

import pygame

OUTPUT = Path(__file__).resolve().parents[1] / "src/ui/assets"
NAMES = ("upgrade_temporary.png", "upgrade_permanent.png")


def process(source_path: str, output_path: Path) -> None:
    source = pygame.image.load(source_path)
    result = pygame.Surface(source.get_size(), pygame.SRCALPHA, 32)
    for y in range(source.get_height()):
        for x in range(source.get_width()):
            r, g, b, alpha = source.get_at((x, y))
            if g > 155 and g > r * 1.65 and g > b * 1.65:
                continue
            result.set_at((x, y), (r, g, b, alpha))
    bounds = result.get_bounding_rect()
    if not bounds:
        raise ValueError(f"No foreground found in {source_path}.")
    cropped = result.subsurface(bounds)
    scale = 128 / max(cropped.get_size())
    size = tuple(max(1, round(dimension * scale)) for dimension in cropped.get_size())
    pygame.image.save(pygame.transform.scale(cropped, size), output_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Pass the hourglass and up-arrow source image paths, in that order.")
    for path, name in zip(sys.argv[1:], NAMES):
        process(path, OUTPUT / name)
