## MODIFIED Requirements

### Requirement: Source-side upgrade authority

Only the signed-asset installer SHALL admit a different release. Installed
control SHALL observe, reload, recover, or remove the current product but SHALL
NOT accept arbitrary release bytes. Forge availability SHALL NOT be an
installation input. The payload transaction SHALL coordinate the installed
payload, installed-state record, and native command link as one rollback
domain. The command link SHALL be a symbolic link on POSIX and a hard link on
Windows; both forms SHALL be admitted only when they identify the exact
installed executable.

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
