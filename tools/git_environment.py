"""Canonical environments for repository-owned Git subprocesses."""

from __future__ import annotations

import os
from collections.abc import Mapping


def isolated_config_environment(
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return the host environment without personal Git configuration."""

    environment = os.environ | {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    if overrides:
        environment.update(overrides)
    return environment
