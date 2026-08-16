## MODIFIED Requirements

### Requirement: Native release validation exercises the installed product

Release validation SHALL exercise the exact native executable that installation
will serve. A temporary copy SHALL NOT be treated as proof that the final
installed inode has paid its first-start cost.

#### Scenario: An operator upgrades a running installation

- **WHEN** a verified release is committed as the successor projection
- **THEN** the exact installed executable completes a bounded prewarm probe
- **AND** the handoff uses the operator's configured installation deadline.
