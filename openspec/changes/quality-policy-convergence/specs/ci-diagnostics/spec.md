## MODIFIED Requirements

### Requirement: Coverage is strict and host-independent

The complete behavior suite SHALL keep aggregate and every semantic package's
statement and branch ratios above the floor declared by the canonical coverage
policy. The policy SHALL state its risk model, exact measurement,
false-positive cost, remediation path, and review condition. File-level ratios
MAY be reported for diagnosis but SHALL NOT independently block promotion.

#### Scenario: a quality gate succeeds

- **WHEN** coverage is evaluated for the exact candidate tree
- **THEN** aggregate and semantic-package ratios satisfy the canonical policy
- **AND** no duplicated threshold or file-sized ratio changes the verdict.

#### Scenario: A quality gate succeeds

- **WHEN** coverage is reported for the exact candidate tree
- **THEN** every aggregate and semantic-package ratio satisfies the canonical policy
- **AND** no required test is skipped merely because the quality host differs from the modeled platform.

#### Scenario: platform behavior contributes coverage

- **WHEN** a platform branch cannot execute natively on the quality host
- **THEN** explicit semantic inputs exercise the branch without host spoofing
- **AND** no exclusion or CI-only production condition substitutes for behavior.
