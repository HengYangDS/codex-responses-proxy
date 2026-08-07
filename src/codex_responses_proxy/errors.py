"""Failure vocabulary shared by installation and native service boundaries."""

from __future__ import annotations


class UnsupportedPlatform(RuntimeError):
    """Report that no service adapter exists for the current operating system."""


class InstallError(RuntimeError):
    """Report a fail-closed installation, route, or lifecycle contract violation."""


class ProductAssemblyError(RuntimeError):
    """Report that a released executable is missing an internal product component."""


class ManualStartRequired(RuntimeError):
    """Report that durable service persistence could not be established."""
