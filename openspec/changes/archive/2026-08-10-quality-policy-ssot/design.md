# Design

## Ownership

| Concern | Owner | Consumer |
| --- | --- | --- |
| Lint and format | `.config/checks/ruff/ruff.toml` | Ruff through Nox |
| Test discovery and warnings | `pytest.ini` | pytest native discovery |
| Type analysis | `.config/checks/ty/ty.toml` | Ty through Nox |
| Coverage measurement | `.config/checks/coverage/coverage.ini` | coverage.py through Nox |
| Coverage hard floor | `.config/checks/coverage/policy.toml` | coverage gate |
| Structure and dependency direction | `.config/checks/architecture/policy.toml` | repository gate |
| Commit grammar | `.config/checks/commits/policy.toml` | repository gate and hooks |
| Editor defaults | `.editorconfig` | IDEs and editors |
| Text layout | `.config/checks/text-layout/policy.toml` | repository gate |

`pyproject.toml` retains build, package, dependency, and distribution metadata.
Nox owns reusable orchestration. ETHOS registers and attests Nox gates. CI and
hooks remain projections and do not restate policy.

## Commit grammar

Human-authored commits use `type(scope): imperative subject`. Types and scopes
are closed positive sets. ETHOS-generated lifecycle commits are admitted by
explicit semantic patterns rather than by weakening the human grammar.
