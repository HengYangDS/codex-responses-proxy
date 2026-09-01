## Context

See [proposal.md](proposal.md). The product behavior and quality-owner changes
are already accepted at the current signed source object. Publication must assign
new immutable version identity and prove the same source through native artifacts,
both Forge planes, and transactional installation.

## Goals / Non-Goals

**Goals:**

- Bind release 3.1.12 to one signed source commit and annotated tag.
- Build each platform asset from the locked repository and sign the complete
  byte-identical release inventory once.
- Publish and re-read the same commit, tag, checksums, signature, manifests, and
  archives on GitLab and GitHub.
- Upgrade the canonical installation only after release verification, then prove
  health, replay behavior, rollback authority, and unchanged conversation data.

**Non-Goals:**

- Change provider routes, client configuration, credential ownership, or protocol
  behavior beyond the already accepted source.
- Rewrite 3.1.11 or any earlier release.
- Treat either Forge or the installed runtime as source authority.

## Decisions

1. **Use 3.1.12.** This is a backward-compatible defect correction over 3.1.11;
   SemVer patch advancement is sufficient and published identity remains
   immutable.
2. **Keep release metadata minimal.** `VERSION` and `CHANGELOG.md` are the only
   edited product release authorities; existing release tooling derives package,
   archive, manifest, and publication metadata.
3. **Require package-only evidence before publication.** The already-built
   candidate must pass native isolated install, replay, recovery, health, and
   exact uninstall while the canonical 8792 service remains unchanged.
4. **Publish identical objects and bytes to peer Forges.** GitLab and GitHub
   authenticate independently but neither may rebuild, rewrite, or re-sign the
   product.
5. **Upgrade transactionally after publication.** The installed service consumes
   the verified release bundle and retains its one supported rollback
   predecessor.

## Risks / Trade-offs

- **A Forge or native runner may be temporarily unavailable** -> preserve the
  exact signed local object and artifact inventory; report one-sided evidence
  explicitly rather than weakening parity.
- **A release-only change can duplicate prior behavior specifications** -> use
  `skip_specs: true` and reference the archived behavior Change.
- **The installed service carries live user traffic** -> verify candidate
  isolation first and use only the public transactional installer.
