# Runtime Upgrade

## Purpose

Define the current native payload, transactional handoff, rollback, recovery,
and supervision invariants.

## Requirements

### Requirement: Source-side upgrade authority

Only the signed-asset installer SHALL admit a different release. The payload
transaction SHALL verify and prewarm the exact committed successor executable
inside the rollback domain before requesting handoff. Handoff readiness SHALL
use the configured bounded installation deadline without an independent,
shorter startup cap. Installed control SHALL observe, reload, recover, or remove
the current product but SHALL NOT accept arbitrary release bytes. Forge
availability SHALL NOT be an installation input. The payload transaction SHALL
coordinate the installed payload, installed-state record, and native command
link as one rollback domain. The command link SHALL be a symbolic link on POSIX
and a hard link on Windows; both forms SHALL be admitted only when they identify
the exact installed executable.

#### Scenario: An operator installs a release

- **WHEN** one signed native archive and its external trust anchor are supplied
- **THEN** the installer verifies and applies the release locally
- **AND** a Forge, Git, Python, uv, Nox, ETHOS, a client control plane, and a
  source checkout are not runtime dependencies.

#### Scenario: A fresh installation fails after payload projection

- **WHEN** payload bytes and the platform-native command link are projected
- **AND** native service startup fails
- **THEN** rollback removes the candidate payload and command link
- **AND** the pre-install absence is restored exactly.

#### Scenario: An upgrade handoff fails

- **WHEN** an existing release is upgraded and successor proof fails
- **THEN** rollback restores the prior payload and prior platform-native command
  target exactly
- **AND** foreign content remains unchanged.

#### Scenario: Windows projects the user command

- **WHEN** installation runs on Windows
- **THEN** the command path is a hard link to the exact installed executable
- **AND** status, rollback, and uninstall classify ownership by file identity
- **AND** no symbolic-link privilege, copied executable, or wrapper is required.

#### Scenario: A cold native successor starts within the configured deadline

- **WHEN** the committed successor needs more than ten seconds for its first start
- **AND** it returns `READY` within the configured installation deadline
- **THEN** the upgrade continues to exact successor identity proof
- **AND** an arbitrary transport cap does not force rollback.

#### Scenario: Exact successor prewarm fails

- **WHEN** the executable committed to the candidate projection fails its bounded probe
- **THEN** the transaction restores the prior projection and command ownership
- **AND** the current verified listener remains available.

### Requirement: The installed payload has one current shape

The installed payload SHALL contain one prewarmed native bundle under `bin/`,
`providers.toml`, their complete manifest, signed-release receipt, and finalized
state. Installation SHALL accept only an empty target or one verified current
native listener whose native supervisor declares the canonical installed
executable. After candidate projection, installation SHALL remove only regular
files declared by the verified predecessor manifest and absent from the
successor manifest. Unknown installation content SHALL remain untouched, and
rollback SHALL restore the complete predecessor projection.

#### Scenario: An incompatible installation is present

- **WHEN** its manifest, bundle inventory, executable, listener identity, or
  canonical supervisor declaration does not match the admitted shape
- **THEN** installation fails before mutation with one bounded removal action
- **AND** no legacy inventory reader, one-file entrypoint, interpreter
  entrypoint, external launcher, or bypass switch admits it.

#### Scenario: A candidate bundle is admitted

- **WHEN** signed release verification has produced the complete candidate
  inventory
- **THEN** every regular file and mode is verified in staging
- **AND** the staged executable completes a bounded prewarm probe
- **AND** native supervision already declares the canonical installed
  executable
- **AND** only then may the payload transaction replace installed bytes.

#### Scenario: The successor omits a predecessor-owned file

- **WHEN** the verified predecessor manifest owns a regular file that the
  verified successor manifest does not declare
- **THEN** installation removes that file after writing the successor
  projection
- **AND** preserves every unowned file
- **AND** rollback restores the removed predecessor-owned file exactly.

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

### Requirement: Rollback owns only current product files

Rollback SHALL snapshot the complete current owned inventory or its complete
absence. Unknown install content SHALL be preserved and SHALL never become
implicitly owned. Candidate paths that collide with unknown content SHALL block
mutation. When an upgrade fails after projecting candidate bytes, rollback
SHALL restore every retained prior byte and remove every verified candidate
file that was absent from the prior snapshot.

#### Scenario: Current payload upgrade fails

- **WHEN** candidate commit or successor proof fails
- **THEN** every prior owned bundle byte and mode is restored
- **AND** unknown content remains unchanged.

#### Scenario: Candidate adds a new frozen-runtime member

