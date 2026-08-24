## Why

The `v3.0.3` release is byte-identical on GitHub and GitLab, yet the live
publication verifier rejects both providers because their already-validated job
maps do not match the evaluator's smaller wire shape. The host also contains
persistent launchd overrides created by older lifecycle generations, so current
native tests must prove that they do not create any further residue.

Both defects weaken terminal evidence: valid publication cannot be proved, and
a successful test can still pollute the host. The repair must preserve strict
schema validation and exact service ownership rather than weaken either gate.

## What Changes

- Normalize each provider's validated hosted evidence to the one evaluator
  schema before composing it with independently verified Git identity.
- Preserve required-job validation inside the GitHub and GitLab adapters while
  keeping the evaluator's boundary closed to unknown fields.
- Extend native lifecycle acceptance to prove no net exact-label registration,
  process, plist, or override residue while leaving the canonical service
  unchanged.
- Treat removal of historical override records as a bounded, exact-label host
  migration rather than silently broadening ordinary product teardown.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `release-governance`: require adapter-shaped hosted evidence to compose into
  one exact dual-Forge proof schema.
- `runtime-upgrade`: require exact macOS teardown to remove every persistent
  launchd projection owned by the isolated service identity.

## Impact

The change affects only release evidence composition and native lifecycle
acceptance. It does not alter provider routing, request transformation,
credentials, client configuration, the formal installed service, or Codex
conversation state.
