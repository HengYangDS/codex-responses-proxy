"""Repository-owned verification and native-distribution sessions."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import cast

import nox

PYTHONS = ("3.12", "3.13", "3.14")
ROOTS = ("src/codex_responses_proxy", "tools", "tests")
ROOT = Path(__file__).parent.resolve()

nox.options.default_venv_backend = "uv"
nox.options.error_on_missing_interpreters = True
nox.options.reuse_existing_virtualenvs = False


@nox.session(python="3.14")
def quick(session: nox.Session) -> None:
    """Run the cheapest deterministic contract and source checks."""

    _install_tools(session)
    environment = _environment()
    session.run("ruff", "check", "--no-cache", ".", env=environment)
    session.run("ruff", "format", "--no-cache", "--check", ".", env=environment)
    session.run("python", "tools/quality/portability.py", env=environment)
    session.run("python", "tools/quality/repository.py", env=environment)
    session.run("python", "-m", "pytest", "-q", "tests/quality/test_contract.py", env=environment)


@nox.session(python=PYTHONS)
def tests(session: nox.Session) -> None:
    """Compile and run the complete behavior inventory on one Python."""

    _install_tools(session)
    work = Path(session.create_tmp()).resolve()
    wheel = _build_wheel(session, work)
    _install_wheel(session, wheel)
    _assert_installed_product(session, work)
    environment = {
        **_environment(),
        "CODEX_RESPONSES_PROXY_EXECUTABLE": str(_installed_executable(session)),
    }
    session.run(
        "python",
        "-m",
        "compileall",
        "-q",
        *ROOTS,
        env={**environment, "PYTHONPYCACHEPREFIX": str(work / "pycache")},
    )
    session.run("python", "-m", "pytest", "-m", "not native_distribution", env=environment)


@nox.session(python="3.12")
def quality(session: nox.Session) -> None:
    """Run static analysis and branch-aware coverage at the compatibility floor."""

    _install_tools(session)
    work = Path(session.create_tmp()).resolve()
    wheel = _build_wheel(session, work)
    _install_wheel(session, wheel)
    _assert_installed_product(session, work)
    environment = {
        **_environment(),
        "CODEX_RESPONSES_PROXY_EXECUTABLE": str(_installed_executable(session)),
    }
    session.run("ruff", "check", "--no-cache", ".", env=environment)
    session.run("ruff", "format", "--no-cache", "--check", ".", env=environment)
    session.run("python", "tools/quality/portability.py", env=environment)
    session.run("python", "tools/quality/repository.py", env=environment)
    session.run(
        "ty",
        "check",
        "--python-version",
        "3.12",
        "--python-platform",
        "all",
        "--error-on-warning",
        "--no-progress",
        *ROOTS,
        env=environment,
    )
    session.run("coverage", "erase", env=environment)
    session.run(
        "coverage",
        "run",
        "-m",
        "pytest",
        "-m",
        "not native_distribution",
        env=environment,
    )
    session.run("coverage", "report", env=environment)
    session.run("python", "tools/quality/branch_coverage.py", env=environment)


@nox.session(python=False)
def full(session: nox.Session) -> None:
    """Run quick checks, strict quality, and every supported interpreter."""

    session.notify("quick")
    session.notify("quality")
    for python in PYTHONS:
        session.notify(f"tests-{python}")


@nox.session(python="3.14")
def release(session: nox.Session) -> None:
    """Build and black-box test this platform's self-contained executable."""

    _install_tools(session)
    work = Path(session.create_tmp()).resolve()
    wheel = _build_wheel(session, work)
    _install_wheel(session, wheel)
    _assert_installed_product(session, work)
    executable = _build_executable(session, work)
    environment = {
        **_environment(),
        "CODEX_RESPONSES_PROXY_EXECUTABLE": str(executable),
        "CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE": str(executable),
    }
    session.run(
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/cli/test_interface.py",
        "tests/service/handoff/test_subprocess.py",
        env=environment,
    )
    _run_without_python(session, executable, "--help")
    _run_without_python(session, executable, "version")
    _run_without_python(session, executable, "status", "--json", success_codes=(0, 2))
    _package_release_asset(session, executable, work)
    session.log(f"native executable accepted: {executable.name}")


def _install_tools(session: nox.Session) -> None:
    """Install the repository-locked verification tool set into this session."""

    requirements = Path(session.create_tmp()) / "quality-requirements.txt"
    python = _session_python(session)
    session.run_install(
        "uv",
        "export",
        "--locked",
        "--only-group",
        "quality",
        "--no-emit-project",
        "--format",
        "requirements.txt",
        "--output-file",
        str(requirements),
        "--project",
        str(ROOT),
        silent=True,
        env={"PYTHONNOUSERSITE": "1", "UV_NO_PROGRESS": "1"},
        external=True,
    )
    session.run_install(
        "uv",
        "pip",
        "install",
        "--python",
        python,
        "--requirements",
        str(requirements),
        "--strict",
        env={"PYTHONNOUSERSITE": "1", "UV_NO_PROGRESS": "1"},
        external=True,
    )


