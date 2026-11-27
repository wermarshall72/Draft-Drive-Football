"""Music and sound-effect volumes, kept in ``settings.json`` beside the profile.

The game plays no audio yet: these values are stored for future audio code,
which reads them through ``DesktopApplication.audio_settings`` (or its
``music_gain`` / ``effects_gain`` properties). The file is not part of a run
save. A missing, damaged, or out-of-range file never blocks startup: it falls
back to the defaults (clamped and rounded to a valid step), and it is never
deleted; the next volume change simply rewrites it. No pygame here.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path

from src.persistence.atomic_io import atomic_write_text
from src.persistence.paths import app_data_dir

LOGGER = logging.getLogger(__name__)

SETTINGS_FILE_NAME = "settings.json"
SETTINGS_FORMAT_VERSION = 1
VOLUME_MIN = 0
VOLUME_MAX = 100
VOLUME_STEP = 5
DEFAULT_MUSIC_VOLUME = 70
DEFAULT_EFFECTS_VOLUME = 80


def normalize_volume(value: float) -> int:
    """Clamp to 0-100 and round half-up to the nearest multiple of 5."""
    clamped = min(VOLUME_MAX, max(VOLUME_MIN, value))
    return int(math.floor(clamped / VOLUME_STEP + 0.5)) * VOLUME_STEP


@dataclass(frozen=True)
class AudioSettings:
    music_volume: int = DEFAULT_MUSIC_VOLUME
    effects_volume: int = DEFAULT_EFFECTS_VOLUME

    def __post_init__(self) -> None:
        for name in ("music_volume", "effects_volume"):
            value = getattr(self, name)
            if (
                isinstance(value, bool) or not isinstance(value, int)
                or normalize_volume(value) != value
            ):
                raise ValueError(f"{name} must be 0-100 in steps of {VOLUME_STEP}.")

    @property
    def music_gain(self) -> float:
        """0.0-1.0 for future music playback."""
        return self.music_volume / VOLUME_MAX

    @property
    def effects_gain(self) -> float:
        """0.0-1.0 for future sound effects."""
        return self.effects_volume / VOLUME_MAX


def settings_path(directory: str | os.PathLike[str] | None = None) -> Path:
    """``settings.json`` in the app-data folder (``directory``, else ``$DDF_DATA_DIR``,
    else the OS folder), resolved on each call."""
    return app_data_dir(directory, create=False) / SETTINGS_FILE_NAME


def load_audio_settings(path: str | os.PathLike[str] | None = None) -> AudioSettings:
    """Saved volumes, or the defaults; never raises for a bad or missing file."""
    target = Path(path) if path is not None else settings_path()
    if not target.exists():
        return AudioSettings()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        LOGGER.warning("Could not read %s; using default volumes: %s", target, error)
        return AudioSettings()
    if not isinstance(data, dict):
        LOGGER.warning("%s does not hold a JSON object; using default volumes.", target)
        return AudioSettings()
    return AudioSettings(
        music_volume=_volume(data, "music_volume", DEFAULT_MUSIC_VOLUME, target),
        effects_volume=_volume(data, "effects_volume", DEFAULT_EFFECTS_VOLUME, target),
    )


def _volume(data: dict, key: str, default: int, path: Path) -> int:
    if key not in data:
        return default
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        LOGGER.warning("%s has an invalid %s (%r); using %d.", path, key, value, default)
        return default
    volume = normalize_volume(value)
    if volume != value:
        LOGGER.warning("%s has an out-of-step %s (%r); using %d.", path, key, value, volume)
    return volume


def save_audio_settings(
    settings: AudioSettings, path: str | os.PathLike[str] | None = None,
) -> None:
    """Atomically write the volumes; raises ``OSError`` on failure."""
    target = Path(path) if path is not None else settings_path()
    text = json.dumps(
        {
            "version": SETTINGS_FORMAT_VERSION,
            "music_volume": settings.music_volume,
            "effects_volume": settings.effects_volume,
        },
        indent=2,
    )
    atomic_write_text(target, text + "\n")
