"""Publish one immutable GitLab-native release asset set."""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.error
import urllib.request
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from codex_responses_proxy import product_identity
from tools.release import assemble_assets
from tools.release import identity
from tools.release import signing


class GitLabPublishError(RuntimeError):
    """GitLab publication failed or conflicts with immutable identity."""


class _GitLabResourceMissingError(GitLabPublishError):
    """One exact GitLab publication resource does not exist."""


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
        try:
            detail = _error_detail(error)
            if error.code == 404:
                raise _GitLabResourceMissingError(f"GitLab resource is missing{detail}") from error
            if error.code == 409:
                raise FileExistsError(url) from error
            raise GitLabPublishError(
                f"GitLab publication failed with HTTP {error.code}{detail}"
            ) from error
        finally:
            error.close()
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
            existing = json.loads(_request(f"{endpoint}/{tag}", token, credential_kind))
        except _GitLabResourceMissingError:
            existing = None
        else:
            _require_matching_release(existing, release, names)
        for asset_name in names:
            payload = (root / asset_name).read_bytes()
            try:
                received = _request(f"{asset_base}/{asset_name}", token, credential_kind)
            except _GitLabResourceMissingError:
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
            if received != payload:
                raise GitLabPublishError(
                    f"GitLab release asset differs before upload: {asset_name}"
                )
            (downloaded / asset_name).write_bytes(received)
        if _verify(downloaded, trust) != names:
            raise GitLabPublishError("GitLab release asset inventory differs after upload")
        if existing is not None:
            return "matched"
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
            _require_matching_release(existing, release, names)
            return "matched"


def _require_matching_release(
    existing: object, expected: Mapping[str, object], names: list[str]
) -> None:
    """Require one existing Release to equal the requested immutable identity."""
    if not isinstance(existing, Mapping):
        raise GitLabPublishError("existing GitLab release does not match immutable identity")
    assets = existing.get("assets")
    links = assets.get("links") if isinstance(assets, Mapping) else None
    link_names = (
        sorted(link.get("name") for link in links if isinstance(link, Mapping))
        if isinstance(links, list)
        else []
    )
    if (
        existing.get("tag_name") != expected["tag_name"]
        or existing.get("name") != expected["name"]
        or existing.get("description") != expected["description"]
        or link_names != names
    ):
        raise GitLabPublishError("existing GitLab release does not match immutable identity")


def _error_detail(error: urllib.error.HTTPError) -> str:
    """Return one bounded, credential-free provider diagnostic."""
    try:
        raw = error.read(2049)
    except OSError:
        return ""
    if len(raw) > 2048:
        raw = raw[:2048]
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        detail = text
    else:
        message = payload.get("message") if isinstance(payload, dict) else payload
        detail = message if isinstance(message, str) else json.dumps(message, sort_keys=True)
    return f": {detail[:512]}" if detail else ""
