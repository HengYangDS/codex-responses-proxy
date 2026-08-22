"""Executable contracts for owned constants and their declared projections."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class TestHardCodingResponsibility:
    """Require controlled values to have one owner and explicit projections."""

    def test_product_identity_is_one_runtime_owner(self) -> None:
        identity = _load(
            "codex_responses_proxy_product_identity",
            "src/codex_responses_proxy/product_identity.py",
        )

        assert identity.PRODUCT_SLUG == "codex-responses-proxy"
        assert identity.DISPLAY_NAME == "Codex Responses Proxy"
        assert identity.COMMAND_NAME == identity.PRODUCT_SLUG
        assert identity.ENVIRONMENT_PREFIX == "CODEX_RESPONSES_PROXY"
        assert identity.SERVICE_ID == f"{identity.PRODUCT_SLUG}.watchdog"
        assert identity.RELEASE_NAMESPACE == f"{identity.PRODUCT_SLUG}-release"

    def test_controlled_values_have_complete_positive_ownership(self) -> None:
        checker = _load(
            "codex_responses_proxy_hard_coding_checker",
            "tools/quality/hard_coding.py",
        )

        report = checker.audit()

        assert report["errors"] == []
        assert report["ok"] is True
        assert set(report["kinds"]) == {
            "derived-projection",
            "domain-constant",
            "policy-parameter",
            "supply-chain-pin",
        }

    def test_hard_coding_policy_rejects_duplicate_owners(self, tmp_path: Path) -> None:
        checker = _load(
            "codex_responses_proxy_hard_coding_duplicate_checker",
            "tools/quality/hard_coding.py",
        )
        source = (ROOT / ".config/quality/policy/hard-coding.toml").read_text(encoding="utf-8")
        control = source.split("[[controls]]", 2)[1]
        malformed = source + "\n[[controls]]" + control
        policy = tmp_path / "hard-coding.toml"
        policy.write_text(malformed, encoding="utf-8")

        report = checker.audit(policy_path=policy)

        assert "hard_coding_duplicate_control:product-slug" in report["errors"]

    def test_product_identity_projection_drift_fails_the_audit(self, tmp_path: Path) -> None:
        checker = _load(
            "codex_responses_proxy_hard_coding_projection_checker",
            "tools/quality/hard_coding.py",
        )
        policy = tmp_path / ".config/quality/policy/hard-coding.toml"
        policy.parent.mkdir(parents=True)
        shutil.copy2(ROOT / ".config/quality/policy/hard-coding.toml", policy)
        owner = tmp_path / "src/codex_responses_proxy/product_identity.py"
        owner.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "src/codex_responses_proxy/product_identity.py", owner)
        pyproject = tmp_path / "pyproject.toml"
        source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        pyproject.write_text(
            source.replace('name = "codex-responses-proxy"', 'name = "drifted-product"', 1),
            encoding="utf-8",
        )

        report = checker.audit(root=tmp_path, policy_path=policy)

        assert (
            "hard_coding_projection_value_mismatch:product-slug:PACKAGE_NAME:"
            "pyproject.toml:project.name"
        ) in report["errors"]
