"""External product publication identity and OpenSSH-agent selection."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]+$")


class PublicationContextError(RuntimeError):
    """Publication identity or signing capability is unavailable."""


@dataclass(frozen=True, slots=True)
class PublicationContext:
    """Caller-owned identity for immutable local Git objects."""

    name: str
    email: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SigningContext:
    """Standard OpenSSH signing inputs selected from the caller's agent."""

    program: Path
    public_key: Path


def load(path: Path) -> PublicationContext:
    """Load the one product identity from an explicit publication context."""

    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
        record = value["product"]
        fields = (
            record["actor-name"],
            record["actor-email"],
            record["active-signing-fingerprint"],
        )
    except (KeyError, OSError, TypeError, tomllib.TOMLDecodeError) as error:
        raise PublicationContextError("invalid product publication context") from error
    if value.get("schema-version") != 1:
        raise PublicationContextError("unsupported publication context schema")
    if not all(isinstance(item, str) and item and "\t" not in item for item in fields):
        raise PublicationContextError("product publication identity is incomplete")
    if _FINGERPRINT.fullmatch(fields[2]) is None:
        raise PublicationContextError("product signing fingerprint is invalid")
    return PublicationContext(*fields)


def select_signing_key(context: PublicationContext, destination: Path) -> SigningContext:
    """Select the exact public key advertised by the active OpenSSH agent."""

    if not os.environ.get("SSH_AUTH_SOCK"):
        raise PublicationContextError("OpenSSH agent is unavailable")
    ssh_add = shutil.which("ssh-add")
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_add or not ssh_keygen:
        raise PublicationContextError("OpenSSH signing tools are unavailable")
    try:
        candidates = subprocess.run(
            (ssh_add, "-L"), check=True, capture_output=True, text=True
        ).stdout.splitlines()
        for line in candidates:
            parts = line.split()
            if len(parts) < 2:
                continue
            public_key = " ".join(parts[:2])
            fingerprint = subprocess.run(
                (ssh_keygen, "-lf", "-", "-E", "sha256"),
                input=public_key + "\n",
                check=True,
                capture_output=True,
                text=True,
            ).stdout.split()[1]
            if fingerprint != context.fingerprint:
                continue
            destination.write_text(public_key + "\n", encoding="ascii")
            subprocess.run((ssh_add, "-T", str(destination)), check=True, capture_output=True)
            return SigningContext(Path(ssh_keygen).resolve(), destination)
    except (OSError, subprocess.CalledProcessError, IndexError, UnicodeError) as error:
        raise PublicationContextError("OpenSSH agent signing capability is invalid") from error
    raise PublicationContextError("required product signing fingerprint is not loaded")
