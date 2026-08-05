"""Repository governance, release-metadata, and privacy-surface contracts."""

from __future__ import annotations

import ntpath
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from codex_responses_proxy import errors
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import install
from codex_responses_proxy.relay import config as runtime_config
import pytest

ROOT = Path(__file__).resolve().parents[2]


class TestInstallationInputValidation:
    def test_home_dir_expands_the_runtime_user_home(self, *, mocker):
        mocker.patch.object(runtime_config.os.path, "expanduser", return_value="/portable/home")
        assert runtime_config.home_dir() == "/portable/home"

    def test_product_roots_are_portable_and_explicitly_overridable(self, subtests, *, mocker):
        cases = (
            (
                {"CODEX_RESPONSES_PROXY_HOME": "~/payload"},
                {"os.name": "posix", "sys.platform": "linux"},
                ("payload", ".local/state/codex-responses-proxy"),
            ),
            (
                {"CODEX_RESPONSES_PROXY_STATE_HOME": "~/state"},
                {"os.name": "posix", "sys.platform": "darwin"},
                ("Library/Application Support/codex-responses-proxy", "state"),
            ),
            (
                {"LOCALAPPDATA": "/portable/local"},
                {"os.name": "nt", "sys.platform": "win32"},
                (
                    "/portable/local/codex-responses-proxy",
                    "/portable/local/codex-responses-proxy/state",
                ),
            ),
            (
                {"XDG_DATA_HOME": "/portable/data", "XDG_STATE_HOME": "/portable/state"},
                {"os.name": "posix", "sys.platform": "linux"},
                ("/portable/data/codex-responses-proxy", "/portable/state/codex-responses-proxy"),
            ),
        )
        for environment, platform, expected in cases:
            mocker.patch.dict(runtime_config.os.environ, environment, clear=True)
            mocker.patch.object(runtime_config.os, "name", platform["os.name"])
            mocker.patch.object(runtime_config.sys, "platform", platform["sys.platform"])
            mocker.patch.object(runtime_config, "home_dir", return_value="/home/tester")
            with subtests.test(platform=platform):
                assert runtime_config.data_dir().endswith(expected[0])
                assert runtime_config.state_dir().endswith(expected[1])

    def test_runtime_configuration_is_loopback_only_and_rejects_invalid_ports(self, subtests):
        assert runtime_config.listener_host() == "127.0.0.1"
        for value in ("0", "65536", "not-a-port"):
            with (
                subtests.test(value=value),
                pytest.raises(runtime_config.ConfigurationError),
            ):
                runtime_config.listener_port({runtime_config.PROXY_PORT_ENV: value})

    def test_runtime_log_defaults_share_the_portable_state_owner(self, *, mocker):
        mocker.patch.dict(runtime_config.os.environ, {}, clear=True)
        mocker.patch.object(runtime_config, "state_dir", return_value="/portable/state")
        assert runtime_config.proxy_log_path() == "/portable/state/proxy.log"
        assert runtime_config.watchdog_log_path() == "/portable/state/watchdog.log"

    def test_runtime_path_overrides_expand_against_the_supplied_home(self):
        environment = {
            "HOME": "/portable/home",
            runtime_config.HOME_ENV: "~/payload",
            runtime_config.STATE_HOME_ENV: "~/state",
        }
        assert runtime_config.data_dir(environment) == "/portable/home/payload"
        assert runtime_config.state_dir(environment) == "/portable/home/state"

    def test_posix_overrides_are_not_reinterpreted_by_a_windows_host(self, *, mocker):
        environment = {
            "HOME": "/portable/home",
            runtime_config.HOME_ENV: "~/payload",
            runtime_config.STATE_HOME_ENV: "/portable/state",
        }
        mocker.patch.object(runtime_config.os, "path", ntpath)
        assert runtime_config.data_dir(environment) == "/portable/home/payload"
        assert runtime_config.state_dir(environment) == "/portable/state"

    def test_service_projection_is_derived_from_one_runtime_contract(self):
        context = runtime_context.RuntimeContext(
            home="/home/team",
            install_dir="/opt/proxy",
            executable="/opt/proxy/bin/codex-responses-proxy",
            log_dir="/var/state/proxy",
            port=8808,
            upstream_timeout=45.0,
        )
        environment = context.service_environment()
        assert set(environment) == {
            runtime_config.PROXY_PORT_ENV,
            runtime_config.PROXY_LOG_ENV,
            runtime_config.WATCHDOG_LOG_ENV,
            runtime_config.PROXY_LOG_MAX_BYTES_ENV,
            runtime_config.PROXY_LOG_BACKUP_COUNT_ENV,
            runtime_config.WATCHDOG_LOG_MAX_BYTES_ENV,
            runtime_config.WATCHDOG_LOG_BACKUP_COUNT_ENV,
            runtime_config.UPSTREAM_TIMEOUT_ENV,
            runtime_config.UPSTREAM_READ_TIMEOUT_ENV,
            runtime_config.WATCHDOG_INTERVAL_ENV,
            runtime_config.WATCHDOG_MAX_BACKOFF_ENV,
        }
        assert runtime_config.load(environment).listener == ("127.0.0.1", 8808)
        assert environment[runtime_config.UPSTREAM_TIMEOUT_ENV] == "45.0"

    def test_fixed_process_capacity_is_not_a_user_setting(self):
        retired_names = {
            "RESPONSES_MAX_CONCURRENCY_ENV",
            "RESPONSES_QUEUE_TIMEOUT_ENV",
            "DEFAULT_RESPONSES_MAX_CONCURRENCY",
            "DEFAULT_MAX_CONCURRENT_RESPONSES",
            "DEFAULT_RESPONSES_QUEUE_TIMEOUT",
        }
        assert retired_names.isdisjoint(vars(runtime_config))
        settings = runtime_config.load({})
        assert {"responses_max_concurrency", "responses_queue_timeout"}.isdisjoint(
            settings.__dataclass_fields__
        )

    def test_runtime_settings_have_one_owner_and_strict_validation(self, subtests):
        environment = {
            runtime_config.PROXY_PORT_ENV: "8801",
            runtime_config.PROXY_LOG_MAX_BYTES_ENV: "8192",
            runtime_config.PROXY_LOG_BACKUP_COUNT_ENV: "4",
            runtime_config.WATCHDOG_LOG_MAX_BYTES_ENV: "12288",
            runtime_config.WATCHDOG_LOG_BACKUP_COUNT_ENV: "5",
            runtime_config.UPSTREAM_TIMEOUT_ENV: "30",
            runtime_config.UPSTREAM_READ_TIMEOUT_ENV: "15.5",
            runtime_config.WATCHDOG_INTERVAL_ENV: "3",
            runtime_config.WATCHDOG_MAX_BACKOFF_ENV: "12",
        }
        settings = runtime_config.load(environment)
        assert settings.listener == ("127.0.0.1", 8801)
        assert settings.proxy_log.max_bytes == 8192
        assert settings.proxy_log.backup_count == 4
        assert settings.watchdog_log.max_bytes == 12288
        assert settings.watchdog_log.backup_count == 5
        assert settings.upstream_timeout == 30
        assert settings.upstream_read_timeout == 15.5
        assert settings.watchdog_interval == 3
        assert settings.watchdog_max_backoff == 12

        invalid = (
            (runtime_config.PROXY_PORT_ENV, True),
            (runtime_config.PROXY_LOG_MAX_BYTES_ENV, "4095"),
            (runtime_config.PROXY_LOG_BACKUP_COUNT_ENV, "11"),
            (runtime_config.UPSTREAM_TIMEOUT_ENV, "0"),
            (runtime_config.UPSTREAM_READ_TIMEOUT_ENV, "infinity"),
            (runtime_config.WATCHDOG_INTERVAL_ENV, "-1"),
            (runtime_config.WATCHDOG_MAX_BACKOFF_ENV, "not-a-number"),
            (runtime_config.WATCHDOG_MAX_BACKOFF_ENV, False),
        )
        for name, value in invalid:
            with (
                subtests.test(name=name, value=value),
                pytest.raises(runtime_config.ConfigurationError),
            ):
                runtime_config.load(cast("Mapping[str, str]", {name: value}))

    def test_build_context_rejects_out_of_range_ports(self, subtests):
        for port in (0, -1, 65536):
            with subtests.test(port=port), pytest.raises(errors.InstallError):
                install.build_context(port)

    def test_build_context_rejects_out_of_bounds_log_retention(self, subtests):
        invalid = (
            {"proxy_log_max_bytes": 4095},
            {"proxy_log_backup_count": -1},
            {"watchdog_log_max_bytes": 64 * 1024 * 1024 + 1},
            {"watchdog_log_backup_count": 11},
        )
        for kwargs in invalid:
            with subtests.test(kwargs=kwargs), pytest.raises(errors.InstallError):
                install.build_context(8791, **kwargs)


