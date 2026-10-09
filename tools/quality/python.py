"""Compose native Python checks and original reports within the owning Nox session."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import unquote
from urllib.parse import urlsplit

import nox

ROOT = Path(__file__).resolve().parents[2]
ROOTS = ("src/codex_responses_proxy", "tools", "tests", "noxfile.py")
RUFF_CONFIG = ROOT / ".config/quality/native/ruff.toml"
TY_CONFIG = ROOT / ".config/quality/native/ty.toml"
COVERAGE_CONFIG = ROOT / ".config/quality/native/coverage.ini"


def source_manifest(root: Path) -> dict[str, str]:
    """Bind installed-package admission to every current tracked source file."""
    source = Path(ROOTS[0])
    result = subprocess.run(
        ("git", "-C", str(root), "ls-files", "-z", "--", source.as_posix()),
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        env={name: value for name, value in os.environ.items() if not name.startswith("GIT_")},
    )
    paths = tuple(root / path for path in result.stdout.split("\0") if path)
    if not paths or any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("installed source inventory is unavailable")
    return {
        path.relative_to(root / source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def static(session: nox.Session, *, environment: Mapping[str, str], minimum_python: str) -> None:
    """Run one native policy and scope for editing feedback and full acceptance."""
    output = _output_directory(session)
    command = (
        "ruff",
        "check",
        "--config",
        str(RUFF_CONFIG),
        "--no-cache",
        ".",
    )
    if output is None:
        session.run(*command, env=environment)
    else:
        _static_report(session, command, output=output, environment=environment)
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
    session.run("python", "tools/quality/text_layout.py", env=environment)
    session.run("python", "-m", "tools.quality.responsibilities", env=environment, silent=True)
    session.run("python", "-m", "tools.quality.hard_coding", env=environment, silent=True)
    session.run("python", "-m", "tools.quality.repository", env=environment)
    session.run(
        "ty",
        "check",
        "--config-file",
        str(TY_CONFIG),
        "--python-version",
        minimum_python,
        "--python-platform",
        "all",
        "--error-on-warning",
        "--no-progress",
        *ROOTS,
        env=environment,
    )


def behavior(
    session: nox.Session, *, environment: dict[str, str | None], require_coverage: bool = False
) -> None:
    """Execute pytest once, retaining its native reports and declared coverage policy."""
    output = _native_output(session, environment)
    measured = require_coverage or output is not None
    if measured:
        session.run("coverage", "erase", "--rcfile", str(COVERAGE_CONFIG), env=environment)
    session.run(
        *(
            ("coverage", "run", "--rcfile", str(COVERAGE_CONFIG), "-m", "pytest")
            if measured
            else ("python", "-m", "pytest")
        ),
        "-m",
        "not native_distribution and not repository_toolchain",
        *(
            (
                "--rootdir",
                str(ROOT),
                "-c",
                str(ROOT / "pytest.ini"),
                "-p",
                "ethos.surface.pytest.plugin",
                "--ethos-runtime-output",
                str(output / f"{session.name}-runtime.json"),
                "--ethos-native-session",
                _native_session(session),
                "--junitxml",
                str(output / f"{session.name}.xml"),
                "--report-log",
                str(output / f"{session.name}-pytest.jsonl"),
            )
            if output is not None
            else ()
        ),
        env=environment,
    )
    if require_coverage:
        session.run("coverage", "report", "--rcfile", str(COVERAGE_CONFIG), env=environment)
        session.run(
            "python",
            "tools/quality/branch_coverage.py",
            "--policy",
            str(ROOT / ".config/quality/policy/coverage.toml"),
            env=environment,
        )
    if output is not None:
        session.run(
            "coverage",
            "xml",
            "--rcfile",
            str(COVERAGE_CONFIG),
            "-o",
            str(output / f"{session.name}-coverage.xml"),
            env=environment,
        )


def _native_output(session: nox.Session, environment: dict[str, str | None]) -> Path | None:
    """Select original checker output without a detached runtime record."""
    environment["ETHOS_NATIVE_OUTPUT_DIR"] = None
    output = _output_directory(session)
    if output is None:
        return None
    environment["COVERAGE_FILE"] = str(output / f".{session.name}.coverage")
    return output


def _static_report(
    session: nox.Session,
    command: tuple[str, ...],
    *,
    output: Path,
    environment: Mapping[str, str],
) -> None:
    """Use the shipped observer for one actual same-child Ruff launch."""
    runtime = output / f"{session.name}-ruff-runtime.json"
    session.run(
        "python",
        "-I",
        "-c",
        "import json,sys; from pathlib import Path; "
        "Path(sys.argv[1]).write_text(json.dumps({'executable':sys.executable, "
        "'version':list(sys.version_info[:3]), 'prefix':sys.prefix}) + '\\n', encoding='utf-8')",
        str(runtime),
        env=environment,
    )
    session.env.update(environment)
    helper = importlib.import_module("ethos.domain.quality.nox")
    binary = Path(session.bin) / ("ruff.exe" if os.name == "nt" else "ruff")
    helper.run_ruff(
        session,
        (
            str(binary),
            *command[1:],
            "--verbose",
            "--output-format",
            "json",
            "--output-file",
            str(output / f"{session.name}-ruff.json"),
        ),
        runtime_output=runtime,
        identity=_native_session(session),
        configuration=RUFF_CONFIG,
    )


def install_native_helpers(session: nox.Session) -> None:
    """Supply only the same installed wheel's observers without changing dependencies."""
    if _output_directory(session) is None:
        return
    try:
        requirement = native_helper_requirement()
    except (OSError, TypeError, ValueError, importlib.metadata.PackageNotFoundError):
        session.error("native evidence requires the selected immutable ETHOS wheel")
    session.install(
        "--no-deps",
        requirement,
        env={"PYTHONNOUSERSITE": "1", "UV_NO_PROGRESS": "1"},
    )


