"""GitLab-native release publication contracts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.release import product_assets, publish_gitlab


def _assets(root: Path, version: str) -> None:
    release: dict[str, bytes] = {}
    for platform in product_assets.RELEASE_PLATFORMS:
        executable = (
            "codex-responses-proxy.exe"
            if platform.startswith("windows-")
            else "codex-responses-proxy"
        )
        files = {executable: product_assets.ArchiveFile(platform.encode(), 0o755)}
        archive_name = product_assets.archive_name(version, platform)
        archive = product_assets.archive_bytes(files, version, platform)
        release[archive_name] = archive
        release[product_assets.manifest_name(platform)] = product_assets.asset_manifest(
            version=version,
            platform=platform,
            archive_name=archive_name,
            archive=archive,
            files=files,
        )
    release[product_assets.CHECKSUM_NAME] = product_assets.checksums(release)
    for name, content in release.items():
        (root / name).write_bytes(content)


def test_publication_creates_and_accepts_only_exact_existing_release(
    tmp_path: Path, mocker
) -> None:
    assets, key = tmp_path / "assets", tmp_path / "signing"
    assets.mkdir()
    _assets(assets, "1.2.3")
    subprocess.run(("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)), check=True)
    public = key.with_suffix(".pub").read_text().strip()
    trust = f'codex-responses-proxy-release namespaces="codex-responses-proxy-release" {public}'
    store: dict[str, bytes] = {}
    release: dict[str, object] = {}

    def request(url: str, _token: str, *, data=None, method="GET") -> bytes:
        name = url.rsplit("/", 1)[-1]
        if "/packages/generic/" in url:
            if method == "PUT":
                store[name] = data
                return b""
            return store[name]
        if method == "POST":
            if release:
                raise FileExistsError(url)
            release.update(json.loads(data))
            return b"{}"
        return json.dumps(release).encode()

    mocker.patch.object(publish_gitlab, "_request", side_effect=request)
    arguments = dict(
        api_base="https://gitlab.example/api/v4",
        project_id=453,
        tag="v1.2.3",
        token="redacted",
        source=assets,
        key=key,
        trust=trust,
    )
    assert publish_gitlab.publish(**arguments) == "created"
    assert publish_gitlab.publish(**arguments) == "matched"
    release["name"] = "wrong"
    with pytest.raises(publish_gitlab.GitLabPublishError, match="immutable identity"):
        publish_gitlab.publish(**arguments)


def test_publication_rejects_invalid_boundary_inputs(tmp_path: Path) -> None:
    with pytest.raises(publish_gitlab.GitLabPublishError):
        publish_gitlab.publish(
            api_base="file:///tmp",
            project_id=0,
            tag="latest",
            token="redacted",
            source=tmp_path,
            key=tmp_path / "missing",
            trust="",
        )