class TestGovernanceMetadata:
    def test_product_module_names_do_not_shadow_the_standard_library(self):
        collisions = sorted(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "src" / "codex_responses_proxy").rglob("*.py")
            if path.stem != "__init__" and path.stem in sys.stdlib_module_names
        )
        assert collisions == []

    def test_listener_port_literals_have_one_production_owner(self):
        production = ROOT / "src" / "codex_responses_proxy"
        owner = production / "relay" / "config.py"
        owner_text = owner.read_text(encoding="utf-8")
        assert owner_text.count("8792") == 1
        assert "8791" not in owner_text
        copied = []
        for source in production.rglob("*.py"):
            if source == owner:
                continue
            text = source.read_text(encoding="utf-8")
            if "8791" in text or "8792" in text:
                copied.append(source.relative_to(ROOT).as_posix())
        assert copied == []

    def test_current_surfaces_use_the_single_replay_owner_and_package_commands(self, subtests):
        """Reject retired artifacts and stale descriptions of the current product."""
        for retired in ("config.example", "evolution/ledger.toml"):
            assert not (ROOT / retired).exists(), retired

        current_surfaces = {
            "README.md": (
                "dedicated semantic-preserving fallback",
                "config.example",
                "tests scripts",
            ),
            "openspec/specs/provider-portable-responses/spec.md": (
                "Classified DMX fallback",
                "one bounded fallback",
            ),
            "docs/evidence/README.md": ("prefer the loopback `control.py",),
            "tools/reliability/observe.py": ("control.py status --json output",),
            "src/codex_responses_proxy/lifecycle/install.py": (
                "inspect `control.py status --json`",
            ),
        }
        for relative, stale_phrases in current_surfaces.items():
            source = (ROOT / relative).read_text(encoding="utf-8")
            for phrase in stale_phrases:
                with subtests.test(path=relative, phrase=phrase):
                    assert phrase not in source

    def test_publication_actors_and_trust_anchors_are_execution_inputs(self):
        tracked = (
            ROOT / "packaging" / "release" / "publication-context.toml",
            ROOT / "packaging" / "release" / "publication-policy.toml",
            ROOT / "packaging" / "release" / "gitlab-allowed-signers",
            ROOT / "packaging" / "release" / "github-allowed-signers",
            ROOT / "packaging" / "release" / "commit-allowed-signers",
        )
        assert not [path for path in tracked if path.exists()]
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "packaging/release/publication-context.toml" in ignored
        assert "packaging/release/*-allowed-signers" in ignored
        assert "packaging/release/commit-allowed-signers" in ignored

    def test_forge_publication_has_no_implicit_actor_or_trust_source(self):
        context = ROOT / "tools" / "forge" / "context.sh"
        assert context.is_file()
        assert not (ROOT / "tools" / "forge" / "provider-context.sh").exists()
        sources = [
            context.read_text(encoding="utf-8"),
            (ROOT / "tools" / "forge" / "check-tag-signature.sh").read_text(encoding="utf-8"),
            (ROOT / "tools" / "release" / "tag-gitlab.sh").read_text(encoding="utf-8"),
            (ROOT / "tools" / "release" / "tag-github.sh").read_text(encoding="utf-8"),
        ]
        for source in sources:
            assert "$root/packaging/release" not in source
            assert "/Users/" not in source
            assert "$HOME/.ssh" not in source
        assert "CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT" in sources[0]
        assert "CODEX_RESPONSES_PROXY_RELEASE_ALLOWED_SIGNERS" in sources[1]

    def test_semantic_packages_replace_retired_flat_modules_without_facades(self):
        retired = ("platform_adapters", "proxy")
        assert not [path for path in retired if (ROOT / path).exists()]
        packages = "cli lifecycle protocol providers relay service".split()
        for package in (f"src/codex_responses_proxy/{name}" for name in packages):
            source = (ROOT / package / "__init__.py").read_text(encoding="utf-8")
            assert "import " not in source, package

    def test_runtime_context_has_one_semantic_owner(self):
        assert (ROOT / "src/codex_responses_proxy/lifecycle/context.py").is_file()
        assert not (ROOT / "src/codex_responses_proxy/lifecycle/layout.py").exists()

    def test_provider_specific_wire_policies_have_a_semantic_owner(self):
        assert not (ROOT / "src/codex_responses_proxy/providers/dmxapi.py").exists()
        assert (ROOT / "src/codex_responses_proxy/providers/policies/dmxapi.py").is_file()
        source = (ROOT / "src/codex_responses_proxy/providers/registry.py").read_text(
            encoding="utf-8"
        )
        assert "from codex_responses_proxy.providers import dmxapi" not in source
        assert "_POLICIES" not in source

    def test_publication_authority_has_no_scripts_module_loader(self):
        source = (ROOT / "tools/release/publication/__init__.py").read_text(encoding="utf-8")
        assert "importlib" not in source
        assert "sys.modules" not in source
        assert not tuple((ROOT / "tools" / "release").glob("publication_proof*.py"))

    def test_collaboration_has_one_append_only_projection_surface(self, subtests):
        assert not (ROOT / "tools" / "forge" / "rewrite-provider-history.py").exists()
        projector = ROOT / "tools" / "forge" / "project.sh"
        assert projector.is_file()
        assert not tuple((ROOT / "tools" / "forge").glob("project-*.sh"))
        source = projector.read_text(encoding="utf-8")
        for destructive in ("filter-branch", "filter-repo", "push --force", "push -f"):
            with subtests.test(destructive=destructive):
                assert destructive not in source
        assert "commit-tree -S" in source
        assert 'git_transport -C "$repository" push' in source

    def test_pre_push_admission_distinguishes_commits_and_annotated_tags(self):
        hook = ROOT / ".githooks/pre-push"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", root], check=True)
            subprocess.run(["git", "-C", root, "config", "user.name", "Test"], check=True)
            subprocess.run(
                ["git", "-C", root, "config", "user.email", "test@example.invalid"],
                check=True,
            )
            (root / "tracked").write_text("accepted\n", encoding="utf-8")
            subprocess.run(["git", "-C", root, "add", "tracked"], check=True)
            subprocess.run(["git", "-C", root, "commit", "-qm", "accepted"], check=True)
            head = subprocess.check_output(
                ["git", "-C", root, "rev-parse", "HEAD"], text=True
            ).strip()
            subprocess.run(["git", "-C", root, "tag", "-a", "v1.0.0", "-m", "release"], check=True)
            tag = subprocess.check_output(
                ["git", "-C", root, "rev-parse", "v1.0.0"], text=True
            ).strip()
            bin_dir = root / "bin"
            bin_dir.mkdir()
            calls = root / "calls"
            fake_ethos = bin_dir / "ethos"
            fake_ethos.write_text(
                '#!/bin/sh\nprintf "<%s>" "$@" >> "$ETHOS_CALLS"\nprintf "\\n" >> "$ETHOS_CALLS"\n',
                encoding="utf-8",
            )
            fake_ethos.chmod(0o755)
            environment = os.environ | {
                "ETHOS_CALLS": str(calls),
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            }

            branch_input = f"refs/heads/dev {head} refs/heads/main {'0' * 40}\n"
            subprocess.run(
                ["sh", hook, "origin", "unused"],
                cwd=root,
                input=branch_input,
                text=True,
                env=environment,
                check=True,
            )
            tag_input = f"refs/tags/v1.0.0 {tag} refs/tags/v1.0.0 {'0' * 40}\n"
            subprocess.run(
                ["sh", hook, "origin", "unused"],
                cwd=root,
                input=tag_input,
                text=True,
                env=environment,
                check=True,
            )

            recorded = calls.read_text(encoding="utf-8").splitlines()
            assert f"<hook><pre-push><refs/heads/main><{head}>" in recorded[0]
            assert f"<hook><pre-push><refs/tags/v1.0.0><{head}>" in recorded[1]

            subprocess.run(["git", "-C", root, "tag", "lightweight"], check=True)
            lightweight = subprocess.check_output(
                ["git", "-C", root, "rev-parse", "lightweight"], text=True
            ).strip()
            rejected = subprocess.run(
                ["sh", hook, "origin", "unused"],
                cwd=root,
                input=f"refs/tags/lightweight {lightweight} refs/tags/lightweight {'0' * 40}\n",
                text=True,
                env=environment,
                capture_output=True,
                check=False,
            )
            assert rejected.returncode != 0
            assert "annotated tag" in rejected.stderr

            orphan_tree = subprocess.check_output(
                ["git", "-C", root, "mktree"], input="", text=True
            ).strip()
            orphan = subprocess.check_output(
                ["git", "-C", root, "commit-tree", orphan_tree, "-m", "orphan"], text=True
            ).strip()
            subprocess.run(
                ["git", "-C", root, "tag", "-a", "outside", orphan, "-m", "outside"],
                check=True,
            )
            outside = subprocess.check_output(
                ["git", "-C", root, "rev-parse", "outside"], text=True
            ).strip()
            rejected = subprocess.run(
                ["sh", hook, "origin", "unused"],
                cwd=root,
                input=f"refs/tags/outside {outside} refs/tags/outside {'0' * 40}\n",
                text=True,
                env=environment,
                capture_output=True,
                check=False,
            )
            assert rejected.returncode != 0
            assert "outside the current accepted history" in rejected.stderr

    def test_lifecycle_never_reads_or_prescribes_client_state(self):
        text = "\n".join(
            Path(ROOT, relative).read_text(encoding="utf-8").lower()
            for relative in (
                "src/codex_responses_proxy/lifecycle/install.py",
                "src/codex_responses_proxy/lifecycle/uninstall.py",
            )
        )
        assert "fully " + "quit & reopen" not in text
        assert "start a " + "new codex thread" not in text
        assert "conversation" not in text
        assert "config.toml" not in text

    def test_installed_control_has_no_payload_upgrade_or_controller_patch_plane(self):
        source = Path(ROOT, "src/codex_responses_proxy/lifecycle/control.py").read_text(
            encoding="utf-8"
        )
        for retired in (
            "apply-control-plane",
            "upgrade_from_stage",
            "commit_payload_transaction",
            "--stage",
        ):
            assert retired not in source

    def test_payload_mutation_accepts_no_raw_source_or_stage_path(self):
        payload_source = Path(
            ROOT, "src", "codex_responses_proxy", "lifecycle", "transaction.py"
        ).read_text(encoding="utf-8")
        install_source = Path(ROOT, "src/codex_responses_proxy/lifecycle/install.py").read_text(
            encoding="utf-8"
        )
        for retired in (
            "stage_payload_transaction",
            "commit_payload_transaction",
            "restore_payload_transaction",
            "finalize_payload_transaction",
        ):
            assert retired not in payload_source
        assert "--stage-only" not in install_source


