## MODIFIED Requirements

### Requirement: Source-side upgrade authority

Only the signed-asset installer SHALL admit a different release. The payload
transaction SHALL verify and prewarm the exact committed successor executable
inside the rollback domain before requesting handoff. Handoff readiness SHALL
use the configured bounded installation deadline without an independent,
shorter startup cap. Installed control SHALL observe, reload, recover, or remove
the current product but SHALL NOT accept arbitrary release bytes. Forge
availability SHALL NOT be an installation input. The payload transaction SHALL
coordinate the selected serving payload, installed-state record, and native
command link as one rollback domain. The selector SHALL determine the active
serving generation and its sole predecessor. The command SHALL resolve to the
newest verified release among those selected generations so serving rollback
cannot downgrade lifecycle control. The command link SHALL be a symbolic link
on POSIX and a hard link on Windows; both forms SHALL be admitted only when they
identify that exact control executable.

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
- **THEN** rollback restores the prior serving payload and stable command
  ownership exactly
- **AND** foreign content remains unchanged.

#### Scenario: Windows projects the user command

- **WHEN** installation runs on Windows
- **THEN** the command path is a hard link to the exact control executable
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

### Requirement: Explicit rollback is one reverse lifecycle transaction

Explicit rollback SHALL select only the immutable predecessor bound to the
current finalized successor. It SHALL verify both selected payload identities,
current installed state, command ownership, and their selector binding before
mutation. It SHALL rebind the native service and complete a bounded listener
handoff to the predecessor identity before reporting success. The returned
predecessor PID SHALL be the only verified product listener when success is
reported; finalized health alone SHALL NOT establish completion. Rollback SHALL
not downgrade the user command or the minimum release admitted by the next
signed-asset installation.

#### Scenario: Exact predecessor rollback succeeds

- **WHEN** the current successor and retained predecessor both verify and the
  predecessor proves accepting, finalized runtime identity
- **THEN** rollback reports state `rolled_back` only after the predecessor PID
  is the sole verified product listener
- **AND** payload, installed state, service definition, and listener identify
  the predecessor
- **AND** the command still identifies the newer verified lifecycle control
  release
- **AND** the displaced successor becomes the one retained predecessor for a
  possible forward reversal.

#### Scenario: Post-rollback lifecycle control

- **WHEN** the operator invokes `status`, `doctor`, `recover`, or `rollback`
  through the installed command after a serving rollback
- **THEN** that command understands the current selector and installed-state
  schemas
- **AND** a release not newer than the retained control release is refused as a
  replay or downgrade.

#### Scenario: Retained evidence is absent

- **WHEN** no retained predecessor exists
- **THEN** rollback reports state `unavailable`
- **AND** changes no filesystem, process, service, command, or listener state.

#### Scenario: Retained evidence is unverifiable

- **WHEN** any carrier shape, byte, mode, digest, generation binding, current
  installed identity, service identity, or listener identity cannot be proved
- **THEN** rollback fails closed before mutation
- **AND** preserves the selected active and predecessor generations for
  inspection.

#### Scenario: Finalized health precedes listener convergence

- **WHEN** the predecessor reports finalized health while the displaced
  successor remains a verified listener
- **THEN** rollback continues bounded convergence and does not report success
- **AND** reports an indeterminate outcome if one sole predecessor listener
  cannot be proved within the bound.

#### Scenario: Reverse handoff has a proved failure

- **WHEN** rollback has selected the predecessor but successor retirement or
  predecessor readiness fails with a proved outcome
- **THEN** the transaction restores the displaced successor serving projection
  and stable command ownership
- **AND** does not report rollback success.

#### Scenario: Reverse handoff outcome is unknown

- **WHEN** neither predecessor finalization nor successor restoration can be
  proved
- **THEN** the active transaction is retained for `recover`
- **AND** no successful rollback or restoration claim is emitted.
