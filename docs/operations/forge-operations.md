# Forge Operations

Status: canonical.

## Model

GitLab and GitHub are independent, complete forge planes. They preserve the
same source tree and release version while retaining separate commit histories,
signed tags, CI execution, and release records. GitLab is the canonical source
checkout; GitHub is its provider-identity projection. Neither forge is a mere
backup or source snapshot.

## Synchronization

Run the projection from a clean canonical checkout:

```bash
sh scripts/project-github-forge.sh
```

The command builds a fresh isolated clone, rewrites only that clone to the
GitHub identity, checks tree parity, and updates `main` under a lease. It never
rewrites canonical refs or overwrites provider-native tags. Historical GitLab
tags are retained as their own evidence; the first post-bootstrap release
starts GitHub-native tag provenance. Later runs verify every overlapping tag
pair before advancing the branch.

## Release behavior

The GitLab tag pipeline and GitHub tag workflow independently verify the
provider-specific tag signature and create a formal release record. Existing
legacy tags are retained as historical evidence; no release claim for them is
upgraded retroactively. New release tags must be signed under the active
provider identity.

## Provider identities

GitLab provenance uses `heng.yang.ds@hotmail.com`. GitHub provenance uses
`hengyang.2003@tsinghua.org.cn`. The same signing key may be bound to distinct
provider identities, but each provider verifies against its own committed
allowed-signers file.
