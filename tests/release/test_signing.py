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
