"""Shared SSH signing boundary for release asset inventories."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

NAMESPACE = "codex-responses-proxy-release"
PRINCIPAL = "codex-responses-proxy-release"


class SignatureError(RuntimeError):
    """Release asset signing or verification failed."""


def sign_and_verify(*, assets: Path, key: Path, trust: str) -> None:
    """Sign and verify the canonical checksum inventory with explicit inputs."""

    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen or not key.is_file() or key.is_symlink() or not trust.strip():
        raise SignatureError("release signing inputs are unavailable")
    checksums = assets / "SHA256SUMS"
    if not checksums.is_file() or checksums.is_symlink():
        raise SignatureError("release checksum inventory is unavailable")
    anchor = assets / ".release-asset-trust"
    signature = assets / "SHA256SUMS.sig"
    anchor.write_text(trust.rstrip("\n") + "\n", encoding="utf-8")
    signature.unlink(missing_ok=True)
    try:
        subprocess.run(
            (ssh_keygen, "-Y", "sign", "-q", "-f", str(key), "-n", NAMESPACE, checksums.name),
            cwd=assets,
            check=True,
            capture_output=True,
        )
        principal = (
            subprocess.run(
                (ssh_keygen, "-Y", "find-principals", "-s", str(signature), "-f", str(anchor)),
                input=checksums.read_bytes(),
                check=True,
                capture_output=True,
            )
            .stdout.decode("ascii")
            .strip()
        )
        if principal != PRINCIPAL:
            raise SignatureError("release asset signature principal is invalid")
        subprocess.run(
            (
                ssh_keygen,
                "-Y",
                "verify",
                "-f",
                str(anchor),
                "-I",
                principal,
                "-n",
                NAMESPACE,
                "-s",
                str(signature),
            ),
            input=checksums.read_bytes(),
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError, UnicodeError) as error:
        raise SignatureError("release asset signature verification failed") from error
    finally:
        anchor.unlink(missing_ok=True)
