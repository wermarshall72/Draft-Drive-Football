"""Prepare the supplied green-screen power, stamina, and volatility icons."""

import sys
from collections import deque
from pathlib import Path

import pygame

OUTPUT = Path(__file__).resolve().parents[1] / "src/ui/assets/stat_icons"
NAMES = ("power.png", "stamina.png", "volatility.png")
ICON_SIZE = 128


def _is_key_green(color: pygame.Color) -> bool:
    return color.g > 150 and color.g > color.r * 1.6 and color.g > color.b * 1.6


def process(source_path: str, output_path: Path) -> None:
    source = pygame.image.load(source_path)
    width, height = source.get_size()
    background = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        queue.extend(((0, y), (width - 1, y)))
    # Flood from the border so green artwork enclosed by outlines (the battery
    # charge) survives while the connected backdrop is removed.
    while queue:
        x, y = queue.popleft()
        if not (0 <= x < width and 0 <= y < height) or background[y * width + x]:
            continue
        if not _is_key_green(source.get_at((x, y))):
            continue
        background[y * width + x] = 1
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    result = pygame.Surface((width, height), pygame.SRCALPHA, 32)
    for y in range(height):
        for x in range(width):
            if not background[y * width + x]:
                result.set_at((x, y), source.get_at((x, y)))
    bounds = result.get_bounding_rect()
    if not bounds:
        raise ValueError(f"No foreground found in {source_path}.")
    cropped = result.subsurface(bounds)
    scale = ICON_SIZE / max(cropped.get_size())
    size = tuple(max(1, round(dimension * scale)) for dimension in cropped.get_size())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(pygame.transform.scale(cropped, size), output_path)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Pass the power, stamina, and volatility source image paths, in that order.")
    for path, name in zip(sys.argv[1:], NAMES):
        process(path, OUTPUT / name)
