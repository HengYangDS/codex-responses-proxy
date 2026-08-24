"""Publish one immutable GitLab-native release asset set."""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.error
import urllib.request
from enum import StrEnum
from pathlib import Path

from codex_responses_proxy import product_identity
from tools.release import assemble_assets
from tools.release import identity
from tools.release import signing


class GitLabPublishError(RuntimeError):
    """GitLab publication failed or conflicts with immutable identity."""


class CredentialKind(StrEnum):
    """GitLab credential semantics admitted by the publication adapter."""

    JOB_TOKEN = "job-token"
    PRIVATE_TOKEN = "private-token"


def _authentication_header(kind: CredentialKind) -> str:
    """Return the GitLab header owned by one declared credential kind."""
    match kind:
        case CredentialKind.JOB_TOKEN:
            return "JOB-TOKEN"
        case CredentialKind.PRIVATE_TOKEN:
            return "PRIVATE-TOKEN"


def _request(
    url: str,
    token: str,
    credential_kind: CredentialKind,
    *,
    data: bytes | None = None,
    method: str = "GET",
) -> bytes:
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header(_authentication_header(credential_kind), token)
    if data is not None and method == "POST":
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:
            content: object = response.read()
            if not isinstance(content, bytes):
                raise GitLabPublishError("GitLab publication response is not binary")
            return content
    except urllib.error.HTTPError as error:
        if error.code == 409:
            raise FileExistsError(url) from error
        raise GitLabPublishError(f"GitLab publication failed with HTTP {error.code}") from error
    except (OSError, urllib.error.URLError) as error:
        raise GitLabPublishError("GitLab publication transport failed") from error


def _verify(assets: Path, trust: str) -> list[str]:
    """Verify one complete pre-signed bundle without changing its bytes."""
    try:
        signing.verify(assets=assets, trust=trust)
        assemble_assets.verify(assets)
    except (OSError, ValueError, signing.SignatureError) as error:
        raise GitLabPublishError("release asset signature verification failed") from error
    return sorted(path.name for path in assets.iterdir() if path.is_file())


def publish(
    *,
    api_base: str,
    project_id: int,
    tag: str,
    token: str,
    credential_kind: CredentialKind,
    source: Path,
    trust: str,
) -> str:
    """Upload, re-download, verify, then create or validate one GitLab Release."""
    if not api_base.startswith(("http://", "https://")) or not identity.is_tag(tag):
        raise GitLabPublishError("GitLab API base or release tag is invalid")
    if project_id < 1 or not source.is_dir() or source.is_symlink():
        raise GitLabPublishError("GitLab project or release asset directory is invalid")
    with tempfile.TemporaryDirectory(
        prefix=f"{product_identity.PRODUCT_SLUG}-gitlab-release-"
    ) as name:
        root, downloaded = Path(name) / "assets", Path(name) / "downloaded"
        shutil.copytree(source, root)
        downloaded.mkdir()
        names = _verify(root, trust)
        asset_base = (
            f"{api_base.rstrip('/')}/projects/{project_id}/packages/generic/"
            f"{product_identity.PRODUCT_SLUG}/{tag}"
        )
        for asset_name in names:
            payload = (root / asset_name).read_bytes()
            try:
                _request(
                    f"{asset_base}/{asset_name}",
                    token,
                    credential_kind,
                    data=payload,
                    method="PUT",
                )
            except FileExistsError:
                pass
            received = _request(f"{asset_base}/{asset_name}", token, credential_kind)
            (downloaded / asset_name).write_bytes(received)
            if received != payload:
                raise GitLabPublishError(f"GitLab release asset differs after upload: {asset_name}")
        if _verify(downloaded, trust) != names:
            raise GitLabPublishError("GitLab release asset inventory differs after upload")
        release = {
            "tag_name": tag,
            "name": product_identity.release_title(tag),
            "description": "Provider-native source release. See CHANGELOG.md for user-relevant changes.",
            "assets": {
                "links": [
                    {
                        "name": item,
                        "url": f"{asset_base}/{item}",
                        "link_type": "package",
                    }
                    for item in names
                ]
            },
        }
        endpoint = f"{api_base.rstrip('/')}/projects/{project_id}/releases"
        try:
            _request(
                endpoint,
                token,
                credential_kind,
                data=json.dumps(release).encode(),
                method="POST",
            )
            return "created"
        except FileExistsError:
            existing = json.loads(_request(f"{endpoint}/{tag}", token, credential_kind))
            links = sorted(link.get("name") for link in existing.get("assets", {}).get("links", []))
            if (
                existing.get("tag_name") != tag
                or existing.get("name") != release["name"]
                or links != names
            ):
                raise GitLabPublishError(
                    "existing GitLab release does not match immutable identity"
                ) from None
            return "matched"
