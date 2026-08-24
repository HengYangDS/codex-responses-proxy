## ADDED Requirements

### Requirement: Hosted evidence has one composition boundary

Each provider adapter SHALL validate its Forge-specific required jobs before
returning hosted evidence. The publication orchestrator SHALL normalize that
validated evidence into one closed provider-neutral evaluator schema; the
evaluator SHALL reject unknown fields rather than accept parallel provider
shapes.

#### Scenario: Adapter-shaped evidence reaches the evaluator

- **WHEN** GitHub and GitLab adapters have validated their complete required-job sets
- **THEN** the orchestrator passes only the canonical CI identity fields to the evaluator
- **AND** the resulting evidence preserves the provider adapters' successful verdict
- **AND** unknown evaluator fields still fail closed.
