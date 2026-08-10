## MODIFIED Requirements

### Requirement: Native bundle containment uses filesystem identity

Release assembly MUST accept a resolved member inside the resolved bundle under
the host filesystem's canonical path identity, MUST reject external members,
and MUST exercise symlink behavior only on hosts that provide the modeled
filesystem semantics.

#### Scenario: Windows canonicalization rewrites separators

- **WHEN** Windows canonical path inputs compare through a host `commonpath`
- **THEN** the comparison result is normalized before identity comparison
- **AND** an internal case-variant member remains accepted

#### Scenario: Windows returns a case-variant path spelling

- **WHEN** an internal resolved member differs from the bundle path only by case
- **THEN** release assembly accepts the member
- **AND** retains its logical bundle path

#### Scenario: A symlink resolves outside the bundle

- **WHEN** a member resolves outside the canonical bundle boundary
- **THEN** release assembly fails closed
- **AND** publishes no asset from that invocation

#### Scenario: A POSIX bundle contains internal symlinks

- **WHEN** the host supports the modeled POSIX symlink semantics
- **THEN** release assembly materializes internal links
- **AND** rejects links that resolve outside the bundle
