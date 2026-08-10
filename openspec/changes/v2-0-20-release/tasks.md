# Tasks

- [x] 1.1 Advance `VERSION`, `CHANGELOG.md`, and README asset examples to `2.0.20`.
- [x] 1.2 Pass focused metadata, documentation, and OpenSpec validation.
- [x] 2.1 Pass quick, quality, Python 3.12/3.13/3.14, native release, and exact-HEAD ETHOS proof.
- [ ] 2.2 Archive and land the release change from the proven commit.
- [ ] 3.1 Publish signed v2.0.20 tags, Releases, and complete assets independently on GitLab and GitHub.
- [ ] 3.2 Prove both Forge projections use the same source commit and byte-identical platform assets.
- [ ] 4.1 Install one trusted v2.0.20 native asset and verify service, version, and payload integrity.
- [ ] 4.2 Verify UCloud, DMXAPI, and AIHubMix switching, replay portability, bounded empty/non-text recovery, provider-scoped 429 handling, original-session continuity, and PyCharm MCP non-regression.
- [ ] 5.1 Retire absorbed lanes and complete repository-family housekeeping.

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
