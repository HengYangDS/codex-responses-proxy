## MODIFIED Requirements

### Requirement: Failed upgrades restore the exact prior payload

When a released upgrade fails after projecting candidate bytes, rollback MUST
restore every retained prior byte and MUST remove every verified candidate file
that was absent from the prior snapshot.

#### Scenario: Candidate adds a new frozen-runtime member

- **WHEN** an upgrade projects a candidate-only file below `bin/`
- **AND** the handoff fails and rollback runs
- **THEN** the candidate-only file is absent
- **AND** the previous manifest, receipt, installed state, executable, and provider manifest are restored exactly
- **AND** content outside the prior-owned and candidate inventories remains unchanged

## Requirement To Task To Proof

| Requirement | Task | Proof |
|---|---|---|
| `runtime-upgrade:Failed upgrades restore the exact prior payload` | `1.2` | `tests/lifecycle/test_transaction.py::test_upgrade_rollback_removes_candidate_only_runtime_members` |
