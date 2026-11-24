"""Where the game keeps its save data on each operating system.

Resolution uses only ``sys.platform`` and environment variables, so it works
the same in development, in a Steam install, and inside the Mac App Store
sandbox (where the home directory already points into the app's container).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

# The one name for the game's data folder. Changing it after release would
# orphan every player's saves (and their Steam Cloud copies): a rename must ship
# with code that moves the old folder's contents to the new one.
APP_DATA_NAME = "Draft Drive Football"

# Linux data folders conventionally use lowercase, hyphenated names.
LINUX_APP_DATA_NAME = APP_DATA_NAME.lower().replace(" ", "-")

# Points the game at another data folder (tests, debugging, portable installs).
DATA_DIR_ENV = "DDF_DATA_DIR"


def platform_data_dir(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """The OS-standard per-user data folder for the game (not created)."""
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else home
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_DATA_NAME
    if platform.startswith("win") or platform == "cygwin":
        appdata = environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / APP_DATA_NAME
    xdg = environ.get("XDG_DATA_HOME")
    # The XDG spec ignores relative paths.
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else home / ".local" / "share"
    return base / LINUX_APP_DATA_NAME


def app_data_dir(
    override: str | os.PathLike[str] | None = None,
    *,
    create: bool = True,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """The game's data folder: ``override``, else ``$DDF_DATA_DIR``, else the OS folder."""
    environ = os.environ if environ is None else environ
    if override is not None:
        directory = Path(override)
    elif environ.get(DATA_DIR_ENV):
        directory = Path(environ[DATA_DIR_ENV])
    else:
        directory = platform_data_dir(platform=platform, environ=environ, home=home)
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory
