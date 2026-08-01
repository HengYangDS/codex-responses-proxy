## Why

The source candidate incorrectly required GitLab and GitHub to share one commit
DAG even though each Forge must expose a different verified contributor email.
One commit cannot carry both author identities, so object equality contradicted
the required provenance model and blocked truthful publication.

## What Changes

- **BREAKING:** replace the two duplicated Forge branch publishers with one
  provider-parametric projector.
- Keep GitLab as the canonical signed source history and append an independently
  signed GitHub identity projection with the same ordered trees and topology.
- Replace equal-commit parity with provider identity, signature, tip-tree, and
  ordered tree-history parity.
- Emit an explicit source-to-provider mapping receipt without committing
  maintainer identity, key paths, Forge coordinates, or credentials.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=Forge identity projection and parity;
  reuse=extend; change=modify; require provider-specific commit identities and
  trust while preserving one content history, forward-only publication, and
  clean failure diagnostics; facet:lifecycle=publication,validation;
  facet:surface=script,test,docs,openspec;
  facet:authority=accepted-head,provider-main,provider-signature,claim,evidence.

## Out of Scope

- Rewriting any existing provider ref, tag, Release, or immutable evidence.
- Supplying a maintainer identity, private key, key path, Forge coordinate, or
  credential from product source.
- Treating offline projection tests as hosted CI, publication, installation, or
  runtime acceptance proof.
- Changing Codex JSONL, SQLite, transcript history, item data, or model metadata.

## Impact

Forge projection and audit tools, release metadata contracts, contributor and
operator documentation, and the `ci-diagnostics` specification change. Tags,
Releases, hosted CI, and deployment remain later externally verified planes.