class TestReleaseMetadata:
    def test_control_and_data_planes_keep_explicit_privacy_boundaries(self, subtests):
        cases = (
            (
                ("src/codex_responses_proxy/lifecycle/control.py",),
                ("def status",),
                ("AIGW", "ChatGPT", "JetBrains"),
            ),
            (
                ("src/codex_responses_proxy/service/entrypoint.py",),
                (),
                (
                    "CODEX_RESPONSES_PROXY_DUMP_BODIES",
                    "CODEX_RESPONSES_PROXY_DUMP_HEADERS",
                    "reject-",
                ),
            ),
            (
                ("src/codex_responses_proxy/relay/config.py",),
                (
                    "CODEX_RESPONSES_PROXY_PROXY_LOG_MAX_BYTES",
                    "CODEX_RESPONSES_PROXY_PROXY_LOG_BACKUP_COUNT",
                    "CODEX_RESPONSES_PROXY_WATCHDOG_LOG_MAX_BYTES",
                    "CODEX_RESPONSES_PROXY_WATCHDOG_LOG_BACKUP_COUNT",
                ),
                (),
            ),
        )
        for paths, required, forbidden in cases:
            source = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in paths)
            with subtests.test(paths=paths):
                for value in required:
                    assert value in source
                for value in forbidden:
                    assert value not in source

    def test_mit_license_is_present(self):
        license_text = Path(ROOT, "LICENSE").read_text(encoding="utf-8")
        assert license_text.startswith("MIT License\n")
