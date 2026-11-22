import argparse
from collections.abc import Sequence
from os import PathLike

from src.application import ApplicationController
from src.profile import PROFILE_PATH
from src.ui.application import DesktopApplication


def main(
    argv: Sequence[str] | None = None,
    *,
    profile_path: str | PathLike[str] = PROFILE_PATH,
) -> None:
    parser = argparse.ArgumentParser(description="Open the CFB Auto-Battler desktop shell.")
    parser.add_argument("--profile-path", default=str(profile_path))
    args = parser.parse_args(argv)
    controller = ApplicationController(args.profile_path)
    DesktopApplication(controller).run()


if __name__ == "__main__":
    main()
