#!/usr/bin/env python3
"""Module-boundary contracts for the proxy transport decomposition."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY_ROOT = ROOT / "proxy"
if str(PROXY_ROOT) not in sys.path:
    sys.path.insert(0, str(PROXY_ROOT))

import control_surface  # noqa: E402
import http_surface  # noqa: E402
import responses_transport  # noqa: E402
import sse_transport  # noqa: E402


class ProxyOwnerBoundaryContracts(unittest.TestCase):
    """Keep transport owners real rather than entrypoint compatibility aliases."""

    def test_owner_modules_expose_their_direct_runtime_surfaces(self) -> None:
        self.assertTrue(callable(sse_transport.relay))
        self.assertTrue(callable(responses_transport.relay))
        self.assertTrue(callable(control_surface.send_status))
        self.assertTrue(issubclass(http_surface.Handler, object))

    def test_entrypoint_does_not_reexport_owner_symbols(self) -> None:
        source = (PROXY_ROOT / "dmx_responses_proxy.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("Handler", definitions)
        self.assertNotIn("sanitize_responses_body", definitions)
        self.assertNotIn("stream_sanitized_sse", definitions)
        self.assertNotIn("_ResilientProxyServer", definitions)

    def test_owner_modules_never_import_the_entrypoint(self) -> None:
        for relative in (
            "control_surface.py",
            "http_surface.py",
            "responses_transport.py",
            "sse_transport.py",
        ):
            tree = ast.parse((PROXY_ROOT / relative).read_text(encoding="utf-8"))
            imported = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            self.assertNotIn("dmx_responses_proxy", imported, relative)

    def test_proxy_is_an_executable_module_set_not_a_package_facade(self) -> None:
        self.assertFalse((PROXY_ROOT / "__init__.py").exists())
        entrypoint = ast.parse((PROXY_ROOT / "dmx_responses_proxy.py").read_text(encoding="utf-8"))
        self.assertFalse(
            any(isinstance(node, ast.ImportFrom) and node.level for node in ast.walk(entrypoint))
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
