## ADDED Requirements

### Requirement: Commit grammar follows the checkout's available integration boundary

Commit-subject verification MUST validate the change range after the most local
available integration boundary without requiring local governance refs in a
Forge checkout.

#### Scenario: A Work Lane has a candidate boundary

- **WHEN** `candidate/dev` is available
- **THEN** only commits after that candidate boundary are checked
- **AND** an invalid Work Lane subject is rejected.

#### Scenario: A Forge tag checkout has no candidate ref

- **WHEN** the checkout exposes `origin/dev` or `origin/main` but no `candidate/dev`
- **THEN** the available remote integration ref is used as the boundary
- **AND** an invalid subject after that boundary is rejected
- **AND** no candidate or Work Lane ref is published to satisfy the checker.

#### Scenario: No integration boundary is available

- **WHEN** the repository has Git history but none of the declared integration refs
- **THEN** all available history is checked
- **AND** history unavailability remains a fail-closed diagnostic.
