# Documentation Root

Status: canonical.

This repository uses a deliberately small documentation kernel. It separates
stable boundary knowledge, durable decisions, proof limits, and release history
without copying a larger governance system into a small transport adapter.

| Surface | Owns |
| --- | --- |
| [architecture/](architecture/authority-and-runtime-boundary.md) | Component boundaries and runtime projection model. |
| [governance/](governance/release-and-change-policy.md) | Change, release, and contributor rules. |
| [decisions/](decisions/README.md) | Decision grammar, coverage rule, and durable rulings. |
| [evidence/](evidence/README.md) | Proof requirements and evidence limits. |
| [operations/](operations/forge-operations.md) | Independent GitLab and GitHub forge operation. |
| [OpenSpec](../openspec/) | Current specifications and active change. |
| [CHANGELOG](../CHANGELOG.md) | Published release history. |

Source, tests, `VERSION`, and CI remain higher authority than prose. Generated
runtime files and host logs are evidence only.
