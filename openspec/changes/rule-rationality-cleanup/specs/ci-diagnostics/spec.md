## REMOVED Requirements

### Requirement: Python structure limits are repository-owned

**Reason:** Repository structure is governed by the positive semantic topology
in `quality-boundaries`. Fixed statement, ELOC, function-size, and nesting
ceilings have no admitted product-risk model and duplicate that authority.

**Migration:** Keep source-size and nesting observations as non-blocking review
evidence. Admit a future blocking threshold only through an explicit risk model,
measurement definition, false-positive analysis, remediation path, and review
condition.

#### Scenario: the obsolete structural ceiling is evaluated

- **WHEN** repository quality evaluates source structure
- **THEN** semantic topology and dependency contracts determine admission
- **AND** descriptive size or nesting measurements do not independently reject the change.