- **WHEN** an upgrade projects a verified candidate-only file below `bin/`
- **AND** handoff fails and rollback runs
- **THEN** the candidate-only file is removed
- **AND** every prior owned byte and mode is restored exactly
- **AND** content outside prior-owned and candidate inventories is unchanged.

#### Scenario: Candidate collides with unknown content

- **WHEN** a candidate path already contains content outside the current owned inventory
- **THEN** the upgrade blocks before payload mutation
- **AND** rollback never claims ownership of that content.

#### Scenario: Retired payload paths leave empty descendants

- **WHEN** an upgrade removes files owned only by the verified predecessor
- **THEN** it also removes empty directories below those retired file parents
- **AND** it preserves every unowned file and symbolic link
- **AND** rollback restores predecessor-owned bytes without recreating
  semantically empty directory residue.

### Requirement: Payload primitives have one semantic owner

Canonical paths and safe file I/O SHALL belong to `owned_files`; candidate
materialization to `candidate`; installed integrity and purge to `projection`;
rollback to `rollback`; journals to `state`; and orchestration to `transaction`.
No forwarding facade or private-name import SHALL create a second authority.
The four transaction roles SHALL remain separate concrete modules rather than
being folded into the orchestrator or projected through a compatibility facade.

#### Scenario: A transaction mutates the payload

- **WHEN** it validates, snapshots, writes, verifies, restores, or finalizes
- **THEN** it calls the defining semantic owner directly.

### Requirement: Listener configuration has one source

The runtime configuration owner SHALL define the default listener port and all
validated overrides. Installer, control, service, and uninstall code SHALL not
copy port, host, log, or concurrency policy.

#### Scenario: A port override is supplied

- **WHEN** an operator selects a valid port through the public CLI
- **THEN** installation, supervision, health, reload, and uninstall use that
  exact value consistently.

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

### Requirement: Uninstall removes only proved product ownership

Uninstall SHALL remove only the exact service, processes, command projection,
and manifest-owned payload associated with the selected installation. An
absent installation SHALL be an idempotent successful no-op. An existing
payload root without valid ownership evidence SHALL be preserved and purge
SHALL fail closed.

#### Scenario: No installation exists

- **WHEN** no owned service, listener, command projection, payload root, or
  installed-state record exists
- **THEN** uninstall succeeds with state `not_installed`
- **AND** `--purge` has the same result without creating or deleting content.

#### Scenario: Unverified content occupies the payload root

- **WHEN** purge observes an existing payload root without a valid ownership
  manifest
- **THEN** it exits nonzero with a precise ownership diagnostic
- **AND** preserves every byte.

#### Scenario: Unknown content shares the install directory

- **WHEN** purge removes every manifest-owned file
- **THEN** unknown content remains untouched
- **AND** the command reports that the directory is not fully purged.

#### Scenario: The installed command link remains product-owned

- **WHEN** uninstall has proved service and process absence
- **AND** the command link still targets the exact installed executable
- **THEN** the command link is removed
- **AND** the payload is preserved unless `--purge` is requested.

#### Scenario: The command path changed ownership

- **WHEN** uninstall observes a foreign file, directory, or link at the command
  path
- **THEN** the path is preserved
- **AND** uninstall reports the ownership conflict without claiming complete
  removal.

### Requirement: Native release artifacts are reproducible

The same accepted source tree, locked supply chain, platform, architecture, and
release inputs SHALL produce byte-identical native assets. Standard-library
modules with nondeterministic bytecode serialization SHALL use supported
PyInstaller collection modes rather than a custom archive rewriter.

#### Scenario: Independent Linux Forges build one release

- **WHEN** GitLab and GitHub build the same accepted tree with the locked Linux toolchain
- **THEN** their native archives and executables have identical SHA-256 digests.

### Requirement: Canonical supervision precedes payload mutation

Installation SHALL require the current native listener and its native
supervisor to identify the canonical installed executable before committing
candidate payload bytes. No alternate launcher, migration bridge, wrapper, or
platform-specific compatibility path SHALL participate in current upgrade
admission.

#### Scenario: A current runtime is upgraded

- **WHEN** the sole listener has current release identity
- **THEN** its native supervisor already declares the canonical installed
  executable before candidate payload mutation
- **AND** any other supervisor target fails closed without changing the
  installed payload.

### Requirement: Upgrade converges the native supervisor generation

After candidate payload commitment and before listener handoff, installation
SHALL replace the platform-native supervisor with one running watchdog
generation executing the canonical committed payload. Product runtime identity
SHALL be reconstructed from the committed, secret-free `runtime-config.json`;
operating-system service definitions SHALL remain derived projections and SHALL
NOT duplicate product configuration. A watchdog that starts a listener SHALL
retain and poll its process handle so an exited child is reaped. If subsequent
handoff rolls back, installation SHALL restore the predecessor payload and
replace native supervision from that payload before returning failure.

