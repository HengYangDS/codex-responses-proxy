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

#### Scenario: A POSIX bundle contains internal symlinks

- **WHEN** the host supports the modeled POSIX symlink semantics
- **THEN** release assembly materializes internal links
- **AND** rejects links that resolve outside the bundle
