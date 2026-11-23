"""Prepare the supplied green-screen flip-arrows and info icons for review screens."""

import sys
from pathlib import Path

from process_stat_icons import process

OUTPUT = Path(__file__).resolve().parents[1] / "src/ui/assets"
NAMES = ("flip_arrows.png", "info_badge.png")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Pass the flip-arrows and info source image paths, in that order.")
    for path, name in zip(sys.argv[1:], NAMES):
        process(path, OUTPUT / name)
