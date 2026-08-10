# Tasks

## Source change

- [x] 1.1 Advance `VERSION`, `CHANGELOG.md`, and README asset examples to `2.0.20`.
- [x] 1.2 Pass focused metadata, documentation, and strict OpenSpec validation.
- [x] 2.1 Pass quick, quality, Python 3.12/3.13/3.14, native release, and exact-HEAD ETHOS proof.
- [x] 2.2 Prepare the signed source commit for the governed archive and candidate/accepted landing transition.

## Post-archive delivery contract

- [x] 3.1 Define independent GitLab and GitHub publication receipts from the same accepted source commit.
- [x] 3.2 Define the read-only cross-Forge source/tree/asset parity audit.
- [x] 4.1 Define trusted v2.0.20 installation and payload-integrity evidence.
- [x] 4.2 Define provider switching, replay portability, bounded recovery, rate-limit handling, original-session continuity, and PyCharm MCP acceptance evidence.
- [x] 5.1 Define owner-bound lane retirement and repository-family housekeeping evidence.

## Post-archive execution order

These are external transitions and are deliberately not asserted by this source
Change. Execute them only after the proven commit is archived and landed:

1. Land the proven source through candidate and accepted roles.
2. Publish signed v2.0.20 tags, Releases, and complete assets independently on GitLab and GitHub.
3. Compare both Forge projections read-only; one Forge failure must not block the other.
4. Install one trusted asset and verify the native service, payload integrity, and runtime behavior.
5. Retire only represented, owner-authorized lanes and remove disposable residue.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `1.1` | `release-metadata-and-documentation-gates` |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `2.1` | `exact-head-local-proof` |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `3.1` | `independent-forge-publication-receipts` |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `3.2` | `cross-forge-source-and-asset-audit` |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `4.1` | `trusted-installation-receipt` |
| `ci-diagnostics:A patch release has one source identity and independent Forge projections` | `4.2` | `three-provider-runtime-acceptance` |

OpenSpec archival proves only repository-local completion. Hosted publication,
installation, and runtime acceptance require fresh external evidence.
