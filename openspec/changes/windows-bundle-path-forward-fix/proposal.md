# Forward-fix Windows bundle path identity

## Why

GitHub Verify for v2.0.17 failed only on Windows because lexical containment
compared resolved paths case-sensitively. The same filesystem member may be
reported with different case, so a valid internal bundle member was rejected.

## What changes

- Compare resolved containment using host-canonical path identity.
- Preserve strict rejection of real escapes, cycles, and non-regular members.
- Align README and release identity at 2.0.18; retain v2.0.17 evidence unchanged.

## Capabilities

### Modified capabilities

- ci-diagnostics: native release containment is host-canonical and fail-closed.

## Non-goals

No provider, relay, runtime-service, credential, conversation-state, or
cross-Forge authority change.
