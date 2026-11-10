import argparse
from collections.abc import Sequence
from os import PathLike

from src.application import ApplicationController
from src.db.schema import DB_PATH, DatabasePath
from src.profile import PROFILE_PATH
from src.ui.application import DesktopApplication


def main(
    argv: Sequence[str] | None = None,
    *,
    profile_path: str | PathLike[str] = PROFILE_PATH,
    db_path: DatabasePath = DB_PATH,
) -> None:
    parser = argparse.ArgumentParser(description="Open the CFB Auto-Battler desktop shell.")
    parser.add_argument("--profile-path", default=str(profile_path))
    parser.add_argument("--db-path", default=str(db_path))
    args = parser.parse_args(argv)
    controller = ApplicationController(args.profile_path, args.db_path)
    DesktopApplication(controller).run()


if __name__ == "__main__":
    main()
