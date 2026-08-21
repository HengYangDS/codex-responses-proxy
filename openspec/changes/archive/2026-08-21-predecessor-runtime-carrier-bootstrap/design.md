## Context

The real upgrade path is driven by the installed predecessor CLI. `2.0.52`
projects the successor payload and starts its handoff child without creating
the runtime carrier introduced later. Candidate-driven testing hid this
boundary because the candidate CLI created the carrier before handoff.

## Decision

Only the handoff-child startup path may create a missing carrier. It accepts
either the complete predecessor product environment or no product environment,
in which case the executable-owned install root and platform defaults define
the contract. A partial product environment is ambiguous and fails closed.

After the atomic write, normal carrier validation and activation run unchanged.
Listener and watchdog startup never bootstrap a carrier. The bridge is removed
in the immediate successor release after the canonical runtime has crossed it.

## Rejected Alternatives

| Alternative | Reason |
| --- | --- |
| Teach the published predecessor about the carrier | Published assets are immutable. |
| Retain environment variables as a second authority | Violates SSOT and preserves migration debt. |
| Bootstrap in every private role | Turns a one-time bridge into permanent fallback behavior. |
| Require uninstall and fresh install | Breaks the required transactional hot upgrade. |

## Risks

- A partial predecessor environment could silently mix values with defaults;
  exact completeness validation rejects it.
- A bootstrap path could outlive the migration; the next release removes it
  after formal runtime proof.
