## Context

See [proposal.md](proposal.md). The accepted tree is four signed commits ahead
of `v3.1.6`, while `VERSION` remains the sole release-identity authority.
Release source, hosted publication, installation, and runtime health are
separate proof surfaces.

## Goals / Non-Goals

**Goals:**

- Assign one new patch identity to the accepted post-3.1.6 source.
- Preserve one source object and byte-identical assets across both Forges.
- Keep the installed 3.1.6 runtime serving until the new candidate is verified.

**Non-Goals:**

- Add product behavior, compatibility paths, or another release authority.
- Encode mutable Forge or host state in the repository.

## Decisions

Use `3.1.7`: the accepted delta is corrective and does not change the public
protocol. Reusing `3.1.6` would violate immutable release identity; a minor or
major increment would overstate compatibility impact.

Archive this release-only Change before constructing the signed release commit.
Then run the repository's existing proof, native-asset, publication, and
installed-lifecycle paths. No release-specific implementation or workflow is
added.

## Risks / Trade-offs

- **Hosted or native evidence can fail after source acceptance** → keep 3.1.6
  installed and healthy until 3.1.7 independently passes candidate validation.
- **Forge assets can diverge** → compare the complete signed asset set by bytes
  before installation acceptance.
