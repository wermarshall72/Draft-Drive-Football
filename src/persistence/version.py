"""The game's release version, recorded in every save for diagnostics."""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import metadata
from pathlib import Path

DISTRIBUTION_NAME = "cfb-auto-battler"
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
_VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


@lru_cache(maxsize=1)
def game_version() -> str:
    """``[project] version`` from pyproject.toml, else the installed metadata."""
    try:
        text = _PYPROJECT.read_text(encoding="utf-8")
    except OSError:
        text = ""
    project = text.split("[project]", 1)[1] if "[project]" in text else ""
    match = _VERSION_LINE.search(project.split("\n[", 1)[0])
    if match:
        return match.group(1)
    try:
        return metadata.version(DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return "unknown"
