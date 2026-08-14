## 1. Bind GitLab execution identity

- [x] 1.1 Add focused contracts for the target cache and synchronized Python identity.
- [x] 1.2 Bind every GitLab post-sync command to the selected interpreter.
- [x] 1.3 Cache UV-managed Python runtimes by declared target platform.

## 2. Verify and deliver

- [x] 2.1 Pass focused workflow and release metadata contracts.
- [x] 2.2 Pass the complete locked quality graph and native release checks.

## Delivery Boundary

Exact-HEAD proof, archive, land, Forge publication, runtime installation, and
lane retirement remain separately evidenced lifecycle effects.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Verification has one repository-owned owner` | `1.1` | `focused workflow contract fails before implementation` |
| `ci-diagnostics:Verification has one repository-owned owner` | `1.2` | `all post-sync commands use the explicit locked Python contract` |
| `ci-diagnostics:GitLab verification bootstrap is bounded and cached` | `1.3` | `target-platform cache includes the managed Python directory` |
| `ci-diagnostics:GitLab verification bootstrap is bounded and cached` | `2.1` | `workflow and release metadata tests pass` |
| `ci-diagnostics:Verification has one repository-owned owner` | `2.2` | `complete locked quality and release graph passes` |
