"""The single saved run: a versioned, checksummed JSON envelope on disk.

File layout (both in the app-data folder)::

    run.json         newest save
    run.backup.json  the previous good save, rotated in before each write

Envelope::

    {
      "format": "draft-drive-football.run",
      "schema_version": 1,
      "game_version": "0.1.0",
      "saved_at": "2026-11-23T18:04:05Z",
      "checksum": "<sha256 hex of the canonical payload JSON>",
      "payload": {"run": <FootballGameController.to_save_data()>}
    }

The file is indented for reading; the checksum covers the canonical payload
JSON, ``json.dumps(payload, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)`` encoded as UTF-8, so formatting changes don't matter. The checksum
detects damage (truncation, bad sectors, partial syncs); it is not a lock, so
the file stays readable and hand-editable for anyone who recomputes it. The
file never holds absolute paths, user or machine names, or local times, so it
can sync between machines through Steam Cloud.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from src.engine.football_controller import FootballGameController
from src.engine.save_data import UnsupportedSave
from src.persistence.atomic_io import fsync_directory
from src.persistence.migrations import (
    CURRENT_SCHEMA_VERSION,
    NewerSaveVersion,
    migrate_payload,
)
from src.persistence.paths import app_data_dir
from src.persistence.version import game_version

LOGGER = logging.getLogger(__name__)

FORMAT = "draft-drive-football.run"
RUN_FILE_NAME = "run.json"
BACKUP_FILE_NAME = "run.backup.json"

Clock = Callable[[], datetime]


class LoadStatus(str, Enum):
    OK = "ok"
    RESTORED_FROM_BACKUP = "restored_from_backup"
    DAMAGED = "damaged"
    UNSUPPORTED_VERSION = "unsupported_version"  # saved by a newer build
    UNSUPPORTED = "unsupported"  # readable, but this build cannot restore it
    NONE = "none"


@dataclass(frozen=True)
class LoadResult:
    status: LoadStatus
    controller: FootballGameController | None = None
    message: str | None = None
    moved_aside: tuple[Path, ...] = ()

    @property
    def blocked(self) -> bool:
        """A save is present that must not be overwritten without asking."""
        return self.status in (LoadStatus.UNSUPPORTED_VERSION, LoadStatus.UNSUPPORTED)


class SaveBlocked(RuntimeError):
    """The existing save can't be loaded and hasn't been abandoned; it is kept."""


class _Damaged(Exception):
    """The file is not a complete, intact run-save envelope."""


def canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def payload_checksum(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def encode_envelope(payload: dict[str, Any], saved_at: datetime) -> bytes:
    """The file bytes: indented JSON whose scalar lists stay on one line."""
    envelope = {
        "format": FORMAT,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "game_version": game_version(),
        "saved_at": saved_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checksum": payload_checksum(payload),
        "payload": payload,
    }
    return (_readable_json(envelope, 0) + "\n").encode("utf-8")


def _readable_json(value: Any, level: int) -> str:
    if isinstance(value, dict):
        if not value:
            return "{}"
        pad = " " * (level + 1)
        body = ",\n".join(
            f"{pad}{json.dumps(key, ensure_ascii=False)}: {_readable_json(item, level + 1)}"
            for key, item in value.items()
        )
        return "{\n" + body + "\n" + " " * level + "}"
    if isinstance(value, list) and any(isinstance(item, (dict, list)) for item in value):
        if all(
            isinstance(item, list)
            and not any(isinstance(inner, (dict, list)) for inner in item)
            for item in value
        ):
            # e.g. deck copies [copy_id, card_id]: one pair per line.
            pad = " " * (level + 1)
            body = ",\n".join(pad + _compact(item) for item in value)
            return "[\n" + body + "\n" + " " * level + "]"
        if all(isinstance(item, list) for item in value) or len(value) <= 3:
            # RNG states ([version, [624 ints], gauss]) and short mixed lists.
            return _compact(value)
        pad = " " * (level + 1)
        body = ",\n".join(pad + _readable_json(item, level + 1) for item in value)
        return "[\n" + body + "\n" + " " * level + "]"
    return _compact(value)


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(", ", ": "))


def decode_envelope(data: bytes) -> dict[str, Any]:
    """The verified envelope; raises ``_Damaged`` for anything incomplete or altered."""
    try:
        envelope = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _Damaged(f"not valid JSON ({error})") from error
    if not isinstance(envelope, dict) or envelope.get("format") != FORMAT:
        raise _Damaged("not a Draft Drive Football run save")
    payload = envelope.get("payload")
    checksum = envelope.get("checksum")
    if not isinstance(payload, dict) or not isinstance(checksum, str):
        raise _Damaged("missing payload or checksum")
    try:
        actual = payload_checksum(payload)
    except ValueError as error:
        raise _Damaged(f"payload cannot be checked ({error})") from error
    if actual != checksum:
        raise _Damaged("checksum mismatch")
    return envelope


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunSaveStore:
    """Owns ``run.json`` and its backup in one data folder."""

    def __init__(
        self,
        directory: str | os.PathLike[str] | None = None,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._directory_override = directory
        self._clock = clock
        self._blocked = False
        # sha256 of the bytes this store last wrote or verified at run.json.
        self._known_good_digest: str | None = None

    @property
    def directory(self) -> Path:
        return app_data_dir(self._directory_override)

    @property
    def run_path(self) -> Path:
        return self.directory / RUN_FILE_NAME

    @property
    def backup_path(self) -> Path:
        return self.directory / BACKUP_FILE_NAME

    @property
    def blocked(self) -> bool:
        return self._blocked

    def exists(self) -> bool:
        return self.run_path.exists() or self.backup_path.exists()

    # -- saving --------------------------------------------------------------

    def save(self, controller: FootballGameController) -> None:
        """Write the run; raises ``OSError`` on I/O failure and ``SaveBlocked``.

        The new file is written and fsynced beside ``run.json`` first; only
        then is the current good ``run.json`` rotated to the backup and the new
        file moved into place. A failure at any step leaves the previous save
        readable (in ``run.json`` or, mid-rotation, in the backup).
        """
        if self._blocked:
            raise SaveBlocked("The existing saved run must be abandoned first.")
        payload = {"run": controller.to_save_data()}
        data = encode_envelope(payload, self._clock())
        directory = self.directory
        run_path = directory / RUN_FILE_NAME
        rotate = self._current_is_good(run_path)
        temporary = directory / f".{RUN_FILE_NAME}.{os.getpid()}.tmp"
        try:
            with open(temporary, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if rotate:
                os.replace(run_path, directory / BACKUP_FILE_NAME)
            os.replace(temporary, run_path)
        finally:
            temporary.unlink(missing_ok=True)
        fsync_directory(directory)
        self._known_good_digest = hashlib.sha256(data).hexdigest()

    def _current_is_good(self, run_path: Path) -> bool:
        """True when the existing ``run.json`` is intact and safe to rotate."""
        try:
            current = run_path.read_bytes()
        except FileNotFoundError:
            return False
        if hashlib.sha256(current).hexdigest() == self._known_good_digest:
            return True
        try:
            envelope = decode_envelope(current)
        except _Damaged:
            # Never rotate damage over the good backup; the new save replaces it.
            return False
        version = envelope.get("schema_version")
        if isinstance(version, int) and version > CURRENT_SCHEMA_VERSION:
            self._blocked = True
            raise SaveBlocked("run.json was saved by a newer version of the game.")
        return True

    # -- loading -------------------------------------------------------------

    def load(self, **controller_options: Any) -> LoadResult:
        """Load the newest restorable save, falling back to the backup."""
        self._blocked = False
        directory = self.directory
        run_path = directory / RUN_FILE_NAME
        backup_path = directory / BACKUP_FILE_NAME
        if not run_path.exists() and not backup_path.exists():
            return LoadResult(LoadStatus.NONE)
        damaged: list[Path] = []
        for path in (run_path, backup_path):
            try:
                data = path.read_bytes()
            except FileNotFoundError:
                continue
            except OSError as error:
                LOGGER.warning("Could not read %s: %s", path.name, error)
                damaged.append(path)
                continue
            try:
                envelope = decode_envelope(data)
            except _Damaged as error:
                LOGGER.warning("Run save %s is damaged: %s", path.name, error)
                damaged.append(path)
                continue
            try:
                controller = restore_controller(envelope, **controller_options)
            except NewerSaveVersion as error:
                self._blocked = True
                return LoadResult(LoadStatus.UNSUPPORTED_VERSION, message=str(error))
            except UnsupportedSave as error:
                LOGGER.warning("Run save %s cannot be restored: %s", path.name, error)
                self._blocked = True
                return LoadResult(LoadStatus.UNSUPPORTED, message=str(error))
            if path == run_path:
                self._known_good_digest = hashlib.sha256(data).hexdigest()
                return LoadResult(LoadStatus.OK, controller)
            moved = tuple(self._move_aside(bad, "damaged") for bad in damaged)
            return LoadResult(
                LoadStatus.RESTORED_FROM_BACKUP,
                controller,
                message="The latest save was damaged; the previous save was restored.",
                moved_aside=moved,
            )
        moved = tuple(self._move_aside(bad, "damaged") for bad in damaged)
        return LoadResult(
            LoadStatus.DAMAGED,
            message="The saved run was damaged and could not be loaded.",
            moved_aside=moved,
        )

    # -- removing ------------------------------------------------------------

    def delete(self) -> None:
        """Forget the saved run (it ended or was quit); the backup goes too."""
        for path in (self.run_path, self.backup_path):
            path.unlink(missing_ok=True)
        self._known_good_digest = None
        self._blocked = False

    def abandon(self) -> tuple[Path, ...]:
        """Set an unloadable save aside (kept, renamed) so a new run can be saved."""
        moved = tuple(
            self._move_aside(path, "abandoned")
            for path in (self.run_path, self.backup_path)
            if path.exists()
        )
        self._known_good_digest = None
        self._blocked = False
        return moved

    def _move_aside(self, path: Path, reason: str) -> Path:
        stamp = self._clock().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = path.name.removesuffix(".json")
        for attempt in range(1000):
            suffix = "" if attempt == 0 else f"-{attempt}"
            target = path.with_name(f"{stem}.{reason}-{stamp}{suffix}.json")
            if not target.exists():
                break
        try:
            os.replace(path, target)
        except OSError as error:
            LOGGER.warning("Could not move %s aside: %s", path.name, error)
            return path
        return target


def restore_controller(
    envelope: dict[str, Any], **controller_options: Any
) -> FootballGameController:
    """Migrate a verified envelope's payload and rebuild the run controller."""
    payload = migrate_payload(envelope["payload"], envelope.get("schema_version"))
    run = payload.get("run")
    if not isinstance(run, dict):
        raise UnsupportedSave("The save has no run.")
    return FootballGameController.from_save_data(run, **controller_options)


# -- one-call helpers -------------------------------------------------------------


def save_run(
    controller: FootballGameController, directory: str | os.PathLike[str] | None = None,
) -> None:
    RunSaveStore(directory).save(controller)


def load_run(directory: str | os.PathLike[str] | None = None) -> LoadResult:
    return RunSaveStore(directory).load()


def delete_run(directory: str | os.PathLike[str] | None = None) -> None:
    RunSaveStore(directory).delete()
