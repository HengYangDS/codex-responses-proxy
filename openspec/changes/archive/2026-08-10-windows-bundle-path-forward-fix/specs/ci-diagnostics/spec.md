## ADDED Requirements

### Requirement: Native bundle containment uses filesystem identity

Release assembly MUST accept a resolved member inside the resolved bundle under
the host filesystem's canonical path identity and MUST reject external members.

#### Scenario: Windows returns a case-variant path spelling

- **WHEN** an internal resolved member differs from the bundle path only by case
- **THEN** release assembly accepts the member
- **AND** retains its logical bundle path

#### Scenario: A symlink resolves outside the bundle

- **WHEN** a member resolves outside the canonical bundle boundary
- **THEN** release assembly fails closed
- **AND** publishes no asset from that invocation
