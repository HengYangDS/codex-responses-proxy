## ADDED Requirements

### Requirement: Forge history matching is linear

The GitHub projector SHALL compute each canonical and projected commit's
identity-neutral fingerprint at most once per invocation and SHALL join those
indexes without weakening publication admission.

#### Scenario: A long admitted projection gains one descendant

- **WHEN** one canonical commit follows an existing GitHub projection
- **THEN** matching work grows with the combined canonical and projected history
- **AND** it does not recompute fingerprints for every source-target pair
- **AND** the target still advances only by an ordinary fast-forward push.
