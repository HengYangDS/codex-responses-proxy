# Design

Provider-local release validation and cross-provider parity are separate
operations.

| Operation | Authority | Timing |
| --- | --- | --- |
| Metadata and tag validation | Selected Forge | Before publication |
| Asset build and Release | Selected Forge | During publication |
| Tree and asset parity | Read-only audit | After both publications |

The regression clones the exact source commit, removes only the pending tag,
then runs the same metadata command for GitLab and GitHub. This models either
Forge preparing the release without inventing a second implementation.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| Independent provider preparation | `1.1` | `test_each_provider_can_independently_prepare_the_release` |
