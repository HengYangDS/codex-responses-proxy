"""Validated JSON value types shared by product boundaries."""

from __future__ import annotations

import math
from collections.abc import Mapping
from collections.abc import Sequence
from types import MappingProxyType
from typing import TypeGuard

type JsonScalar = bool | int | float | str | None
type JsonValue = JsonScalar | JsonObject | list[JsonValue]
# ``object`` is intentional at object access sites: JSON is validated recursively
# once at ingress, then each schema owner narrows its own fields before use.
type JsonObject = dict[str, object]
type ReadOnlyJsonObject = Mapping[str, object]
type FrozenJsonObject = Mapping[str, object]


def is_json_value(value: object) -> TypeGuard[JsonValue]:
    """Return whether ``value`` is finite JSON with string object keys."""
    if value is None or isinstance(value, bool | int | str):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and is_json_value(item) for key, item in value.items())
    return False


def is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether ``value`` is a validated JSON object."""
    return isinstance(value, dict) and is_json_value(value)


def freeze_object(value: object) -> FrozenJsonObject:
    """Recursively freeze a validated JSON object."""
    if not is_json_object(value):
        raise TypeError("expected a finite JSON object with string keys")

    def freeze(item: object) -> object:
        if isinstance(item, Mapping):
            return MappingProxyType({key: freeze(child) for key, child in item.items()})
        if isinstance(item, Sequence) and not isinstance(item, str):
            return tuple(freeze(child) for child in item)
        return item

    return MappingProxyType({key: freeze(item) for key, item in value.items()})


def thaw_value(value: object) -> object:
    """Copy frozen JSON evidence into mutable canonical JSON values."""
    if isinstance(value, Mapping):
        return {str(key): thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_value(item) for item in value]
    return value
