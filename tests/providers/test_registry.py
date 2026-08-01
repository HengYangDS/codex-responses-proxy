#!/usr/bin/env python3
"""Declarative provider registry and closed wire-policy extension contracts."""

from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.providers import registry  # noqa: E402


def _policy_source(version: str) -> str:
    return (
        "COOLDOWN_CAPACITY = 1\n"
        "COOLDOWN_SECONDS = 1\n"
        f"POLICY_VERSION = {version!r}\n"
        "def is_classified_error(status, payload): return False\n"
        "def exhausted_payload(attempts): return b'{}'\n"
        f"def policy_fingerprint(raw): return {version!r}\n"
    )


def _manifest(root: Path, text: str) -> Path:
    path = root / "codex_responses_proxy/providers/manifest.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@contextmanager
def _policy_package(root: Path, name: str, modules: Mapping[str, str]) -> Iterator[str]:
    package = root / name
    policies = package / "policies"
    policies.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (policies / "__init__.py").write_text("", encoding="utf-8")
    for module, source in modules.items():
        (policies / f"{module}.py").write_text(source, encoding="utf-8")
    prefix = f"{name}.policies"
    with (
        mock.patch.object(registry, "POLICY_PACKAGE", prefix),
        mock.patch.object(sys, "path", [str(root), *sys.path]),
    ):
        try:
            yield prefix
        finally:
            for module in tuple(sys.modules):
                if module == name or module.startswith(f"{name}."):
                    sys.modules.pop(module, None)


