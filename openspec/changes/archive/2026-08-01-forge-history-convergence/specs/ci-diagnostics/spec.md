## MODIFIED Requirements

### Requirement: Provider identities are independent

GitLab SHALL retain accepted commits in its verified identity domain. GitHub
SHALL use its verified identity domain for an equivalent projection.

#### Scenario: Forge emails differ

- **WHEN** the two Forges require different verified emails
- **THEN** their commit IDs differ
- **AND** their corresponding trees are equal.

### Requirement: Projection continuity is append-only

A provider projection SHALL preserve messages, dates, ordered trees, and parent
topology after its admitted base and SHALL only fast-forward the target.

#### Scenario: GitHub already has an admitted base

- **WHEN** accepted source advances after the mapped GitHub tip
- **THEN** only missing descendants are projected
- **AND** the old GitHub tip remains an ancestor of the new tip.

### Requirement: Projection requires one lineage match

The projector SHALL require exactly one identity-neutral source match for an
existing provider tip before creating commits or updating refs.

#### Scenario: A target match is absent or ambiguous

- **WHEN** the provider tip has zero or multiple source matches
- **THEN** projection fails before any ref update
- **AND** it offers no force or rewrite escape.

### Requirement: Projection failures retain bounded diagnostics

The publication runner SHALL return a failed child status without adding a
Python exception traceback.

#### Scenario: A projection child rejects its invocation

- **WHEN** the child exits nonzero with its own diagnostic
- **THEN** the runner returns that status
- **AND** it emits no `Traceback` or `CalledProcessError` text.

### Requirement: Unpublished canonical descendants may converge

Accepted descendants not present on either Forge SHALL be replayed onto the
exact GitLab tip only after that tip has one identity-neutral accepted match.

#### Scenario: Accepted and GitLab histories are disconnected

- **WHEN** the histories match uniquely before unpublished accepted commits
- **THEN** only those descendants are replayed and re-signed
- **AND** duplicate-history merges and force updates remain forbidden.

### Requirement: Active GitLab signing key advances explicitly

New GitLab commits and tags SHALL use the selected registered fingerprint while
predecessor trust anchors remain available for immutable history.

#### Scenario: The active key changes

- **WHEN** a registered successor key is selected
- **THEN** runner, projection, tag command, agent, and trust input agree
- **AND** older reachable commits remain verifiable.
