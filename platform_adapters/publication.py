"""Live dual-Forge publication verification and process-local authority.

The JSON-shaped evaluator and provider adapters produce evidence only.  This
module is the sole authority minter: :func:`verify` contacts both independent
Forge planes in the current installer process, validates the repository-owned
policy, and returns a single-use :class:`PublishedRelease`.  There is
deliberately no JSON loader or public constructor for that capability.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tomllib
import weakref
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, SupportsIndex


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class PublicationError(RuntimeError):
    """Report unavailable, ambiguous, or mismatched publication evidence."""


def _authority_kernel() -> tuple[type[PublishedRelease], Any, Any]:
    """Create the capability type plus closure-bound verifier and consumer."""

    token = object()
    issued: weakref.WeakSet[PublishedRelease] = weakref.WeakSet()

    class PublishedRelease:
        """Opaque single-use authority minted by live dual-Forge verification."""

        __slots__ = ("_evidence", "_consumed", "__weakref__")
        _evidence: Mapping[str, Any]
        _consumed: bool

        def __init__(
            self,
            *,
            evidence: Mapping[str, Any],
            _token: object | None = None,
        ) -> None:
            if _token is not token:
                raise TypeError("PublishedRelease is opaque; use publication.verify()")
            object.__setattr__(self, "_evidence", _freeze_mapping(evidence))
            object.__setattr__(self, "_consumed", False)

        def __setattr__(self, name: str, value: object) -> None:
            raise PublicationError("published release capability is immutable")

        def __copy__(self) -> PublishedRelease:
            raise PublicationError("published release capability cannot be copied")

        def __deepcopy__(self, memo: object) -> PublishedRelease:
            del memo
            raise PublicationError("published release capability cannot be copied")

        def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[Any, ...]:
            del protocol
            raise PublicationError("published release capability cannot be serialized")

        def evidence(self) -> Mapping[str, Any]:
            """Return immutable secret-free evidence for receipts and diagnostics."""

            return self._evidence

    def mint(evidence: Mapping[str, Any]) -> PublishedRelease:
        authority = PublishedRelease(evidence=evidence, _token=token)
        issued.add(authority)
        return authority

    def consume_issued(candidate: object) -> Mapping[str, Any]:
        if type(candidate) is not PublishedRelease or candidate not in issued:
            raise PublicationError("released-source admission requires a live PublishedRelease")
        if candidate._consumed:
            raise PublicationError("published release authority was already consumed")
        object.__setattr__(candidate, "_consumed", True)
        return candidate.evidence()

    def verify_authority(
        *,
        tag: str,
        gitlab_remote: str,
        gitlab_api_base: str,
        gitlab_repo: str,
        github_remote: str,
        github_repo: str,
        gitlab_anchor: Path,
        github_anchor: Path,
        policy_path: Path,
    ) -> PublishedRelease:
        """Verify exact signed releases on both Forges and mint one-use authority."""

        if _TAG.fullmatch(tag) is None:
            raise PublicationError("publication tag must be exact vMAJOR.MINOR.PATCH")
        evaluator = _script_module("publication_proof")
        git = _script_module("publication_proof_git")
        gitlab = _script_module("publication_proof_gitlab")
        github = _script_module("publication_proof_github")
        policy = load_policy(policy_path)
        try:
            gitlab_git = git.collect(
                provider="gitlab", remote=gitlab_remote, tag=tag, anchor=gitlab_anchor
            )
            github_git = git.collect(
                provider="github", remote=github_remote, tag=tag, anchor=github_anchor
            )
            gitlab_hosted = gitlab.collect(
                api_base=gitlab_api_base,
                repository=gitlab_repo,
                tag=tag,
                tag_object_oid=str(gitlab_git["tag_object_oid"]),
                commit_oid=str(gitlab_git["commit_oid"]),
                required_jobs=policy["gitlab_jobs"],
            )
            github_hosted = github.collect(
                repository=github_repo,
                tag=tag,
                tag_object_oid=str(github_git["tag_object_oid"]),
                commit_oid=str(github_git["commit_oid"]),
                required_jobs=policy["github_jobs"],
            )
            result = evaluator.evaluate(
                tag,
                {**gitlab_git, **gitlab_hosted},
                {**github_git, **github_hosted},
                policy,
            )
        except (
            git.GitProofError,
            gitlab.GitLabProofError,
            github.GitHubProofError,
            ValueError,
            KeyError,
            OSError,
        ) as error:
            raise PublicationError("live publication evidence is unavailable or invalid") from error
        if result.get("verified") is not True:
            raise PublicationError("dual-Forge publication proof did not verify")
        forges = result.get("forges")
        if not isinstance(forges, Mapping):
            raise PublicationError("verified publication evidence is malformed")
        return mint(
            {
                "schema_version": 1,
                "tag": tag,
                "verified": True,
                "tree_equal": True,
                "forges": dict(forges),
            }
        )

    return PublishedRelease, consume_issued, verify_authority


PublishedRelease, consume, verify = _authority_kernel()
del _authority_kernel


def load_policy(path: Path) -> dict[str, tuple[str, ...]]:
    """Load the single repository-owned required-job policy fail closed."""

    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
        if value.get("schema-version") != 1:
            raise ValueError("unsupported publication policy schema")
        gitlab = tuple(value["gitlab"]["required-jobs"])
        github = tuple(value["github"]["required-jobs"])
    except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as error:
        raise PublicationError("publication policy is unavailable or invalid") from error
    for provider, jobs in (("gitlab", gitlab), ("github", github)):
        if (
            not jobs
            or len(set(jobs)) != len(jobs)
            or any(not isinstance(job, str) or not job for job in jobs)
        ):
            raise PublicationError(f"{provider} publication jobs must be unique and nonempty")
    return {"gitlab_jobs": gitlab, "github_jobs": github}


def _script_module(name: str) -> ModuleType:
    path = SCRIPTS / f"{name}.py"
    qualified = f"codex_dmx_proxy_{name}"
    existing = sys.modules.get(qualified)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(qualified, path)
    if spec is None or spec.loader is None:
        raise PublicationError(f"publication verifier module is unavailable: {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    def freeze(item: Any) -> Any:
        if isinstance(item, Mapping):
            return MappingProxyType({str(key): freeze(child) for key, child in item.items()})
        if isinstance(item, list | tuple):
            return tuple(freeze(child) for child in item)
        return item

    return MappingProxyType({str(key): freeze(item) for key, item in value.items()})
