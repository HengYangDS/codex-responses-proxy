# Contributing to Codex DMX Proxy

## Scope and boundaries

Keep changes within the proxy's data-plane and lifecycle responsibilities. Do
not make AIGW manage the proxy process. Do not make the proxy directly rewrite AIGW-owned
marked configuration. Any explicit compatibility bridge must invoke AIGW's public
command and verify its resulting canonical state. Do not alter Codex sessions, archives, SQLite, or model
metadata as a workaround for upstream replay incompatibility.

## Local workflow

Use an isolated Git worktree. Keep user-owned dirty checkouts untouched. This
repository has no third-party runtime dependency; ordinary reading and editing
requires no local installer beyond a supported Python interpreter.

```bash
python scripts/check_release_metadata.py --prepare-release
python scripts/check_markdown_presentation.py
python scripts/test_release_metadata.py
PYTHON=python3.12 RUFF=ruff TY=ty sh scripts/run-python-quality.sh
for py in python3.12 python3.13 python3.14; do
  "$py" -m compileall -q codex_dmx_proxy watchdog install.py uninstall.py control.py governance.py tests scripts
  "$py" scripts/run-python-tests.py
done
```

Add a failing regression before production behavior changes. Tests must not
require real user credentials, a live third-party endpoint, or a mutation of
`~/.codex`.

The quality command enforces aggregate, statement, and measured branch coverage
independently at 95% or higher. No one result substitutes for either independent
result emitted by `scripts/check_branch_coverage.py`.

`scripts/observe-reliability.py` is source-side observation only. It accepts a
supplied secret-free `control.py status --json` snapshot and may write an
explicit operator-selected baseline file. It must not contact an endpoint,
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
   follow GitLab tag creation, while independently signed GitHub tag dates may
   differ;
4. no release claims without executable evidence.

GitLab is the canonical strict plane: validation requires complete history,
every non-pending release heading must have a local tag, and its heading date
must equal that GitLab tag's creation date. GitHub may retain canonical or
legacy headings absent from its own tag namespace, but every GitHub-native tag
still requires a heading; its independently signed native date does not rewrite
GitLab chronology.
`python scripts/check_release_metadata.py --provider gitlab --prepare-release`
enforces the GitLab candidate. GitHub main uses ordinary `--provider github`
validation so a dated candidate remains valid after its preparation day; exact
tag verification adds `--tag v<VERSION>`. Do not write an inferred or planned
release into `CHANGELOG.md`.

GitLab **Project Name** is the human-facing `Codex DMX Proxy`; its stable clone
**Path** remains `codex-dmx-proxy`. Never change the Path as a cosmetic rename.

## Forge discipline

GitLab and GitHub are independent release planes. GitLab provenance uses
`heng.yang.ds@hotmail.com`; the GitHub projection uses
`hengyang.2003@tsinghua.org.cn`. Do not copy provider-native tags between
forges. Every reachable commit must use the relevant provider identity for both
author and committer and must be `Verified` under that provider trust anchor.
Use `sh scripts/project-gitlab-forge.sh` to normalize the complete GitLab DAG,
then `sh scripts/project-github-forge.sh` for GitHub. Both commands rewrite only
an isolated clone, preserve source tree/topology/message/date semantics, retain
provider-specific tags, verify every commit, and update `main` under a lease.

Create a GitLab release tag only through `sh scripts/tag-gitlab-release.sh
v<VERSION>`. It pins the GitLab identity and its tracked signing key explicitly,
so a GitHub conditional Git identity cannot sign a GitLab tag by mistake. After
GitLab tag publication and its CI evidence, run `sh scripts/tag-github-release.sh
v<VERSION>` from the clean canonical GitLab `main`. The command first proves
that the exact signed GitLab tag binds `HEAD`, then fetches the complete GitHub
tag namespace into an isolated GitHub checkout, creates and validates the
provider-native tag at the equal-tree GitHub `main` tip, and pushes only that
single tag.
