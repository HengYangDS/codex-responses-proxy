## Context

GitHub contains only its provider-native release-tag subset, while GitLab owns
the canonical complete chronology. The metadata checker already models that
distinction. The failure came from the test driver calling the checker without
its provider argument only after the current version's tag existed.

## Goals / Non-Goals

**Goals:**

- Keep one chronology policy owner in `tools/release/metadata.py`.
- Make the regression driver propagate its execution plane in every branch.
- Preserve fail-closed signing, exact-tag, and immutable-history behavior.
- Produce clean hosted diagnostics and a forward-only patch release.

**Non-Goals:**

- Add a chronology bypass, synthesize missing GitHub tags, or weaken GitLab.
- Move product policy into provider workflow YAML.
- Treat a local pass, tag, or one Forge release as terminal completion.

## Decisions

1. The test driver derives the provider only from the existing
   `GITHUB_ACTIONS=true` execution-plane signal and passes `--provider github`
   in both pending and tagged branches. This is the smallest repair at the
   faulty boundary; changing checker defaults would weaken local and GitLab
   verification.
2. The exact GitHub tag checkout remains the integration fixture. A local clone
   with GitHub's real tag subset proves the failing and repaired paths without
   fabricating chronology.
3. `v2.0.1` remains immutable. `v2.0.2` carries the repair and must pass both
   provider-native release pipelines with their external trust anchors.

## Risks / Trade-offs

- GitHub Actions environment coupling could drift -> contract tests pin the
  workflow signal and hosted tag CI remains the final integration proof.
- A passing metadata job could hide another release blocker -> retain the full
  quality matrix, signature gates, asset verification, installation, and
  runtime acceptance as distinct gates.

## Migration Plan

Land the tested repair, publish Forge-specific signed commits and tags, verify
both releases and assets, and install only from the verified signed release.
Before publication the rollback is the parent commit; afterward rollback uses
the governed previous signed release and transactional installer.
