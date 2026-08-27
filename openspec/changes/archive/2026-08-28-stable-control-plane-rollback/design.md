## Context

See [proposal.md](proposal.md) for the user-visible failure. Transaction
activation currently projects the command to the active generation,
unintentionally treating serving selection as lifecycle-control selection.

## Goals / Non-Goals

**Goals:**

- Give the serving payload and lifecycle command one precise owner each.
- Preserve one selector and one native command without another carrier.
- Keep rollback reversible while preventing an older executable from becoming
  the operator's control surface.
- Make post-rollback verification use the command users actually invoke.

**Non-Goals:**

- No compatibility reader for an older release.
- No second selector, wrapper, copied command, or command-version state field.
- No change to provider routing, client configuration, or handoff transport.

## Decisions

### Derive control from selected immutable identities

The active and predecessor generations already contain verified release
identities. The lifecycle command resolves to the newer strict SemVer identity
among those generations, while the active selector continues to drive serving
and native supervision. This is a derived view of one authority, not a new
state carrier.

Persisting a separate control-generation field was rejected because it would
create a second mutable authority that every transaction and recovery path
would have to reconcile.

### Preserve an unchanged command projection

Projecting an already correct native link is an idempotent no-op. Reverse
activation therefore changes the selector and supervisor but does not churn the
command inode or expose an older executable through PATH.

Changing an old binary to understand new state was rejected because published
payloads are immutable and compatibility readers would preserve the wrong
ownership model.

### Admit forward installs above the control release

After serving rollback, installed state deliberately describes the older
serving payload. A new signed asset is therefore compared with the derived
lifecycle control release, not the serving release. This prevents replay of the
already installed newer control plane and admits only a genuinely newer
upgrade.

## Risks / Trade-offs

- **Either selected identity is corrupt** → lifecycle mutation fails closed;
  read-only status still reports the more specific payload or rollback defect.
- **Serving and command releases differ after rollback** → status reports the
  serving release while command ownership is independently proved against the
  derived control generation.
- **Future non-numeric versions** → the existing strict released-payload SemVer
  contract remains authoritative; no new version grammar is introduced.

## Migration Plan

Publish a normal patch release. Its installer upgrades the current release,
after which rollback keeps the patch executable as the user command while the
retained predecessor serves. A second rollback restores the newer payload
without changing command ownership. No persisted state migration is required.
