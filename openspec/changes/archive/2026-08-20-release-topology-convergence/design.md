## Context

See [proposal.md](proposal.md). `product_assets.RELEASE_PLATFORMS` already owns
the supported release inventory, and `assemble_assets` already verifies and
assembles native artifacts. The defect is duplicated orchestration: CI events
repeat source proof, while Forge publishers can create or sign different asset
subsets.

## Goals / Non-Goals

**Goals:**

- Make proof responsibility a partition rather than overlapping event handlers.
- Make one complete, signed bundle the release authority.
- Keep both Forges optional projections of the same Git and asset objects.
- Fail closed on any missing platform, byte, checksum, signature, or trust
  identity.

**Non-Goals:**

- Move product test semantics or platform support policy into ETHOS.
- Make either Forge authoritative for product identity.
- Add another release manifest, compatibility path, or provider-specific bundle.

## Decisions

### Partition CI by proof context

Review pipelines run the complete source, quality, and platform-test matrix.
Pushes to `dev` and `main` run a bounded accepted-source confirmation. Tags run
tag identity, complete native asset, publication, and installation acceptance.
A proposal push with an open or imminent MR/PR does not run a second full
pipeline.

This is preferable to caching arbitrary job output: a proof context remains
explicit and each event has one reason to exist.

### Use the existing release inventory as the only asset SSOT

`product_assets.RELEASE_PLATFORMS` determines the exact archive and manifest
names. Evaluators and publishers consume it directly. They do not infer a valid
inventory from whichever files happen to be present.

### Sign one bundle once

Native builders produce unsigned platform archives and manifests. The existing
assembler verifies the full inventory, creates `SHA256SUMS`, and signs it once.
Both Forge publishers upload those exact bytes and verify them after download.
Forge transport credentials remain local to each adapter; they cannot alter the
bundle.

This replaces independent per-Forge signing. A detached organizational
endorsement may be added later, but it cannot replace or mutate product
identity.

### Keep ETHOS and repository responsibilities separate

ETHOS owns the generic role, lifecycle, proof-identity reuse, exact-CAS, and
Forge-adapter protocol. This repository owns its concrete jobs, supported
platforms, assets, release acceptance, and runtime tests. CI files are thin
projections over those two owners, not a third lifecycle definition.

## Risks / Trade-offs

- **A review pipeline is unavailable** → protected-branch admission remains
  closed; do not compensate by rerunning an unrelated branch pipeline.
- **One platform builder is unavailable** → local source closure remains
  valid, but the release cannot claim a complete bundle.
- **A Forge publication partially succeeds** → report peer-local state and
  retry the unchanged bundle idempotently; never rebuild or re-sign.
- **Existing release workflows assume provider-local signing** → migrate in
  one breaking cutover before creating `v2.0.53`; no compatibility path remains.

## Migration Plan

1. Tighten evaluator tests and implementation.
2. Partition CI triggers and prove workflow contracts.
3. Remove GitLab-local signing and publish one pre-signed complete bundle.
4. Run local gates and hosted review proof.
5. Promote the exact signed commit, create one annotated tag, and publish the
   unchanged bundle to both peers.
6. Verify parity, install the macOS asset, exercise the runtime, then retire the
   work lane and obsolete release residue.
