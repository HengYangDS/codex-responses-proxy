## MODIFIED Requirements

### Requirement: Recovery binds candidate, rollback, and live runtime

Recovery SHALL distinguish no transaction, an unmutated `prepared`
transaction, a `recovery_required` payload transition, and an invalid retained
transaction. No transaction SHALL be an idempotent successful no-op. A prepared
transaction SHALL be closed only when its canonical journal is the sole
transaction-root entry. Recovery of a mutated projection SHALL require one
canonical journal, a fully verified current candidate bundle, a fully verified
current rollback bundle, and matching accepting runtime identity. Any existing but unverifiable transaction carrier SHALL fail closed without
mutation and identify whether the transaction root or journal is missing, a
symbolic link, the wrong filesystem type, malformed JSON, non-canonical JSON,
an unsupported schema, or invalid under the current schema.

The public recovery result SHALL be exactly one of `not_required`, `closed`,
`finalized`, or `rolled_back`. `finalized` requires the accepting runtime to
match the committed candidate's release, serving payload, release receipt, and
manifest identities. `rolled_back` requires the retained rollback identity;
neither outcome may be inferred from process presence alone.

#### Scenario: No transaction exists

- **WHEN** the exact transaction root is absent
- **THEN** recovery succeeds with state `not_required`
- **AND** changes no payload, command, listener, service, or filesystem entry.

#### Scenario: A prepared transaction contains only its canonical journal

- **WHEN** admission completed but payload mutation never began
- **THEN** recovery removes the transaction root without changing payload,
  command, listener, or supervision
- **AND** reports the transaction as closed.

#### Scenario: A prepared transaction contains additional content

- **WHEN** any file, directory, link, or ambiguous journal field exists beyond
  the canonical prepared journal
- **THEN** recovery fails closed and preserves the complete transaction root.

#### Scenario: All identities agree

- **WHEN** release, complete file inventory, serving digest, receipt, manifest
  digest, transaction, and runtime state match
- **THEN** recovery restores the exact prior payload and clears the hold.

#### Scenario: Any identity differs

- **WHEN** a required byte, path, mode, digest, PID, state, or journal field
  differs
- **THEN** recovery fails closed without changing the payload or journal.

#### Scenario: The transaction carrier is invalid

- **WHEN** recovery observes a symbolic-link or non-directory transaction root,
  a missing or symbolic-link journal, malformed or non-canonical JSON, an
  unsupported schema, or invalid current-schema fields
- **THEN** recovery fails before any lifecycle mutation
- **AND** identifies the exact failed invariant
- **AND** leaves all retained files and the independently serving runtime
  unchanged.

### Requirement: Native supervision is self-contained and portable

The released executable SHALL install and inspect its user service through the
native macOS, Linux, or Windows adapter without an ambient Python interpreter,
optional process utility, source path, user identity, or workstation-specific
coordinate. The default installation SHALL retain the public service identity;
every alternate installation root SHALL use a deterministic identity derived
from that root. Signal paths SHALL revalidate exact process identity
immediately before mutation. Creation, observation, and teardown of one
native service SHALL consume the same exact runtime context. Native acceptance
on each supported operating system MUST exercise install, status, recovery,
and uninstall through that platform's built artifact; source tests, mocks, and
cross-compilation MUST NOT be reported as equivalent native product evidence.

#### Scenario: A supported host lacks development tools

- **WHEN** the product is installed on a clean supported host
- **THEN** service installation, listener discovery, handoff, status, and
  uninstall remain available from the released executable alone.

#### Scenario: An alternate root is installed for validation

- **WHEN** a signed asset is installed with a non-default product data root
- **THEN** native supervision SHALL use an identity unique to that absolute root
- **AND** installation SHALL not unload, replace, or report the default service
- **AND** uninstall SHALL address only the alternate identity and its listener.

#### Scenario: The default root is upgraded

- **WHEN** the signed installer targets the canonical product data root
- **THEN** it SHALL use the public service identity and current handoff protocol
- **AND** alternate validation identities SHALL remain untouched.

#### Scenario: A supported host accepts a native release

- **WHEN** the platform-built release artifact is installed into an isolated user root
- **THEN** the public status command reports the exact installed release and healthy owned service
- **AND** recovery reports the correct state without mutating healthy absence
- **AND** uninstall removes the exact owned service, processes, projection, payload, and command
- **AND** the host inventory has no net product residue after teardown

#### Scenario: A native lifecycle fails before completion

- **WHEN** installation, handoff, recovery, or an assertion fails on a supported host
- **THEN** bounded teardown uses the exact resolved service and process identities
- **AND** unrelated or canonical installations remain unchanged
- **AND** any unverifiable owned state remains explicit rather than being deleted by prefix

#### Scenario: A platform runner is unavailable

- **WHEN** one hosted platform cannot schedule a native acceptance job
- **THEN** that platform's product evidence remains unavailable
- **AND** successful evidence from another platform is not relabeled as proof for the unavailable platform


#### Scenario: Isolated native verification ends

- **WHEN** an isolated macOS, Linux, or Windows lifecycle completes or aborts
- **THEN** teardown addresses only its exact service identity and carrier
- **AND** proves its owned watchdog, listener, and handoff processes have exited
- **AND** leaves the canonical service and listener unchanged
- **AND** leaves no net host service residue.
