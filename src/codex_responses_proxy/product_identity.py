"""Canonical product identity shared by runtime and release projections."""

from __future__ import annotations

PRODUCT_SLUG = "codex-responses-proxy"
DISPLAY_NAME = "Codex Responses Proxy"
PACKAGE_NAME = PRODUCT_SLUG
COMMAND_NAME = PRODUCT_SLUG
ENVIRONMENT_PREFIX = PRODUCT_SLUG.replace("-", "_").upper()
SERVICE_ID = f"{PRODUCT_SLUG}.watchdog"
RELEASE_NAMESPACE = f"{PRODUCT_SLUG}-release"
RELEASE_PRINCIPAL = RELEASE_NAMESPACE


def environment_name(suffix: str) -> str:
    """Return one product-scoped environment-variable name."""
    return f"{ENVIRONMENT_PREFIX}_{suffix}"


def executable_name(*, windows: bool) -> str:
    """Return the public executable name for one platform family."""
    return f"{COMMAND_NAME}.exe" if windows else COMMAND_NAME


def release_title(tag: str) -> str:
    """Return the canonical human-facing release title."""
    return f"{DISPLAY_NAME} {tag}"


def command(*arguments: str) -> str:
    """Return one user-facing command line rooted at the public executable."""
    return " ".join((COMMAND_NAME, *arguments))
