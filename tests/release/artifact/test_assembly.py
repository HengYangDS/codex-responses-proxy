"""Contracts for deterministic, checksum-bound release assets."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.release.artifact.fixtures import native_inputs
from tools.release.artifact import __main__ as commands
from tools.release.artifact import assembly
from tools.release.artifact import format as assets


class AssemblyContracts:
    """Verify the assembly owner of native release artifacts."""

    def test_native_platform_outputs_assemble_into_one_release(self, tmp_path: Path) -> None:
        inputs = native_inputs(tmp_path)
        version = "1.2.3"
        output = tmp_path / "release"
        release = assembly.assemble(tuple(inputs), output)
        assert set(release) == assets.release_asset_names(
            version, assets.RELEASE_PLATFORMS, require_signature=False
        )
        assets.release_digests(release, version, assets.RELEASE_PLATFORMS, require_signature=False)

    def test_native_outputs_are_assembled_signed_and_verified_by_one_owner(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        inputs = native_inputs(tmp_path)
        key = tmp_path / "signing"
        subprocess.run(("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)), check=True)
        public = key.with_suffix(".pub").read_text().strip()
        trust = f'codex-responses-proxy-release namespaces="codex-responses-proxy-release" {public}'

        digests = assembly.assemble_sign_verify(
            inputs=tuple(inputs), output=tmp_path / "release", key=key, trust=trust
        )

        assert set(digests) == assets.release_asset_names("1.2.3", assets.RELEASE_PLATFORMS)
        assert key.is_file()
        assert assembly.verify(tmp_path / "release", trust=trust) == digests
        monkeypatch.setenv("RELEASE_ASSET_TRUST", trust)
        commands.main(("verify", "--assets", str(tmp_path / "release")))
        assert capsys.readouterr().out.strip() == f"verified release assets: {len(digests)} files"
