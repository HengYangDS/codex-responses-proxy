# Documentation

This repository uses a deliberately small documentation kernel. It separates
stable boundary knowledge, durable decisions, proof limits, and release history
without copying a larger governance system into a small transport adapter.

| Domain         | Document                                                                         | Owns                                                                                |
| -------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Architecture   | [Authority and runtime boundary](architecture/authority-and-runtime-boundary.md) | Product position, component boundaries, Provider admission, and runtime projection. |
| Decisions      | [Decision register](decisions/decision-register.md)                              | Decision grammar, coverage rule, and durable rulings.                               |
| Evidence       | [Evidence policy](evidence/evidence-policy.md)                                   | Proof requirements and evidence limits.                                             |
| Governance     | [Release and change policy](governance/release-and-change-policy.md)             | Change, release, and contributor rules.                                             |
| Operations     | [Forge operations](operations/forge-operations.md)                               | Independent GitLab and GitHub operation.                                            |
| Specifications | [OpenSpec](../openspec/)                                                         | Current specifications and active change.                                           |
| History        | [Changelog](../CHANGELOG.md)                                                     | Published release history.                                                          |

Source, tests, `VERSION`, and CI remain higher authority than prose. Generated
runtime files and host logs are evidence only.
