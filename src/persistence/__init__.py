"""UI-free save files: data folder, atomic writes, the run save, and migrations.

Nothing here imports pygame. Engine objects own their save-data format
(``to_save_data`` / ``from_save_data``); this package only handles files.
"""

from src.engine.save_data import UnsupportedSave
from src.persistence.paths import (
    APP_DATA_NAME,
    DATA_DIR_ENV,
    app_data_dir,
    legacy_database_path,
)
from src.persistence.run_save import (
    LoadResult,
    LoadStatus,
    RunSaveStore,
    SaveBlocked,
    delete_run,
    load_run,
    save_run,
)

__all__ = [
    "APP_DATA_NAME",
    "DATA_DIR_ENV",
    "LoadResult",
    "LoadStatus",
    "RunSaveStore",
    "SaveBlocked",
    "UnsupportedSave",
    "app_data_dir",
    "delete_run",
    "legacy_database_path",
    "load_run",
    "save_run",
]
