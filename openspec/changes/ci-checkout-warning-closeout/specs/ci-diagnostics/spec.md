## ADDED Requirements

### Requirement: Reused self-hosted checkout preserves diagnostic integrity

A GitHub job on the repository's reused self-hosted runner SHALL keep a valid
pre-checkout `HEAD` reachable only for the checkout transition and SHALL remove
that temporary reachability after checkout. The workflow SHALL NOT change
runner-global Git configuration or suppress unrelated Git diagnostics.

#### Scenario: Checkout replaces an unreferenced detached revision

- **WHEN** a trusted self-hosted job starts from a detached revision that no
  branch or tag retains
- **THEN** the workflow makes that revision reachable before checkout
- **AND** checkout does not emit the abandoned-commit warning
- **AND** an always-running post-checkout step removes the temporary ref.

#### Scenario: Hosted Windows checkout is isolated

- **WHEN** the supported Windows matrix uses its hosted runner workspace
- **THEN** it continues to use the ordinary pinned checkout action
- **AND** the self-hosted temporary-ref lifecycle is not projected into that
  job.
