# Contributing to Codex Responses Proxy

## Scope and boundaries

Keep changes within the proxy's data-plane and lifecycle responsibilities.
AIGW may select the proxy as an ordinary HTTP endpoint, but neither product
owns the other's process, configuration, or lifecycle. The proxy must not read
or rewrite AIGW or client configuration. Do not alter Codex sessions, archives,
SQLite, or model metadata as a workaround for upstream replay incompatibility.

## Local workflow

Use an isolated Git worktree. Keep user-owned dirty checkouts untouched. This
repository has no third-party runtime dependency; ordinary reading and editing
requires no local installer beyond a supported Python interpreter.

```bash
uv sync --locked --only-group quality
uv run --locked --no-sync nox -s quick
uv run --locked --no-sync nox -s quality
uv run --locked --no-sync nox -s tests-3.12 tests-3.13 tests-3.14
uv run --locked --no-sync nox -s release
```

Nox creates repository-owned, non-reused environments and installs the product
as a non-editable wheel before tests. Do not add `PYTHONPATH`, import-path
injection, or a system-environment fallback: those hide packaging defects.

Add a failing regression before production behavior changes. Tests must not
require real user credentials, a live third-party endpoint, or a mutation of
`~/.codex`.

## Provider extensions

`src/codex_responses_proxy/providers/manifest.toml` is the provider registry. An
ordinary OpenAI-compatible Responses endpoint requires only one `[providers.<slug>]` table with its
`base_url`; do not add a Python branch, inventory entry, environment variable,
installer option, or release-script case. Only a real provider-specific wire
contract may add `policy = "<slug>"` and one matching module under
`src/codex_responses_proxy/providers/policies/`. The loader validates that module
against the closed policy protocol, and the release inventory derives its file
from the validated manifest. Keep provider policy modules pure: no HTTP
dispatch, mutable runtime state, credentials, host paths, or Forge identity.
The released manifest is also the installed runtime's sole provider registry:
there is no environment or installer override that can create a second
authority. Every request selects an explicit `/<provider>/v1` namespace;
unscoped `/v1` is rejected rather than silently choosing a provider.

The quality command enforces aggregate, statement, and measured branch coverage
independently at 95% or higher. No one result substitutes for either independent
result emitted by `tools/quality/branch_coverage.py`.

`tools/reliability/observe.py` is repository-side observation only. It accepts a
supplied secret-free
`codex-responses-proxy status --json` snapshot and
may write an explicit operator-selected baseline file. It must not contact an endpoint,
read configuration, retain payloads, or invoke lifecycle control. Tests must
cover a first-window baseline, runtime restart/identity boundary, upstream and
local failure classes, the exact input-variant classification threshold, and
the deliberate-drain boundary.

## Change and release discipline

Use focused Conventional Commits (`fix:`, `feat:`, `docs:`, `ci:`). `VERSION`
is the release source of truth. Keep `CHANGELOG.md` in this order:

1. `## [Unreleased]` immediately below the introduction;
2. the GitLab-owned canonical release chronology in descending SemVer order;
3. every provider-native tag represented exactly once; canonical heading dates
   follow the UTC date of GitLab tag creation, while independently signed
   GitHub tag dates may differ;
4. no release claims without executable evidence.

GitLab is the canonical strict plane: validation requires complete history,
every non-pending release heading must have a local tag, and its heading date
must equal the UTC date of that GitLab tag's creation. GitHub may retain
canonical or legacy headings absent from its own tag namespace, but every
GitHub-native tag still requires a heading; its independently signed native
date does not rewrite GitLab chronology.
`python tools/release/metadata.py --provider gitlab --prepare-release`
enforces the GitLab candidate. GitHub main uses ordinary `--provider github`
validation so a dated candidate remains valid after its preparation day; exact
tag verification adds `--tag v<VERSION>`. Do not write an inferred or planned
release into `CHANGELOG.md`.

GitLab **Project Name** is the human-facing `Codex Responses Proxy`; its stable clone
**Path** remains `codex-responses-proxy`. Never change the Path as a cosmetic rename.

## Forge discipline

GitLab and GitHub publish one ordered source-tree history through different
verified identity domains. Create and land the canonical GitLab commit with its
GitLab author, committer, and trusted signature. Then run
`sh tools/forge/project.sh --provider gitlab` and
`sh tools/forge/project.sh --provider github`. The GitHub projection preserves
trees, messages, dates, and parent topology while using the GitHub actor email
and trust anchor. Both updates are ordinary forward-only pushes; neither copies
tags, force-pushes, or rewrites an existing remote commit. Ambiguous divergence
requires an explicit recorded migration decision.

Create a GitLab release tag only through `sh tools/release/tag-gitlab.sh
v<VERSION>`. It binds the caller-provided GitLab tag actor to the selected
OpenSSH-agent fingerprint, so a GitHub tag identity cannot sign it by mistake. After
GitLab tag publication and its CI evidence, run `sh tools/release/tag-github.sh
v<VERSION>` from the clean canonical GitLab `main`. The command first proves
that the exact signed GitLab tag binds `HEAD`, then fetches the complete GitHub
tag namespace into an isolated GitHub checkout, creates and validates the
provider-native tag at the equal-tree GitHub `main` tip, and pushes only that
single tag.