def _build_wheel(session: nox.Session, work: Path) -> Path:
    """Build the exact wheel exercised by behavior and quality sessions."""

    wheelhouse = work / "wheelhouse"
    wheelhouse.mkdir()
    session.run_install(
        "uv", "build", "--wheel", "--out-dir", str(wheelhouse), str(ROOT), external=True
    )
    wheels = tuple(wheelhouse.glob("*.whl"))
    if len(wheels) != 1:
        session.error(f"expected one wheel, found {len(wheels)}")
    return wheels[0]


def _install_wheel(session: nox.Session, wheel: Path) -> None:
    """Install only the built product artifact, never the source checkout."""

    session.run_install(
        "uv",
        "pip",
        "install",
        "--python",
        _session_python(session),
        "--no-deps",
        "--strict",
        str(wheel),
        env={"PYTHONNOUSERSITE": "1", "UV_NO_PROGRESS": "1"},
        external=True,
    )


def _session_python(session: nox.Session) -> str:
    """Return the concrete interpreter path selected by Nox."""

    python = session.python
    if not isinstance(python, (str, os.PathLike)):
        session.error("Nox did not provide one concrete Python interpreter")
    return os.fspath(cast("str | os.PathLike[str]", python))


def _assert_installed_product(session: nox.Session, work: Path) -> None:
    """Prove imports and packaged data resolve outside the source checkout."""

    probe = (
        "from pathlib import Path; "
        "import codex_responses_proxy as package; "
        "from codex_responses_proxy.providers import registry; "
        "root = Path(package.__file__).resolve(); "
        "manifest = registry.default_manifest_path().resolve(); "
        "assert not root.is_relative_to(Path.cwd().resolve()); "
        "assert manifest.is_file()"
    )
    with session.chdir(work):
        session.run("python", "-I", "-c", probe, env=_environment())


def _installed_executable(session: nox.Session) -> Path:
    """Return the console executable installed from this session's built wheel."""

    name = "codex-responses-proxy.exe" if os.name == "nt" else "codex-responses-proxy"
    executable = Path(session.bin) / name
    if not executable.is_file():
        session.error(f"installed console executable was not produced: {executable}")
    return executable


def _build_executable(session: nox.Session, work: Path) -> Path:
    """Build one native executable with only release-owned data."""

    name = "codex-responses-proxy.exe" if os.name == "nt" else "codex-responses-proxy"
    dist = work / "dist"
    command = (
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--log-level",
        "ERROR",
        "--onefile",
        "--name",
        "codex-responses-proxy",
        "--distpath",
        str(dist),
        "--workpath",
        str(work / "build"),
        "--specpath",
        str(work),
        "--add-data",
        f"{ROOT / 'VERSION'}{os.pathsep}.",
        "--add-data",
        f"{ROOT / 'src/codex_responses_proxy/providers/manifest.toml'}"
        f"{os.pathsep}codex_responses_proxy/providers",
        "--collect-submodules",
        "codex_responses_proxy.providers.policies",
        str(ROOT / "src/codex_responses_proxy/cli/__main__.py"),
    )
    session.run(*command, env=_environment())
    executable = dist / name
    if not executable.is_file():
        session.error(f"native executable was not produced: {executable}")
    return executable


def _package_release_asset(session: nox.Session, executable: Path, work: Path) -> None:
    """Export one manifest-bound native asset set after black-box acceptance."""

    output = Path(session.posargs[0]).resolve() if session.posargs else work / "release-assets"
    platform_id = {
        ("Darwin", "arm64"): "macos-arm64",
        ("Linux", "x86_64"): "linux-x86_64",
        ("Windows", "AMD64"): "windows-x86_64",
    }.get((platform.system(), platform.machine()))
    if platform_id is None:
        session.error(
            f"unsupported native release platform: {platform.system()}-{platform.machine()}"
        )
    session.run(
        "python",
        "-m",
        "tools.release.assets",
        "--executable",
        str(executable),
        "--platform",
        platform_id,
        "--output",
        str(output),
        env=_environment(),
    )


def _run_without_python(
    session: nox.Session,
    executable: Path,
    *arguments: str,
    success_codes: tuple[int, ...] = (0,),
) -> None:
    """Run a black-box command with no Python executable or package path."""

    empty_path = Path(session.create_tmp()) / "empty-path"
    empty_path.mkdir(exist_ok=True)
    environment = {
        "HOME": str(Path.home()),
        "PATH": str(empty_path),
        "PYTHONHOME": "",
        "PYTHONPATH": "",
        "PYTHONNOUSERSITE": "1",
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", "") if platform.system() == "Windows" else "",
    }
    session.run(
        str(executable),
        *arguments,
        env=environment,
        external=True,
        success_codes=success_codes,
    )


def _environment() -> dict[str, str]:
    """Return the deterministic environment shared by every session."""

    return {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONWARNINGS": "error",
        **({"COVERAGE_FILE": os.environ["COVERAGE_FILE"]} if "COVERAGE_FILE" in os.environ else {}),
    }
