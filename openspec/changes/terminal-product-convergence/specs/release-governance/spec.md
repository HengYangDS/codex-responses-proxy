## ADDED Requirements

### Requirement: One CI model covers every integration path

CUE SHALL own the semantic CI graph, including jobs, dependencies, triggers,
matrices, platform claims, evidence reuse, release admission, and generated
projection inventory. GitHub Actions and GitLab CI SHALL be checked projections
of that graph. Proposal review, proposal update, maintainer fast-forward, `dev`,
`main`, and tag events SHALL each produce or consume exact-revision evidence
without duplicating jobs that prove no additional fact.

#### Scenario: A developer updates a proposal

- **WHEN** the proposal review SHA changes
- **THEN** the required review graph runs for that exact SHA
- **AND** successful merge deletes the unprotected proposal branch.

#### Scenario: A maintainer fast-forwards an admitted commit

- **WHEN** the exact commit already has reusable evidence for the unchanged
  source, locks, platform, and release context
- **THEN** the target consumes that revision-bound evidence
- **AND** any changed proof input triggers only the newly required jobs.

### Requirement: Publication closes source, Forge, and branch state

A release SHALL create one signed local commit and annotated tag object, project
those exact objects independently to selected Forges, publish complete matching
asset inventories, and retire merged proposal and delivery refs. GitHub and
GitLab MAY supply different native runner sets, but each projection SHALL state
the facts it proves and SHALL NOT relabel another platform's evidence.

#### Scenario: A release is complete

- **WHEN** both selected Forge publications and installed-product acceptance pass
- **THEN** local and remote `main` and `dev` identify the accepted object
- **AND** merged proposal branches, remote `work/*`, draft releases, and failed
  unpublished intermediates have been removed.
