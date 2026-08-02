#!/usr/bin/env python3
"""Executable contracts for the serving package boundaries and identity SSOT."""

from __future__ import annotations

import ast
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "codex_responses_proxy"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.listener import control, server  # noqa: E402
from codex_responses_proxy.payload import digest, identity, inventory  # noqa: E402
from codex_responses_proxy.replay import request as replay_request  # noqa: E402
from codex_responses_proxy.supervision import native_service  # noqa: E402
from codex_responses_proxy.transport import responses, sse  # noqa: E402


class ProxyOwnerBoundaryContracts(unittest.TestCase):
    def test_payload_modules_never_reach_into_peer_private_symbols(self) -> None:
        payload = PACKAGE / "payload"
        violations = []
        for path in sorted(payload.glob("*.py")):
            tree = ast.parse(path.read_text())
            peers = {
                alias.asname or alias.name
                for node in tree.body
                if isinstance(node, ast.ImportFrom)
                and node.module == "codex_responses_proxy.payload"
                for alias in node.names
            }
            violations.extend(
                f"{path.relative_to(PACKAGE)}:{node.lineno}:{node.value.id}.{node.attr}"
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in peers
                and node.attr.startswith("_")
            )
        self.assertEqual(violations, [])

    def test_payload_modules_never_forward_peer_symbols(self) -> None:
        payload = PACKAGE / "payload"
        violations = []
        allowed = {
            "projection.py": {
                "RUNTIME_PAYLOAD_FILES",
                "SERVING_PAYLOAD_FILES",
                "PAYLOAD_MANIFEST_FILENAME",
                "RELEASE_RECEIPT_FILENAME",
            }
        }
        for path in sorted(payload.glob("*.py")):
            tree = ast.parse(path.read_text())
            peers = {
                alias.asname or alias.name
                for node in tree.body
                if isinstance(node, ast.ImportFrom)
                and node.module == "codex_responses_proxy.payload"
                for alias in node.names
            }
            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = {target.id for target in targets if isinstance(target, ast.Name)}
                if (
                    isinstance(value, ast.Attribute)
                    and isinstance(value.value, ast.Name)
                    and value.value.id in peers
                    and not names.issubset(allowed.get(path.name, set()))
                ):
                    violations.append(
                        f"{path.relative_to(PACKAGE)}:{node.lineno}:{value.value.id}.{value.attr}"
                    )
        self.assertEqual(violations, [])

    def test_semantic_owners_expose_direct_runtime_surfaces(self) -> None:
        self.assertTrue(callable(sse.relay))
        self.assertTrue(callable(responses.relay))
        self.assertTrue(callable(control.send_status))
        self.assertTrue(issubclass(server.Handler, object))

    def test_entrypoint_composes_without_redefining_owner_symbols(self) -> None:
        tree = ast.parse((PACKAGE / "listener" / "entrypoint.py").read_text())
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue({"create_server", "main"}.issubset(definitions))
        self.assertTrue(
            {"Handler", "sanitize_responses_body", "stream_sanitized_sse"}.isdisjoint(definitions)
        )

    def test_owner_modules_never_import_the_entrypoint(self) -> None:
        for relative in ("commands/control.py", "listener/server.py", "transport/sse.py"):
            tree = ast.parse((PACKAGE / relative).read_text())
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            self.assertNotIn("codex_responses_proxy.listener.entrypoint", imports, relative)

    def test_response_transport_has_no_listener_facade(self) -> None:
        self.assertFalse((PACKAGE / "listener" / "responses.py").exists())
        for relative in ("transport/responses.py", "transport/exchange.py", "transport/relay.py"):
            self.assertTrue((PACKAGE / relative).is_file(), relative)

    def test_packages_are_declarations_not_reexport_facades(self) -> None:
        for relative in (
            "__init__.py",
            "commands/__init__.py",
            "deployment/__init__.py",
            "listener/__init__.py",
            "payload/__init__.py",
            "recovery/__init__.py",
            "release/__init__.py",
            "replay/__init__.py",
            "runtime/__init__.py",
            "supervision/__init__.py",
            "transport/__init__.py",
        ):
            tree = ast.parse((PACKAGE / relative).read_text())
            self.assertFalse(
                any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)),
                relative,
            )

    def test_runtime_state_is_split_into_concrete_semantic_owners(self) -> None:
        self.assertFalse((PACKAGE / "runtime" / "state.py").exists())
        owners = {
            "runtime/admission.py": "admit_response",
            "runtime/operational_log.py": "log",
            "runtime/telemetry.py": "record_counter",
            "transport/cooldown.py": "remember_failure",
        }
        for relative, public_symbol in owners.items():
            with self.subTest(relative=relative):
                source = (PACKAGE / relative).read_text(encoding="utf-8")
                tree = ast.parse(source)
                definitions = {
                    node.name
                    for node in tree.body
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                }
                self.assertIn(public_symbol, definitions)

        offenders = []
        for path in sorted(PACKAGE.rglob("*.py")):
            if path.name == "__init__.py":
                continue
            source = path.read_text(encoding="utf-8")
            if "codex_responses_proxy.runtime import state" in source:
                offenders.append(path.relative_to(PACKAGE).as_posix())
        self.assertEqual(offenders, [])

    def test_replay_projection_returns_structured_metrics(self) -> None:
        result = replay_request.sanitize_responses_body(
            json.dumps(
                {
                    "store": True,
                    "previous_response_id": "rs_private",
                    "input": [
                        {"type": "reasoning", "encrypted_content": "private"},
                        {"type": "message", "role": "user", "content": "hello"},
                    ],
                }
            ).encode()
        )
        self.assertIsInstance(result, replay_request.ProjectionResult)
        self.assertEqual(result.status, "projected")
        self.assertEqual(result.metrics.reasoning_items, 1)
        self.assertEqual(result.metrics.provider_bindings, 1)
        self.assertNotIn("private", result.diagnostic())

    def test_server_bindings_are_required_and_immutable(self) -> None:
        bindings = server.Bindings(
            control.Bindings(mock.Mock(return_value={}), mock.Mock()), "dmx/test"
        )
        with (
            mock.patch.object(server, "_BINDINGS", None),
            mock.patch.object(server.Handler, "server_version", "unconfigured"),
        ):
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                server._bindings()
            server.configure(bindings)
            server.configure(bindings)
            self.assertIs(server._bindings(), bindings)
            with self.assertRaisesRegex(RuntimeError, "already configured"):
                server.configure(server.Bindings(bindings.control, "dmx/other"))

    def test_server_routes_each_method_to_one_owner(self) -> None:
        handler = object.__new__(server.Handler)
        bindings = control.Bindings(mock.Mock(return_value={}), mock.Mock())
        with (
            mock.patch.object(server, "_BINDINGS", server.Bindings(bindings, "dmx/test")),
            mock.patch.object(control, "set_drain") as drain,
            mock.patch.object(control, "prepare_handoff") as handoff,
            mock.patch.object(control, "send_status") as status,
            mock.patch.object(responses, "relay") as relay,
        ):
            for method, path, owner, arguments in (
                ("do_POST", "/control/drain", drain, (True,)),
                ("do_POST", "/control/handoff", handoff, (bindings,)),
                ("do_POST", "/v1/responses", relay, ("POST",)),
                ("do_GET", "/healthz", status, (bindings,)),
                ("do_GET", "/v1/responses", relay, ("GET",)),
                ("do_DELETE", "/control/drain", drain, (False,)),
                ("do_DELETE", "/v1/responses/resp", relay, ("DELETE",)),
                ("do_PATCH", "/v1/responses/resp", relay, ("PATCH",)),
                ("do_PUT", "/v1/responses", relay, ("PUT",)),
            ):
                with self.subTest(method=method, path=path):
                    for candidate in (drain, handoff, status, relay):
                        candidate.reset_mock()
                    handler.path = path
                    getattr(handler, method)()
                    owner.assert_called_once_with(handler, *arguments)

    def test_loaded_identity_accepts_only_exact_loaded_release(self) -> None:  # noqa: C901
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entrypoint = root / inventory.ENTRYPOINT
            entrypoint.parent.mkdir(parents=True)
            entrypoint.write_bytes(b"entrypoint\n")
            (root / "VERSION").write_text("1.2.3\n")
            provider_manifest = root / "codex_responses_proxy/providers/manifest.toml"
            provider_manifest.parent.mkdir(parents=True)
            provider_manifest.write_text(
                'version = 1\n[providers.fixture]\nbase_url = "https://fixture.invalid/v1"\n'
            )
            files = {
                relative: digest.sha256_file(root / relative)
                for relative in ("VERSION", "codex_responses_proxy/providers/manifest.toml")
            }
            for relative in inventory.SERVING_MODULES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(relative.encode())
                files[relative] = digest.sha256_file(path)
            files[inventory.ENTRYPOINT] = digest.sha256_file(entrypoint)
            manifest = {
                "release": "1.2.3",
                "release_receipt_sha256": "a" * 64,
                "serving_files": files,
                "serving_payload_sha256": inventory.serving_payload_sha256(files),
            }
            (root / inventory.MANIFEST_FILENAME).write_text(json.dumps(manifest))
            from types import ModuleType

            modules = {}
            for relative, name in inventory.SERVING_MODULES.items():
                module = ModuleType(name)
                module.__file__ = str(root / relative)
                modules[name] = module
            with mock.patch.dict(sys.modules, modules, clear=False):
                frozen = identity.freeze_loaded_payload(entrypoint)
                self.assertIsNotNone(frozen)
                wrong_entrypoint = root / "other.py"
                wrong_entrypoint.write_text("other")
                cases = (
                    ("wrong entrypoint", None, None, wrong_entrypoint),
                    ("non-object files", {"serving_files": []}, None, entrypoint),
                    ("non-string digest", {"serving_files": {"VERSION": 1}}, None, entrypoint),
                    (
                        "incomplete files",
                        {"serving_files": {"VERSION": files["VERSION"]}},
                        None,
                        entrypoint,
                    ),
                    ("missing module", None, (next(iter(modules)), None), entrypoint),
                    (
                        "missing module path",
                        None,
                        (next(iter(modules)), ModuleType("missing")),
                        entrypoint,
                    ),
                    (
                        "wrong module path",
                        None,
                        (next(iter(modules)), _module("wrong", wrong_entrypoint)),
                        entrypoint,
                    ),
                    (
                        "wrong later module path",
                        None,
                        (tuple(modules)[-1], _module("wrong", wrong_entrypoint)),
                        entrypoint,
                    ),
                    (
                        "wrong digest",
                        {"serving_files": {**files, "VERSION": "0" * 64}},
                        None,
                        entrypoint,
                    ),
                    ("wrong aggregate", {"serving_payload_sha256": "0" * 64}, None, entrypoint),
                    ("bad receipt", {"release_receipt_sha256": "bad"}, None, entrypoint),
                    ("wrong release", {"release": "9.9.9"}, None, entrypoint),
                )
                for name, changes, module_change, candidate in cases:
                    with self.subTest(name=name):
                        if changes:
                            _write_manifest(root, {**manifest, **changes})
                        with mock.patch.dict(
                            sys.modules, dict([module_change]) if module_change else {}
                        ):
                            self.assertIsNone(identity.freeze_loaded_payload(candidate))
                        _write_manifest(root, manifest)
                _write_manifest(root, [])
                self.assertIsNone(identity.freeze_loaded_payload(entrypoint))
                _write_manifest(root, manifest)
                self.assertIsNotNone(identity.freeze_loaded_payload(entrypoint))

    def test_server_hardening_and_handoff_listener_adoption(self) -> None:
        connection = mock.Mock()
        server._disable_nagle(connection)
        connection.setsockopt.assert_called_once_with(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        connection.setsockopt.side_effect = OSError
        server._disable_nagle(connection)

        with mock.patch.object(socket, "getfqdn", side_effect=AssertionError("DNS lookup")):
            created = server.ResilientProxyServer(("127.0.0.1", 0), server.Handler)
        try:
            self.assertEqual(created.server_name, "127.0.0.1")
            self.assertEqual(created.server_port, created.server_address[1])
        finally:
            created.server_close()

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        with mock.patch.object(socket, "getfqdn", side_effect=AssertionError("DNS lookup")):
            adopted = server.server_from_listener(listener)
        self.assertIs(adopted.socket, listener)
        self.assertEqual(adopted.server_address, listener.getsockname())
        self.assertEqual(adopted.server_name, "127.0.0.1")
        self.assertEqual(adopted.server_port, adopted.server_address[1])
        adopted.server_close()

    def test_server_tracks_handlers_and_classifies_disconnects(self) -> None:
        proxy = object.__new__(server.ResilientProxyServer)
        with (
            mock.patch("http.server.ThreadingHTTPServer.process_request_thread") as process,
            mock.patch.object(server.admission, "begin_handler") as begin,
            mock.patch.object(server.admission, "end_handler") as end,
        ):
            server.ResilientProxyServer.process_request_thread(proxy, None, None)
            begin.assert_called_once()
            process.assert_called_once()
            end.assert_called_once()
            process.side_effect = RuntimeError
            with self.assertRaises(RuntimeError):
                server.ResilientProxyServer.process_request_thread(proxy, None, None)
            self.assertEqual(end.call_count, 2)

        with mock.patch.object(server.operational_log, "log") as log:
            try:
                raise BrokenPipeError("closed")
            except BrokenPipeError:
                server.ResilientProxyServer.handle_error(proxy, None, None)
            log.assert_called_once()
        with mock.patch("http.server.ThreadingHTTPServer.handle_error") as fallback:
            try:
                raise RuntimeError("failed")
            except RuntimeError:
                server.ResilientProxyServer.handle_error(proxy, None, None)
            fallback.assert_called_once()

    def test_native_service_selection_is_total_for_supported_hosts(self) -> None:
        for platform, expected in (
            ("darwin", "macos"),
            ("linux", "linux"),
            ("linux2", "linux"),
            ("win32", "windows"),
            ("cygwin", "windows"),
        ):
            with self.subTest(platform=platform), mock.patch.object(sys, "platform", platform):
                self.assertEqual(native_service.adapter().__name__.rsplit(".", 1)[-1], expected)
        with (
            mock.patch.object(sys, "platform", "plan9"),
            self.assertRaisesRegex(RuntimeError, "unsupported platform: plan9"),
        ):
            native_service.adapter()


def _write_manifest(root: Path, manifest: object) -> None:
    (root / inventory.MANIFEST_FILENAME).write_text(json.dumps(manifest))


def _module(name: str, path: Path) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(path)
    return module


if __name__ == "__main__":
    unittest.main(verbosity=2)
