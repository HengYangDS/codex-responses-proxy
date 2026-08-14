## 1. Release identity

- [x] 1.1 Advance `VERSION` to 2.0.34.
- [x] 1.2 Record the accepted GitLab Python identity repair in the Changelog.
- [x] 1.3 Add the forward-only patch scenario to the release identity contract.
- [x] 1.4 Remove the mutable release version from README installation examples.

## 2. Verification and delivery

- [x] 2.1 Pass release metadata, OpenSpec strict validation, and exact-HEAD proof.

## Delivery Boundary

Archive, candidate integration, accepted closeout, independent Forge
publication, trusted installation, runtime acceptance, and lane retirement are
post-Change lifecycle effects. Each remains incomplete until its own public
command receipt proves it; none is a prerequisite for archiving this completed
Change.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `1.1` | `VERSION` |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `1.2` | `CHANGELOG.md` |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `1.3` | `OpenSpec strict validation` |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `1.4` | `version-neutral README contract` |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `2.1` | `exact-HEAD proof attestation` |
