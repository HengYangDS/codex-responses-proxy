## Context

See [proposal.md](proposal.md). The accepted tree contains the replay repair,
while `VERSION` remains the sole release-identity authority. Source acceptance,
Forge publication, installed upgrade, and same-task recovery are separate proof
surfaces.

## Goals / Non-Goals

**Goals:**

- Assign one patch release to the accepted corrective source.
- Preserve one signed source object and byte-identical assets across both
  Forges.
- Keep the working 3.1.7 runtime serving until 3.1.8 passes installation and
  replay acceptance.

**Non-Goals:**

- Add another replay path, compatibility shim, or release authority.
- Modify Codex conversation storage or model metadata.

## Decisions

Use `3.1.8`: the accepted delta repairs replay of an existing client record and
does not widen the public CLI or provider contract. Reusing `3.1.7` would violate
immutable release identity; a minor increment would overstate compatibility
impact.

Archive this release-only Change before constructing the signed release object.
Then reuse the repository's existing proof, asset, publication, and
transactional installation paths. Final acceptance requires the previously
failing ETHOS task itself to continue; listener health alone is insufficient.

## Risks / Trade-offs

- **Hosted or native evidence can fail after source acceptance** → keep 3.1.7
  installed and healthy until 3.1.8 is independently accepted.
- **The repair may pass unit tests but not full replay** → retry the unchanged
  task and roll back through the existing generation switch if it still fails.
- **Forge assets can diverge** → compare the signed asset set by bytes before
  installation acceptance.
