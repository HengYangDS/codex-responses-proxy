## ADDED Requirements

### Requirement: Native handoff fixtures release temporary bundles

Native release acceptance MUST terminate and re-observe every fixture-owned
proxy process before removing its copied bundle, MUST tolerate only a transient
Windows mapped-module lock for a bounded interval, and MUST fail if the payload
remains locked.

#### Scenario: Windows releases a mapped module after process exit

- **WHEN** every fixture-owned proxy process has exited
- **AND** the first payload cleanup reports `PermissionError`
- **THEN** acceptance retries cleanup within a bounded deadline
- **AND** succeeds when the lock is released

#### Scenario: The payload remains locked

- **WHEN** cleanup continues to report `PermissionError` through the deadline
- **THEN** acceptance fails
- **AND** does not hide the residual payload

#### Scenario: Cleanup reports another error

- **WHEN** payload cleanup reports an error other than `PermissionError`
- **THEN** acceptance fails immediately
