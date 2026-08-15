## MODIFIED Requirements

### Requirement: Source-side upgrade authority

Only the signed-asset installer SHALL admit a different release. Installed
control SHALL observe, reload, recover, or remove the current product but SHALL
NOT accept arbitrary release bytes. Forge availability SHALL NOT be an
installation input. The payload transaction SHALL coordinate the installed
payload, installed-state record, and native command link as one rollback
domain.

#### Scenario: An operator installs a release

- **WHEN** one signed native archive and its external trust anchor are supplied
- **THEN** the installer verifies and applies the release locally
- **AND** a Forge, Git, Python, uv, Nox, ETHOS, a client control plane, and a
  source checkout are not runtime dependencies.

#### Scenario: A fresh installation fails after payload projection

- **WHEN** payload bytes and the native command link are projected
- **AND** native service startup fails
- **THEN** rollback removes the candidate payload and command link
- **AND** the pre-install absence is restored exactly.

#### Scenario: An upgrade handoff fails

- **WHEN** an existing release is upgraded and successor proof fails
- **THEN** rollback restores the prior payload and prior command target exactly
- **AND** foreign content remains unchanged.

### Requirement: Uninstall removes only proved product ownership

Uninstall SHALL remove native supervision and exact owned listener processes.
It SHALL remove the user command link only while that link still resolves to
the exact installed executable. `--purge` SHALL additionally require a valid
current manifest, remove only its owned files, preserve unknown content, and
fail nonzero if residue remains.

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

## Requirement To Task To Proof

| Requirement | Task | Proof |
|---|---|---|
| `runtime-upgrade:Source-side upgrade authority` | `1.2` | `tests/lifecycle/test_transaction.py; tests/lifecycle/deployment/test_handoff.py` |
| `runtime-upgrade:Uninstall removes only proved product ownership` | `2.2` | `tests/lifecycle/test_command.py; tests/lifecycle/test_control.py` |
