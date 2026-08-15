## Context

The accepted source already removes GitLab release-time `apt-get` and runs
publication in the pinned Linux release image. Version 2.0.34 was published
before that repair.

## Goals / Non-Goals

**Goals:**

- Assign the repaired accepted source a new immutable patch identity.
- Preserve independent GitLab and GitHub publication.
- Keep `VERSION` as the sole release identity.

**Non-Goals:**

- Runtime, provider, protocol, dependency, or asset-layout changes.
- Rewriting any existing release record.

## Decisions

Advance directly to 2.0.35. Reusing 2.0.34 would conflate two source states;
introducing another version carrier would violate the existing SSOT contract.
The existing pinned release image remains the only GitLab publication runtime.

## Risks / Trade-offs

- **Forge or runner delay** -> Complete local proof and each available Forge
  independently; do not weaken platform gates or rewrite history.
