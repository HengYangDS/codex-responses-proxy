# Documentation Root

Status: canonical.

This repository uses a deliberately small documentation kernel. It separates
stable boundary knowledge, durable decisions, dated proof, and release history
without copying a larger governance system into a small transport adapter.

| Surface | Owns |
| --- | --- |
| [architecture/](architecture/authority-and-runtime-boundary.md) | Component boundaries and runtime projection model. |
| [governance/](governance/release-and-change-policy.md) | Change, release, and contributor rules. |
| [decisions/](decisions/0001-control-plane-data-plane-boundary.md) | Durable, revisitable design rulings. |
| [evidence/](evidence/README.md) | Verification records and proof limits. |
| [operations/](operations/forge-operations.md) | Independent GitLab and GitHub forge operation. |
| [CHANGELOG](../CHANGELOG.md) | Published release history. |

Source, tests, `VERSION`, and CI remain higher authority than prose. Generated
runtime files and host logs are evidence only.
