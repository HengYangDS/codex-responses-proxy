## MODIFIED Requirements

### Requirement: Local product closure is Forge-free

The repository SHALL declare one local verification command and one local
installation command that operate from its isolated locked environment. It SHALL
also declare distinct GitLab and GitHub remote aliases and tracked CI surfaces.
GitLab and GitHub SHALL remain independent publication peers: neither Forge may
consume the other Forge's CI status or release assets as publication authority.
Only `main`, `dev`, and `proposal/*` are remote-eligible; `candidate/dev` and
`work/*` remain local-only. Forge publication SHALL be an optional distribution
projection, not a prerequisite for local product closure. A completed
publication-topology Change SHALL carry only the minimal compare-and-swap
authority required by the governed candidate integration operation.

#### Scenario: Both Forges are unavailable

- **WHEN** a clean accepted checkout has no reachable remote
- **THEN** the declared repository-owned command can verify the current source
- **AND** an operator can install a verified current-platform artifact through
  the declared isolated product executable
- **AND** no hosted publication fact is falsely claimed.

#### Scenario: Either Forge is independently available

- **WHEN** GitLab or GitHub alone can receive an admitted remote-eligible branch
- **THEN** that Forge can run its own tracked CI and publish its own release
- **AND** the unavailable peer creates no dependency or substitute authority
- **AND** no `candidate/dev` or `work/*` ref is published.

#### Scenario: Source proof is complete

- **WHEN** exact-HEAD repository proof passes and the Change is archived
- **THEN** the governed landing command can atomically advance `candidate/dev`
- **AND** the permission does not authorize direct publication or runtime mutation
- **AND** no alternate integration path is introduced.
