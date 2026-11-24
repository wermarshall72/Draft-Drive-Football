"""Crash-safe file replacement shared by the profile and the run save."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: str | os.PathLike[str], data: bytes) -> None:
    """Replace ``path`` with ``data`` so readers see the old file or the new one.

    The bytes go to a temporary file in the same folder, are flushed and
    fsynced, then ``os.replace`` swaps them into place. On any failure the
    temporary file is removed and the existing file is left untouched.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
        temporary_path = None
        fsync_directory(target.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def atomic_write_text(path: str | os.PathLike[str], text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def fsync_directory(directory: str | os.PathLike[str]) -> None:
    """Persist a rename on POSIX; Windows cannot open folders, so it is skipped."""
    if os.name != "posix":
        return
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
