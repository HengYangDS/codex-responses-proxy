"""Repository-owned verification and native-distribution sessions."""

from __future__ import annotations

import os
import platform
import re
import socket
import tempfile
import tomllib
from pathlib import Path
from typing import cast

import nox

from codex_responses_proxy import product_identity
from codex_responses_proxy.runtime.process_environment import native_process_environment
from codex_responses_proxy.service import runtime as service_runtime

ROOT = Path(__file__).parent.resolve()
PYTHONS = tuple((ROOT / ".python-versions").read_text(encoding="utf-8").splitlines())
MIN_PYTHON, *_, MAX_PYTHON = PYTHONS
RELEASE_PYTHON = (ROOT / ".python-release").read_text(encoding="utf-8").strip()
ROOTS = ("src/codex_responses_proxy", "tools", "tests")
RUFF_CONFIG = ROOT / ".config/quality/native/ruff.toml"
TY_CONFIG = ROOT / ".config/quality/native/ty.toml"
COVERAGE_CONFIG = ROOT / ".config/quality/native/coverage.ini"
PERFORMANCE_POLICY = ROOT / ".config/quality/policy/performance.toml"

nox.options.default_venv_backend = "uv"
nox.options.error_on_missing_interpreters = True
nox.options.reuse_existing_virtualenvs = False


@nox.session(python=MAX_PYTHON)
def quick(session: nox.Session) -> None:
    """Run the cheapest deterministic contract and source checks."""
    _install_tools(session)
    environment = _environment()
    session.run(
        "ruff",
        "check",
        "--config",
        str(RUFF_CONFIG),
        "--no-cache",
        ".",
        env=environment,
    )
    session.run(
        "ruff",
        "format",
        "--config",
        str(RUFF_CONFIG),
        "--no-cache",
        "--check",
        ".",
        env=environment,
    )
    session.run(
        "ruff",
        "check",
        "--config",
        str(RUFF_CONFIG),
        "--select",
        "D",
        "--no-cache",
        "src",
        "tools",
        "noxfile.py",
        env=environment,
    )
    session.run("python", "tools/quality/text_layout.py", env=environment)
    session.run("python", "-m", "tools.quality.responsibilities", env=environment)
    session.run("python", "-m", "tools.quality.hard_coding", env=environment)
    session.run("python", "-m", "tools.quality.repository", env=environment)
    session.run(
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/quality/test_contract.py",
        env=environment,
    )


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
        product_identity.environment_name("EXECUTABLE"): str(_installed_executable(session)),
    }
    session.run(
        "python",
        "-m",
        "compileall",
        "-q",
        *ROOTS,
        env={**environment, "PYTHONPYCACHEPREFIX": str(work / "pycache")},
    )
    session.run(
        "python",
        "-m",
        "pytest",
        "-m",
        "not native_distribution and not repository_toolchain",
        env=environment,
    )


@nox.session(python=MIN_PYTHON)
def quality(session: nox.Session) -> None:
    """Run static analysis and branch-aware coverage at the compatibility floor."""
    _install_tools(session)
    work = Path(session.create_tmp()).resolve()
    wheel = _build_wheel(session, work)
    _install_wheel(session, wheel)
    _assert_installed_product(session, work)
    environment = {
        **_environment(),
        product_identity.environment_name("EXECUTABLE"): str(_installed_executable(session)),
    }
    session.run(
        "ruff",
        "check",
        "--config",
        str(RUFF_CONFIG),
        "--no-cache",
        ".",
        env=environment,
    )
    session.run(
        "ruff",
        "format",
        "--config",
        str(RUFF_CONFIG),
        "--no-cache",
        "--check",
        ".",
        env=environment,
    )
    session.run(
        "ruff",
        "check",
        "--config",
        str(RUFF_CONFIG),
        "--select",
        "D",
        "--no-cache",
        "src",
        "tools",
        "noxfile.py",
        env=environment,
    )
    session.run("python", "tools/quality/text_layout.py", env=environment)
    session.run("python", "-m", "tools.quality.responsibilities", env=environment)
    session.run("python", "-m", "tools.quality.hard_coding", env=environment)
    session.run("python", "-m", "tools.quality.repository", env=environment)
    session.run(
        "ty",
        "check",
        "--config-file",
        str(TY_CONFIG),
        "--python-version",
        MIN_PYTHON,
        "--python-platform",
        "all",
        "--error-on-warning",
        "--no-progress",
        *ROOTS,
        env=environment,
    )
    session.run("coverage", "erase", "--rcfile", str(COVERAGE_CONFIG), env=environment)
    session.run(
        "coverage",
        "run",
        "--rcfile",
        str(COVERAGE_CONFIG),
        "-m",
        "pytest",
        "-m",
        "not native_distribution and not repository_toolchain",
        env=environment,
    )
    session.run("coverage", "report", "--rcfile", str(COVERAGE_CONFIG), env=environment)
    session.run(
        "python",
        "tools/quality/branch_coverage.py",
        "--policy",
        str(ROOT / ".config/quality/policy/coverage.toml"),
        env=environment,
    )


