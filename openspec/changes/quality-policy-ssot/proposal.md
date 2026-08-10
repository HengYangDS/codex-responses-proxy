# Quality Policy SSOT

## Why

ETHOS executes the repository gates, but Proxy quality policy is split between
`pyproject.toml`, Nox, and checker constants. Gate registration without explicit
policy owners leaves adoption structurally incomplete.

## What changes

- Move tool-native policy to explicit owners.
- Keep `.ethos/profile.toml` as the gate registry, not a threshold store.
- Enforce one scoped Conventional Commit grammar for human-authored commits.
- Preserve the existing quality floor while removing duplicate configuration.

## Non-goals

- Do not modify ETHOS source.
- Do not change runtime behavior or release identity.
- Do not add a second quality orchestrator beside Nox.
