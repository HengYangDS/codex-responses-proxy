## Why

Responses replay currently classifies item types independently in diagnostics and
provider-portable projection. A type can therefore be reported as recognized by
one path but rejected as unknown by the path that decides whether any upstream
request is safe, producing false-green tests and opaque replay failures.

## What Changes

- Replace the parallel item-type collections and dispatch assumptions with one
  typed policy that owns each supported Responses item kind and its projection
  strategy.
- Derive diagnostics and provider-portable projection from that policy.
- Distinguish a genuinely unknown item from a recognized client schema whose
  portable semantics are not yet implemented, while continuing to fail closed
  before upstream I/O.
- Safely remove a complete Codex-local `local_shell_call` and
  `function_call_output` replay pair while preserving the current dialogue.
- Delete duplicated item-kind knowledge from implementation and tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-portable-responses`: define one authoritative item policy and a
  bounded schema-drift failure for recognized but unsupported client items.

## Impact

- Affects Responses request projection, structural diagnostics, and their
  contract tests.
- Does not modify Codex conversation history, client configuration, provider
  routing, credentials, the installed 3.1.11 runtime, or provider-specific
  fallback behavior.
- Adds no dependency or compatibility path.