@nox.session(python=RELEASE_PYTHON)
def performance(session: nox.Session) -> None:
    """Measure deterministic product overhead and emit machine-readable evidence."""
    _install_tools(session)
    work = Path(session.create_tmp()).resolve()
    wheel = _build_wheel(session, work)
    _install_wheel(session, wheel)
    _assert_installed_product(session, work)
    output = Path(session.posargs[0] if session.posargs else session.create_tmp()).resolve()
    output.mkdir(parents=True, exist_ok=True)
    benchmark_log = output / "benchmark.log"
    environment = {
        **_environment(),
        product_identity.environment_name("HOME"): str(output / "payload"),
        product_identity.environment_name("STATE_HOME"): str(output / "state"),
    }
    execution = tomllib.loads(PERFORMANCE_POLICY.read_text(encoding="utf-8"))["execution"]
    common = [
        "--quiet",
        "--processes",
        str(execution["processes"]),
        "--values",
        str(execution["values"]),
        "--warmups",
        str(execution["warmups"]),
        "--min-time",
        str(execution["minimum_time_seconds"]),
        "--output",
    ]
    with benchmark_log.open("w", encoding="utf-8") as log:
        session.run(
            "python",
            "-m",
            "tools.performance.benchmark",
            *common,
            str(output / "latency.json"),
            env=environment,
            stderr=log,
        )
        session.run(
            "python",
            "-m",
            "tools.performance.memory",
            "--track-memory",
            *common,
            str(output / "memory.json"),
            env=environment,
            stderr=log,
        )
    session.run(
        "python",
        "-m",
        "tools.performance.verify",
        "--policy",
        str(PERFORMANCE_POLICY),
        "--latency",
        str(output / "latency.json"),
        "--memory",
        str(output / "memory.json"),
        env=environment,
    )


@nox.session(python=False)
def governance(session: nox.Session) -> None:
    """Run the repository governance graph with the locked external toolchain."""
    session.run(
        "mise",
        "exec",
        "--locked",
        "--",
        "uv",
        "run",
        "--locked",
        "--no-sync",
        "python",
        "-m",
        "tools.quality.governance",
        *session.posargs,
        external=True,
        env=_environment(),
    )


@nox.session(python=False)
def full(session: nox.Session) -> None:
    """Run governance, strict quality, and every remaining supported interpreter."""
    session.notify("governance")
    session.notify("quality")
    for python in PYTHONS[1:]:
        session.notify(f"tests-{python}")


