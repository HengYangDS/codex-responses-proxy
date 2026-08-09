## MODIFIED Requirements

### Requirement: Supply-chain pins are current and reproducible

Project metadata SHALL declare exact audited stable quality and packaging
dependencies, the committed uv lock SHALL own their transitive closure, hosted
Actions SHALL use immutable revisions, and GitLab Python images SHALL use supported minor tags bound to immutable registry digests.

#### Scenario: A GitLab Python image is selected

- **WHEN** a GitLab job selects the supported floor or latest Python image
- **THEN** the reference contains the supported minor tag and a SHA-256 digest
- **AND** its minor version matches the corresponding boundary in
  `.python-versions`
- **AND** tests derive this relation instead of duplicating the concrete pin.

#### Scenario: The supply chain advances

- **WHEN** an audited stable dependency, hosted Action release, or CI base image
  supersedes the repository pin
- **THEN** its existing SSOT is updated without adding a parallel version owner
- **AND** lock, workflow, and repository quality contracts pass together.

## Requirement To Task To Proof

| Requirement | Task | Proof |
|---|---|---|
| `ci-diagnostics:Supply-chain pins are current and reproducible` | `1.1` | `nox:quality` |
