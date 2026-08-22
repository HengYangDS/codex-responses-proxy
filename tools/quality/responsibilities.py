"""Validate the repository quality responsibility map."""

from __future__ import annotations

import json
import subprocess
import tomllib
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / ".config/quality/responsibility-map.toml"
RATIONALE_FIELDS = (
    "risk_model",
    "measurement",
    "false_positive_cost",
    "remediation",
    "review_condition",
)


def _strings(value: object, *, field: str, errors: list[str]) -> tuple[str, ...]:
    """Return one non-empty unique string sequence or record a precise error."""
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        errors.append(f"responsibility_map_{field}_must_be_nonempty_string_list")
        return ()
    values = tuple(item for item in value if isinstance(item, str))
    if len(values) != len(set(values)):
        errors.append(f"responsibility_map_{field}_must_be_unique")
    return values


def _tracked_paths(root: Path) -> tuple[str, ...]:
    """Return tracked and pending repository paths without ignored host state."""
    completed = subprocess.run(
        (
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ),
        cwd=root,
        check=True,
        capture_output=True,
    )
    return tuple(
        sorted(
            path.decode()
            for path in completed.stdout.split(b"\0")
            if path and not path.decode().startswith(".codebase-memory/")
        )
    )


def _role_matches(path: str, role: dict[str, object]) -> bool:
    """Return whether one path belongs to the role's exact positive scope."""
    files = _optional_strings(role.get("files"))
    prefixes = _optional_strings(role.get("prefixes"))
    return path in files or any(path.startswith(prefix) for prefix in prefixes)


def _optional_strings(value: object) -> tuple[str, ...]:
    """Return a string sequence for an optional role selector."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _mapping(value: object, *, label: str, errors: list[str]) -> dict[str, object]:
    """Return one string-keyed mapping or record its malformed boundary."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        errors.append(f"responsibility_map_{label}_must_be_table")
        return {}
    return dict(value)


def audit(root: Path = ROOT, policy_path: Path = MAP) -> dict[str, object]:
    """Return exact ownership gaps for carriers, scopes, concerns, and configuration."""
    policy = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if policy.get("schema_version") != 1:
        errors.append("responsibility_map_schema_version_must_be_1")
    for field in ("owner", "purpose"):
        value = policy.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"responsibility_map_{field}_must_be_nonempty_string")

    roles: dict[str, dict[str, object]] = {}
    for index, raw_role in enumerate(policy.get("roles", [])):
        role = _mapping(raw_role, label=f"role_{index}", errors=errors)
        identifier = role.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"responsibility_map_role_{index}_id_must_be_nonempty_string")
            continue
        if identifier in roles:
            errors.append(f"responsibility_map_duplicate_role:{identifier}")
            continue
        description = role.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(f"responsibility_map_role_description_missing:{identifier}")
        files = _optional_strings(role.get("files"))
        prefixes = _optional_strings(role.get("prefixes"))
        if not files and not prefixes:
            errors.append(f"responsibility_map_role_scope_missing:{identifier}")
        if not all(isinstance(path, str) and path for path in (*files, *prefixes)):
            errors.append(f"responsibility_map_role_scope_invalid:{identifier}")
        roles[identifier] = role

    scopes: dict[str, tuple[str, ...]] = {}
    for index, raw_scope in enumerate(policy.get("scopes", [])):
        scope = _mapping(raw_scope, label=f"scope_{index}", errors=errors)
        identifier = scope.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"responsibility_map_scope_{index}_id_must_be_nonempty_string")
            continue
        if identifier in scopes:
            errors.append(f"responsibility_map_duplicate_scope:{identifier}")
            continue
        role_ids = _strings(scope.get("roles"), field=f"scope_{identifier}_roles", errors=errors)
        errors.extend(
            f"responsibility_map_unknown_role:{identifier}:{role_id}"
            for role_id in role_ids
            if role_id not in roles
        )
        scopes[identifier] = role_ids

    concerns: dict[str, dict[str, object]] = {}
    for index, raw_concern in enumerate(policy.get("concerns", [])):
        concern = _mapping(raw_concern, label=f"concern_{index}", errors=errors)
        identifier = concern.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"responsibility_map_concern_{index}_id_must_be_nonempty_string")
            continue
        if identifier in concerns:
            errors.append(f"responsibility_map_duplicate_concern:{identifier}")
            continue
        for field in ("owner", "scope", "session", *RATIONALE_FIELDS):
            value = concern.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.extend([f"responsibility_map_concern_field_missing:{identifier}:{field}"])
        scope = concern.get("scope")
        if isinstance(scope, str) and scope not in roles and scope not in scopes:
            errors.append(f"responsibility_map_unknown_scope:{identifier}:{scope}")
        configurations = _strings(
            concern.get("configuration"),
            field=f"concern_{identifier}_configuration",
            errors=errors,
        )
        errors.extend(
            f"responsibility_map_missing_configuration:{identifier}:{configuration}"
            for configuration in configurations
            if not (root / configuration).is_file()
        )
        concerns[identifier] = concern

    assignments: dict[str, str] = {}
    for path in _tracked_paths(root):
        owners = [identifier for identifier, role in roles.items() if _role_matches(path, role)]
        if not owners:
            errors.append(f"responsibility_map_unowned_carrier:{path}")
        elif len(owners) > 1:
            errors.append(f"responsibility_map_multiple_roles:{path}:{','.join(sorted(owners))}")
        else:
            assignments[path] = owners[0]

    return {
        "ok": not errors,
        "errors": sorted(errors),
        "roles": sorted(roles),
        "scopes": sorted(scopes),
        "concerns": sorted(concerns),
        "assignments": assignments,
    }


def main(argv: Iterable[str] = ()) -> None:
    """Print the responsibility audit as stable JSON and fail on every gap."""
    if tuple(argv):
        raise SystemExit("responsibility audit accepts no arguments")
    report = audit()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
