## Why

The accepted source and GitLab `main` describe the same history through an
identity-neutral tree, message, date, and parent match, but the refs have no
common Git ancestor. A merge of both duplicate histories would make the
existing GitHub projection ambiguous and would preserve redundant topology
rather than one authoritative lineage.

The release policy also contradicts the implemented Forge model: it first
allows provider-specific commit identities and then forbids the identity
projection that produces them. The canonical CI specification carries the
same projection contract in one oversized requirement that emits an OpenSpec
diagnostic on every otherwise-clean validation.

## What Changes

- Define one bounded convergence rule: replay only unpublished accepted
  descendants onto the current GitLab tip after a unique identity-neutral base
  match, then sign the successor commits in the GitLab identity domain.
- Keep GitLab publication unchanged and GitHub publication as an append-only
  identity projection; neither Forge may be force-updated.
- Split the projection contract into small, non-overlapping requirements so
  strict OpenSpec validation is diagnostic-free.
- Rebind the existing active CI Claim to this continuation instead of creating
  another truth owner.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=Forge lineage convergence and projection clarity;
  reuse=extend; change=modify; distinguish unpublished canonical convergence
  from ordinary append-only publication and remove validation noise;
  facet:lifecycle=validation,publication;
  facet:surface=docs,openspec,claim,git-history;
  facet:authority=accepted-head,gitlab-main,github-main,claim,evidence.

## Out of Scope

- Rewriting a published branch, tag, Release, or immutable evidence record.
- Merging two complete identity-equivalent histories into a duplicate DAG.
- Changing runtime, provider, payload, installation, or Codex conversation
  state.

## Impact

Only the release policy, the existing `ci-diagnostics` specification and
Claim, and the unpublished accepted successor commits change. Hosted CI,
publication, release, installation, and runtime acceptance remain separate
post-landing transitions.
