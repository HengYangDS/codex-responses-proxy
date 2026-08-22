"""Canonical release-version and annotated-tag identities."""

from __future__ import annotations

import re
from typing import Final

_SEMVER: Final = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_RELEASE_TAG: Final = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def is_version(value: str) -> bool:
    """Return whether ``value`` is one strict release SemVer."""
    return _SEMVER.fullmatch(value) is not None


def is_tag(value: str) -> bool:
    """Return whether ``value`` is one strict annotated release-tag name."""
    return _RELEASE_TAG.fullmatch(value) is not None


def version_from_tag(value: str) -> str:
    """Return strict SemVer from one valid release tag."""
    if not is_tag(value):
        raise ValueError("release tag must be exact vMAJOR.MINOR.PATCH")
    return value[1:]
