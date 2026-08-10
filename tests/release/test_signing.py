"""Shared release-asset signature contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools.release import signing
import pytest


def test_sign_and_verify_uses_one_external_trust_boundary(tmp_path: Path) -> None:
    key, assets = tmp_path / "signing", tmp_path / "assets"
    assets.mkdir()
    (assets / "SHA256SUMS").write_text("abc\n", encoding="ascii")
    subprocess.run(("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)), check=True)
    public = key.with_suffix(".pub").read_text().strip()
    trust = f'codex-responses-proxy-release namespaces="codex-responses-proxy-release" {public}'

    signing.sign_and_verify(assets=assets, key=key, trust=trust)

    assert (assets / "SHA256SUMS.sig").is_file()
    assert not (assets / ".release-asset-trust").exists()


def test_sign_and_verify_rejects_missing_key_and_wrong_trust(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "SHA256SUMS").write_text("abc\n", encoding="ascii")
    with pytest.raises(signing.SignatureError):
        signing.sign_and_verify(assets=assets, key=tmp_path / "missing", trust="")


def test_signing_failure_reports_the_openssh_reason_without_traceback(
    tmp_path: Path, mocker
) -> None:
    """Keep CI failure output concise while preserving the actionable cause."""

    key, assets = tmp_path / "signing", tmp_path / "assets"
    key.write_text("incomplete private key", encoding="utf-8")
    assets.mkdir()
    (assets / "SHA256SUMS").write_text("abc\n", encoding="ascii")
    error = subprocess.CalledProcessError(
        255,
        ("ssh-keygen", "-Y", "sign"),
        stderr=b"Load key signing: error in libcrypto\n",
    )
    mocker.patch.object(subprocess, "run", side_effect=error)
    mocker.patch.object(signing.shutil, "which", return_value="/usr/bin/ssh-keygen")

    with pytest.raises(signing.SignatureError, match="OpenSSH rejected the release signing key"):
        signing.sign_and_verify(assets=assets, key=key, trust="release trust")


def test_verify_uses_external_trust_without_mutating_assets(tmp_path: Path) -> None:
    key, assets = tmp_path / "signing", tmp_path / "assets"
    assets.mkdir()
    (assets / "SHA256SUMS").write_text("abc\n", encoding="ascii")
    subprocess.run(("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)), check=True)
    public = key.with_suffix(".pub").read_text().strip()
    trust = f'codex-responses-proxy-release namespaces="codex-responses-proxy-release" {public}'
    signing.sign_and_verify(assets=assets, key=key, trust=trust)
    before = {path.name: path.read_bytes() for path in assets.iterdir()}

    signing.verify(assets=assets, trust=trust)

    assert {path.name: path.read_bytes() for path in assets.iterdir()} == before
