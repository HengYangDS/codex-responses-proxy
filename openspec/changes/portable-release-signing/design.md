# Design

The protected Forge environment owns private-key creation, permissions, and
cleanup. Release tooling receives only an existing path, rejects missing or
symbolic-link inputs, and delegates signing and verification to OpenSSH.

| Boundary | Owner |
| --- | --- |
| Key material and native permissions | Forge secret environment |
| Asset assembly | `tools.release.assemble_assets` |
| SSHSIG generation and verification | `tools.release.signing` |
| Input-shape regression | Release and workflow contract tests |

This removes one secret copy and one platform-specific permission assumption
without adding a second cryptographic implementation.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Release signing uses one provider-owned key path` | `1.1` | `release-signing-contracts` |
