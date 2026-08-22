## Why

Lifecycle commands currently collapse distinct states into misleading output:
`recover` reports a missing transaction as a damaged journal, pristine
`uninstall --purge` reports a missing manifest as a fault, and diagnostics can
recommend `reload` when the product is not installed. These contradictions
make safe normal states look broken and send users toward commands that cannot
succeed.

## What Changes

- Define absence, pending recovery, invalid evidence, degraded installation,
  and completed mutation as mutually exclusive lifecycle outcomes.
- Make `recover` and `uninstall` idempotent when their owned target is absent,
  while continuing to reject ambiguous or invalid owned state.
- Make `status`, `doctor`, human output, JSON output, exit status, help, and next
  actions project the same precise state.
- Exercise the complete public command grammar against pristine, healthy,
  recoverable, and invalid installations.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `product-interface`: Require precise shared Human/JSON lifecycle semantics.
- `runtime-upgrade`: Define recovery and uninstall behavior when no owned
  transaction or installation exists.

## Impact

The public lifecycle result model, presentation, transaction recovery,
uninstall/purge preconditions, diagnostics, CLI tests, native executable
acceptance, and operator documentation are affected. Provider routing,
credentials, client configuration, Codex state, and the running formal service
are not modified during source development.