On macOS, installation SHALL bind the exact GUI-domain service, prove any
predecessor watchdog PID has exited, bootstrap the current plist, and re-read
the exact successor PID. Plist registration, executable-path equality, or a
successful platform command alone SHALL NOT establish convergence.

#### Scenario: One runtime carrier projects to native service managers

- **WHEN** a committed payload is installed on macOS, Linux, or Windows
- **THEN** the watchdog and native-service adapter reconstruct the same exact
  executable, installation root, log root, and service identity from
  `runtime-config.json`
- **AND** launchd, systemd user services, or Task Scheduler contain only the
  native invocation and service-manager metadata
- **AND** no platform definition becomes a second product configuration source.

#### Scenario: An installed macOS watchdog is replaced during upgrade

- **WHEN** candidate payload bytes have committed while an earlier watchdog
  generation is registered
- **THEN** the installer boots out the exact prior launchd service
- **AND** proves the predecessor PID is absent within a bounded deadline
- **AND** bootstraps the current plist into the exact GUI domain
- **AND** accepts only a distinct running PID returned and re-observed for the
  exact service label
- **AND** leaves the independent listener serving throughout replacement.

#### Scenario: A current native runtime is upgraded

- **WHEN** candidate bytes have committed and the current listener remains
  accepting
- **THEN** the native supervisor is replaced by a generation executing the
  candidate payload
- **AND** listener handoff begins only after the exact service registration,
  executable, and running generation are proved.

#### Scenario: A watchdog-owned listener exits

- **WHEN** a listener spawned by the resident watchdog reaches a terminal
  process state
- **THEN** the watchdog polls its retained process handle
- **AND** no zombie process remains owned by that watchdog.

#### Scenario: Handoff rolls back after supervisor replacement

- **WHEN** successor handoff fails with a proved rollback outcome
- **THEN** the predecessor payload is restored
- **AND** native supervision is replaced by a generation executing that restored
  payload.

#### Scenario: Launchd cannot prove generation replacement

- **WHEN** bootout, predecessor exit, bootstrap, kickstart, or successor PID
  observation fails or is ambiguous
- **THEN** installation fails with an actionable lifecycle error
- **AND** does not report native supervision as converged.

#### Scenario: An isolated native lifecycle ends

- **WHEN** a noncanonical installation succeeds, fails, times out, or raises
- **THEN** teardown removes the exact service registration and projection path
  used at creation
- **AND** proves every process owned by that exact service has exited
- **AND** leaves the canonical service and listener unchanged
- **AND** the set of noncanonical host service projections has no net growth.

### Requirement: Handoff finalization observes the exact successor

After commit, the controller SHALL read bounded health snapshots through the
shared listener until the complete expected successor identity is served. A
snapshot from the retiring process, a transient socket failure, or a transient
health read failure SHALL be treated as an observation to retry, not success or
immediate failure. Deadline expiry SHALL identify the failed lifecycle phase
without including exception messages, request content, headers, credentials,
or upstream payloads.

#### Scenario: A health read fails during ownership transfer

- **WHEN** a post-commit health read raises an ordinary exception
- **THEN** the controller continues bounded observation
- **AND** finalizes only after the exact successor PID and payload identity are
  accepting and not draining
- **AND** rolls back if the deadline expires without that proof.

#### Scenario: The retiring listener answers during ownership transfer

- **WHEN** the first post-commit health snapshot still identifies the retiring
  process
- **THEN** the controller continues bounded observation
- **AND** finalizes only after the exact successor PID and payload identity are
  accepting and not draining.

#### Scenario: Successor observation does not converge

- **WHEN** the deadline expires or health observation fails
- **THEN** the transaction follows its rollback or recovery-required contract
- **AND** operational output records only the failed phase and exception class.

#### Scenario: The supervisor target is noncanonical

- **WHEN** installation observes any supervisor target other than the canonical
  installed executable
- **THEN** it rejects the upgrade before service or payload mutation
- **AND** the same invariant applies on macOS, Linux, and Windows.

### Requirement: Carrier-bound native handoff is the only upgrade protocol

A running upgrade SHALL bind the health snapshot to exactly one listener owned
by the installed executable, commit the admitted prewarmed bundle, and bind
native supervision to that committed executable before requesting transactional
handoff. A successor SHALL prove its PID, executable, release, manifest,
serving aggregate, receipt, accepting state, and non-draining state. The
handoff child SHALL own only listener transfer and runtime identity; it SHALL
NOT mutate the platform-native supervisor. Every private service role SHALL
activate one existing, validated `runtime-config.json` located in the installed
executable's payload root before importing or starting product runtime behavior.
Environment variables are a projection of that carrier, not an alternate source
and not an input from which a missing carrier may be created.

