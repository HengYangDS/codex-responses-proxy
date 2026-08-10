# Evidence layout Specification

## Purpose

Define the durable project-owned evidence roots and preserve one semantic owner
for independent Forge parity auditing.

## Requirements
### Requirement: Durable evidence roots have one project meaning

The repository SHALL admit only top-level evidence roots with a current,
project-owned acceptance meaning. Claims and chronicles SHALL remain the only
durable roots until another evidence family is deliberately specified and gated.

#### Scenario: An unowned evidence root is introduced

- **WHEN** a tracked or physical top-level directory appears below `evidence/`
  without an admitted project meaning
- **THEN** the repository quality command reports that directory
- **AND** the change cannot pass quality proof.

### Requirement: Forge parity retains its existing semantic owner

Dual-Forge source and release equality SHALL remain a publication concern owned
by the Forge auditor. It SHALL NOT be projected into a generic adopter-parity
directory merely to preserve an empty layout.

#### Scenario: Cross-Forge parity is audited

- **WHEN** GitLab and GitHub publication state is compared
- **THEN** `tools/forge/audit.py` produces the read-only parity result
- **AND** no `evidence/parity` carrier is required.

