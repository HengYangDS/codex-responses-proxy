# Forge Operations

GitLab and GitHub are independent publication planes for one product source
tree. Neither is a mirror service for the other.

## Model

```mermaid
flowchart LR
    L["Accepted local source"] --> G["GitLab"]
    L --> H["GitHub"]
    G --> A["Read-only audit"]
    H --> A
```

| Plane | Owns |
| --- | --- |
| Local | Accepted source, build, test, installation, runtime proof |
| GitLab | Provider-specific commit identities, CI, signed tag, Release, assets |
| GitHub | Provider-specific commit identities, CI, signed tag, Release, assets |
| Audit | Read-only comparison after both publications exist |

## Execution inputs

Publication context is external and protected. It may admit multiple authorized
actors and signers for team operation.

```toml
schema_version = 1
provider = "gitlab-or-github"
repository = "group-or-owner/repository"
commit_allowed_signers = "/protected/path"
tag_allowed_signers = "/protected/path"
```

The command plane consumes, among other protected values:

- `CODEX_RESPONSES_PROXY_GITLAB_COMMIT_ALLOWED_SIGNERS`;
- `CODEX_RESPONSES_PROXY_GITHUB_COMMIT_ALLOWED_SIGNERS`.

Product source contains no actor email, personal key, fingerprint, token, or
local checkout path.

## Branch publication

```bash
sh tools/forge/project.sh --provider gitlab
sh tools/forge/project.sh --provider github
```

Each projection:

1. reads the selected provider context;
2. verifies source and provider-native history;
3. creates only the required provider-specific commit identities;
4. proves the update is forward-only and fast-forward;
5. pushes only allowed refs.

No history rewrite, force push, tag copy, or cross-Forge credential use is
admitted.

## Tags and releases

```bash
sh tools/release/tag-gitlab.sh v<VERSION>
sh tools/release/tag-github.sh v<VERSION>
```

Each Forge builds and publishes its own assets. A GitLab job does not query or
download a GitHub release; a GitHub job does not query or download a GitLab
release.

A failed release remains immutable evidence. Repair by advancing `VERSION`,
Changelog, source, tag, and Release.

## Read-only parity audit

Refresh the required tracking refs, then run:

```bash
python3 tools/forge/audit.py \
  --tag "v$(cat VERSION)" \
  --gitlab-remote "$GITLAB_REMOTE" \
  --gitlab-api-base "$GITLAB_API_BASE" \
  --gitlab-repo "$GITLAB_REPOSITORY" \
  --github-remote "$GITHUB_REMOTE" \
  --github-repo "$GITHUB_REPOSITORY" \
  --gitlab-anchor "$GITLAB_ANCHOR" \
  --github-anchor "$GITHUB_ANCHOR" \
  --policy "$PUBLICATION_JOB_POLICY" \
  --json
```

The audit proves only the facts it observes. It does not authorize installation
or repair an incomplete release.

| Compared | Rule |
| --- | --- |
| Version and tag target | Same accepted product version and equal source tree |
| Required CI | Each provider's own required jobs succeed |
| Release record | Each provider has its own formal Release |
| Common platform assets | Archive and manifest payload digests match |
| Signatures | Verified independently; byte equality is not required |
| Platform-only assets | Valid on the publishing Forge; no false full-set equality |

## Runners

A runner belongs to one `Forge × repository × platform × executor × purpose`
boundary.

- Description identifies project, host platform, executor, and purpose.
- Tags express target capability, not a fictitious host identity.
- Every job proves actual OS and architecture before building.
- Verification and release privileges remain separate.
- A runner for one repository or Forge never serves the other implicitly.

Missing or mismatched runner capability blocks the job; it is not an allowed
failure and must not be disguised by platform monkeypatching.
