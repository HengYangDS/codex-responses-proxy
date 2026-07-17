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
python scripts/check_release_metadata.py
python scripts/check_markdown_presentation.py
python scripts/test_release_metadata.py
for py in python3.12 python3.13 python3.14; do
  "$py" -m compileall -q proxy watchdog platform_adapters install.py uninstall.py control.py tests scripts
  "$py" tests/test_package.py
done
```

Add a failing regression before production behavior changes. Tests must not
require real user credentials, a live third-party endpoint, or a mutation of
`~/.codex`.

## Change and release discipline

Use focused Conventional Commits (`fix:`, `feat:`, `docs:`, `ci:`). `VERSION`
is the release source of truth. Keep `CHANGELOG.md` in this order:

1. `## [Unreleased]` immediately below the introduction;
2. released SemVer headings in exact descending tag order, each dated with its
   matching Git tag creation date;
3. no release claims without executable evidence.

`python scripts/check_release_metadata.py` enforces this chronology; do not
write an inferred or planned release into `CHANGELOG.md`.

GitLab **Project Name** is the human-facing `Codex DMX Proxy`; its stable clone
**Path** remains `codex-dmx-proxy`. Never change the Path as a cosmetic rename.

## Forge discipline

GitLab and GitHub are independent release planes. GitLab provenance uses
`heng.yang.ds@hotmail.com`; the GitHub projection uses
`hengyang.2003@tsinghua.org.cn`. Do not copy provider-native tags between
forges. Use `sh scripts/project-github-forge.sh` only from a clean canonical
GitLab checkout; it rewrites an isolated clone, preserves provider-specific
tags, and updates GitHub `main` under a lease.
