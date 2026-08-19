## MODIFIED Requirements

### Requirement: A patch release has one source identity and independent Forge projections

`VERSION`, package metadata, Changelog, documentation, signed tag, and assets
SHALL derive from one accepted local commit. The release tag SHALL be signed
once as one local Git tag object and pushed unchanged to either optional Forge.
Each Forge SHALL run and publish independently without consuming the other.

#### Scenario: Both Forge planes publish the current patch

- **WHEN** local exact-HEAD proof passes and the signed local tag exists
- **THEN** GitLab and GitHub receive the same commit OID and tag object OID
- **AND** each publishes its own CI result, Release record, and complete assets
- **AND** a later read-only audit compares exact identities and payload digests.

#### Scenario: One Forge publication fails

- **WHEN** either Forge cannot publish
- **THEN** the other remains independently publishable and usable
- **AND** no local or peer Git object is rewritten to conceal the failure.

#### Scenario: A release asset is installed

- **WHEN** an operator installs the platform archive for the value in `VERSION`
- **THEN** the installer verifies the complete release set and external trust anchor before mutation
- **AND** the installed executable reports that exact version and passes runtime acceptance.

#### Scenario: Accepted source advances after a release

- **WHEN** an accepted unreleased repair changes the source tree after the
  version in the latest immutable tag
- **THEN** `VERSION` advances to one newer SemVer patch before publication
- **AND** the Changelog records the repair under that same version
- **AND** existing tags, runs, Releases, and assets remain unchanged.

#### Scenario: GitLab publishes from the immutable runtime

- **WHEN** GitLab publishes the current patch
- **THEN** the job uses the repository-declared immutable release runtime
- **AND** it does not install operating-system packages during publication.

### Requirement: Dual-Forge lineage compares exact current identity

The parity audit SHALL require local, GitLab, and GitHub current branch OIDs and
release tag object OIDs to be equal. Equal trees or an equal ordered tree suffix
SHALL NOT substitute for exact object identity.

#### Scenario: Provider tips have equal trees but different commits

- **WHEN** GitLab and GitHub point to different commit OIDs with equal trees
- **THEN** parity fails
- **AND** publication remains incomplete until both refs equal the local source OID.

## ADDED Requirements

### Requirement: Product release metadata is Forge-neutral

The release metadata validator SHALL derive product version, Changelog, and tag
state only from the exact local checkout. Forge selection, transport identity,
and peer-local Release records SHALL remain outside that product semantic.

#### Scenario: Either Forge validates the same source object

- **WHEN** GitLab or GitHub runs release metadata validation for the same commit
- **THEN** both invoke the same provider-free command and observe the same result
- **AND** no provider flag, provider tag namespace, or compatibility alias exists.

## REMOVED Requirements

### Requirement: Forge continuity recovery is exact and forward-only

**Reason**: provider-specific histories no longer exist; the exact local object is
the only source and exact remote CAS owns replacement safety.

**Migration**: perform one explicit expected-tip replacement, then use ordinary
fast-forward publication.

### Requirement: Explicit continuity maps only successors after its exact base

**Reason**: there is no source-to-provider history mapping in the terminal model.

**Migration**: delete continuity maps and verify exact branch/tag OIDs directly.
