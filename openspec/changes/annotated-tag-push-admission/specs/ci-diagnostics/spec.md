## MODIFIED Requirements

### Requirement: Protected Git publication remains proof-bound

Every non-deletion protected Git update SHALL pass ETHOS publication admission.
Branch updates SHALL bind admission to their pushed commit. Annotated tag
updates SHALL preserve the tag ref, prove that the tag object peels to a commit
contained in the current accepted history, and bind ETHOS proof admission to
the current accepted commit. Lightweight or unrelated tags MUST fail closed.

#### Scenario: A signed historical release tag is restored

- **WHEN** an unchanged annotated release tag is absent from a Forge
- **AND** its commit is contained in the current accepted history
- **THEN** the pre-push guard admits the tag ref against the proven current
  accepted commit
- **AND** release verification independently proves tag signature and exact
  object identity.
