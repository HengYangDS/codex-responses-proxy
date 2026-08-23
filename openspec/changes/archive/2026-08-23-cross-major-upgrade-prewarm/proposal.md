## Why

Native upgrade currently prewarms a successor through the public version-reporting grammar. The 3.0.0 removal of the `version` subcommand therefore made the still-supported 2.0.58 installer reject the otherwise valid 3.0.0 payload after committing it, proving that a public CLI cleanup can accidentally break the transactional lifecycle.

## What Changes

- Give native payload prewarm one private, version-neutral executable role that is independent of the public CLI grammar.
- Make current installers invoke that private role and verify the exact committed executable still starts successfully.
- Define major-version transitions explicitly: an installer using the stable private role supports in-place successors; an older incompatible installer requires candidate-owned bootstrap rather than a permanent public compatibility alias.
- Add focused regressions that prevent public command changes from altering the prewarm protocol.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: Separate the stable installer-to-candidate prewarm protocol from public command syntax and define the bounded major-transition bootstrap.

## Impact

The private executable-role contract, payload prewarm implementation, lifecycle tests, runtime-upgrade specification, release compatibility policy, and operator upgrade documentation change. Responses traffic, provider behavior, public command inventory, and native supervision remain unchanged.
