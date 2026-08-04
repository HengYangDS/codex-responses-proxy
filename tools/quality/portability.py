#!/usr/bin/env python3
"""Reject durable product bindings owned by a user, host, or Forge deployment."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
_SCOPED_SUFFIXES = frozenset({".md", ".py", ".sh", ".toml", ".yml", ".yaml"})
_IGNORED_PREFIXES = (
    "evidence/",
    "openspec/changes/archive/",
)
_IGNORED_FILES = frozenset({"CHANGELOG.md", "LICENSE"})
_IGNORED_NAMES = frozenset()
_RULES = (
    ("absolute-home", re.compile(r"(?:/Users/|/home/)[A-Za-z0-9._-]+/")),
    ("windows-home", re.compile(r"[A-Za-z]:[/\\\\]Users[/\\\\][A-Za-z0-9._-]+[/\\\\]")),
    ("package-manager-prefix", re.compile(r"/(?:opt/homebrew|usr/local)/(?:bin|opt)/")),
    ("personal-key-path", re.compile(r"(?:\.ssh[/\\\\]|id_(?:ed25519|rsa)[A-Za-z0-9._-]*)")),
    (
        "personal-identity",
        re.compile(
            r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@(?!example\.)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        ),
    ),
)
_IP = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")


@dataclass(frozen=True, slots=True)
class Finding:
    """One stable portability violation."""

    path: str
    line: int
    rule: str


def _tracked(root: Path) -> tuple[str, ...]:
    """Return stage-zero tracked paths without using the working tree as ownership truth."""

    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return tuple(sorted(path.decode() for path in completed.stdout.split(b"\0") if path))


def _in_scope(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (
        relative not in _IGNORED_FILES
        and path.name not in _IGNORED_NAMES
        and not relative.startswith(_IGNORED_PREFIXES)
        and path.suffix.lower() in _SCOPED_SUFFIXES
    )


def _private_address(line: str) -> bool:
    for match in _IP.finditer(line):
        try:
            address = ipaddress.ip_address(match.group())
        except ValueError:
            continue
        if address.is_private and not address.is_loopback:
            return True
    return False


def audit(root: Path = ROOT, *, paths: tuple[str, ...] | None = None) -> tuple[Finding, ...]:
    """Return deterministic findings for durable product surfaces only."""

    findings: list[Finding] = []
    for relative in paths or _tracked(root):
        if not _in_scope(relative):
            continue
        path = root / relative
        if not path.is_file() or path.is_symlink():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeError:
            findings.append(Finding(relative, 0, "non-utf8-product-surface"))
            continue
        for number, line in enumerate(lines, 1):
            for rule, pattern in _RULES:
                if pattern.search(line):
                    findings.append(Finding(relative, number, rule))
            if _private_address(line):
                findings.append(Finding(relative, number, "private-network"))
    return tuple(sorted(set(findings), key=lambda item: (item.path, item.line, item.rule)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = audit()
    if args.json:
        print(json.dumps([asdict(finding) for finding in findings], sort_keys=True))
    elif findings:
        for finding in findings:
            print(f"{finding.rule}:{finding.path}:{finding.line}")
    else:
        print("Portability ownership contract: OK")
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
