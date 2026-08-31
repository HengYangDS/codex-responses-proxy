## Context

See [proposal.md](proposal.md). GitLab generic packages accept repeated uploads
of the same filename and version as additional records, so upload-first retry
logic is not idempotent. The Release record and package bytes are independently
observable provider state.

## Goals / Non-Goals

**Goals:**

- Reuse exact existing asset bytes and upload only missing files.
- Validate an existing Release before treating a retry as complete.
- Surface bounded GitLab error detail at the adapter boundary.

**Non-Goals:**

- Add a second publication workflow or compatibility behavior.
- Change tag, bundle, signing, or GitHub semantics.

## Decisions

Read each canonical package URL before upload. HTTP 404 means the asset is
missing; identical bytes are reusable; differing bytes fail closed. This uses
the existing package URL as the sole asset identity rather than adding a local
publication registry.

Read and validate the tag-specific Release before transferring assets. A
matching Release still verifies every linked asset byte; a missing Release may
reuse a partially uploaded package. A create race is resolved by reading and
validating the winning Release.

The HTTP adapter preserves a short decoded provider response in non-secret
errors. Credentials remain request headers and are never included.

## Risks / Trade-offs

- **A retry adds read requests** → Publication is infrequent; exact idempotency
  and restartability outweigh the small cost.
- **Provider text may be large or malformed** → Bound and normalize diagnostic
  text before exposing it.
