# Spec Delta

## ADDED Requirements

### Requirement: Supported native lifecycles are behaviorally symmetric

macOS, Linux, and Windows SHALL expose the same public install, status, doctor,
reload, rollback, recover, upgrade, and uninstall semantics while native
adapters own only their operating-system service operations. Each platform SHALL
prove the complete lifecycle using its own released artifact; a container, mock,
source execution, cross-compilation, or another operating system SHALL NOT
substitute for native product evidence.

#### Scenario: A supported platform accepts a release

- **WHEN** its signed native artifact is installed into an isolated user context
- **THEN** install, health, active-target no-op, upgrade, rollback, recovery,
  re-upgrade, uninstall, and reinstall reach their declared terminal states
- **AND** teardown leaves no owned service, process, transaction, payload,
  command, temporary carrier, or host-configuration residue.

#### Scenario: The requested artifact is already active

- **WHEN** a signed artifact exactly matches the healthy active release receipt
  and serving payload, with an idle transaction journal and verified supervisor
- **THEN** `install` returns `unchanged` without creating a transaction,
  replacing files, rebinding supervision, or restarting the listener
- **AND** the lifecycle operation uses the same context that owns its mutation
  lock rather than reconstructing paths or authority during installation.

#### Scenario: Linux service admission fails without a user manager

- **WHEN** Linux installation cannot reach a systemd user manager before any
  service registration or process creation
- **THEN** it reports `native_service_unavailable` and restores payload,
  command, and transaction state without invoking native-service removal
- **AND** the error describes the required user-service environment rather than
  a deleted generation path or private process entrypoint
- **AND** an unreachable manager remains an unknown service observation, not
  proof of absence; uncertain failures after service mutation still preserve the
  transaction for recovery.

#### Scenario: Linux installation preserves user-wide host policy

- **WHEN** a reachable user manager accepts the Proxy service
- **THEN** installation changes only its owned unit and process resources
- **AND** user lingering remains host-administered policy, not an implicit
  installer side effect or a source of credential prompts.

### Requirement: Terminal cleanup survives process interruption

Once a transaction has completed its projection and required supervisor binding,
its terminal outcome SHALL survive partial removal of transaction-owned
resources. Recovery SHALL continue disposal without repeating those completed
effects or depending on a payload or snapshot already removed. Transaction
authority SHALL remain available until disposal completes, and a new transaction
SHALL wait for that completion.

#### Scenario: Cleanup is interrupted after terminal effects

- **WHEN** cleanup fails after removing part of a discarded generation, a
  rollback snapshot, or the entire temporary transaction directory
- **THEN** a new process completes only the remaining owned cleanup
- **AND** selected payloads, installed metadata, command projection, and native
  supervision remain unchanged.

#### Scenario: Payload removal is interrupted

- **WHEN** native supervision and owned processes have stopped and a purge
  removes only part of its verified payload
- **THEN** the existing transaction journal retains the exact root-relative file
  digests until disposal completes
- **AND** either `recover` or repeated `uninstall --purge` resumes that removal
  without requiring a deleted executable, manifest, or generation selector
- **AND** changed files, symbolic links, unknown files, and unknown empty
  directories remain untouched and prevent a successful purge result.

#### Scenario: An interrupted first installation has a starting native service

- **WHEN** the original CLI has committed a candidate and submitted native
  supervision, but recovery cannot prove an accepting runtime
- **THEN** recovery verifies the journal-bound candidate and removes only its
  exact native registration and owned processes before discarding payload or
  recovery authority
- **AND** an absent health response does not establish service absence
- **AND** selector, rollback snapshot, and command restoration are admitted
  before native disposal; any drift preserves supervision and recovery input
- **AND** a missing configured executable permits cleanup only after proved
  native absence, never after an unreadable or ambiguous registration
- **AND** unknown cleanup or mismatched supervision preserves the journal and
  candidate without a successful rollback result
- **AND** a non-fresh transition preserves prior-generation supervision.

#### Scenario: Windows cannot observe the exact scheduled task

- **WHEN** the exact native task query fails or returns malformed task XML
- **THEN** recovery preserves unknown service state and refuses native disposal
- **AND** only the documented not-found HRESULT establishes task absence,
  independent of the operating system's display language
- **AND** a query timeout or access failure cannot produce rollback success.

### Requirement: Capable handoff preserves request admission

A runtime-to-runtime handoff that advertises the admission-preserving capability
SHALL transfer listener ownership without changing the request-admission state.
Draining is reserved for the legacy native-generation replacement path whose
current runtime cannot perform that handoff.

#### Scenario: A capable runtime is upgraded or rolled back under load

