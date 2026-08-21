## Why

Hosted verification currently projects different proof graphs for GitLab and
GitHub. GitLab serializes all supported Python versions inside one MR job and a
tag pipeline exposes only tag verification, while GitHub has explicit version
and native-platform nodes. This obscures failures, prevents runner-level
parallelism, and makes a green Forge mean something different on each peer.

## What Changes

- Model review, accepted-source, tag, native-asset, publication, and parity as
  distinct proof contexts.
- Give Python 3.12, 3.13, and 3.14 independent GitLab jobs generated from one
  matrix, matching GitHub's version topology.
- Make every tag pipeline prove source identity, the complete immutable native
  bundle, provider-local publication, re-download, and byte equality.
- Keep expensive product construction single-owner while requiring both Forges
  to verify and project the same bundle; a successful build on one Forge is not
  evidence of publication on the other.
- Replace handwritten, drifting workflow topology with one declarative source
  and generated GitLab/GitHub projections.
- Keep branch admission and proof reuse in the repository lifecycle owner;
  generated CI expresses only checks that the Forges actually execute.
- Remove obsolete job names, publication-policy expectations, and declarative
  fields without an executable consumer after the new topology becomes
  authoritative.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `release-governance`: define one provider-neutral proof graph, independent
  version nodes, exact tag publication obligations, and the boundary between
  shared product construction and provider-local verification.

## Impact

CI topology and generation, workflow contract tests, hosted publication
evidence, release policy, Forge operations, decision records, and the release
governance specification change. Provider routing, credentials, client
configuration, installed runtime behavior, and Codex private state do not.
