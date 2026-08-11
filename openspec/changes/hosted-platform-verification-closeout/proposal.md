# Hosted platform verification closeout

## Why

The v2.0.23 hosted matrix exposed two test-harness gaps: Windows path semantics
made a structurally equal dataclass assertion platform-dependent, and the new
process-generation branches were not covered on the compatibility-floor quality
runner.

## Outcome

Keep production behavior unchanged. Express the identity assertion using the
captured fields after platform normalization and cover the fail-closed process
edges directly.
