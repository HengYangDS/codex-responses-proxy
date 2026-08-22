## MODIFIED Requirements

### Requirement: CI projects the complete repository quality contract

The repository SHALL own one explicit quality graph whose concerns cover every
tracked carrier and whose commands are composed once in repository-owned Nox
sessions. Local development, repository hooks, GitHub, and GitLab SHALL invoke
those sessions as projections rather than duplicate their command bodies. CUE
SHALL validate the semantic equivalence of both Forge projections while allowing
only runner-native setup and capability-specific platform differences. A green
subset, repeated equivalent jobs, or success on one Forge SHALL NOT be
represented as complete repository quality.

#### Scenario: A proposal revision is pushed

- **WHEN** either Forge receives a new proposal commit
- **THEN** source governance, Python quality, each supported Python runtime, and applicable platform/release checks execute for that exact commit
- **AND** a previous green commit cannot satisfy the revised proposal.

#### Scenario: A maintainer advances an accepted branch

- **WHEN** `dev` or `main` advances by an authorized maintainer path
- **THEN** the same repository-owned graph executes for the resulting exact commit
- **AND** direct fast-forward authority does not bypass product proof.

#### Scenario: Forge projections are compared

- **WHEN** repository governance renders or validates GitHub and GitLab CI
- **THEN** both projections contain the same named semantic gates and consume the same Nox owners
- **AND** provider YAML contains no independent quality-policy implementation.

#### Scenario: A tag is evaluated

- **WHEN** an annotated release tag is proposed
- **THEN** the tag pipeline proves source identity, the complete quality graph, supported runtimes, native assets, and release metadata for the tagged commit
- **AND** no branch result or other Forge result substitutes for the tag's own evidence.

#### Scenario: Python quality is evaluated

- **WHEN** repository Python is admitted
- **THEN** formatting, correctness, modernization, imports, typing, naming, exceptions, logging, subprocess safety, security-sensitive execution, pytest idioms, complexity, and performance-smell rules SHALL be evaluated
- **AND** type diagnostics and warnings SHALL fail the gate
- **AND** source or test suppressions SHALL NOT be used to satisfy newly admitted rules.

#### Scenario: Non-Python carriers are evaluated

- **WHEN** repository quality executes
- **THEN** TOML, YAML, JSON/schema, Markdown, prose, links, workflow syntax, secrets, OpenSpec, generated projections, semantic names, commit subjects, decision records, dependency direction, dependency hygiene, package build, installed artifact behavior, and text-byte invariants SHALL each have an explicit owner or an explicit product-irrelevance decision
- **AND** each admitted concern SHALL run over its complete declared inventory.

#### Scenario: A stricter rule is proposed

- **WHEN** a rule family or threshold is added or tightened
- **THEN** its defect class, scope, false-positive cost, remediation, and review condition SHALL be declared
- **AND** existing findings SHALL be repaired or the rule SHALL remain visibly pending
- **AND** copying another repository's number or configuration SHALL NOT itself establish suitability.
