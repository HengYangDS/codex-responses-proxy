## ADDED Requirements

### Requirement: Accepted corrections advance through immutable SemVer releases

Accepted source that is absent from the latest published release SHALL receive
a new Semantic Versioning identity and immutable signed tag. `VERSION` SHALL
remain the sole version authority, `CHANGELOG.md` SHALL record the forward
release history, and previously published provenance SHALL NOT be rewritten.

#### Scenario: Backward-compatible defect correction is ready for release

- **WHEN** accepted source corrects a defect without changing the public
  compatibility contract and is absent from the latest published release
- **THEN** the release owner SHALL advance the patch version
- **AND** the new signed tag and release bundle SHALL bind that exact accepted
  source.

#### Scenario: Earlier release provenance already exists

- **WHEN** a correction follows an existing published version
- **THEN** the correction SHALL use a later SemVer identity
- **AND** the earlier tag, release record, and assets SHALL remain unchanged.
