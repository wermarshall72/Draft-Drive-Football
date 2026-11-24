import argparse
from collections.abc import Sequence
from os import PathLike

from src.application import ApplicationController
from src.persistence.paths import DATA_DIR_ENV, app_data_dir
from src.persistence.run_save import RunSaveStore
from src.profile import default_profile_path
from src.ui.application import DesktopApplication


def main(
    argv: Sequence[str] | None = None,
    *,
    profile_path: str | PathLike[str] | None = None,
) -> None:
    parser = argparse.ArgumentParser(description="Open the CFB Auto-Battler desktop shell.")
    parser.add_argument(
        "--profile-path", default=None if profile_path is None else str(profile_path),
        help="Team profile file (default: profile.json in the data folder).",
    )
    parser.add_argument(
        "--data-dir", default=None,
        help=f"Folder for the profile and saved run (default: ${DATA_DIR_ENV}, "
        "else the OS app-data folder).",
    )
    args = parser.parse_args(argv)
    data_dir = app_data_dir(args.data_dir)
    profile = args.profile_path or default_profile_path(data_dir)
    controller = ApplicationController(profile)
    DesktopApplication(controller, run_store=RunSaveStore(data_dir)).run()


if __name__ == "__main__":
    main()
