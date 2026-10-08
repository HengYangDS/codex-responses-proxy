"""Compose native Python checks and original reports within the owning Nox session."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import nox

ROOT = Path(__file__).resolve().parents[2]
ROOTS = ("src/codex_responses_proxy", "tools", "tests", "noxfile.py")
RUFF_CONFIG = ROOT / ".config/quality/native/ruff.toml"
TY_CONFIG = ROOT / ".config/quality/native/ty.toml"
COVERAGE_CONFIG = ROOT / ".config/quality/native/coverage.ini"


def static(session: nox.Session, *, environment: Mapping[str, str], minimum_python: str) -> None:
    """Run one native policy and scope for editing feedback and full acceptance."""
    output = _output_directory(session)
    session.run(
        "ruff",
        "check",
        "--config",
        str(RUFF_CONFIG),
        "--no-cache",
        ".",
        *(
            (
                "--output-format",
                "json",
                "--output-file",
                str(output / f"{session.name}-ruff.json"),
            )
            if output is not None
            else ()
        ),
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
        *(("--junitxml", str(output / f"{session.name}.xml")) if output is not None else ()),
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
    """Emit child identity into the selected runner-owned attempt without nested writes."""
    environment["ETHOS_NATIVE_OUTPUT_DIR"] = None
    output = _output_directory(session)
    if output is None:
        return None
    environment["COVERAGE_FILE"] = str(output / f".{session.name}.coverage")
    session.run(
        "python",
        "-I",
        "-c",
        "import json,sys; from pathlib import Path; "
        "Path(sys.argv[1]).write_text(json.dumps({'executable':sys.executable, "
        "'version':list(sys.version_info[:3]), 'prefix':sys.prefix}) + '\\n', encoding='utf-8')",
        str(output / f"{session.name}-runtime.json"),
        env=environment,
    )
    return output


def _output_directory(session: nox.Session) -> Path | None:
    """Resolve the selected native report directory before any report producer runs."""
    selected = os.environ.get("ETHOS_NATIVE_OUTPUT_DIR")
    if not selected:
        return None
    output = Path(selected)
    if not output.is_absolute() or not output.is_dir() or output.is_symlink():
        session.error("native output directory is unavailable")
    return output
