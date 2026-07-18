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

## Parity audit

Run the read-only audit from the canonical checkout whenever a release is
considered or housekeeping is performed:

```bash
python3 scripts/audit-dual-forge-parity.py --json
```

It uses isolated temporary clones to inspect provider-native tags and verifies:

- GitLab/GitHub `main` tree equality;
- provider-specific commit-identity domains;
- overlapping provider-native tag signatures and trees; and
- absence of non-`main` local or remote branches, plus the current worktree
  inventory.

It never pushes, deletes, rewrites, or creates refs. A failed audit is evidence
of divergence or incomplete housekeeping, not permission to force convergence.

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

## Local signing bridge

`scripts/tag-github-release.sh` uses `DMX_GITHUB_SSH_SIGNING_PROGRAM` when it
is explicitly set; otherwise it uses Git's configured `gpg.ssh.program`. On
this workstation that setting is a Keychain-aware bridge, so an isolated tag
clone can sign without assuming its parent shell inherited `SSH_AUTH_SOCK`.
The command fails closed if no executable signing program is configured.