def native_helper_requirement() -> str:
    """Resolve native PEP 610 wheel custody before supplying another Nox child."""
    distribution = importlib.metadata.distribution("ethos")
    provenance = json.loads(distribution.read_text("direct_url.json") or "null")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("url"), str):
        raise ValueError("native helper wheel provenance is unavailable")
    selected = urlsplit(provenance["url"])
    archive = provenance.get("archive_info", {})
    if not isinstance(archive, dict):
        raise ValueError("native helper wheel provenance is invalid")
    hashes = archive.get("hashes", {})
    if not isinstance(hashes, dict):
        raise ValueError("native helper wheel provenance is invalid")
    digest = hashes.get("sha256") or parse_qs(selected.fragment).get("sha256", [""])[0]
    path = unquote(selected.path, errors="strict")
    wheel = Path(path.removeprefix("/") if os.name == "nt" else path)
    if (
        selected.scheme != "file"
        or selected.netloc not in ("", "localhost")
        or selected.query
        or not wheel.is_absolute()
        or wheel.is_symlink()
        or not wheel.is_file()
        or wheel.suffix != ".whl"
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or hashlib.sha256(wheel.read_bytes()).hexdigest() != digest
    ):
        raise ValueError("native helper wheel identity is invalid")
    return f"ethos @ {wheel.as_uri()}#sha256={digest}"


def _native_session(session: nox.Session) -> str:
    """Bind the concrete signature exposed by the original Nox session."""
    version = session.python
    if not isinstance(version, str):
        session.error("native evidence requires one concrete Python session")
    return session.name if session.name.endswith(f"-{version}") else f"{session.name}-{version}"


def _output_directory(session: nox.Session) -> Path | None:
    """Resolve the selected native report directory before any report producer runs."""
    selected = os.environ.get("ETHOS_NATIVE_OUTPUT_DIR")
    if not selected:
        return None
    output = Path(selected)
    if not output.is_absolute() or not output.is_dir() or output.is_symlink():
        session.error("native output directory is unavailable")
    return output