class ProviderRegistryTests(unittest.TestCase):
    def test_accepts_only_absolute_http_upstream_urls(self) -> None:
        self.assertEqual(
            registry._base_url("test", "https://example.test/"), "https://example.test"
        )
        self.assertEqual(
            registry._base_url("test", "https://example.test:8443/v1"),
            "https://example.test:8443/v1",
        )
        self.assertEqual(
            registry._base_url("test", "http://127.0.0.1:8791/v1/"),
            "http://127.0.0.1:8791/v1",
        )
        invalid = (
            None,
            "",
            "https://example.test/with space",
            "http://example.test",
            "https://user:secret@example.test",
            "https://example.test?route=other",
            "https://example.test#fragment",
            "https://example.test:bad",
            "not-a-url",
        )
        for value in invalid:
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(
                    ValueError, "^provider 'test' base_url must be an absolute HTTP\\(S\\) URL$"
                ),
            ):
                registry._base_url("test", value)

    def test_manifest_loader_rejects_each_closed_schema_boundary(self) -> None:
        documents = (
            "not toml = [",
            "version = 2\n[providers.dmxapi]\nbase_url = 'https://x.test'\n",
            "version = 1\n",
            "version = 1\ndefault = 'dmxapi'\n[providers.dmxapi]\nbase_url = 'https://x.test'\n",
            "version = 1\n[providers.Bad]\nbase_url = 'https://x.test'\n",
            "version = 1\n[providers.x]\nbase_url = 'https://x.test'\nextra = true\n",
            "version = 1\n[providers.x]\nbase_url = 'https://x.test'\npolicy = 'unknown'\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for document in documents:
                with self.subTest(document=document), self.assertRaises(ValueError):
                    registry.load(_manifest(root, document))
            loaded = registry.load(
                _manifest(
                    root,
                    "version = 1\n"
                    "[providers.dmxapi]\nbase_url = 'https://x.test/v1/'\npolicy = 'dmxapi'\n",
                )
            )
        self.assertIsNotNone(loaded.profiles["dmxapi"].empty_response)
        with self.assertRaises(ValueError):
            registry.load(Path("does-not-exist.toml"))

    def test_ordinary_provider_requires_only_one_manifest_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loaded = registry.load(
                _manifest(
                    Path(directory),
                    "version = 1\n"
                    "[providers.new-gateway]\nbase_url = 'https://gateway.example/v1'\n",
                )
            )
        self.assertEqual(tuple(loaded.profiles), ("new-gateway",))
        self.assertEqual(loaded.profiles["new-gateway"].base_url, "https://gateway.example/v1")
        self.assertIsNone(loaded.profiles["new-gateway"].empty_response)

    def test_special_policy_is_one_module_plus_one_manifest_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loaded = registry.load(
                _manifest(
                    Path(directory),
                    "version = 1\n"
                    "[providers.gateway]\nbase_url = 'https://gateway.example/v1'\n"
                    "policy = 'dmxapi'\n",
                )
            )
        policy = loaded.profiles["gateway"].empty_response
        self.assertIsNotNone(policy)
        assert policy is not None
        self.assertEqual(policy.POLICY_VERSION, "empty-response-retry-v1")
        self.assertFalse(hasattr(policy, "build_fallback"))
        self.assertFalse(hasattr(policy, "recover_dialogue"))
        self.assertEqual(
            registry.policy_module_names(loaded),
            ("codex_responses_proxy.providers.policies.dmxapi",),
        )

    def test_policy_loader_rejects_path_missing_and_incomplete_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with _policy_package(
                root, "invalid_policy_fixture", {"incomplete": "POLICY_VERSION = 'v1'\n"}
            ):
                documents = (
                    "policy = '../escape'\n",
                    "policy = 'missing'\n",
                    "policy = 'incomplete'\n",
                )
                for declaration in documents:
                    with self.subTest(declaration=declaration), self.assertRaises(ValueError):
                        registry.load(
                            _manifest(
                                root,
                                "version = 1\n[providers.gateway]\n"
                                "base_url = 'https://gateway.example/v1'\n" + declaration,
                            )
                        )

    def test_policy_module_identity_is_package_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with _policy_package(root, "first_policy_fixture", {"shared": _policy_source("first")}):
                first = registry.load(
                    _manifest(
                        root,
                        "version = 1\n[providers.gateway]\n"
                        "base_url = 'https://gateway.example/v1'\npolicy = 'shared'\n",
                    )
                )
            with _policy_package(
                root, "second_policy_fixture", {"shared": _policy_source("second")}
            ):
                second = registry.load(root / "codex_responses_proxy/providers/manifest.toml")
        first_policy = first.profiles["gateway"].empty_response
        second_policy = second.profiles["gateway"].empty_response
        assert first_policy is not None and second_policy is not None
        self.assertEqual(
            (first_policy.POLICY_VERSION, second_policy.POLICY_VERSION), ("first", "second")
        )

    def test_failed_manifest_load_leaves_no_policy_module_residue(self) -> None:
        cases = (
            (
                "later provider",
                "version = 1\n"
                "[providers.first]\nbase_url = 'https://first.example/v1'\npolicy = 'first'\n"
                "[providers.second]\nbase_url = 'https://second.example/v1'\npolicy = 'missing'\n",
            ),
            (
                "explicit default",
                "version = 1\ndefault = 'first'\n"
                "[providers.first]\nbase_url = 'https://first.example/v1'\npolicy = 'first'\n",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with _policy_package(
                root, "atomic_policy_fixture", {"first": _policy_source("first")}
            ) as prefix:
                module_name = f"{prefix}.first"
                for label, document in cases:
                    with self.subTest(label=label), self.assertRaises(ValueError):
                        registry.load(_manifest(root, document))
                    self.assertNotIn(module_name, sys.modules)

    def test_loaded_policy_module_must_live_inside_its_declared_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside.py"
            outside.write_text("outside\n", encoding="utf-8")
            with _policy_package(root, "boundary_policy_fixture", {}) as prefix:
                fake = ModuleType(f"{prefix}.escape")
                fake.__file__ = str(outside)
                fake.__dict__.update(
                    COOLDOWN_CAPACITY=1,
                    COOLDOWN_SECONDS=1,
                    POLICY_VERSION="escape",
                    is_classified_error=lambda status, payload: False,
                    exhausted_payload=lambda attempts: b"{}",
                    policy_fingerprint=lambda raw: "escape",
                )
                with (
                    mock.patch.dict(sys.modules, {fake.__name__: fake}),
                    self.assertRaises(ValueError),
                ):
                    registry.load(
                        _manifest(
                            root,
                            "version = 1\n[providers.gateway]\n"
                            "base_url = 'https://gateway.example/v1'\npolicy = 'escape'\n",
                        )
                    )

    def test_public_loader_does_not_expose_an_arbitrary_policy_package(self) -> None:
        self.assertEqual(tuple(inspect.signature(registry.load).parameters), ("path",))

    def test_policy_import_failure_is_a_clean_manifest_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with _policy_package(
                root,
                "broken_policy_fixture",
                {"broken": "raise RuntimeError('module initialization failed')\n"},
            ) as prefix:
                with self.assertRaisesRegex(ValueError, "provider policy 'broken' is unavailable"):
                    registry.load(
                        _manifest(
                            root,
                            "version = 1\n[providers.gateway]\n"
                            "base_url = 'https://gateway.example/v1'\npolicy = 'broken'\n",
                        )
                    )
                self.assertNotIn(f"{prefix}.broken", sys.modules)

    def test_registry_rejects_ambiguous_or_malformed_request_targets(self) -> None:
        routes = registry.Registry({"gateway": registry.Profile("gateway", "https://x.test")})
        for path in ("http://[invalid", "https://x.test/v1/responses", "/v2/responses"):
            with self.subTest(path=path):
                self.assertIsNone(routes.resolve(path))

    def test_registry_resolves_only_declared_provider_routes(self) -> None:
        routes = registry.Registry(
            {
                "alpha": registry.Profile("alpha", "https://alpha.example/v1"),
                "beta": registry.Profile("beta", "https://beta.example/v1"),
            },
        )
        self.assertEqual(
            routes.resolve("/alpha/v1/responses"),
            (routes.profiles["alpha"], "https://alpha.example/v1/responses"),
        )
        self.assertEqual(
            routes.resolve("/beta/v1/models?limit=1"),
            (routes.profiles["beta"], "https://beta.example/v1/models?limit=1"),
        )
        for path in (
            "/v1/responses",
            "/unknown/v1/responses",
            "/alpha/other",
            "/beta/v2/responses",
        ):
            with self.subTest(path=path):
                self.assertIsNone(routes.resolve(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
