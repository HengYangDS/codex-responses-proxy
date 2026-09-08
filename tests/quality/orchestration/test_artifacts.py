"""Artifact admission and release input contracts."""

from __future__ import annotations

import os
import subprocess
import sysconfig
import venv
from contextlib import chdir
from pathlib import Path
from types import ModuleType

import pytest
from pytest_mock import MockerFixture

from tests.quality.fixtures import ROOT


@pytest.mark.parametrize("source_checkout", [False, True])
def test_installed_product_probe_distinguishes_environment_from_source_checkout(
    source_checkout: bool,
    tmp_path: Path,
    mocker: MockerFixture,
    nox_configuration: ModuleType,
) -> None:
    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False).create(environment)
    site_packages = Path(
        sysconfig.get_path("purelib", vars={"base": str(environment), "platbase": str(environment)})
    )
    checkout = tmp_path / "checkout"
    source = checkout / "src" if source_checkout else site_packages
    package = source / "codex_responses_proxy"
    providers = package / "providers"
    providers.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (providers / "__init__.py").write_text("", encoding="utf-8")
    (providers / "registry.py").write_text(
        "from pathlib import Path\n"
        "def default_manifest_path():\n"
        "    return Path(__file__).with_name('manifest.toml')\n",
        encoding="utf-8",
    )
    (providers / "manifest.toml").write_text("", encoding="utf-8")
    if source_checkout:
        (site_packages / "source-checkout.pth").write_text(str(source) + "\n", encoding="utf-8")
    work = checkout / "build"
    work.mkdir(parents=True)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    session = mocker.Mock()
    session.chdir.side_effect = chdir
    session.run.side_effect = lambda *args, **_kwargs: subprocess.run(
        [str(python), *args[1:]], check=True, capture_output=True, text=True
    )
    mocker.patch.object(nox_configuration, "ROOT", checkout)

    if source_checkout:
        with pytest.raises(subprocess.CalledProcessError):
            nox_configuration._assert_installed_product(session, work)
    else:
        nox_configuration._assert_installed_product(session, work)


@pytest.mark.parametrize(
    "owner", ["_session_packages", "_installed_executable", "_build_executable"]
)
def test_missing_build_output_cannot_establish_artifact_acceptance(
    owner: str,
    tmp_path: Path,
    mocker: MockerFixture,
    nox_configuration: ModuleType,
) -> None:
    session = mocker.Mock(bin=str(tmp_path))
    session.run.return_value = None
    session.error.side_effect = RuntimeError
    arguments = (session, tmp_path) if owner == "_build_executable" else (session,)
    with pytest.raises(RuntimeError):
        getattr(nox_configuration, owner)(*arguments)


def test_release_packaging_requires_a_supported_native_platform(
    tmp_path: Path,
    mocker: MockerFixture,
    nox_configuration: ModuleType,
) -> None:
    session = mocker.Mock(posargs=[])
    session.error.side_effect = RuntimeError
    mocker.patch.object(nox_configuration.platform, "system", return_value="unsupported")
    with pytest.raises(RuntimeError):
        nox_configuration._package_release_asset(session, tmp_path / "bundle", tmp_path)
    session.run.assert_not_called()


def test_wheel_build_preserves_the_tool_owned_dependency_cache(
    tmp_path: Path, mocker: MockerFixture, nox_configuration: ModuleType
) -> None:
    session = mocker.Mock()
    wheelhouse = tmp_path / "wheelhouse"
    wheel = wheelhouse / "product.whl"
    session.run_install.side_effect = lambda *_args, **_kwargs: wheel.touch()

    assert nox_configuration._build_wheel(session, tmp_path) == wheel
    session.run_install.assert_called_once_with(
        "uv", "build", "--wheel", "--out-dir", str(wheelhouse), str(ROOT), external=True
    )


@pytest.mark.parametrize("wheel_count", [0, 2])
def test_wheel_build_requires_one_unambiguous_artifact(
    wheel_count: int,
    tmp_path: Path,
    mocker: MockerFixture,
    nox_configuration: ModuleType,
) -> None:
    session = mocker.Mock()
    session.error.side_effect = RuntimeError

    def build(*_args: str, **_kwargs: object) -> None:
        for index in range(wheel_count):
            (tmp_path / "wheelhouse" / f"product-{index}.whl").touch()

    session.run_install.side_effect = build
    with pytest.raises(RuntimeError):
        nox_configuration._build_wheel(session, tmp_path)
    session.error.assert_called_once_with(f"expected one wheel, found {wheel_count}")


@pytest.mark.parametrize("missing_input", [None, "asset", "trust"])
def test_release_compatibility_requires_real_predecessor_inputs_before_build(
    missing_input: str | None,
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
    nox_configuration: ModuleType,
) -> None:
    session = mocker.Mock()
    asset, trust = tmp_path / "previous.zip", tmp_path / "trust.json"
    for role, path, suffix in (
        ("asset", asset, "PREVIOUS_RELEASE_ASSET"),
        ("trust", trust, "PREVIOUS_RELEASE_TRUST_ANCHOR"),
    ):
        name = nox_configuration.product_identity.environment_name(suffix)
        if role == missing_input:
            monkeypatch.delenv(name, raising=False)
        else:
            path.touch()
            monkeypatch.setenv(name, str(path))
    build = mocker.patch.object(
        nox_configuration,
        "_build_native_candidate",
        return_value=(tmp_path, tmp_path / "bundle", tmp_path / "proxy"),
    )
    if missing_input:
        with pytest.raises(RuntimeError, match="unavailable"):
            nox_configuration.release_compatibility(session)
        build.assert_not_called()
        session.run.assert_not_called()
    else:
        nox_configuration.release_compatibility(session)
        session.run.assert_called_once()
        assert session.run.call_args.args == (
            "python",
            "-m",
            "pytest",
            "-q",
            "tests/release/test_native_compatibility.py",
        )
        environment = session.run.call_args.kwargs["env"]
        assert environment[
            nox_configuration.product_identity.environment_name("PREVIOUS_RELEASE_ASSET")
        ] == str(asset)
        assert environment[
            nox_configuration.product_identity.environment_name("PREVIOUS_RELEASE_TRUST_ANCHOR")
        ] == str(trust)


def test_release_runtime_uses_the_session_interpreter(
    mocker: MockerFixture, nox_configuration: ModuleType
) -> None:
    """Compare the release session interpreter, not the Nox launcher."""
    session = mocker.Mock()
    session.run.return_value = "3.14.7\n"

    nox_configuration._assert_release_runtime(session)

    session.run.assert_called_once_with(
        "python",
        "-c",
        "import platform; print(platform.python_version())",
        env=nox_configuration._environment(),
        silent=True,
    )
    session.run.return_value = "3.14.6\n"
    session.error.side_effect = RuntimeError
    with pytest.raises(RuntimeError):
        nox_configuration._assert_release_runtime(session)
