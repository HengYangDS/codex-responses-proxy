## Context

See [proposal.md](proposal.md). The accepted tree contains the
checkout-preservation correction, while `VERSION` remains the sole release
identity authority. Source acceptance, Forge publication, installation, and
runtime health are distinct proof surfaces.

## Goals / Non-Goals

**Goals:**

- Assign one patch release to the accepted corrective source.
- Preserve one signed source object and byte-identical assets across both
  Forges.
- Keep the working `3.1.9` runtime serving until `3.1.10` passes candidate
  installation, rollback, and runtime acceptance.

**Non-Goals:**

- Add another release path, compatibility shim, or release authority.
- Modify Codex configuration, conversation storage, or model metadata.

## Decisions

Use `3.1.10`: the accepted delta corrects release verification without changing
the public protocol. Reusing `3.1.9` would violate immutable release identity;
a minor increment would overstate compatibility impact.

Archive this release-only Change before constructing the signed release
object. Reuse the repository's existing proof, asset, publication, and
transactional installation paths rather than adding release-specific logic.

## Risks / Trade-offs

- **Hosted or native evidence can fail after source acceptance** -> keep
  `3.1.9` installed and healthy until `3.1.10` is independently accepted.
- **Forge assets can diverge** -> compare the complete asset set by filename
  and SHA-256 before installation acceptance.
