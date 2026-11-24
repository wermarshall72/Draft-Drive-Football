"""Step-by-step upgrades of older run-save payloads.

Each entry in ``MIGRATIONS`` upgrades a payload from ``schema_version`` N to
N + 1 and works only on plain dicts (never on engine objects, which change
over time). To change the save format:

1. Bump ``CURRENT_SCHEMA_VERSION``.
2. Register ``MIGRATIONS[old] = _migrate_old_to_new`` that rewrites the old
   payload into the new shape (e.g. map a retired card ID to its replacement).
3. Add a fixture-based test next to ``test_migration_template`` in
   ``tests/test_run_save.py``.

A migration may raise ``UnsupportedSave`` when an old save cannot be carried
forward; the player is then offered to abandon it.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, MutableMapping
from typing import Any

from src.engine.save_data import UnsupportedSave

CURRENT_SCHEMA_VERSION = 1

Migration = Callable[[dict[str, Any]], dict[str, Any]]

# schema_version N -> function returning the payload at N + 1.
MIGRATIONS: MutableMapping[int, Migration] = {}


class NewerSaveVersion(UnsupportedSave):
    """The save was written by a newer build (for example via Steam Cloud)."""


def migrate_payload(
    payload: dict[str, Any],
    from_version: int,
    *,
    to_version: int = CURRENT_SCHEMA_VERSION,
    migrations: MutableMapping[int, Migration] | None = None,
) -> dict[str, Any]:
    """Upgrade ``payload`` to ``to_version``; the input is never modified."""
    registry = MIGRATIONS if migrations is None else migrations
    if isinstance(from_version, bool) or not isinstance(from_version, int):
        raise UnsupportedSave("The save has no valid schema version.")
    if from_version > to_version:
        raise NewerSaveVersion(
            f"Saved by a newer version of the game (save format {from_version}, "
            f"this build reads up to {to_version})."
        )
    upgraded = copy.deepcopy(payload) if from_version < to_version else payload
    for version in range(from_version, to_version):
        step = registry.get(version)
        if step is None:
            raise UnsupportedSave(
                f"Save format {from_version} is too old to upgrade (no step from {version})."
            )
        upgraded = step(upgraded)
        if not isinstance(upgraded, dict):
            raise UnsupportedSave(f"Upgrading save format {version} failed.")
    return upgraded