#### Scenario: Every private role activates the same carrier

- **WHEN** the listener, handoff child, or watchdog starts from an admitted
  installed executable
- **THEN** it resolves the carrier from that executable
- **AND** validates the carrier before product startup
- **AND** replaces inherited product settings with the carrier projection.

#### Scenario: A private role lacks a valid carrier

- **WHEN** any private role cannot read one valid executable-owned carrier
- **THEN** startup fails closed before listener, handoff, or watchdog behavior
  begins
- **AND** no private role creates a carrier from inherited environment variables
  or platform defaults.

#### Scenario: A current release upgrades successfully

- **WHEN** the sole verified listener supports handoff and the successor proves
  the admitted identity
- **THEN** installation writes the successor carrier and binds native
  supervision to the committed successor before requesting listener handoff
- **AND** the handoff child does not restart or replace its own supervisor
- **AND** startup performs no first-run bundle extraction
- **AND** at most one listener accepts requests at each barrier.

#### Scenario: Supervisor rebinding fails before handoff

- **WHEN** the platform-native supervisor cannot be proved to declare the
  committed successor
- **THEN** handoff is not requested
- **AND** the prior payload and native supervision are restored
- **AND** the operation fails.

#### Scenario: Handoff rolls back

- **WHEN** failure resolution proves the original runtime resumed
- **THEN** the exact complete rollback inventory is restored
- **AND** native supervision is rebound to the restored predecessor
- **AND** the operation fails.

#### Scenario: Handoff outcome is unknown

- **WHEN** neither finalization nor rollback can be proved
- **THEN** candidate and rollback bundle bytes remain transaction-bound for
  recovery
- **AND** native supervision remains bound to the committed candidate
- **AND** no success or rollback claim is emitted.

### Requirement: Runtime carrier remains install-generation stable

The supported predecessor installer and successor payload SHALL implement one
stable, secret-free `runtime-config.json` contract. Operating-system service
definitions SHALL remain derived projections and SHALL NOT expand that product
carrier with host-only ownership coordinates.

#### Scenario: A predecessor writes the successor carrier

- **WHEN** a supported published predecessor installs a newer signed payload
- **THEN** the predecessor writes the same current runtime-carrier schema that
  the successor consumes
- **AND** the successor activates without a compatibility parser or migration
  branch.

#### Scenario: macOS service ownership is projected

- **WHEN** installation creates or removes one launchd service
- **THEN** its exact plist path and `HOME` projection come from the live runtime
  context used by that operation
- **AND** the persisted product carrier remains platform-neutral.

### Requirement: Payload prewarm uses a private stable protocol

The installer SHALL prewarm the exact committed successor executable through a
private, side-effect-free executable role whose grammar is independent of the
public CLI. A public command rename or removal SHALL NOT change that protocol.
When an installed predecessor predates the stable role and cannot invoke the
successor, the operator SHALL bootstrap with the verified successor executable;
the product SHALL NOT retain a public compatibility alias solely for that
historical installer.

#### Scenario: Current installer prewarms a successor

- **WHEN** an admitted successor has been committed inside the rollback domain
- **THEN** the installer invokes the private prewarm role on that exact executable
- **AND** the role exits without reading runtime state, starting supervision, or
  changing product data.

#### Scenario: Public CLI grammar changes

- **WHEN** a release adds, renames, or removes a public command or option
- **THEN** the installer-to-successor prewarm invocation remains unchanged
- **AND** release verification fails if it is coupled to the public grammar.

#### Scenario: Historical installer lacks the stable role

- **WHEN** an installed predecessor cannot activate a breaking successor because
  it uses retired public syntax
- **THEN** the verified successor executable is used once to perform the upgrade
- **AND** no public compatibility command or permanent migration parser is added.

### Requirement: macOS lifecycle leaves no new persistent service projections

On macOS, each bounded native lifecycle SHALL leave the product-owned launchd
registration, process, plist, and override sets unchanged after exact service
teardown. Teardown SHALL address one fully qualified service target and SHALL
NOT reset a launchd domain, match a service-name prefix, or change the canonical
service while cleaning an alternate installation. Historical overrides created
by older product generations SHALL be handled only by a separate exact-label
host migration.

#### Scenario: An isolated macOS lifecycle ends

- **WHEN** an alternate-root lifecycle succeeds, fails, times out, or is interrupted
- **THEN** exact-label teardown removes its service registration, owned processes, and plist
- **AND** the product-owned override set has no net growth
- **AND** the pre-existing canonical service projection and listener remain unchanged
- **AND** the host has no net noncanonical service residue from that lifecycle.
