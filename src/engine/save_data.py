"""Shared helpers for the engine's own save-data format.

Every engine object that is part of a run owns explicit ``to_save_data`` and
``from_save_data`` methods built on these helpers. Save data is plain JSON
types only (dict, list, str, int, float, bool, None). Content is stored by
stable identifiers (card, copy, coach, player type, upgrade IDs) and enums by
``.value``; loading looks identifiers up in the current catalogs and raises
``UnsupportedSave`` for anything it does not recognize, so a schema migration
can handle it instead of the game crashing.

This module performs no file I/O and has no UI dependencies; the
``src.persistence`` package does the file work.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from enum import Enum
from typing import Any, TypeVar

E = TypeVar("E", bound=Enum)
T = TypeVar("T")


class UnsupportedSave(ValueError):
    """Save data this build cannot restore (unknown ID, bad shape, or version)."""


def rng_to_data(rng: random.Random) -> list[Any]:
    """Exact ``random.Random`` state as JSON lists (restored by ``rng_from_data``)."""
    version, internal, gauss_next = rng.getstate()
    return [version, list(internal), gauss_next]


def rng_from_data(data: Any, what: str = "random generator") -> random.Random:
    rng = random.Random()
    try:
        version, internal, gauss_next = data
        if (
            not isinstance(internal, list)
            or any(isinstance(value, bool) or not isinstance(value, int) for value in internal)
            or (gauss_next is not None and not isinstance(gauss_next, float))
        ):
            raise TypeError("invalid state values")
        rng.setstate((version, tuple(internal), gauss_next))
    except (TypeError, ValueError) as error:
        raise UnsupportedSave(f"Invalid {what} state.") from error
    return rng


def required(data: Any, key: str, kind: type | tuple[type, ...], what: str) -> Any:
    """Read one required field and check its JSON type (``bool`` is not an int)."""
    if not isinstance(data, Mapping):
        raise UnsupportedSave(f"{what} must be an object.")
    if key not in data:
        raise UnsupportedSave(f"{what} is missing {key!r}.")
    value = data[key]
    kinds = kind if isinstance(kind, tuple) else (kind,)
    if isinstance(value, bool) and bool not in kinds:
        raise UnsupportedSave(f"{what} field {key!r} has the wrong type.")
    if float in kinds and isinstance(value, int) and not isinstance(value, bool):
        return value
    if not isinstance(value, kinds):
        raise UnsupportedSave(f"{what} field {key!r} has the wrong type.")
    return value


def optional(
    data: Any, key: str, kind: type | tuple[type, ...], what: str, default: Any = None
) -> Any:
    """Read a field that is omitted (or null) when it holds its default value."""
    if not isinstance(data, Mapping):
        raise UnsupportedSave(f"{what} must be an object.")
    if data.get(key) is None:
        return default
    return required(data, key, kind, what)


def enum_value(enum_type: type[E], value: Any, what: str) -> E:
    try:
        return enum_type(value)
    except ValueError as error:
        raise UnsupportedSave(f"Unknown {what}: {value!r}.") from error


def optional_enum(enum_type: type[E], value: Any, what: str) -> E | None:
    return None if value is None else enum_value(enum_type, value, what)


def lookup(table: Mapping[str, T], key: Any, what: str) -> T:
    """Resolve a stable identifier in a current catalog."""
    if not isinstance(key, str) or key not in table:
        raise UnsupportedSave(f"Unknown {what}: {key!r}.")
    return table[key]


def items(data: Any, what: str) -> list[Any]:
    if not isinstance(data, list):
        raise UnsupportedSave(f"{what} must be a list.")
    return data


def build(what: str, factory: Callable[[], T]) -> T:
    """Run a validating constructor, reporting its ValueError as UnsupportedSave."""
    try:
        return factory()
    except UnsupportedSave:
        raise
    except (ValueError, TypeError, KeyError) as error:
        raise UnsupportedSave(f"Invalid {what}: {error}") from error
