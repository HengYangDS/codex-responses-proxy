## ADDED Requirements

### Requirement: Forge continuity recovery is exact and forward-only

When a trusted provider tip lacks a direct canonical fingerprint match, the
projector SHALL resume only from an explicit canonical base, its exact projected
anchor, and the exact observed provider tip. It SHALL verify provider identity
and signatures, require one unique identity-neutral base match, and append
canonical successors without rewriting any existing ref.

#### Scenario: Exact continuity coordinates are current

- **WHEN** the canonical base has one provider match and the provider tip is unchanged
- **THEN** the provider tip becomes the append-only parent of the canonical base
- **AND** only canonical successors are recreated
- **AND** `main` and `dev` advance atomically without force.

#### Scenario: The provider changed after observation

- **WHEN** the live provider tip differs from the expected provider tip
- **THEN** projection fails before commit creation or ref mutation
- **AND** the caller must re-observe every continuity coordinate.

### Requirement: Dual-Forge lineage compares current semantic continuity

The parity audit SHALL require equal current tip trees and a non-empty equal
ordered tree suffix ending at both provider tips. It SHALL NOT require unrelated
historical prefixes from different provider cutovers to contain the same number
of commits.

#### Scenario: Provider cutovers have different historical prefixes

- **WHEN** GitLab and GitHub have independently trusted prefixes but share the current ordered tree suffix
- **THEN** lineage continuity passes
- **AND** provider provenance, tags, Releases, assets, and housekeeping remain independently checked.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Forge continuity recovery is exact and forward-only` | `1.1` | `tests/forge/test_forward_only.py` |
| `ci-diagnostics:Dual-Forge lineage compares current semantic continuity` | `1.4` | `tools/forge/audit.py; tests/forge/test_audit.py` |
