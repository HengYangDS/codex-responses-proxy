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
- `CODEX_RESPONSES_PROXY_GITHUB_COMMIT_ALLOWED_SIGNERS`;
- `CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY`, a protected Forge secret;
- `CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST`, the matching allowed-signers
  entry.

The GitLab file variable supplies its protected file path directly. The fixed
Ubuntu GitHub release job materializes its text secret once with mode `0600`.
Both adapters then supply the same file-path contract to release tooling.
Product code never accepts private-key text, recreates permissions, or writes a
second copy.

Product source contains no actor email, personal key, fingerprint, token, or
local checkout path.

## Branch publication

```bash
uv run --locked --no-sync python -m tools.forge.project \
  --provider gitlab --publication-context "$PUBLICATION_CONTEXT" \
  --anchor "$GITLAB_COMMIT_ANCHOR" --repository "$GITLAB_REPOSITORY" \
  --runner-tag "$GITLAB_RUNNER_TAG"
uv run --locked --no-sync python -m tools.forge.project \
  --provider github --publication-context "$PUBLICATION_CONTEXT" \
  --anchor "$GITHUB_COMMIT_ANCHOR" --repository "$GITHUB_REPOSITORY"
```

If a previously published provider tip was created as an exact forward-only
checkpoint after a verified canonical ancestor, resume with all three observed
coordinates:

```bash
uv run --locked --no-sync python -m tools.forge.project \
  --provider <gitlab-or-github> \
  --continuity-base <canonical-ancestor> \
  --projected-anchor <provider-match-for-that-ancestor> \
  --expect-remote-tip <observed-provider-tip> \
  --publication-context "$PUBLICATION_CONTEXT" \
  --anchor <provider-commit-anchor> --repository <provider-repository>
```

This is an exact continuity input, not a bypass: the projector verifies the
active provider trust epoch, requires one unique identity-neutral match for the
canonical base, cuts both ordered histories at that exact base and anchor,
compares the current provider tip, and then appends successors by ordinary
atomic fast-forward. Repeated fingerprints in retired prefixes do not
participate; ambiguity among successors after the cut still fails closed.

Each projection:

1. reads the selected provider context;
2. verifies source and provider-native history;
3. creates only the required provider-specific commit identities;
4. proves the update is forward-only and fast-forward;
5. atomically advances that Forge's protected `main` and `dev` to the same
   provider-native commit;
6. pushes no other branch.

`main` is the default release branch. `dev` is the shared integration branch.
They intentionally point to the same provider-native commit immediately after
publication; later proposal integration may advance `dev` first. Local
`candidate/dev` and `work/*` refs are never published.

No history rewrite, force push, tag copy, or cross-Forge credential use is
admitted.

## Tags and releases

```bash
uv run --locked --no-sync python -m tools.release.tag --provider gitlab --tag v<VERSION> \
  --publication-context "$PUBLICATION_CONTEXT" --anchor "$GITLAB_TAG_ANCHOR"
uv run --locked --no-sync python -m tools.release.tag --provider github --tag v<VERSION> \
  --publication-context "$PUBLICATION_CONTEXT" --anchor "$GITHUB_TAG_ANCHOR"
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
  --gitlab-remote "$GITLAB_REMOTE" \
  --github-remote "$GITHUB_REMOTE" \
  --gitlab-commit-anchor "$GITLAB_COMMIT_ANCHOR" \
  --github-commit-anchor "$GITHUB_COMMIT_ANCHOR" \
  --gitlab-author-email "$GITLAB_AUTHOR_EMAIL" \
  --github-author-email "$GITHUB_AUTHOR_EMAIL" \
  --gitlab-tag-anchor "$GITLAB_TAG_ANCHOR" \
  --github-tag-anchor "$GITHUB_TAG_ANCHOR" \
  --gitlab-projection-receipt "$GITLAB_PROJECTION_RECEIPT" \
  --github-projection-receipt "$GITHUB_PROJECTION_RECEIPT" \
  --json
```

The audit proves only the facts it observes. It does not authorize installation
or repair an incomplete release. Each projection receipt must bind the current
provider `main` tip and supply the exact projected continuity anchor created by
the publication transaction. The audit verifies provenance from that anchor
through the current tip; it rejects a missing, stale, or unreachable receipt
instead of silently applying today's trust policy to unrelated retired history.

Persistent branches are read from `.ethos/workspace.toml`. Local `main`, `dev`,
and `candidate/dev`, plus remote `main` and `dev`, are therefore expected
topology. Any other local or remote branch remains housekeeping residue.

| Compared | Rule |
| --- | --- |
| Version and tag target | Same accepted product version and equal source tree |
| Branch lineage | Non-empty equal ordered tree suffix ending at the current tip |
| Required CI | Each provider's own required jobs succeed |
| Release record | Each provider has its own formal Release |
| Common platform assets | Archive and manifest payload digests match |
| Signatures | Verified independently from each exact continuity anchor |
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

GitLab verification starts from digest-pinned official UV/Python images. The
image owns only the executor; `uv.lock` owns project dependencies and Nox owns
the verification graph. A project-scoped runner cache may shorten downloads,
but an empty cache must remain correct. Ordinary verification must not reinstall
UV, redownload its primary interpreter, or build an editable source package
before Nox builds and tests the wheel.
