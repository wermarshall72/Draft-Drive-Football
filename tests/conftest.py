"""Keep every test away from the real home and app-data folders."""

from pathlib import Path

import pytest

from src.persistence.paths import DATA_DIR_ENV


@pytest.fixture(autouse=True)
def isolated_data_folders(tmp_path_factory: pytest.TempPathFactory,
                          monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the data folder, home, and OS app-data variables at temp folders."""
    root = tmp_path_factory.mktemp("isolated-home")
    data_dir = root / "app-data"
    monkeypatch.setenv(DATA_DIR_ENV, str(data_dir))
    monkeypatch.setenv("HOME", str(root / "home"))
    monkeypatch.setenv("USERPROFILE", str(root / "home"))
    monkeypatch.setenv("APPDATA", str(root / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(root / "xdg"))
    return data_dir


@pytest.fixture
def tips_seen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start desktops with every one-time tip already seen.

    For tests that drive Esc: a visible tip takes Esc before the pause menu does
    (see test_first_time_help.py). Clicks never need this; tips don't block them.
    """
    from src.ui import application, football_tips

    class SeenTips(football_tips.TipState):
        def __init__(self, seen=(), on_seen=lambda _tip_id: None) -> None:
            super().__init__(football_tips.TIP_IDS, on_seen)

    monkeypatch.setattr(application, "TipState", SeenTips)
