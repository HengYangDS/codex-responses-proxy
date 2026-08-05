# Forge Operations

Status: canonical.

## Model

GitLab and GitHub are independent identity and publication planes for one
forward-only content history. Product source owns no Forge URL, organization, account, author,
credential, trust anchor, or signing key. Repository-local remotes select the
transport target; protected execution inputs select publication actors and
trust.

A canonical GitLab commit is created once in an isolated development lane,
reviewed, tested, and signed before it lands. GitLab publishes that object.
GitHub appends an independently signed identity projection with equal trees,
messages, dates, and parent topology. Neither operation force-pushes a branch,
imports provider-native tag objects, or edits existing remote commits. A remote
without one unique canonical tree-history match is a human-governed migration
condition, not permission for automation to guess or rewrite history.

## Execution inputs

Publication operators provide untracked identity and trust inputs outside the
repository. `CODEX_RESPONSES_PROXY_GITLAB_COMMIT_ALLOWED_SIGNERS` and
`CODEX_RESPONSES_PROXY_GITHUB_COMMIT_ALLOWED_SIGNERS` may admit multiple authorized
keys, but every current commit must carry its Forge's selected actor email. These
provider-specific commit identities are provenance, not product defaults.

Forge-native tag actors remain separate. An untracked TOML publication context
contains one record per Forge:

```toml
[gitlab]
actor-name = "publication actor"
actor-email = "verified-address@example.test"
active-signing-fingerprint = "SHA256:..."
```

Select it through `CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT`. Select tag trust
through `CODEX_RESPONSES_PROXY_GITLAB_ALLOWED_SIGNERS`,
`CODEX_RESPONSES_PROXY_GITHUB_ALLOWED_SIGNERS`, or the exact command-specific
anchor input. These files are deployment identity/trust projections and are
ignored by Git. They must never become product defaults.

A commit anchor must admit every key that appears in the history it governs, not
only the key in current use. Branch publication verifies each commit reachable
from the source ref, so one rotated signing key missing from the anchor fails the
whole projection while every signature is cryptographically good; Git reports
this as `No principal matched` and `%G?` of `U`, which is a trust gap, not a bad
signature. Because the two planes carry different actor emails, an anchor is
per-plane: a file that binds only the GitLab principal cannot verify the GitHub
projection's own history, and vice versa. Before publishing, confirm coverage by
comparing the distinct `%GK` fingerprints across the source ref and the remote
tip against the principals in each anchor. Recovering a signer's public key from
the signatures the anchor is meant to validate is circular and does not
establish trust.

## Branch publication

From a clean accepted checkout, project both identity domains through one direct
semantic entrypoint:

```bash
CODEX_RESPONSES_PROXY_GITLAB_COMMIT_ALLOWED_SIGNERS="$GITLAB_COMMIT_ANCHOR" \
CODEX_RESPONSES_PROXY_GITHUB_COMMIT_ALLOWED_SIGNERS="$GITHUB_COMMIT_ANCHOR" \
  sh tools/forge/project.sh --provider gitlab --source-ref HEAD \
  --map-output "$GITLAB_MAPPING"

CODEX_RESPONSES_PROXY_GITLAB_COMMIT_ALLOWED_SIGNERS="$GITLAB_COMMIT_ANCHOR" \
CODEX_RESPONSES_PROXY_GITHUB_COMMIT_ALLOWED_SIGNERS="$GITHUB_COMMIT_ANCHOR" \
  sh tools/forge/project.sh --provider github --source-ref HEAD \
  --map-output "$GITHUB_MAPPING"
```

The command verifies canonical source against GitLab identity and trust, reads
only the selected repository-local remote, uses an isolated clone with ambient
global Git configuration disabled, and performs an ordinary fast-forward,
forward-only push.
GitHub maps the current verified tip to exactly one canonical commit and creates
only missing descendants. Rejection leaves source and remote refs unchanged.

## Release tags

Each Forge owns an immutable signed annotated tag and formal Release record for
the same version and tree. Commit and tag objects differ because identity and
trust planes differ. Tag commands consume the
same external publication context and require the exact active key to already
be available through the standard OpenSSH agent interface. They never read a
password, start an agent, access a personal key path, or retry authentication.

## Parity audit

Run the read-only audit with explicit context and anchors:

```bash
python3 tools/forge/audit.py \
  --gitlab-commit-anchor "$GITLAB_COMMIT_ANCHOR" \
  --github-commit-anchor "$GITHUB_COMMIT_ANCHOR" \
  --gitlab-author-email "$GITLAB_AUTHOR_EMAIL" \
  --github-author-email "$GITHUB_AUTHOR_EMAIL" \
  --gitlab-tag-anchor "$GITLAB_TAG_ANCHOR" \
  --github-tag-anchor "$GITHUB_TAG_ANCHOR" \
  --json
```

It verifies distinct `main` commit IDs, equal tip and ordered tree histories,
provider-scoped commit identity and trust, overlapping provider-native tag
signatures and trees, and unexpected branches/worktrees.
It never pushes, deletes, rewrites, or creates refs. A failed audit proves only
divergence or incomplete housekeeping.

## Authentication and runners

Git transport and API authentication are caller-owned external concerns.
Prefer SSH remotes backed by caller-owned OpenSSH configuration or an agent;
never embed tokens or passwords in URLs. Runner labels, executable paths, and
installation roots are adopter deployment policy, not product truth.

Branch projection fails before its push unless a read-only Forge admission can
prove that required verification is schedulable. Set
`CODEX_RESPONSES_PROXY_GITLAB_PROJECT` to the URL-encoded GitLab project path and
`CODEX_RESPONSES_PROXY_GITHUB_REPOSITORY` to the GitHub `owner/repository`
coordinate. Set `CODEX_RESPONSES_PROXY_GITLAB_RUNNER_TAG` to the exact project
runner tag also projected as the GitLab CI variable. GitLab admission requires
an active, online, unpaused project runner with that tag; GitHub admission
requires Actions and both tracked workflows to be active. These caller-supplied
coordinates and labels are deployment inputs, not product defaults. A CI job
cannot diagnose an absent runner because that job would also remain pending, so
admission intentionally runs before the push.
