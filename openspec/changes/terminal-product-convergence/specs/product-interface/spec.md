# Spec Delta

## ADDED Requirements

### Requirement: The product boundary remains a narrow optional data plane

The Proxy SHALL accept and translate supported Responses traffic, own its
loopback listener and installed lifecycle, and expose bounded operational
commands. It SHALL NOT own Provider selection, credentials, client installation,
client configuration, model selection, conversation history, repository
lifecycle, or AIGW behavior. A client or control plane MAY select the Proxy as
one ordinary endpoint, but the Proxy SHALL install and operate independently.

#### Scenario: The Proxy is used without AIGW

- **WHEN** an operator supplies a valid upstream route and starts the installed
  product
- **THEN** request translation, status, diagnostics, lifecycle, and uninstall
  work
- **AND** no AIGW executable, profile, state, service, or configuration is read.

#### Scenario: A control plane composes with the Proxy

- **WHEN** an external control plane selects the Proxy loopback endpoint
- **THEN** the Proxy receives an ordinary supported request
- **AND** neither product imports, installs, starts, stops, or mutates the
  other.

### Requirement: Responses admission follows protocol rather than brand

Generic request admission SHALL depend on the declared Responses contract, not
on Codex identity or a Provider brand. A Chat Completions-only endpoint SHALL
NOT be admitted as a Responses Provider.

#### Scenario: A second Responses client uses the same data plane

- **WHEN** a non-Codex client sends a supported Responses request to a declared
  Provider route without Codex installed or configured
- **THEN** the same admission, response, streaming, and error contracts apply
- **AND** no Codex identity or history is required for that request.

### Requirement: Public operations have one precise result contract

Every public command SHALL return one typed semantic outcome shared by human and
JSON renderers. The outcome SHALL distinguish healthy absence, degraded state,
invalid input, unavailable recovery, required recovery, completed mutation, and
failed mutation, and SHALL identify only the safe next action owned by that
command.

#### Scenario: A public command cannot complete

- **WHEN** a documented precondition or external dependency is missing
- **THEN** the command names the failed boundary and one actionable next step
- **AND** emits no traceback, warning, internal type, private path, credential,
  request content, or unrelated usage dump.

#### Scenario: Lifecycle evidence contradicts a completed operation

- **WHEN** a reload result names a nonpositive process ID or the same
  predecessor and successor, or a cleanup result has a negative or non-integer
  stopped count
- **THEN** the public outcome boundary rejects the result before either renderer
- **AND** emits one bounded failure instead of successful operation output.

#### Scenario: Installation fails and compensation also fails

- **WHEN** a fresh install fails and native cleanup or payload rollback cannot
  finish
- **THEN** the public failure retains both the initial and compensation
  boundaries
- **AND** native generation removal reports its numeric operating-system error
  without private paths or arbitrary exception text
- **AND** unavailable service admission does not trigger native cleanup
- **AND** existing recovery authority remains intact until exact cleanup
  succeeds.

#### Scenario: Cleanup has no live process to stop

- **WHEN** valid cleanup evidence reports zero stopped processes
- **THEN** the public outcome remains successful in both human and JSON output
- **AND** does not invent a process or require a positive count.
