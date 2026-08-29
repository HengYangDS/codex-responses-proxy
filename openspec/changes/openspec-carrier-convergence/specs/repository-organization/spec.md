## MODIFIED Requirements

### Requirement: Semantic documentation architecture

Proxy SHALL use the resolved official OpenSpec workflow artifacts as the sole
tracked authority for product change intent and SHALL organize its small
canonical documentation kernel by semantic domain. ETHOS SHALL derive a
transient Commitment containing only `schema_version`, `id`, and `acceptance`
from the selected OpenSpec projection when governance evaluation requires it.
An additional tracked carrier SHALL exist only when it owns a current invariant
that official OpenSpec artifacts and existing authorities cannot represent, has
one named owner and current consumer, replaces rather than parallels another
authority, and defines its retirement condition. Content document filenames
SHALL state their subjects. Repository checks and release metadata SHALL
consume those semantic paths directly.

#### Scenario: Reader enters the documentation

- **WHEN** a reader starts at `docs/README.md`
- **THEN** every canonical document SHALL be reachable through the domain map
- **AND** no redirect-only local index SHALL be required.

#### Scenario: A content-bearing register or policy is stored

- **WHEN** a document owns Decision Record registration or evidence policy
- **THEN** its filename SHALL identify that subject
- **AND** no container-named compatibility copy SHALL remain.

#### Scenario: Repository tooling consumes documentation paths

- **WHEN** quality or release validation reads a canonical document
- **THEN** it SHALL use the same semantic path exposed to readers
- **AND** the documentation tree and executable contract SHALL not diverge.

#### Scenario: Official OpenSpec artifacts carry the intent

- **WHEN** proposal, specification, design, tasks, metadata, configuration, or
  Git history already carry all current meaning for a Change
- **THEN** the repository SHALL retain no additional summary, scope inventory,
  capability descriptor, empty index, or equivalent parallel carrier.

#### Scenario: An additional carrier is necessary

- **WHEN** an invariant cannot be represented by official OpenSpec artifacts or
  an existing authority
- **THEN** the carrier SHALL identify its unique invariant, owner, current
  consumer, replaced authority, and retirement condition
- **AND** validation SHALL reject it if any fact is absent or unverifiable.

#### Scenario: Governance evaluates change intent

- **WHEN** ETHOS evaluates the selected OpenSpec change
- **THEN** it SHALL compile the Commitment transiently from official OpenSpec
  artifacts
- **AND** the repository SHALL persist no parallel Commitment carrier.

#### Scenario: Historical change evidence is inspected

- **WHEN** a maintainer inspects an archived change
- **THEN** official OpenSpec archives and Git history SHALL describe the tracked
  change
- **AND** ETHOS Attestations SHALL remain the effect-evidence surface.
