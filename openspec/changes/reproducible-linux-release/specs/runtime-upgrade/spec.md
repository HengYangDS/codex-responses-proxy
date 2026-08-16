## MODIFIED Requirements

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

### Requirement: Native release artifacts are reproducible

The same accepted source tree, locked supply chain, platform, architecture, and
release inputs SHALL produce byte-identical native assets. Standard-library
modules with nondeterministic bytecode serialization SHALL use supported
PyInstaller collection modes rather than a custom archive rewriter.

#### Scenario: Independent Linux Forges build one release

- **WHEN** GitLab and GitHub build the same accepted tree with the locked Linux toolchain
- **THEN** their native archives and executables have identical SHA-256 digests.
