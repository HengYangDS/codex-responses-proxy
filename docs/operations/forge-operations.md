# Forge Operations

Status: canonical.

## Model

GitLab and GitHub are independent, complete forge planes. They preserve the
same source trees, parent topology, messages, author dates, committer dates, and
release version while retaining separate provider-signed commit histories,
signed tags, CI execution, and release records. GitLab is the canonical source
checkout; GitHub is its provider-identity projection. Neither forge is a mere
backup or source snapshot.

Every reachable commit on a provider `main` has one provider-native author and
committer identity and a signature accepted by that provider's tracked trust
anchor. The Forge UI must consequently report those commits as `Verified`.
Contributor views are projections of this complete commit-history invariant;
they are not repaired by profile aliases or display-name changes.

## Synchronization

Normalize GitLab history from a clean source checkout, then project GitHub:

```bash
sh scripts/project-gitlab-forge.sh
sh scripts/project-github-forge.sh
```

Each command builds a fresh isolated clone and uses
`scripts/rewrite-provider-history.py` to recreate every reachable commit with
the provider identity and SSH signature. The rewriter preserves tree, parent
shape, message bytes, author date, and committer date, then verifies every
rewritten commit before `main` changes under an exact remote-tip lease. It never
overwrites provider-native tags. Historical tags and Releases remain immutable
evidence of their original commit objects; a later normalized branch does not
retroactively change those records.

## Parity audit

Run the read-only audit from the canonical checkout whenever a release is
considered or housekeeping is performed:

```bash
python3 scripts/audit-dual-forge-parity.py --json
```

It uses isolated temporary clones to inspect provider-native tags and verifies:

- GitLab/GitHub `main` tree equality;
- provider-specific author and committer identity domains;
- a provider-trusted signature on every reachable commit;
- overlapping provider-native tag signatures and trees; and
- absence of non-`main` local or remote branches, plus the current worktree
  inventory.

It never pushes, deletes, rewrites, or creates refs. A failed audit is evidence
of divergence or incomplete housekeeping, not permission to force convergence.

## Release behavior

GitHub verification and release share one repository-scoped local registration:
`codex-dmx-proxy-github-macos-arm64`. It accepts only trusted `main`, tag, and
manual workflow revisions; pull-request workflow code does not run on that
host. Its LaunchAgent, work directory, cache, and registration are a
repository-scoped evidence boundary and may not serve another repository or
any GitLab job. A successful separate GitHub-hosted `windows-2025` matrix
proves the Python `socket.share()`/`socket.fromshare()` process contract for this
repository; it does not prove an actual user's Windows Scheduled Task host or
system-wide configuration. GitLab uses its separate project-scoped Docker
runner selected by `codex-dmx-proxy-gitlab-ci`.

The GitLab tag pipeline and GitHub tag workflow independently verify the
provider-specific tag signature and create a formal release record. Existing
legacy tags are retained as historical evidence; no release claim for them is
upgraded retroactively. New release tags must be signed under the active
provider identity.

## Provider identities

GitLab provenance uses `Yang HENG <heng.yang.ds@hotmail.com>`. GitHub provenance
uses `HengYang <hengyang.2003@tsinghua.org.cn>`. Author and committer must both
match the relevant identity for every reachable commit. The same signing key
may be bound to distinct provider identities, but each provider verifies every
commit and tag against its own committed allowed-signers file.

## Local signing bridge

`scripts/tag-github-release.sh` uses `DMX_GITHUB_SSH_SIGNING_PROGRAM` when it
is explicitly set; otherwise it uses Git's configured `gpg.ssh.program`. On
this workstation that setting is a Keychain-aware bridge, so an isolated tag
clone can sign without assuming its parent shell inherited `SSH_AUTH_SOCK`.
The command fails closed if no executable signing program is configured.
