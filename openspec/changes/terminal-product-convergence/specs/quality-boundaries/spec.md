## ADDED Requirements

### Requirement: Logical and physical topology are one positive model

The repository SHALL positively declare the semantic owner, role, allowed
dependency direction, public entrypoint, generated status, and retirement
condition for every tracked source, test, tool, configuration, specification,
documentation, workflow, schema, and root carrier. Physical packages and paths
SHALL mirror that model. Undeclared and multiply owned entities SHALL fail
admission without a historical forbidden-name list.

#### Scenario: A repository entity is added or moved

- **WHEN** repository quality evaluates the candidate tree
- **THEN** the entity resolves to exactly one declared semantic owner
- **AND** its imports, consumers, location, and name conform to the owner's
  dependency direction and vocabulary.

#### Scenario: A flat suffix family or catch-all owner exists

- **WHEN** files are distinguished by Provider, platform, action, or vague role
  suffixes instead of a semantic package boundary
- **THEN** convergence absorbs, precisely renames, splits, or deletes the owner
- **AND** no wrapper, alias, re-export, or forwarding compatibility path remains.

### Requirement: Quality rules are complete, rational, and singly owned

Every applicable formatting, import, correctness, modernization, naming,
documentation, typing, exception, logging, security, dependency, architecture,
dead-code, test, prose, configuration, link, workflow, secret, license,
vulnerability, coverage, complexity, performance, commit, and release concern
SHALL have one mature tool or product-semantic owner. Each blocking policy SHALL
state scope, protected risk, measurement, false-positive cost, remediation, and
review condition. Warnings, blanket ignores, permanent baselines, duplicate
thresholds, and unexplained disabled rules SHALL fail admission.

#### Scenario: A quality rule is reviewed

- **WHEN** maintainers inspect the responsibility map and native tool configuration
- **THEN** the rule has one authority and a proportionate evidence model
- **AND** custom code exists only where no mature tool can express the required
  repository or product semantic.

#### Scenario: A numeric threshold is proposed

- **WHEN** source size, complexity, nesting, parameters, coverage, or performance
  becomes blocking
- **THEN** the threshold derives from an explicit risk and observed distribution
- **AND** a stricter number is not accepted merely because it is smaller.

#### Scenario: A full verification prerequisite fails

- **WHEN** governance or quality fails in the ordered Nox full graph
- **THEN** native Nox stops before starting its dependent sessions
- **AND** preserves the failed result without claiming partial admission.

#### Scenario: Every full verification prerequisite passes

- **WHEN** the ordered full graph has successful prerequisites
- **THEN** every remaining declared Python session executes
- **AND** no required session is skipped to reduce verification time.

#### Scenario: Cold development uses a deeply nested home

- **WHEN** a clean checkout reconstructs its environment without operator state
- **THEN** the exact project configuration and complete release tags remain inputs
- **AND** isolated signing tests use a fixture-owned short native socket rather
  than the operator's authentication agent or a HOME-relative socket
- **AND** the exact foreground agent exits before its temporary files are removed.
