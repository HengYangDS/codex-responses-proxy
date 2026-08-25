## MODIFIED Requirements

### Requirement: Human and machine interfaces share one result model

The installed executable SHALL render concise, task-oriented human output by
default and stable JSON only when `--json` is requested. Every public command
SHALL support both projections and SHALL preserve one semantic result and exit
status model across them. Healthy absence, pending recovery, invalid evidence,
degraded installation, and completed mutation SHALL be distinct outcomes.
Human output SHALL use consistent sections, display-width alignment,
actionable state-specific guidance, and no serialized object dump. Source
modules, Python launch syntax, repository paths, and release-operator commands
SHALL remain outside the end-user journey. Status SHALL report release identity
from the verified installed-state record and command discoverability without
consulting repository files or a second state authority. Runtime evidence SHALL
be returned only when its PID is the sole listener owned by the selected
installation. An installed command path SHALL be interpreted using the native
absolute-path and link semantics of the host that recorded it. Recovery SHALL identify the exact failed carrier invariant when the
transaction root or journal is missing, a symbolic link, the wrong filesystem
type, malformed JSON, non-canonical JSON, an unsupported schema, or invalid
under the current schema. It MUST preserve those bytes, retain one stable
\`recovery_state_invalid\` error code and read-only next action, and distinguish
that evidence failure from the health of an independently serving runtime.

#### Scenario: An operator inspects the installed service

- **WHEN** the operator runs `codex-responses-proxy status`
- **THEN** the command presents release, payload, command, service, listener,
  and transaction state in a scannable layout
- **AND** `status --json` exposes the same semantics
- **AND** Windows accepts its recorded native absolute command path without
  treating a foreign path syntax as valid
- **AND** `doctor` classifies a missing or foreign command projection as an
  actionable failure
- **AND** a listener is healthy only when its runtime payload identity matches
  the currently committed installed candidate
- **AND** neither output exposes a Python module invocation or source-checkout
  requirement.

#### Scenario: The product is not installed

- **WHEN** `status`, `doctor`, `recover`, or `uninstall` observes no owned
  installation or transaction
- **THEN** each command identifies the absent state without calling it corrupt,
  unknown, recovered, or removed
- **AND** `doctor` recommends installation rather than reload
- **AND** `recover` and `uninstall` return successful explicit no-op results.

#### Scenario: Automation invokes any public command

- **WHEN** automation invokes `install`, `status`, `doctor`, `recover`, `reload`,
  `uninstall`, or `version` with `--json`
- **THEN** the command emits one stable JSON value and no human decoration
- **AND** successful lifecycle results use one `state` discriminator rather
  than parallel boolean or mode fields
- **AND** expected failures expose one stable error `code`, one concise
  `message`, and one directly executable `next` command
- **AND** expected failures remain nonzero without a traceback or warning.

#### Scenario: Another listener occupies the selected port

- **WHEN** loopback health responds but its PID is not the sole listener owned by
  the selected installation
- **THEN** status omits untrusted runtime evidence
- **AND** doctor reports an identity mismatch without treating that listener as
  this product.

#### Scenario: Retained recovery evidence is invalid

- **WHEN** a transaction root exists but its canonical journal is missing, a
  symbolic link, the wrong filesystem type, malformed JSON, non-canonical JSON,
  an unsupported schema, or invalid under the current schema
- **THEN** recovery returns the exact invalid carrier classification
- **AND** returns \`recovery_state_invalid\` with \`status --json\` as its next action
- **AND** it does not describe an independently serving runtime as unavailable
- **AND** it does not mutate or delete the retained bytes.