- **WHEN** a verified current runtime advertises both selected-generation and
  admission-preserving handoff capabilities
- **THEN** upgrade or rollback uses that handoff while new requests continue to
  be admitted and already accepted requests reach terminal responses
- **AND** no request is rejected with `proxy_draining` during the transition.

#### Scenario: A legacy runtime cannot preserve admission

- **WHEN** the verified current runtime lacks the admission-preserving handoff
  capability
- **THEN** lifecycle selects the bounded native-generation replacement path
- **AND** health and command output expose the actual admission state without
  claiming an admission-preserving transition.

### Requirement: Legacy lifecycle state has no implicit compatibility authority

An installed payload, journal, launcher, supervisor, manifest, command, or
schema shape that cannot satisfy the current exact ownership and transition
contract SHALL be rejected before mutation. After the terminal lifecycle has no
consumer for an earlier shape, its reader, writer, fallback, migration bypass,
and tests SHALL be deleted.

#### Scenario: A legacy carrier is encountered

- **WHEN** current code cannot prove its exact ownership and safe transition
- **THEN** the public command reports the bounded removal or reinstall action
- **AND** no compatibility inference or permissive fallback mutates it.

#### Scenario: An installed payload has no generation selector

- **WHEN** an upgrade encounters installed metadata without a durable generation
  selector
- **THEN** it requests explicit uninstall and fresh installation before creating
  a transaction or changing payload, command, or service state
- **AND** fresh installation creates only its command rollback record, while
  current-layout upgrade and rollback reuse the selected immutable generations
  without a parallel payload snapshot or layout migration.

## MODIFIED Requirements

### Requirement: macOS launchd replacement proves the exact watchdog PID

On macOS, supervision SHALL bind the current UID's native user domain without
requiring a graphical login. Replacement SHALL prove the exact predecessor
process and registration absent before changing its carrier, then prove a
distinct successor PID in that domain. A legacy GUI service is a migration
subject, never an alternate current supervision target. Command success or an
unavailable domain SHALL NOT prove convergence or service absence.

#### Scenario: A user has no graphical login

- **WHEN** the native user domain is reachable and has no associated GUI login
- **THEN** installation binds a Background-session launch agent in that domain
- **AND** status and teardown use its exact user-domain service target
- **AND** no login domain, protected user, or disabled-state override changes.

#### Scenario: An installed macOS watchdog is replaced during upgrade

- **WHEN** candidate payload bytes have committed while an earlier watchdog
  generation is registered and listener handoff proves terminal admission
- **AND** that watchdog is the unique user-domain service or exact legacy GUI
  service identified through a proved associated GUI login
- **THEN** replacement verifies its executable and watchdog process identity
- **AND** proves both process exit and exact registration absence before
  rewriting the carrier and bootstrapping the canonical user-domain successor
- **AND** a distinct PID returned by kickstart is re-observed and owned
- **AND** the independent terminal listener keeps serving throughout.

#### Scenario: Launchd cannot prove generation replacement

- **WHEN** both domains register the exact label, a required observation fails,
  or bootout, predecessor identity or exit, registration removal, bootstrap,
  kickstart or successor PID observation fails or is ambiguous
- **THEN** installation reports an actionable lifecycle error
- **AND** does not guess a domain, report absence or claim convergence
- **AND** a carrier remains unchanged until predecessor removal is proved.

#### Scenario: A registered watchdog has no carrier

- **WHEN** the exact service remains registered after its plist disappears
- **THEN** status does not report it absent merely because the file is missing
- **AND** teardown proves its exact registration and owned process absent before
  reporting success.

#### Scenario: Current control retains an authentic published predecessor

- **WHEN** an immutable published predecessor's own installer requires a GUI
  domain unavailable to the current native review account
- **THEN** the current public controller installs its untouched signed asset
  with the original external trust anchor
- **AND** complete payload files, receipt, serving digest and actual listener
  identify that authentic predecessor before upgrade and after rollback
- **AND** the explicit candidate upgrades and rolls back without uninstalling,
  resetting or substituting the retained predecessor
- **AND** no result claims that the obsolete installer supports headless use.

#### Scenario: Current recovery reads genuinely old-produced state

- **WHEN** the original published old CLI leaves an interrupted journal and
  payload projection in an isolated native target
- **THEN** current public recovery consumes those unchanged old-produced bytes
- **AND** proves its declared terminal result and exact owned-resource cleanup
- **AND** preserves unrelated content, canonical processes, both domain
  registrations, disabled overrides and plist bytes
- **AND** a current-generated journal, rebuilt old CLI, route-modified asset or
  old invocation with no recovery input cannot satisfy this qualification.
