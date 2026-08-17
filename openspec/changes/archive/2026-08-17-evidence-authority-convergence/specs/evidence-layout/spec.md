## MODIFIED Requirements

### Requirement: Current evidence has one authority chain

The repository SHALL NOT maintain a tracked `evidence/` root, Claim family,
Chronicle family, or compatibility taxonomy. Current acceptance SHALL derive
from exact repository facts, tests, OpenSpec history, release artifacts, and
ETHOS-selected Attestations. A claim SHALL be a proposition within such a
bounded result rather than an independent carrier.

#### Scenario: A result is evaluated

- **WHEN** a local, hosted, publication, installation, or runtime result is evaluated
- **THEN** its exact source revision, verifier, scope, evidence, and limit are explicit
- **AND** no tracked Claim or Chronicle is required.

#### Scenario: Historical explanation is retained

- **WHEN** historical rationale remains useful
- **THEN** it is retained by OpenSpec archive, decision record, Changelog, or Git history
- **AND** it never becomes current acceptance authority.

### Requirement: Forge comparison has one semantic owner

Cross-Forge source and release comparison SHALL remain a transient publication
audit owned by the Forge audit command. It SHALL become durable only through a
revision-bound release artifact or ETHOS-selected Attestation.

#### Scenario: Forge state is compared

- **WHEN** GitLab and GitHub publication state is audited
- **THEN** the Forge audit command produces the comparison result
- **AND** no parallel evidence taxonomy is created.
