## Context

See [proposal.md](proposal.md). The behavior is already accepted on `dev`; this
Change assigns immutable release identity and carries that exact source through
the existing release pipeline.

## Goals / Non-Goals

**Goals:**

- Bind `3.1.13` to one signed source commit and annotated tag.
- Build and publish one byte-identical native inventory to both Forges.
- Upgrade the canonical installation transactionally and preserve rollback.

**Non-Goals:**

- Change protocol behavior beyond the accepted source.
- Rewrite `3.1.12` or introduce another release authority.
- Modify client configuration, credentials, or conversation storage.

## Decisions

1. Make the existing forward-only release policy normative: accepted source
   absent from the latest release receives a new immutable SemVer identity, and
   a backward-compatible defect correction advances the patch version.
2. Keep `VERSION` and `CHANGELOG.md` as the only edited release authorities;
   existing tooling derives artifacts and publication metadata.
3. Run the full repository gates once after focused metadata validation, then
   publish the same signed objects and bytes to GitLab and GitHub.
4. Upgrade the installed service only from the verified release and prove
   health, rollback authority, and residue-free closeout.

## Risks / Trade-offs

- [A Forge is temporarily unavailable] -> preserve exact local objects and
  report one-sided publication without weakening parity requirements.
- [The live service carries active traffic] -> use the existing transactional
  handoff and rollback path; do not replace payload files directly.
