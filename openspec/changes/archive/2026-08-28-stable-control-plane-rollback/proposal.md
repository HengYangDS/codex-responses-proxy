## Why

Explicit rollback correctly restored the retained serving payload but also
repointed the user's command to that older executable. The operation therefore
reported success while ordinary lifecycle commands could no longer understand
the current selector layout.

## What Changes

- Keep the platform-native user command on the newest verified release among
  the active and retained generations.
- Let the selector continue to own only the active serving payload and its sole
  predecessor; native supervision remains bound to the active generation.
- Compare future installations with the lifecycle control release, preventing
  a serving rollback from reopening downgrade or replay admission.
- Exercise post-rollback operations through the installed command rather than
  a test-only candidate executable path.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: separate stable lifecycle command ownership from the
  selector's reversible serving-payload choice.

## Impact

The change affects generation resolution, command projection, transaction
recovery, status, uninstall, native compatibility acceptance, and their
documentation. It adds no dependency, carrier, selector, compatibility reader,
provider behavior, or client configuration authority. The formal installation
remains unchanged until a signed patch release passes native acceptance.