@nox.session(python=RELEASE_PYTHON)
def release_asset(session: nox.Session) -> None:
    """Build and accept a native asset without requiring a host service manager."""
    work, bundle, executable = _build_native_candidate(session)
    environment = {
        **_environment(),
        product_identity.environment_name("EXECUTABLE"): str(executable),
        product_identity.environment_name("NATIVE_EXECUTABLE"): str(executable),
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
    _accept_native_executable(session, executable)
    _package_release_asset(session, bundle, work)


@nox.session(python=RELEASE_PYTHON)
def release(session: nox.Session) -> None:
    """Build and accept this platform's asset and native service lifecycle."""
    work, bundle, executable = _build_native_candidate(session)
    environment = {
        **_environment(),
        product_identity.environment_name("EXECUTABLE"): str(executable),
        product_identity.environment_name("NATIVE_EXECUTABLE"): str(executable),
    }
    session.run(
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/cli/test_interface.py",
        "tests/release/test_native_lifecycle.py",
        "tests/service/handoff/test_subprocess.py",
        env=environment,
    )
    _accept_native_executable(session, executable)
    _package_release_asset(session, bundle, work)


def _build_native_candidate(session: nox.Session) -> tuple[Path, Path, Path]:
    """Build one source-independent native candidate from the locked repository."""
    _install_tools(session, "quality", "release")
    _assert_release_runtime(session)
    work = Path(session.create_tmp()).resolve()
    wheel = _build_wheel(session, work)
    _install_wheel(session, wheel)
    session.run(
        "python",
        "-m",
        "tools.release.assets",
        "normalize",
        "--packages",
        str(_session_packages(session)),
        env=_environment(),
    )
    _assert_installed_product(session, work)
    bundle, executable = _build_executable(session, work)
    return work, bundle, executable


def _accept_native_executable(session: nox.Session, executable: Path) -> None:
    """Prove the native executable starts without a Python runtime on PATH."""
    _run_without_python(session, executable, "--help")
    _run_without_python(session, executable, "--version")
    _run_without_python(
        session,
        executable,
        "status",
        "--json",
        isolated_listener=True,
        success_codes=(0, 2),
    )
    session.log(f"native executable accepted: {executable.name}")


@nox.session(python=RELEASE_PYTHON)
def release_compatibility(session: nox.Session) -> None:
    """Upgrade one verified published predecessor to this native candidate."""
    previous_asset = _required_file(
        product_identity.environment_name("PREVIOUS_RELEASE_ASSET"),
        "published predecessor asset",
    )
    previous_trust = _required_file(
        product_identity.environment_name("PREVIOUS_RELEASE_TRUST_ANCHOR"),
        "published predecessor trust anchor",
    )
    _work, bundle, executable = _build_native_candidate(session)
    session.run(
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/release/test_native_compatibility.py",
        env={
            **_environment(),
            product_identity.environment_name("NATIVE_EXECUTABLE"): str(executable),
            product_identity.environment_name("NATIVE_BUNDLE"): str(bundle),
            product_identity.environment_name("PREVIOUS_RELEASE_ASSET"): str(previous_asset),
            product_identity.environment_name("PREVIOUS_RELEASE_TRUST_ANCHOR"): str(previous_trust),
        },
    )


def _required_file(variable: str, label: str) -> Path:
    """Return one explicit regular file input without guessing a host path."""
    value = os.environ.get(variable, "")
    path = Path(value).expanduser() if value else Path()
    if not value or not path.is_file() or path.is_symlink():
        raise RuntimeError(f"{label} is unavailable; set {variable}")
    return path.resolve(strict=True)


def _install_tools(session: nox.Session, *groups: str) -> None:
    """Install the repository-locked verification tool set into this session."""
    requirements = Path(session.create_tmp()) / "requirements.txt"
    python = _session_python(session)
    command = [
        "uv",
        "export",
        "--locked",
        "--no-emit-project",
        "--format",
        "requirements.txt",
        "--output-file",
        str(requirements),
        "--project",
        str(ROOT),
    ]
    for group in groups or ("quality",):
        command.extend(("--group", group))
    session.run_install(
        *command,
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
    with tempfile.TemporaryDirectory(prefix=f"{product_identity.PRODUCT_SLUG}-uv-") as cache:
        session.run_install(
            "uv",
            "build",
            "--wheel",
            "--cache-dir",
            cache,
            "--out-dir",
            str(wheelhouse),
            str(ROOT),
            external=True,
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
        "--strict",
        str(wheel),
        env={"PYTHONNOUSERSITE": "1", "UV_NO_PROGRESS": "1"},
        external=True,
    )


def _session_packages(session: nox.Session) -> Path:
    """Return this session interpreter's installed package directory."""
    packages = session.run(
        "python",
        "-c",
        "import sysconfig; print(sysconfig.get_path('purelib'))",
        silent=True,
        env=_environment(),
    )
    if not isinstance(packages, str):
        session.error("release session package directory is unavailable")
    return Path(packages.strip()).resolve(strict=True)


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
    name = product_identity.executable_name(windows=os.name == "nt")
    executable = Path(session.bin) / name
    if not executable.is_file():
        session.error(f"installed console executable was not produced: {executable}")
    return executable


def _build_executable(session: nox.Session, work: Path) -> tuple[Path, Path]:
    """Build one native directory bundle with only release-owned data."""
    name = product_identity.executable_name(windows=os.name == "nt")
    dist = work / "dist"
    command = (
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--log-level",
        "ERROR",
        "--onedir",
        "--name",
        product_identity.PRODUCT_SLUG,
        "--distpath",
        str(dist),
        "--workpath",
        str(work / "build"),
        "--specpath",
        str(work),
        "--additional-hooks-dir",
        str(ROOT / "tools/release/hooks"),
        "--add-data",
        f"{ROOT / 'VERSION'}{os.pathsep}.",
        "--add-data",
        (
            f"{ROOT / 'src/codex_responses_proxy/providers/manifest.toml'}"
            f"{os.pathsep}codex_responses_proxy/providers"
        ),
        "--collect-submodules",
        "codex_responses_proxy.providers.policies",
        str(ROOT / "src/codex_responses_proxy/cli/__main__.py"),
    )
    session.run(*command, env=_environment())
    bundle = dist / product_identity.PRODUCT_SLUG
    executable = bundle / name
    if not executable.is_file():
        session.error(f"native executable was not produced: {executable}")
    _run_without_python(session, executable, "--version")
    _run_without_python(session, executable, service_runtime.PREWARM_MODE)
    return bundle, executable


def _assert_release_runtime(session: nox.Session) -> None:
    """Reject native builds outside the repository-declared runtime."""
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    image = metadata["tool"][product_identity.PRODUCT_SLUG]["linux-release-image"]
    match = re.search(r"python:(\d+\.\d+\.\d+)-", image)
    version = session.run(
        "python",
        "-c",
        "import platform; print(platform.python_version())",
        env=_environment(),
        silent=True,
    )
    if (
        match is None
        or RELEASE_PYTHON != match.group(1)
        or not isinstance(version, str)
        or version.strip() != RELEASE_PYTHON
    ):
        session.error("release interpreter differs from the immutable release runtime")


def _package_release_asset(session: nox.Session, bundle: Path, work: Path) -> None:
    """Export one manifest-bound native asset set after black-box acceptance."""
    output = Path(session.posargs[0]).resolve() if session.posargs else work / "release-assets"
    try:
        platform_id = product_identity.native_release_platform(
            platform.system(), platform.machine()
        )
    except ValueError as error:
        session.error(str(error))
    session.run(
        "python",
        "-m",
        "tools.release.assets",
        "--bundle",
        str(bundle),
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
    isolated_listener: bool = False,
    success_codes: tuple[int, ...] = (0,),
) -> None:
    """Run a black-box command with no Python executable or package path."""
    sandbox = Path(session.create_tmp()) / "black-box"
    empty_path = sandbox / "empty-path"
    empty_path.mkdir(parents=True, exist_ok=True)
    environment = native_process_environment(
        user_home=sandbox / "home",
        install_root=sandbox / "payload",
        state_root=sandbox / "state",
        command_search_path=empty_path,
    )
    if isolated_listener:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = str(reservation.getsockname()[1])
            session.run(
                str(executable),
                *arguments,
                "--port",
                port,
                env=environment,
                external=True,
                success_codes=success_codes,
            )
        return
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
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONWARNINGS": "error",
        "SOURCE_DATE_EPOCH": "315532800",
        "UV_LINK_MODE": "copy",
        **(
            {
                product_identity.environment_name("RELEASE_TAG_REMOTE"): os.environ[
                    product_identity.environment_name("RELEASE_TAG_REMOTE")
                ]
            }
            if product_identity.environment_name("RELEASE_TAG_REMOTE") in os.environ
            else {}
        ),
        **({"COVERAGE_FILE": os.environ["COVERAGE_FILE"]} if "COVERAGE_FILE" in os.environ else {}),
    }
