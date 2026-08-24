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

### Requirement: GitLab publication preserves credential semantics

The publication composition root SHALL require one declared GitLab credential
kind and SHALL map a CI job token to `JOB-TOKEN` and a personal, project, or
group access token to `PRIVATE-TOKEN`. It SHALL read only the environment
variable owned by the declared kind and SHALL NOT guess or fall through to a
different credential kind.

#### Scenario: A maintainer publishes outside GitLab CI

- **WHEN** the maintainer selects `private-token`
- **THEN** publication reads the product-scoped private-token variable
- **AND** every GitLab request uses `PRIVATE-TOKEN`
- **AND** an available `CI_JOB_TOKEN` cannot silently replace the selected credential.
