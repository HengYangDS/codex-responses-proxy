"""Admit one public command result before human or JSON projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from typing import cast

type PublicCommand = Literal[
    "install", "status", "doctor", "recover", "reload", "rollback", "uninstall"
]
type SuccessState = Literal[
    "installed",
    "upgraded",
    "unchanged",
    "running",
    "degraded",
    "invalid",
    "not_installed",
    "not_required",
    "recovery_required",
    "reloaded",
    "unavailable",
    "rolled_back",
    "closed",
    "finalized",
    "purged",
    "uninstalled",
]


@dataclass(frozen=True, slots=True)
class Success:
    """One validated successful command observation or mutation."""

    command: PublicCommand
    state: SuccessState
    evidence: dict[str, object]
    exit_code: int


@dataclass(frozen=True, slots=True)
class Failure:
    """One bounded public failure independent of a private exception."""

    code: str
    problem: str
    next_command: str
    exit_code: Literal[2] = 2


type PublicOutcome = Success | Failure


def admit(command: str, raw: Mapping[str, object] | None) -> Success:
    """Reject malformed internal results instead of presenting false success."""
    if not isinstance(raw, Mapping):
        raise ValueError("public command result is not an object")
    evidence = dict(raw)
    state = evidence.get("state")
    match command, evidence:
        case "status", {
            "state": ("running" | "degraded" | "invalid" | "not_installed" | "recovery_required"),
            "detail": str(),
            "payload_integrity": Mapping(),
            "command": Mapping(),
            "service": str(),
            "listener_pids": list(),
        }:
            pass
        case "doctor", {"state": _, "ok": bool(), "checks": Mapping() as checks} if (
            state in {"running", "degraded", "invalid", "not_installed", "recovery_required"}
            and checks
        ):
            pass
        case "install", {"state": ("installed" | "upgraded" | "unchanged"), "release": str()}:
            pass
        case "install", {
            "state": ("installed" | "upgraded"),
            "runtime": {"release": str()},
        }:
            pass
        case "reload", {"state": "reloaded", "old_pid": old_pid, "new_pid": new_pid} if (
            type(old_pid) is int and type(new_pid) is int
        ):
            pass
        case "rollback", {"state": "unavailable", "detail": str()}:
            pass
        case "rollback", {"state": "unchanged", "release": str()}:
            pass
        case "rollback", {"state": "rolled_back", "from_release": str(), "to_release": str()}:
            pass
        case "recover", {"state": "not_required"}:
            pass
        case "recover", {
            "state": ("closed" | "rolled_back" | "finalized" | "purged"),
            "transaction_id": str(),
            "version": str(),
        }:
            pass
        case "uninstall", {
            "state": (
                "not_installed" | "uninstalled" | "purged" | "closed" | "rolled_back" | "finalized"
            ),
            "stopped": stopped,
            "command_removed": bool(),
        } if type(stopped) is int:
            pass
        case _:
            raise ValueError(f"{command} result is invalid")
    return Success(
        command,
        cast("SuccessState", state),
        evidence,
        1 if command == "doctor" and evidence["ok"] is False else 0,
    )
