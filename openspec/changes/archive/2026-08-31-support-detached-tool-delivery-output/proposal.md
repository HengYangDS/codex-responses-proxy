## Why

Codex now persists cross-task delivery results as standalone
`function_call_output` items identified by tool name and namespace rather than a
local `call_id`. The proxy rejects that valid client history before upstream
I/O, so the affected conversation cannot continue.

## What Changes

- Project a structurally valid standalone tool delivery into ordinary
  provider-portable input instead of inventing a missing call relationship.
- Keep malformed, ambiguous, or provider-bound output structures fail-closed.
- Add an exact regression derived from the observed Codex replay shape.

## Capabilities

### Modified Capabilities

- `provider-portable-responses`: Admit the bounded standalone tool-delivery
  shape emitted by Codex while preserving the closed replay grammar.

## Impact

- Request projection in `protocol/request.py`.
- Provider-portable replay tests and specification.
- No conversation-store mutation, provider-specific branch, dependency, or
  new runtime state.
