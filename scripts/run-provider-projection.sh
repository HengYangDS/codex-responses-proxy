#!/bin/sh
""":"
exec python3 "$0" "$@"
":"""
"""Run one provider projection with one command-scoped signing key admission."""

import argparse
import os
import subprocess
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("provider", choices=("gitlab", "github"))
    command.add_argument("arguments", nargs=argparse.REMAINDER)
    return command


def run(command: list[str], *, environment: dict[str, str]) -> None:
    subprocess.run(command, check=True, env=environment)


def main() -> None:
    args = parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    key = Path(
        os.environ.get(
            f"DMX_{args.provider.upper()}_SIGNING_KEY",
            Path.home() / f".ssh/id_aigw_{args.provider}_signing_20260729.pub",
        )
    ).expanduser()
    private_key = key.with_suffix("")
    script = root / f"scripts/project-{args.provider}-forge.sh"
    if not key.is_file() or not private_key.is_file() or not script.is_file():
        raise SystemExit("provider projection signing inputs are unavailable")
    environment = os.environ.copy()
    if subprocess.run(
        ("/usr/bin/ssh-add", "-T", str(key)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        env=environment,
    ).returncode == 0:
        run(("/bin/sh", str(script), *args.arguments), environment=environment)
        return
    askpass = Path(
        environment.get("DMX_SSH_ASKPASS", Path.home() / ".local/libexec/agent/git-ssh-keychain-askpass")
    )
    service = environment.get(
        f"DMX_{args.provider.upper()}_KEYCHAIN_SERVICE",
        f"aigw.git.signing.{args.provider}.20260729",
    )
    if not askpass.is_file() or not os.access(askpass, os.X_OK):
        raise SystemExit("provider projection askpass helper is unavailable")
    agent = subprocess.run(
        ("/usr/bin/ssh-agent", "-s"), capture_output=True, text=True, check=True
    )
    for assignment in agent.stdout.split(";"):
        name, separator, value = assignment.strip().partition("=")
        if separator and name in {"SSH_AUTH_SOCK", "SSH_AGENT_PID"}:
            environment[name] = value
    if not all(environment.get(name) for name in ("SSH_AUTH_SOCK", "SSH_AGENT_PID")):
        raise SystemExit("ssh-agent did not expose its capability")
    try:
        admission = {
            **environment,
            "AIGW_GIT_KEYCHAIN_SERVICE": service,
            "SSH_ASKPASS": str(askpass),
            "SSH_ASKPASS_REQUIRE": "force",
            "DISPLAY": "codex-keychain",
        }
        run(
            ("/usr/bin/ssh-add", "--apple-use-keychain", str(private_key)),
            environment=admission,
        )
        run(("/usr/bin/ssh-add", "-T", str(key)), environment=environment)
        run(("/bin/sh", str(script), *args.arguments), environment=environment)
    finally:
        subprocess.run(
            ("/bin/kill", environment["SSH_AGENT_PID"]),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


if __name__ == "__main__":
    main()
